"""自由自然语言 → 受控动作计划 的翻译器（agent / 框架共用）。

背景与目标
----------
此前的 W 步骤要求业务人员使用一套「受控关键字」（如 `搜索 "微信"` /
`观察 "搜索框" 是否可见`）。本模块让业务人员**只用写大白话**即可，例如：

    "在搜索框里输入微信然后回车"
    "看看搜索框在不在"
    "点开第一个结果进详情"
    "切到手机屏幕大小看看有没有横向滚动"

翻译器把每句话拆成若干「微动作」(ActionIR)，动作类型与 step_executor 已有的
`_do_*` 实现一一对应（open / search / click / observe / wait / viewport / count /
screenshot），再由执行器按规范关键字重新派发执行。

两种引擎
--------
1. 启发式（默认，离线）：正则 + 关键词规则，覆盖常见业务措辞，零依赖、零联网。
2. LLM（可选）：当 settings.NL_USE_LLM=True 且配置了兼容 OpenAI 的 API 时，
   调用大模型把任意自由表述拆成 JSON 动作计划；任何异常均回退到启发式。

对外主入口
----------
    translate_step(text, use_llm=False) -> List[ActionIR]
    canonical_text(act) -> str         # 由 ActionIR 还原成受控关键字串

ActionIR.action 取值：open / search / click / observe / wait / viewport /
count / screenshot / ranking / ranking_first / download
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import config.settings as settings


# ---------------------------------------------------------------------------
# 动作中间表示
# ---------------------------------------------------------------------------
@dataclass
class ActionIR:
    """一条微动作。target / viewport / min_count 按 action 类型可选。"""

    action: str  # open/search/click/observe/wait/viewport/count/screenshot/ranking/ranking_first/download
    target: Optional[str] = None
    viewport: Optional[Tuple[int, int]] = None
    min_count: Optional[int] = None


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _quoted(text: str) -> Optional[str]:
    """提取首个被引号包裹的内容（支持半角/全角双引号、单引号、直角引号）。"""
    patterns = [
        r'"([^"]+)"',          # 半角双引号
        r"'([^']+)'",          # 半角单引号
        r'[""]([^""]+)[""]',   # 全角双引号
        r"「([^」]+)」",        # 直角引号
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def _extract_viewport(text: str) -> Optional[Tuple[int, int]]:
    """从 '375x667' / '375X667' / '375*667' 提取 (w, h)。"""
    m = re.search(r"(\d{2,5})\s*[xX*]\s*(\d{2,5})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _extract_min_count(text: str) -> int:
    """从断言文案中提取期望的最小数量（默认 1）。"""
    m = re.search(r">=\s*(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"至少\s*(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*个", text)
    if m:
        return int(m.group(1))
    return 1


# 提取动词后宾语时跳过的停用字符（语气/方位/连词等）
_STOP_RUN = (
    r"[^\s并然后接着再及与、，。；：！？\n回车确认提交按钮框里内中点击搜索等待"
    r"观察看看检查进入打开访问了下吗呢吧啊咦哎到向在用从把被将才上这那该此的]"
)


def _extract_target_after(text: str, verbs: Tuple[str, ...]) -> Optional[str]:
    """取动词之后的宾语片段（直到停用字符为止）。"""
    for v in verbs:
        idx = text.find(v)
        if idx >= 0:
            rest = text[idx + len(v):]
            rest = re.sub(r"^[了下个的之中里内到向在用从把被将才]+\s*", "", rest)
            m = re.match(r"(" + _STOP_RUN + r"+)", rest)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return None


def _run_after_char(p: str, ch: str) -> Optional[str]:
    """取某字符之后、直到停用字符的一段（用于「点X」裸点结构）。"""
    idx = p.find(ch)
    if idx < 0:
        return None
    rest = p[idx + 1:]
    m = re.match(r"(" + _STOP_RUN + r"+)", rest)
    return m.group(1).strip() if m else None


def _wait_target(p: str) -> Optional[str]:
    """等待动作的目标：URL 片段优先。"""
    q = _quoted(p)
    if q:
        return q
    m = re.search(r"/[A-Za-z0-9_\-/.]+", p)  # /search、/appdetail 之类
    if m:
        return m.group(0)
    m = re.search(r"(?:包含|变成|到|为|出现|跳转)\s*[「『]?([A-Za-z0-9_\-/.]+)", p)
    if m:
        return m.group(1)
    return None


# 元素引用 → 受控别名（用于「观察 X 是否可见 / 点击 X」）
ELEMENT_REFS = {
    "搜索框": "搜索框", "搜索": "搜索框",
    "logo": "logo", "标志": "logo", "图标": "logo", "品牌": "logo",
    "页脚": "页脚", "底部": "页脚",
    "下载": "下载",
    "导航": "导航", "分类": "导航",
    "区块": "内容区块", "板块": "内容区块", "栏目": "内容区块", "内容": "内容区块",
    "结果": "结果",
}


# ---------------------------------------------------------------------------
# 意图判定
# ---------------------------------------------------------------------------
def _is_screenshot(p: str) -> bool:
    return bool(re.search(r"截图|截个图|拍个照|存个图|留个图", p))


def _is_ranking(p: str) -> bool:
    """是否涉及排行榜 / 榜单（导航或点击榜单第一）。"""
    return bool(re.search(r"排行榜|榜单|热门榜|排行|榜上", p))


def _is_ranking_first(p: str) -> bool:
    """是否为『点击排行榜第一的应用』这类动作。"""
    return _is_ranking(p) and any(k in p for k in ("第一", "榜首", "首位", "第1", "排行第一", "榜单第一"))


def _is_viewport(p: str) -> bool:
    if _extract_viewport(p):
        return True
    if "视口" in p or "响应式" in p:
        return True
    if ("手机" in p or "移动" in p) and any(
        k in p for k in ("视图", "大小", "布局", "屏幕", "尺寸", "宽度", "视口", "样子",
                        "切", "缩", "改", "调", "变成")
    ):
        return True
    return False


def _is_open(p: str) -> bool:
    if "访问" in p:
        return True
    if "详情" in p or "结果" in p:  # 进入/打开详情 → 走点击
        return False
    if "打开" in p and "点开" not in p:
        return True
    if "进入" in p and any(k in p for k in ("首页", "官网", "网站", "应用宝", "主页")):
        return True
    if "回到首页" in p or "返回首页" in p:
        return True
    return False


def _is_search(p: str) -> bool:
    if any(v in p for v in ("搜一下", "搜个", "检索", "查一下", "查一查", "查找", "查询", "找一下", "找一找")):
        return True
    if "搜索" in p and "框" not in p:  # 排除「搜索框」这类元素引用
        return True
    if "输入" in p and ("搜索框" in p or "搜索" in p):
        return True
    return False


def _is_count(p: str) -> bool:
    if any(v in p for v in ("统计", "数一数", "数一下", "数数", "个数")):
        return True
    if "结果" in p and any(k in p for k in ("多少", "几个")):
        return True
    return False


def _is_click(p: str) -> bool:
    if any(v in p for v in ("点击", "点开", "点一下", "点进", "单击", "按下", "点选")):
        return True
    if re.search(r"(?<![一-龥])点[一-龥]", p):  # 裸「点X」（排除「一点/重点」）
        return True
    if "进入" in p and any(k in p for k in ("详情", "结果", "页面")):
        return True
    if "打开" in p and any(k in p for k in ("详情", "结果")):
        return True
    return False


def _is_wait(p: str) -> bool:
    return any(v in p for v in ("等待", "直到", "等一下", "等页面", "等结果", "等加载", "等它"))


def _is_observe(p: str) -> bool:
    if any(v in p for v in (
        "观察", "检查", "看看", "确认", "验证", "校验", "断言", "是否", "能不能",
        "有没有", "在不在", "是否存在", "是否正常", "可见吗", "显示吗", "包含吗",
        "对不对", "是不是", "应不应该", "预期",
    )):
        return True
    # 含元素引用、且不是其它动作 → 视为可见性断言
    if any(ref in p for ref in ELEMENT_REFS) and not (
        _is_search(p) or _is_click(p) or _is_open(p) or _is_wait(p) or _is_count(p)
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# 单句翻译
# ---------------------------------------------------------------------------
def _translate_single(p: str) -> List[ActionIR]:
    p = p.strip()
    if not p:
        return []

    if _is_screenshot(p):
        return [ActionIR("screenshot")]

    # 二维码/扫码：等待并断言二维码弹窗出现（用于「预期结果有二维码」的步骤）。
    # 务必先于 observe/click 识别，避免被「观察…」或「点击下载…」分支误处理。
    if "二维码" in p or "扫码" in p:
        return [ActionIR("observe_qr")]

    # 排行榜：导航到榜单页 / 点击榜单第一的应用（务必先于 open/click 识别，
    # 避免「打开排行榜」被误判为打开首页、「点击排行榜第一的应用」被误判为普通点击）
    if _is_ranking(p):
        if _is_ranking_first(p):
            return [ActionIR("ranking_first")]
        return [ActionIR("ranking")]

    if _is_viewport(p):
        vp = _extract_viewport(p) or (375, 667)
        return [ActionIR("viewport", viewport=vp)]

    if _is_open(p):
        q = _quoted(p)
        if q and (q.startswith("http") or "." in q):
            return [ActionIR("open", target=q)]
        return [ActionIR("open")]

    if _is_search(p):
        target = (
            _extract_target_after(
                p, ("搜索", "搜一下", "搜个", "查一下", "查一查", "查找", "查询",
                    "找一下", "找一找", "检索", "搜", "输入")
            )
            or _quoted(p)
            or settings.POOLS.probe_app_name
        )
        return [ActionIR("search", target=target)]

    if _is_count(p):
        target = _quoted(p)  # 未引述时留空，执行时回退到上下文搜索词
        return [ActionIR("count", target=target)]

    if _is_click(p):
        # 点击下载按钮（进入下载流程）。排除导航「下载客户端」链接。
        if "下载" in p and "客户端" not in p:
            return [ActionIR("download")]
        if "结果" in p or "详情" in p or (
            "第" in p and ("一" in p or "1" in p) and "个" in p
        ):
            return [ActionIR("click", target="结果")]
        if "导航" in p or "分类" in p:
            return [ActionIR("click", target="导航")]
        target = (
            _quoted(p)
            or _extract_target_after(p, ("点击", "点开", "单击", "按下", "点选", "进入", "打开"))
            or _run_after_char(p, "点")
        )
        if target:
            # 去掉尾部冗余方位词，提升文本定位命中率
            target = re.sub(r"(分类|导航|按钮|链接|选项|菜单|区域|位置)$", "", target)
            if target:
                return [ActionIR("click", target=target)]
        return []

    if _is_wait(p):
        if "url" in p.lower() or "地址" in p or "/" in p:
            frag = _wait_target(p)
            return [ActionIR("wait", target=frag)]
        target = _quoted(p) or _extract_target_after(p, ("等待", "等", "直到")) or _wait_target(p)
        if target:
            # 去掉尾部「出现 / 加载 / 完成」等冗余动词，避免等待不存在的文本
            target = re.sub(r"(出现|加载|完成|出来|显示|渲染|好|了|之后|后)$", "", target)
        return [ActionIR("wait", target=target)]

    if _is_observe(p):
        return _translate_observe(p)

    return []


def _translate_observe(p: str) -> List[ActionIR]:
    if "标题" in p:
        return [ActionIR("observe", target="页面标题非空")]

    if ("横向" in p and ("溢出" in p or "滚动" in p)) or ("溢出" in p and "横向" in p):
        return [ActionIR("observe", target="无横向溢出")]

    if "结果" in p and any(k in p for k in ("数量", "多少", "几个", "至少", ">=", "≥")) or re.search(r"\d+\s*个", p):
        n = _extract_min_count(p)
        return [ActionIR("observe", target="结果数量", min_count=n)]

    if ("移动端" in p or "手机" in p) and any(
        k in p for k in ("内容", "渲染", "显示", "正常", "可见")
    ):
        return [ActionIR("observe", target="页面有可见内容")]
    if any(k in p for k in ("能正常渲染", "正常渲染", "有可见内容", "渲染正常")):
        return [ActionIR("observe", target="页面有可见内容")]

    # 元素引用（可见性）
    for ref in sorted(ELEMENT_REFS, key=len, reverse=True):
        if ref in p:
            return [ActionIR("observe", target=f"可见::{ELEMENT_REFS[ref]}")]

    # 文本存在 / 可见
    q = _quoted(p) or _extract_target_after(
        p, ("观察", "检查", "看看", "确认", "验证", "是否", "有没有", "在不在",
            "是否存在", "是否正常", "可见吗", "显示吗", "包含吗", "对不对", "是不是", "预期")
    )
    if q:
        if any(k in p for k in ("存在", "有没有", "在不在", "包含", "是否显示", "显示吗")):
            return [ActionIR("observe", target=f"存在::{q}")]
        return [ActionIR("observe", target=f"可见::{q}")]
    return []


# ---------------------------------------------------------------------------
# 多意图拆分（并 / 然后 / 接着 / 之后 / 以及）
# ---------------------------------------------------------------------------
def _split_intents(text: str) -> List[str]:
    parts = re.split(r"\s*(?:并|并且|然后|接着|之后|以及)\s*", text)
    return [p.strip() for p in parts if p.strip()]


def translate_step_heuristic(text: str) -> List[ActionIR]:
    """离线启发式：自由中文 → 动作计划。"""
    text = (text or "").strip()
    if not text:
        return []
    plan: List[ActionIR] = []
    for part in _split_intents(text):
        plan.extend(_translate_single(part))
    # 过滤空动作（如「回车」「确认」等衔接词被拆出后无动作）
    return [a for a in plan if a.action]


# ---------------------------------------------------------------------------
# 可选 LLM 引擎（兼容 OpenAI Chat Completions，stdlib 实现，失败回退启发式）
# ---------------------------------------------------------------------------
def translate_step_llm(text: str) -> Optional[List[ActionIR]]:
    """调用兼容 OpenAI 的接口把自由表述拆成动作计划；失败返回 None。"""
    if not settings.LLM_API_KEY:
        return None
    prompt = (
        "你是一个测试用例步骤解析器。把用户给出的中文测试步骤，"
        "拆成有序的动作列表。每个动作用 JSON 表示："
        '{"action": "open|search|click|observe|wait|viewport|count|screenshot",'
        ' "target": "可选文本", "viewport": "可选 WxH", "min_count": 可选整数}。\n'
        "规则：\n"
        '- search 的 target 为要搜索的词；click 的 target 为要点击的文本，'
        '若点击搜索结果进详情则用 target="结果"，点击导航用 target="导航"。\n'
        '- observe 的 target：标题非空用"页面标题非空"，无横向溢出用"无横向溢出"，'
        '结果数量用"结果数量"(配 min_count)，移动端有内容用"页面有可见内容"，'
        '否则用"可见::元素名"或"存在::文本"。\n'
        '- viewport 的 viewport 为 "375x667" 形式。\n'
        "只输出 JSON 数组，不要解释。\n"
        f"步骤：{text}"
    )
    try:
        import urllib.request
        import urllib.error

        payload = {
            "model": settings.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        req = urllib.request.Request(
            f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        arr = json.loads(_extract_json_array(content))
        plan = []
        for item in arr:
            act = ActionIR(action=item.get("action"))
            if item.get("target"):
                act.target = item["target"]
            if item.get("viewport"):
                m = re.search(r"(\d+)\s*[xX*]\s*(\d+)", str(item["viewport"]))
                if m:
                    act.viewport = (int(m.group(1)), int(m.group(2)))
            if item.get("min_count") is not None:
                act.min_count = int(item["min_count"])
            plan.append(act)
        return plan or None
    except Exception:  # noqa: BLE001
        return None


def _extract_json_array(s: str) -> str:
    """从模型可能夹带的文本里抠出第一个 JSON 数组。"""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    m = re.search(r"\[.*\]", s, re.DOTALL)
    return m.group(0) if m else "[]"


# ---------------------------------------------------------------------------
# 主入口 & 规范还原
# ---------------------------------------------------------------------------
def translate_step(text: str, use_llm: bool = False) -> List[ActionIR]:
    """自由中文 → 动作计划。默认启发式；use_llm=True 且配置密钥时优先 LLM。"""
    if use_llm:
        llm_plan = translate_step_llm(text)
        if llm_plan:
            return llm_plan
    return translate_step_heuristic(text)


def canonical_text(act: ActionIR) -> str:
    """把一条 ActionIR 还原成 step_executor 能识别的受控关键字串。"""
    a = act.action
    if a == "open":
        return f'打开 "{act.target}"' if act.target else "打开首页"
    if a == "search":
        return f'搜索 "{act.target}"'
    if a == "count":
        if act.target and act.target != "结果":
            return f'统计 "{act.target}" 相关结果数量'
        return "统计 相关结果数量"
    if a == "click":
        if act.target == "结果":
            return '点击第一个 "结果"'
        if act.target == "导航":
            return '点击 "导航"'
        return f'点击 "{act.target}"'
    if a == "wait":
        tgt = act.target or ""
        if tgt and ("/" in tgt or "http" in tgt or "search" in tgt or "appdetail" in tgt):
            return f'等待URL包含 "{tgt}"'
        return f'等待 "{tgt}" 出现' if tgt else '等待 "" 出现'
    if a == "viewport":
        w, h = act.viewport or (375, 667)
        return f'切换视口 "{w}x{h}"'
    if a == "screenshot":
        return "截图"
    if a == "ranking":
        return "打开排行榜"
    if a == "ranking_first":
        return "点击排行榜第一的应用"
    if a == "download":
        return "点击下载按钮"
    if a == "observe_qr":
        return "观察二维码出现"
    if a == "observe":
        tgt = act.target or ""
        if tgt == "页面标题非空":
            return "观察 页面标题 非空"
        if tgt == "无横向溢出":
            return "观察 无横向溢出"
        if tgt == "结果数量":
            return f"观察 结果数量 至少 {act.min_count or 1} 个"
        if tgt == "页面有可见内容":
            return "观察 页面有可见内容"
        if tgt.startswith("存在::"):
            return f'观察 "{tgt[4:]}" 存在'
        if tgt.startswith("可见::"):
            return f'观察 "{tgt[4:]}" 是否可见'
        return f'观察 "{tgt}" 是否可见' if tgt else "观察 元素 是否可见"
    return "截图"


def canonical_step_text(acts: List[ActionIR]) -> str:
    """多条动作合并成一条规范 W 步骤串（供生成器写入 cases.md）。"""
    if not acts:
        return ""
    return "；".join(canonical_text(a) for a in acts)


if __name__ == "__main__":
    import sys

    for line in sys.argv[1:] or ["在搜索框输入微信并回车", "看看搜索框在不在", "点开第一个结果进详情"]:
        plan = translate_step(line)
        print(f"{line}  →  {[canonical_text(a) for a in plan]}")
