"""数据驱动执行入口：自动读取 cases/cases.md 的全部用例并逐条执行。

设计要点
--------
- **不绑定任何具体用例**：本文件不含 TC01/TC02… 的硬编码逻辑，而是用
  pytest.mark.parametrize 把 cases.md 解析出的所有用例变成独立的测试节点
  （用例增删只改 cases.md，本文件无需改动）。
- 每条 W 步骤交给 core.step_executor.StepExecutor 按「受控关键字」解释执行，
  复用 DynamicLocator（抗改版定位）+ BasePage 动作 + settings.POOLS 候选词库。
- 每步经 StepRecorder 记录（截图 + 有效性校验），失败自动诊断（UI/接口）并落报告。

维护人员只需编辑 cases/cases.md 即可新增/修改用例，完全无需了解本脚本。
"""

import pytest

import config.settings as settings
from core.case_reader import parse_cases
from core.dynamic_locators import DynamicLocator
from core.pages.base_page import BasePage
from core.step_executor import StepExecutor
from core.step_recorder import StepRecorder

# 启动时解析一次，得到全部用例 id 列表（作为参数化维度）
_CASES = parse_cases()
_CASE_IDS = sorted(_CASES.keys())


@pytest.mark.smoke
@pytest.mark.parametrize("case_id", _CASE_IDS, ids=_CASE_IDS)
def test_case_from_md(case_id, page):
    """按 cases.md 中的 S/G/W/T 逐条执行单个用例（数据驱动）。"""
    tc = _CASES[case_id]

    # 每用例独立的浏览器上下文（page 为函数级 fixture，天然隔离）
    page.set_default_timeout(settings.DEFAULT_TIMEOUT)
    page.set_default_navigation_timeout(settings.NAVIGATION_TIMEOUT)
    base = BasePage(page)
    loc = DynamicLocator(page)
    executor = StepExecutor(page, base, loc)

    # 基线：先进入首页（与「有头观看每一步」一致）
    base.goto(settings.BASE_URL)

    rec = StepRecorder(page, case_id, tc.title)
    rec.scenario(tc.scenario)
    rec.given(tc.given)

    ctx: dict = {}
    all_ok = True
    for step in tc.steps:
        text = step["text"]
        ok, detail = executor.run(text, ctx)
        print(f"    ↳ {detail}")
        rec.when(text, verify=lambda: ok, note=detail)
        if not ok:
            all_ok = False
            # 不立即中断：继续记录后续步骤，便于完整诊断
    rec.then(tc.then, verify=lambda: all_ok)

    assert all_ok, f"用例 {case_id} 存在失败步骤，请打开 reports/应用宝官网自动化测试报告.html 查看失败诊断"
