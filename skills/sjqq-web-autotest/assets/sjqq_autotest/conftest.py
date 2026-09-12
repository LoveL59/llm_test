"""pytest 全局配置与 fixtures。

职责：
1. 通过 pytest-playwright 管理浏览器/上下文/页面生命周期；
2. 统一视口、超时、浏览器启动参数（Windows 环境适配）；
3. 提供 base_url / home 等可复用 fixtures；
4. 用例失败自动截图 + 失败诊断（UI 元素失效 vs 接口失败），并在报告中标记原因；
5. 用例开始前先读取唯一用例文件 cases/cases.md 并按其执行（有头可视化）；
6. 每次重跑前清理所有日志/中间态，按批次(日期)隔离证据截图，确保环境不被污染。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pytest

import config.settings as settings
from core.paths import (
    PROJECT_ROOT,
    REPORTS_DIR,
    EVIDENCE_DIR,
    CASES_FILE,
    DIAGNOSIS_FILE,
    REPORT_FILENAME,
)
from core.paths import case_evidence_dir
from core.case_reader import parse_cases, dump
from core import diagnostics

REPORTS_DIR.mkdir(exist_ok=True)

# 收集每个用例的最终结果（pass/fail/耗时/失败原因），供「优化报告」生成使用
_SESSION_OUTCOMES: dict = {}
# 失败截图（本批次证据目录下 FAIL_<case>.png）
_FAIL_SHOTS: dict = {}


def _nodeid_to_case_id(nodeid: str) -> str | None:
    """把 pytest 节点 id 映射到用例 id。

    兼容两种形态：
      - 旧式脚本：test_01_*.py -> TC01
      - 数据驱动参数化：test_cases_md.py::test_case_from_md[TC02] -> TC02
    统一从 nodeid 中提取 TC\\d+。
    """
    m = re.search(r"TC(\d+)", nodeid)
    if m:
        return f"TC{m.group(1)}"
    return None


# ---------------------------------------------------------------------------
# 环境清理：每次重跑前清理日志/中间态，按批次隔离证据（截图+日期）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def clean_environment():
    """测试任务启动前先清理上一轮的日志与中间产物，确保环境不被污染。

    仅清理「日志/中间态」：
      - reports/cases_loaded.log、reports/results.json、reports/diagnosis.json
      - 各批次证据目录里的 steps.log / steps.json（保留 PNG 截图）
    保留「测试报告 + 截图(+日期)」：reports/应用宝官网自动化测试报告.html 与
    reports/evidence/<RUN_TS>/ 下的 PNG 截图（按批次/日期隔离，互不干扰）。
    """
    print("\n" + "=" * 72)
    print("🧹 [环境清理] 清理日志与中间态，确保重跑环境干净（保留报告与截图）")
    removed = []

    # 1) 根目录日志/中间产物
    for pat in ("cases_loaded.log", "results.json", "diagnosis.json"):
        p = REPORTS_DIR / pat
        if p.exists():
            try:
                p.unlink()
                removed.append(p.name)
            except Exception:  # noqa: BLE001
                pass

    # 2) 旧失败截图（根目录）
    for p in REPORTS_DIR.glob("fail_*.png"):
        try:
            p.unlink()
            removed.append(p.name)
        except Exception:  # noqa: BLE001
            pass

    # 3) 各批次证据目录里的日志/中间 json（保留 PNG 截图）
    if REPORTS_DIR.exists():
        for sub in REPORTS_DIR.glob("evidence/*"):
            if not sub.is_dir():
                continue
            for name in ("steps.log", "steps.json"):
                lp = sub / name
                if lp.exists():
                    try:
                        lp.unlink()
                        removed.append(f"{sub.name}/{name}")
                    except Exception:  # noqa: BLE001
                        pass

    # 确保本批次证据根目录存在
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    if removed:
        print("    已清理: " + ", ".join(removed))
    else:
        print("    无需清理（环境已干净）")
    print("=" * 72 + "\n")
    yield


# ---------------------------------------------------------------------------
# 先读用例：测试开始前加载唯一的用例文件 cases/cases.md 并打印，确保按用例执行
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def load_cases_first():
    """测试任务启动时先读取用例文件 cases/cases.md，并打印/留存全部 S/G/W/T 摘要。

    满足需求：执行测试任务时，先读用例，然后按照用例执行；有头浏览器可见每一步。
    同时把读取到的用例摘要写入 reports/cases_loaded.log，便于事后核验「先读了什么」。
    """
    print("\n" + "=" * 72)
    print(f"📖 [先读用例] 加载用例文件: {CASES_FILE}")
    try:
        cases = parse_cases()
        summary = dump(cases)
        print(f"    共 {len(cases)} 条用例，将按顺序执行：")
        print("-" * 72)
        print(summary)
        # 持久化，便于核验「先读用例」
        loaded_log = REPORTS_DIR / "cases_loaded.log"
        loaded_log.write_text(
            f"# 执行前读取的用例文件: {CASES_FILE}\n# 共 {len(cases)} 条用例\n\n{summary}",
            encoding="utf-8",
        )
        print(f"    （已留存至 {loaded_log}）")
    except FileNotFoundError as e:
        print(f"    ❌ 未找到用例文件：{e}")
        raise
    except Exception as e:  # noqa: BLE001
        print(f"    [warn] 解析用例文件出错: {e}")
    print("=" * 72 + "\n")
    yield


@pytest.fixture(scope="session")
def all_cases():
    """供各用例取用已解析的用例数据（dict[case_id, TestCase]）。"""
    return parse_cases()


# ---------------------------------------------------------------------------
# 浏览器上下文参数（视口、UA 等），覆盖 pytest-playwright 默认值
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": settings.VIEWPORT,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "ignore_https_errors": True,
        # 接受下载事件：使「点击下载→触发文件下载 / 二维码下载流程」可被断言捕获
        "accept_downloads": True,
    }


# 使用本机已安装的 Google Chrome（channel="chrome"），避免下载 Chromium
# （Playwright CDN 在部分网络环境不可达；本机已有 Chrome，符合"优先参考本机已安装"）
# 直接覆盖 browser 夹具，确保以系统 Chrome 启动。
# 执行模式语义：settings.HEADED=True 表示「有头 / 可见窗口」模式
# （业务/非自动化人员可实时观看每一步）；HEADED=False 表示「无头/后台」模式。
# 注意 Playwright 的 headless 参数与变量语义相反：
#   headless=True  → 无窗口（无头）；headless=False → 有窗口（有头）。
# 因此必须传 headless=not settings.HEADED，否则会出现
# 「变量写的是有头、浏览器却无窗口」或反之的错配，进而让报告执行模式标签失真。
@pytest.fixture(scope="session")
def browser(browser_type, browser_type_launch_args):
    browser = browser_type.launch(
        channel="chrome",
        headless=not settings.HEADED,
        slow_mo=settings.SLOW_MO,
        **browser_type_launch_args,
    )
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    return {
        **browser_type_launch_args,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ],
    }


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def home(page):
    """进入应用宝首页并返回 HomePage 页面对象（已设置默认超时）。"""
    page.set_default_timeout(settings.DEFAULT_TIMEOUT)
    page.set_default_navigation_timeout(settings.NAVIGATION_TIMEOUT)
    from core.pages.home_page import HomePage

    hp = HomePage(page)
    hp.goto(settings.BASE_URL)
    return hp


# ---------------------------------------------------------------------------
# 网络监听（每用例挂载）：捕获接口失败 / 网络异常，供失败诊断使用
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _monitor(page, request):
    case_id = _nodeid_to_case_id(request.node.nodeid)
    if case_id:
        diagnostics.reset_network(case_id)
        diagnostics.attach_network_monitor(page, case_id)
    yield


# ---------------------------------------------------------------------------
# 失败自动截图 + 失败诊断
# ---------------------------------------------------------------------------
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # 仅在「调用阶段」时记录该用例的最终结果，供「优化报告」生成使用
    if report.when == "call":
        case_id = _nodeid_to_case_id(item.nodeid)
        if case_id is not None:
            status = "passed" if report.passed else ("failed" if report.failed else "skipped")
            msg = (report.longreprtext or "")[:800] if report.failed else ""
            _SESSION_OUTCOMES[case_id] = {
                "status": status,
                "message": msg,
                "duration": getattr(report, "duration", 0) or 0,
            }

        # 失败时：诊断（UI 元素失效 vs 接口失败）+ 保存失败截图到本批次证据目录
        if report.failed:
            page = item.funcargs.get("page")
            if page is not None and case_id is not None:
                try:
                    diag = diagnostics.diagnose_failure(page, case_id, report.longreprtext or "")
                    print(f"\n🔍 [失败诊断] {case_id}: {diag['summary']}")
                    if diag.get("api_issues"):
                        for a in diag["api_issues"]:
                            print(f"    ⚠ 接口: {a}")
                    if settings.CAPTURE_ON_FAILURE:
                        shot_path = case_evidence_dir(case_id) / f"FAIL_{case_id}.png"
                        try:
                            page.screenshot(path=str(shot_path), full_page=True)
                            _FAIL_SHOTS[case_id] = shot_path.name
                            print(f"    📸 失败截图: {shot_path}")
                        except Exception as e:  # noqa: BLE001
                            print(f"    [warn] 失败截图保存失败: {e}")
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] 失败诊断出错: {e}")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """全部用例执行完后，写出 results.json / diagnosis.json 并生成内嵌截图的报告。"""
    try:
        # 把执行模式嵌入 results.json（与用例结果同源、同一次 sessionfinish 写出），
        # 作为报告执行模式标签的权威来源，确保「报告标注」与「真实运行」永不脱钩
        # （此前依赖独立的 run_meta.json，会被不同环境变量的进程覆盖而失真）。
        _results_doc = {
            "__meta__": {
                "headed": settings.HEADED,
                "slow_mo": settings.SLOW_MO,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
            **_SESSION_OUTCOMES,
        }
        (REPORTS_DIR / "results.json").write_text(
            json.dumps(_results_doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 持久化「真实运行模式」：浏览器究竟是有头还是无头，由 pytest 运行那一刻决定。
        # 报告无论何时重建都读此值，避免事后用不同 SJQQ_HEADED 重建报告导致标注失真。
        try:
            (REPORTS_DIR / "run_meta.json").write_text(
                json.dumps(
                    {"headed": settings.HEADED, "slow_mo": settings.SLOW_MO},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass
        diag_map = diagnostics.all_diagnoses()
        DIAGNOSIS_FILE.write_text(
            json.dumps(diag_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        from core.report_builder import build_and_write

        out = build_and_write(_results_doc, diagnosis_map=diag_map)
        print(f"\n📊 [优化报告] 已生成: {out}（内嵌每步截图 + 失败诊断，参考 Allure 风格）")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 生成优化报告失败: {e}")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """在终端末尾打印一份精简的用例结果摘要，便于 agent / 人直接看到结果。"""
    if not _SESSION_OUTCOMES:
        return
    lines = ["", "=" * 72, "📋 测试结果摘要（读取 reports/results.json）", "-" * 72]
    passed = failed = skipped = 0
    for cid in sorted(_SESSION_OUTCOMES):
        r = _SESSION_OUTCOMES[cid]
        st = r.get("status", "unknown")
        dur = r.get("duration", 0) or 0
        if st == "passed":
            passed += 1
            icon = "✅"
        elif st == "failed":
            failed += 1
            icon = "❌"
        elif st == "skipped":
            skipped += 1
            icon = "⏭"
        else:
            icon = "❔"
        lines.append(f"  {icon} {cid}  [{st:<7}]  {dur:5.1f}s")
    lines.append("-" * 72)
    total = len(_SESSION_OUTCOMES)
    verdict = "全部通过 🎉" if failed == 0 else f"{failed} 条失败，请打开报告细看"
    lines.append(f"  合计 {total} | 通过 {passed} | 失败 {failed} | 跳过 {skipped}  →  {verdict}")
    lines.append(f"  报告: reports/{REPORT_FILENAME}")
    lines.append("=" * 72)
    terminalreporter.write_line("\n".join(lines))
