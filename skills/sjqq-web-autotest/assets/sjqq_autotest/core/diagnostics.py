"""失败诊断：用例失败时定位「UI 元素失效」还是「接口(后端)失败」，产出可读原因。

为什么要它
----------
测试失败时，光知道「用例失败」不够，业务/开发更需要知道：
  - 是前端 UI 失效（元素改版/文案变更/被遮挡/动态识别候选未命中）？
  - 还是后端接口失败（请求超时/DNS/连接中断，或接口返回 4xx/5xx）？
本模块在用例执行期间挂监听，失败时自动给出分层诊断，并在报告中标记失败原因。

机制
----
1. 网络监听：page.on("requestfailed") 收集连接级失败；page.on("response") 收集
   接口（fetch/xhr/json 或 URL 含 api/ajax/json 等）的非 2xx 响应。直接回答
   「接口是否失败」。已过滤浏览器扩展噪音、纯静态资源、第三方 SDK 连接噪音。
2. 元素诊断：失败时解析异常中的定位器描述，并对一组「关键 UI 元素」做存在/可见
   探测，区分：元素完全未出现 / 存在但不可见 / 可见但交互超时。
3. 汇总：写出结构化诊断到 _DIAGNOSIS[case_id]，供 report_builder 在报告中渲染。
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

import config.settings as settings

# case_id -> 本次用例期间捕获的接口/网络问题（字符串列表）
_NETWORK_ISSUES: dict[str, list[str]] = {}
# case_id -> 结构化诊断字典
_DIAGNOSIS: dict[str, dict] = {}

# 判断是否为「接口(后端)」请求的 URL / 资源类型规则。
# 用单词边界，避免把 api100.js 这类「词内包含 api」的静态资源误判为接口。
_API_URL_RE = re.compile(
    r"(?<![a-z0-9])(api|apis|ajax|json|rest|graphql|service|gateway|interface|rpc|data)(?![a-z0-9])",
    re.I,
)
_API_RESOURCE_TYPES = {"fetch", "xhr", "websocket"}
# 浏览器扩展 / 本地环回等噪音来源，直接忽略
_IGNORE_SCHEMES = ("chrome-extension://", "moz-extension://", "edge-extension://")
# 静态资源类型，其连接失败/404 不作为「接口失败」计入
_STATIC_TYPES = {"image", "font", "media", "stylesheet", "script", "manifest", "other"}
# 静态资源扩展名（即便返回 json content-type 也不算接口），除非是真正的 XHR/fetch
_STATIC_EXT = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".map", ".html", ".htm",
)

# 站点自身域名：只有「本站 / 明显接口路径 / 主文档」才作为高优「接口失败」信号，
# 排除第三方 SDK（如 *.sdk.myapp.com）连接失败等环境噪音，避免误导排障。
_SITE_HOST = urlparse(settings.BASE_URL).netloc.split(":")[0].lower()


def reset_network(case_id: str) -> None:
    """每个用例执行前清空网络问题记录（也避免 pytest-rerunfailures 重复累积）。"""
    _NETWORK_ISSUES[case_id] = []


def _is_noise(url: str) -> bool:
    u = (url or "").lower()
    if any(u.startswith(s) for s in _IGNORE_SCHEMES):
        return True
    # 已知良性第三方/分享 SDK 的受控中断（如 jssdk/share-page 的 abort），
    # 即便同源也属正常行为，不计入「接口/网络失败」，避免误报后端/网关问题。
    if "/share-page/" in u or "/jssdk/" in u or "qqapi" in u or "mqqapi" in u:
        return True
    return False


def _is_static_asset(url: str) -> bool:
    u = (url or "").lower().split("?")[0]
    return u.endswith(_STATIC_EXT)


def _is_same_origin(url: str) -> bool:
    try:
        host = urlparse(url).netloc.split(":")[0].lower()
    except Exception:  # noqa: BLE001
        return False
    return host == _SITE_HOST or host.endswith("." + _SITE_HOST)


def _is_api_signal(url: str, resource_type: str) -> bool:
    """该请求是否值得作为「接口/网络失败」信号（本站 / 接口路径 / 主文档）。"""
    if resource_type == "document":
        return True
    return _is_same_origin(url) or bool(_API_URL_RE.search(url))


def attach_network_monitor(page, case_id: str) -> None:
    """给 page 注册网络监听，记录本次用例期间失败的请求 / 异常接口响应。"""

    def on_request_failed(request) -> None:
        if _is_noise(request.url):
            return
        rt = (request.resource_type or "").lower()
        # 静态资源（图片/字体/样式/脚本等）的连接失败视为噪音
        if rt in _STATIC_TYPES:
            return
        # 仅保留与接口/本站强相关（主文档、接口路径、同域 fetch/xhr）的失败
        if not _is_api_signal(request.url, rt):
            return
        if rt not in _API_RESOURCE_TYPES and not (
            _is_same_origin(request.url) or _API_URL_RE.search(request.url)
        ):
            return
        reason = request.failure or "未知原因"
        _NETWORK_ISSUES[case_id].append(
            f"网络请求失败: {request.method} {_short(request.url)} -> {reason}"
        )

    def on_response(response) -> None:
        if response.status < 400:
            return
        if _is_noise(response.url):
            return
        rt = (response.request.resource_type or "").lower()
        ct = (response.headers.get("content-type") or "").lower()
        url = response.url
        # fetch/xhr 但若指向静态资源（.js/.css 等）且路径不像接口，则视为静态加载而非业务接口
        is_api = rt in _API_RESOURCE_TYPES and not (
            _is_static_asset(url) and not _API_URL_RE.search(url)
        )
        if not is_api and "json" in ct and not _is_static_asset(url):
            is_api = True
        if not is_api and _API_URL_RE.search(url) and not _is_static_asset(url):
            is_api = True
        # 仅本站/接口路径/主文档才计入接口失败（排除第三方 SDK 噪音）
        if is_api and not _is_api_signal(url, rt):
            is_api = False
        if not is_api:
            return
        _NETWORK_ISSUES[case_id].append(
            f"接口异常: {response.request.method} {_short(url)} -> HTTP {response.status}"
        )

    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)


def _short(url: str, n: int = 120) -> str:
    """截断过长 URL，便于在报告中展示。"""
    return url if len(url) <= n else url[: n - 1] + "…"


# ---------------------------------------------------------------------------
# UI 关键元素探测
# ---------------------------------------------------------------------------
def _state_of(locator) -> str:
    """返回单个定位器的状态：可见 / 存在但不可见 / 未找到 / 未知。"""
    try:
        n = locator.count()
    except Exception:  # noqa: BLE001
        return "未知"
    if n == 0:
        return "未找到(missing)"
    try:
        if locator.first.is_visible():
            return "可见(visible)"
    except Exception:  # noqa: BLE001
        pass
    return "存在但不可见(hidden)"


def _any_state(locator) -> str:
    """对一组候选（OR 合并）定位器，返回「任一可见 / 全部未找到 / 部分不可见」。"""
    try:
        n = locator.count()
    except Exception:  # noqa: BLE001
        return "未知"
    if n == 0:
        return "未找到(missing)"
    for i in range(n):
        try:
            if locator.nth(i).is_visible():
                return "可见(visible)"
        except Exception:  # noqa: BLE001
            continue
    return "存在但不可见(hidden)"


def probe_key_elements(page) -> dict:
    """对一组「关键 UI 元素」做存在/可见探测，返回 {元素名: 状态}。

    用于在失败时快速判断是「UI 元素失效」还是「UI 正常但内容/接口异常」。
    """
    from core.dynamic_locators import DynamicLocator

    loc = DynamicLocator(page)
    pools = settings.POOLS
    out: dict[str, str] = {}
    out["搜索框"] = _state_of(loc.search_input())
    out["品牌logo"] = _any_state(loc.alt(*pools.logo_alts))
    out["导航关键词"] = _any_state(loc.text(*pools.nav_keywords))
    out["区块标题"] = _any_state(loc.text(*pools.home_section_titles))
    out["下载按钮"] = _any_state(loc.button_visible(*pools.download_keywords))
    return out


def _extract_locator_hint(exc_text: str) -> str | None:
    """从异常文本里尽量提取 Playwright 定位器描述，作为失败线索。"""
    if not exc_text:
        return None
    # 形如：waiting for locator("get_by_text(...)").first to be visible
    m = re.search(r'locator\((["\'])(.*?)\1\)', exc_text)
    if m:
        return f"locator({m.group(2)})"
    m = re.search(r"(get_by_\w+|get_by_role|locator)\([^)]*\)", exc_text)
    if m:
        return m.group(0)[:160]
    return None


def _failing_step_reason(case_id: str) -> dict | None:
    """读取真正失败的步骤原因（effective=False 的 W 步骤），作为最权威的失败原因。

    优先读内存中活跃的记录器（teardown 时直接可用，不依赖 steps.json 落地时序）；
    读不到再回退到最新批次的 steps.json。避免被第三方 SDK 良性中断等网络噪音误导。
    """
    try:
        from core.step_recorder import StepRecorder

        rec = StepRecorder.get_active(case_id)
        steps = rec.steps if rec is not None else None
        if not steps:
            from core.paths import get_latest_evidence_dir

            p = get_latest_evidence_dir() / case_id / "steps.json"
            if not p.exists():
                return None
            steps = json.loads(p.read_text(encoding="utf-8")).get("steps", [])
        for s in steps:
            if s.get("kind") == "W" and s.get("effective") is False:
                return {
                    "badge": f"W{s.get('no')}",
                    "text": (s.get("text") or "").strip(),
                    "note": (s.get("note") or "").strip(),
                }
    except Exception:  # noqa: BLE001
        return None
    return None


def diagnose_failure(page, case_id: str, exc_text: str = "") -> dict:
    """用例失败时生成结构化诊断。

    返回 dict：
      {
        "summary": 一行结论（用于报告顶部失败原因），
        "ui": {元素名: 状态},
        "api_issues": [接口/网络问题字符串],
        "locator_hint": 异常中的定位器线索（可为 None），
        "page_state": {"url":..., "title":...},
      }
    该 dict 会被写入 _DIAGNOSIS[case_id]，供报告渲染。
    """
    api_issues = list(_NETWORK_ISSUES.get(case_id, []))
    ui: dict[str, str] = {}
    page_state: dict[str, str] = {}
    try:
        ui = probe_key_elements(page)
        page_state = {
            "url": page.url,
            "title": (page.title() or "")[:120],
        }
    except Exception as e:  # noqa: BLE001
        ui = {"探测异常": str(e)[:120]}

    locator_hint = _extract_locator_hint(exc_text)

    # 结论优先级：真实失败步骤原因 > 接口失败 > UI 关键元素缺失/不可见 > 交互超时 > 通用
    step_reason = _failing_step_reason(case_id)
    missing = [k for k, v in ui.items() if v.startswith("未找到")]
    hidden = [k for k, v in ui.items() if "不可见" in v]
    ui_ok = not missing and not hidden

    if step_reason:
        reason = step_reason["note"] or "步骤断言未满足"
        summary = f"断言失败（{step_reason['badge']} {step_reason['text']}）：{reason}"
    elif api_issues:
        summary = "接口/网络异常（见接口诊断），疑似后端或网关问题，非纯前端 UI 失效。"
    elif missing:
        summary = f"关键 UI 元素缺失（{', '.join(missing)}），疑似页面改版/文案变更/动态识别候选未命中。"
    elif hidden:
        summary = f"关键 UI 元素存在但不可见（{', '.join(hidden)}），疑似布局/遮挡/样式失效。"
    elif locator_hint:
        summary = "目标元素未出现/不可见（疑似 UI 改版、文案变更或动态识别候选未命中），请核对下方定位器线索与关键元素状态。"
    else:
        summary = "用例断言未满足，未能从异常中识别具体元素/接口，请结合下方页面状态排查。"

    diag = {
        "summary": summary,
        "ui": ui,
        "api_issues": api_issues,
        "locator_hint": locator_hint,
        "page_state": page_state,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _DIAGNOSIS[case_id] = diag
    return diag


def get_diagnosis(case_id: str) -> dict | None:
    return _DIAGNOSIS.get(case_id)


def all_diagnoses() -> dict:
    return dict(_DIAGNOSIS)
