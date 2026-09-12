"""优化测试报告生成器（参考 Allure 开源报告风格）。

设计要点
--------
1. 单一自包含 HTML（应用宝官网自动化测试报告.html）：所有步骤截图以 base64 内嵌，不依赖外部文件，
   可直接发给业务人员 / 在任意浏览器打开。
2. 内容来源：
   - 用例 S/G/W/T 文案：来自唯一的真相源 cases/cases.md（core.case_reader）；
   - 每步证据截图、有效性校验：来自各用例执行时写出的
     reports/evidence/<批次>/<case_id>/steps.json（core.step_recorder）；
   - 用例最终通过/失败/耗时：来自 pytest 结束时写出的 reports/results.json，
     或在 conftest 的 sessionfinish 中直接传入 outcome_map。
3. UI 参考 Allure：顶部汇总条（总数/通过/失败/耗时）、用例卡片（左侧状态色条 +
   状态徽章）、步骤时间线（步骤编号、中文描述、有效性徽章、可点击放大的截图）。
4. 纯前端交互（折叠/展开、截图灯箱放大），无外部依赖。

用法
----
- 自动化接入：conftest.py 在 pytest_sessionfinish 调用 build_and_write(outcome_map)。
- 独立复生成：在项目根目录运行 `python make_report.py`（读取已有的 results.json 与证据）。
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from pathlib import Path

import config.settings as settings
from core.case_reader import parse_cases
from core.paths import REPORTS_DIR, RUN_TS, DIAGNOSIS_FILE, get_latest_evidence_dir

# 运行元数据：pytest 实际运行时的真实模式（有头/无头），由 conftest 在 sessionfinish 写入。
# 报告无论何时重建都读此值，避免「报告标注」与「实际运行」不一致
# （例如 pytest 有头跑了、事后却用 SJQQ_HEADED=0 重建报告，会误标为无头）。
RUN_META_FILE = REPORTS_DIR / "run_meta.json"


def read_run_meta() -> dict:
    """读取 pytest 实际运行时的持久化元数据（run_meta.json，兜底用）；缺省返回空 dict。"""
    if RUN_META_FILE.exists():
        try:
            return json.loads(RUN_META_FILE.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _effective_headed(outcome_map: dict | None) -> bool:
    """解析报告应显示的执行模式（有头/无头）。

    来源优先级（越靠前越权威）：
      1. results.json.__meta__.headed —— 与用例结果同源、同一次 pytest 运行写出，
         永不会和「产出这份报告的真实运行」脱钩，是报告标注的唯一权威来源；
      2. run_meta.json（历史兼容兜底）；
      3. 当前进程 config.settings.HEADED（仅在以上都缺失时回退）。
    """
    if outcome_map:
        m = (outcome_map.get("__meta__") or {})
        if m.get("headed") is not None:
            return bool(m["headed"])
    meta = read_run_meta()
    if meta.get("headed") is not None:
        return bool(meta["headed"])
    return settings.HEADED

# ---------------------------------------------------------------------------
# 静态资源：CSS / JS（普通字符串，避免 f-string 的大括号转义问题）
# ---------------------------------------------------------------------------
CSS = """
:root{
  --bg:#f3f5f9; --card:#ffffff; --ink:#1f2733; --muted:#6b7785;
  --line:#e4e9f0; --accent:#3b6fd6; --accent-soft:#eaf1ff;
  --pass:#1f9d57; --pass-soft:#e7f7ee; --fail:#e0483b; --fail-soft:#fdecea;
  --warn:#e8a33d; --warn-soft:#fdf3e3; --shadow:0 1px 3px rgba(20,40,80,.08);
  --radius:12px;
}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Roboto,Helvetica,Arial,sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.55;font-size:14px}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:24px 20px 64px}

/* 头部 */
header{background:linear-gradient(135deg,#2b4a8b,#3b6fd6);color:#fff;border-radius:var(--radius);
  padding:22px 26px;box-shadow:var(--shadow);margin-bottom:20px}
header h1{margin:0 0 6px;font-size:21px;font-weight:700;letter-spacing:.3px}
header .sub{opacity:.92;font-size:13px}
header .meta{margin-top:12px;display:flex;flex-wrap:wrap;gap:10px}
header .chip{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.25);
  border-radius:999px;padding:3px 12px;font-size:12px}

/* 汇总条 */
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 18px;box-shadow:var(--shadow);text-align:center}
.stat .num{font-size:30px;font-weight:800;line-height:1}
.stat .lbl{margin-top:6px;color:var(--muted);font-size:12.5px}
.stat.total .num{color:var(--ink)}
.stat.passed .num{color:var(--pass)}
.stat.failed .num{color:var(--fail)}
.stat.time .num{font-size:22px;color:var(--accent)}

/* 用例卡片 */
.case{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);margin-bottom:18px;overflow:hidden}
.case>.head{display:flex;align-items:center;gap:12px;padding:14px 18px;cursor:pointer;
  border-left:6px solid var(--muted)}
.case.passed>.head{border-left-color:var(--pass)}
.case.failed>.head{border-left-color:var(--fail)}
.case.unknown>.head{border-left-color:var(--warn)}
.case>.head .cid{font-weight:700;font-size:14px;background:var(--accent-soft);color:var(--accent);
  border-radius:8px;padding:3px 10px}
.case>.head .title{flex:1;font-weight:600}
.status{font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px}
.status.passed{background:var(--pass-soft);color:var(--pass)}
.status.failed{background:var(--fail-soft);color:var(--fail)}
.status.unknown{background:var(--warn-soft);color:var(--warn)}
.case>.head .dur{color:var(--muted);font-size:12px}
.case>.head .chev{color:var(--muted);transition:transform .2s;font-size:13px}
.case.open>.head .chev{transform:rotate(90deg)}

.body{padding:0 18px 18px;display:none}
.case.open .body{display:block}

/* S/G/T 区块 */
.sgt{display:grid;grid-template-columns:96px 1fr;gap:8px 12px;margin:14px 0;
  background:#fafbfd;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.sgt .k{font-weight:700;color:var(--accent);font-size:12.5px}
.sgt .v{color:var(--ink)}
/* W 步骤在 SGT 网格内渲染：去掉独立左侧时间线，避免与 S/G 列错位 */
.sgt .v .steps{border-left:none;margin:6px 0 2px;padding-left:0}
.sgt .v .step{padding:9px 0 9px 30px}
.sgt .v .step-no{left:0}
.sgt .v .step:before{left:-3px;top:15px;width:10px;height:10px}

/* 步骤时间线 */
.steps{border-left:2px solid var(--line);margin:6px 0 4px 8px;padding-left:0}
.step{position:relative;padding:10px 0 10px 26px;display:flex;gap:12px;align-items:flex-start}
.step:before{content:"";position:absolute;left:-7px;top:16px;width:12px;height:12px;border-radius:50%;
  background:#fff;border:2px solid var(--accent)}
.step.t:before{background:var(--pass);border-color:var(--pass)}
.step-body{flex:1;min-width:0}
.step-no{position:absolute;left:-30px;top:10px;width:22px;height:22px;border-radius:50%;
  background:var(--accent);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center}
.step-no.t{background:var(--pass)}
.step-text{font-size:13.5px}
.step-note{font-size:12px;color:var(--muted);margin-top:3px;padding:3px 8px;background:#f5f7fa;border-radius:6px;display:inline-block}
.badge{display:inline-block;font-size:11.5px;font-weight:700;padding:1px 9px;border-radius:999px;margin-left:8px;vertical-align:middle}
.badge.ok{background:var(--pass-soft);color:var(--pass)}
.badge.bad{background:var(--fail-soft);color:var(--fail)}
.badge.na{background:#eef1f5;color:var(--muted)}
.shot{display:block;max-width:560px;width:100%;margin-top:8px;border:1px solid var(--line);
  border-radius:8px;cursor:zoom-in;transition:filter .15s}
.shot:hover{filter:brightness(.97)}
.note{color:var(--muted);font-style:italic;padding:8px 0}

/* 失败诊断区块 */
.diag{margin:12px 0 4px;border:1px solid var(--fail);border-radius:10px;
  background:var(--fail-soft);padding:12px 14px}
.diag .h{font-weight:800;color:var(--fail);margin-bottom:8px;font-size:13px}
.diag .sum{font-weight:700;color:var(--fail);margin-bottom:8px}
.diag .sub{font-weight:700;color:var(--ink);margin:10px 0 4px;font-size:12.5px}
.uitable{border-collapse:collapse;width:100%;font-size:12.5px;margin:2px 0 4px}
.uitable td{border:1px solid var(--line);padding:5px 9px;background:#fff}
.uitable td.k{color:var(--accent);font-weight:600;width:140px}
.st-ok{color:var(--pass);font-weight:700}
.st-bad{color:var(--fail);font-weight:700}
.diag ul{margin:4px 0 2px;padding-left:20px}
.diag li{margin:2px 0;color:var(--ink)}
.failure-reason{margin:10px 0 12px;border:2px solid var(--fail);border-radius:10px;
  background:#fff5f5;padding:12px 14px}
.failure-reason .fr-h{font-weight:800;color:var(--fail);font-size:13.5px;margin-bottom:8px}
.failure-reason .fr-step{margin:6px 0;padding-left:2px;border-left:3px solid var(--fail);padding:4px 0 4px 10px}
.failure-reason .fr-no{display:inline-block;font-weight:800;color:#fff;background:var(--fail);
  border-radius:6px;padding:1px 7px;margin-right:8px;font-size:12px}
.failure-reason .fr-text{font-weight:700;color:var(--ink)}
.failure-reason .fr-note{color:var(--muted);font-size:12.5px;margin-top:4px;line-height:1.6}
.diag .meta{color:var(--muted);font-size:12px;margin-top:6px}
.diag .failshot{display:block;max-width:680px;width:100%;margin-top:10px;border:1px solid var(--fail);
  border-radius:8px;cursor:zoom-in}

/* 灯箱 */
#lightbox{position:fixed;inset:0;background:rgba(15,23,42,.86);display:none;align-items:center;
  justify-content:center;z-index:999;cursor:zoom-out;padding:30px}
#lightbox img{max-width:92vw;max-height:92vh;border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,.5)}
footer{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
footer .ref{color:var(--accent)}
@media(max-width:720px){.summary{grid-template-columns:repeat(2,1fr)}.sgt{grid-template-columns:1fr}}
"""

JS = """
function toggle(el){el.classList.toggle('open');}
function zoom(img){var lb=document.getElementById('lightbox');lb.querySelector('img').src=img.src;lb.style.display='flex';}
function closeLb(){document.getElementById('lightbox').style.display='none';}
// 默认展开首条，其余折叠
document.addEventListener('DOMContentLoaded',function(){
  var cases=document.querySelectorAll('.case');
  cases.forEach(function(c,i){ if(i===0) c.classList.add('open'); });
});
"""

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _b64_img(img_path: Path) -> str | None:
    if not img_path.exists():
        return None
    try:
        data = img_path.read_bytes()
        return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


def _eff_badge(eff) -> str:
    if eff is True:
        return '<span class="badge ok">✅ 有效</span>'
    if eff is False:
        return '<span class="badge bad">❌ 无效</span>'
    return '<span class="badge na">— 未校验</span>'


def _load_steps(case_id: str) -> dict | None:
    # 读取证据一律用「最新批次」目录，保证实时运行与 make_report.py 事后复生成
    # 都能定位到正确的截图（避免独立进程重新生成 RUN_TS 指向空目录）。
    p = get_latest_evidence_dir() / case_id / "steps.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    return None


def _ui_state_cls(state: str) -> str:
    """把 UI 元素状态映射为红/绿样式类。"""
    if not state:
        return "st-bad"
    if state.startswith("可见"):
        return "st-ok"
    return "st-bad"


def _build_diagnosis_html(diag: dict, case_id: str) -> str:
    """渲染失败诊断区块（UI 元素状态 + 接口/网络失败 + 失败截图）。"""
    if not diag:
        return ""

    summary = _esc(diag.get("summary", "用例失败，未捕获到诊断信息。"))
    ui = diag.get("ui", {}) or {}
    api = diag.get("api_issues", []) or []
    hint = diag.get("locator_hint")
    ps = diag.get("page_state", {}) or {}

    # UI 元素状态表
    rows = []
    for name, st in ui.items():
        cls = _ui_state_cls(st)
        rows.append(
            f'<tr><td class="k">{_esc(name)}</td><td class="{cls}">{_esc(st)}</td></tr>'
        )
    ui_table = f'<table class="uitable">{"".join(rows)}</table>' if rows else ""

    # 接口/网络失败列表
    if api:
        api_html = "<ul>" + "".join(f"<li>{_esc(a)}</li>" for a in api) + "</ul>"
    else:
        api_html = '<div class="note">未发现接口/网络异常（非接口层失败）。</div>'

    # 失败截图（最新批次证据目录下 FAIL_<case>.png）
    shot_html = ""
    fshot = get_latest_evidence_dir() / case_id / f"FAIL_{case_id}.png"
    if fshot.exists():
        img = _b64_img(fshot)
        if img:
            shot_html = (
                f'<div class="sub">失败瞬间截图</div>'
                f'<img class="failshot" src="{img}" alt="失败截图" onclick="zoom(this)">'
            )

    hint_html = f'<div class="meta">异常定位器线索：{_esc(hint)}</div>' if hint else ""
    ps_html = ""
    if ps.get("url") or ps.get("title"):
        ps_html = (
            f'<div class="meta">失败页面状态：URL={_esc(ps.get("url",""))}；'
            f'Title={_esc(ps.get("title",""))}</div>'
        )

    return f"""
    <div class="diag">
      <div class="h">🔍 失败诊断（UI 元素失效 vs 接口失败）</div>
      <div class="sum">结论：{summary}</div>
      <div class="sub">① UI 关键元素状态</div>
      {ui_table}
      <div class="sub">② 接口 / 网络诊断</div>
      {api_html}
      {ps_html}
      {hint_html}
      {shot_html}
    </div>"""


def _build_failure_reason(step_map: dict) -> str:
    """从真实执行证据中提取失败原因：凡 effective=False 的 W 步骤即失败点。

    返回醒目的「失败原因」区块，放在失败用例卡片内（与用例一一对应），
    文案取自该步骤的 note（执行器如实记录的真实失败原因，如站点缺陷说明）。
    """
    fails = [stp for stp in step_map.values() if stp.get("effective") is False]
    if not fails:
        return ""
    items = []
    for stp in fails:
        no = stp.get("no")
        text = _esc(stp.get("text", ""))
        note = (stp.get("note") or "").strip()
        if len(note) > 280:
            note = note[:277] + "…"
        note_html = f'<div class="fr-note">{_esc(note)}</div>' if note else ""
        items.append(
            f'<div class="fr-step">'
            f'<span class="fr-no">W{no}</span>'
            f'<span class="fr-text">{text}</span>'
            f"{note_html}"
            f"</div>"
        )
    return (
        '<div class="failure-reason">'
        '<div class="fr-h">❌ 失败原因</div>'
        + "".join(items)
        + "</div>"
    )



def _status_from_outcome(outcome_map: dict, case_id: str) -> tuple[str, str, float]:
    """返回 (status, message, duration)。status ∈ passed/failed/unknown。"""
    rec = outcome_map.get(case_id)
    if rec:
        return rec.get("status", "unknown"), rec.get("message", ""), float(rec.get("duration", 0) or 0)
    return "unknown", "", 0.0


# ---------------------------------------------------------------------------
# 报告构建
# ---------------------------------------------------------------------------
def build_report_html(
    cases: dict,
    outcome_map: dict,
    diagnosis_map: dict | None = None,
    headed: bool | None = None,
) -> str:
    """生成完整 HTML 字符串。cases: {case_id: TestCase}；outcome_map: {case_id: {...}}。

    diagnosis_map（可选）：{case_id: 诊断dict}，来自 core.diagnostics，用于失败用例标记原因。
    headed（可选）：执行模式标签来源。None 时回退 settings.HEADED；一般传入 pytest 实际运行时的
    持久化值（见 read_run_meta），确保报告标注与真实运行一致。
    """
    diagnosis_map = diagnosis_map or {}
    # 优先使用持久化的真实运行模式；缺省才回退当前进程配置
    is_headed = headed if headed is not None else settings.HEADED
    gen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total = len(cases)
    passed = failed = 0
    total_dur = 0.0
    for cid in cases:
        st, _msg, dur = _status_from_outcome(outcome_map, cid)
        total_dur += dur
        if st == "passed":
            passed += 1
        elif st == "failed":
            failed += 1

    summary_html = f"""
    <div class="summary">
      <div class="stat total"><div class="num">{total}</div><div class="lbl">用例总数</div></div>
      <div class="stat passed"><div class="num">{passed}</div><div class="lbl">通过</div></div>
      <div class="stat failed"><div class="num">{failed}</div><div class="lbl">失败</div></div>
      <div class="stat time"><div class="num">{total_dur:.1f}s</div><div class="lbl">总耗时</div></div>
    </div>"""

    cards = []
    for cid, tc in cases.items():
        st, msg, dur = _status_from_outcome(outcome_map, cid)
        status_cls = "passed" if st == "passed" else ("failed" if st == "failed" else "unknown")
        status_label = {"passed": "通过", "failed": "失败", "unknown": "未知"}[status_cls]

        # ---- 严格 S-G-W-T 四段式：W 步骤以用例定义为准，附执行截图 ----
        steps_data = _load_steps(cid)
        step_map: dict = {}
        if steps_data and steps_data.get("steps"):
            for stp in steps_data["steps"]:
                if stp.get("kind") == "W":
                    step_map[stp.get("no")] = stp

        def _w_shot(no) -> str | None:
            stp = step_map.get(no)
            if stp and stp.get("screenshot"):
                img = _b64_img(get_latest_evidence_dir() / cid / stp["screenshot"])
                if img:
                    return img
            return None

        if tc.steps:
            w_rows = []
            for s in tc.steps:
                no = s["no"]
                stp = step_map.get(no)
                img = _w_shot(no)
                eff = stp.get("effective") if stp else None
                note = (stp or {}).get("note", "")
                shot_html = (
                    f'<img class="shot" src="{img}" alt="步骤截图" onclick="zoom(this)">'
                    if img else ""
                )
                note_html = f'<div class="step-note">{_esc(note)}</div>' if note else ""
                w_rows.append(
                    f'<div class="step">'
                    f'<span class="step-no">W{no}</span>'
                    f'<div class="step-body">'
                    f'<div class="step-text">{_esc(s["text"])} {_eff_badge(eff)}</div>'
                    f"{note_html}{shot_html}"
                    f"</div></div>"
                )
            w_html = '<div class="steps">' + "".join(w_rows) + "</div>"
        else:
            w_html = '<div class="note">用例未定义 W 步骤。</div>'

        sgt_html = (
            f'<div class="sgt">'
            f'<div class="k">S 场景</div><div class="v">{_esc(tc.scenario) or "—"}</div>'
            f'<div class="k">G 前提</div><div class="v">{_esc(tc.given) or "—"}</div>'
            f'<div class="k">W 步骤</div><div class="v">{w_html}</div>'
            f'<div class="k">T 预期</div><div class="v">{_esc(tc.then) or "—"}</div>'
            f"</div>"
        )

        msg_html = ""
        if status_cls == "failed":
            # 失败原因（与用例一一对应）：取自真实执行证据中 effective=False 的步骤 note
            fr_html = _build_failure_reason(step_map)
            # 结构化失败诊断（UI 元素失效 vs 接口失败）作为补充
            diag = diagnosis_map.get(cid)
            diag_html = _build_diagnosis_html(diag, cid) if diag else ""
            raw = f'<div class="note" style="color:var(--fail)">⚠ 原始异常：{_esc(msg[:500])}</div>' if msg else ""
            msg_html = fr_html + diag_html + raw

        cards.append(
            f'<div class="case {status_cls} open" id="case-{cid}">'
            f'<div class="head" onclick="toggle(this.parentNode)">'
            f'<span class="cid">{_esc(cid)}</span>'
            f'<span class="title">{_esc(tc.title)}</span>'
            f'<span class="status {status_cls}">{status_label}</span>'
            f'<span class="dur">{dur:.1f}s</span>'
            f'<span class="chev">▶</span>'
            f"</div>"
            f'<div class="body">{sgt_html}{msg_html}</div>'
            f"</div>"
        )

    cards_html = "\n".join(cards)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>应用宝官网自动化测试报告</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>应用宝官网（sj.qq.com）自动化测试报告</h1>
    <div class="sub">pytest + Playwright · 动态识别（多候选 OR）· 每步截图内嵌 · {'有头可视化执行' if is_headed else '无头批量执行'}</div>
    <div class="meta">
      <span class="chip">测试对象：{_esc(settings.BASE_URL)}</span>
      <span class="chip">浏览器：本机 Chrome（channel=chrome）</span>
      <span class="chip">生成时间：{gen}</span>
      <span class="chip">运行批次：{_esc(RUN_TS)}</span>
      <span class="chip">执行模式：{'有头可视化' if is_headed else '无头（CI 批量）'}</span>
    </div>
  </header>

  {summary_html}

  {cards_html}

  <footer>
    报告由自动化框架生成，参考 <span class="ref">Allure</span> 开源测试报告风格 ·
    截图与有效性校验逐步骤留痕，便于非自动化人员核验
  </footer>
</div>

<div id="lightbox" onclick="closeLb()"><img src="" alt="放大查看"></div>
<script>{JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def build_and_write(outcome_map: dict | None = None, diagnosis_map: dict | None = None) -> Path:
    """构建报告并写入 reports/应用宝官网自动化测试报告.html。

    outcome_map 可缺省：缺省时尝试从 reports/results.json 读取（独立复生成场景）。
    diagnosis_map 可缺省：缺省时尝试从 reports/diagnosis.json 读取。
    """
    if outcome_map is None:
        rp = REPORTS_DIR / "results.json"
        if rp.exists():
            try:
                outcome_map = json.loads(rp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                outcome_map = {}
        else:
            outcome_map = {}

    if diagnosis_map is None:
        if DIAGNOSIS_FILE.exists():
            try:
                diagnosis_map = json.loads(DIAGNOSIS_FILE.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                diagnosis_map = {}
        else:
            diagnosis_map = {}

    cases = parse_cases()
    # 执行模式标签采用 results.json.__meta__（与用例结果同源，权威），确保与真实运行一致。
    headed = _effective_headed(outcome_map)
    html = build_report_html(cases, outcome_map, diagnosis_map, headed=headed)
    out = REPORTS_DIR / "应用宝官网自动化测试报告.html"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    p = build_and_write()
    print(f"报告已生成: {p}")
