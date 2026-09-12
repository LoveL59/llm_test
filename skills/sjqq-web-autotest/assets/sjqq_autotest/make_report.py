"""独立复生成「优化报告」(reports/应用宝官网自动化测试报告.html)。

无需重跑用例：读取已有的执行证据（reports/evidence/<id>/steps.json）与结果
（reports/results.json），重新生成内嵌每步截图的 Allure 风格报告。

用法：
    cd sjqq_autotest
    ./venv/Scripts/python make_report.py     # Windows；macOS/Linux 用 ./venv/bin/python
"""

from __future__ import annotations

import json

import config.settings as settings
from core.paths import REPORTS_DIR, DIAGNOSIS_FILE
from core.report_builder import build_and_write, read_run_meta


def main() -> None:
    rp = REPORTS_DIR / "results.json"
    outcome_map: dict = {}
    if rp.exists():
        try:
            outcome_map = json.loads(rp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 读取 results.json 失败: {e}")

    # 失败诊断（UI 元素失效 vs 接口失败）一并读取，与实时运行保持一致
    diagnosis_map: dict = {}
    if DIAGNOSIS_FILE.exists():
        try:
            diagnosis_map = json.loads(DIAGNOSIS_FILE.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 读取 diagnosis.json 失败: {e}")

    out = build_and_write(outcome_map, diagnosis_map=diagnosis_map)
    print(f"报告已生成: {out}")
    # 执行模式以 pytest 真实运行的持久化元数据为准，避免受当前环境变量干扰
    meta = read_run_meta()
    mode = "有头" if (settings.HEADED if meta.get("headed") is None else meta["headed"]) else "无头"
    print(f"  用例结果: {len(outcome_map)} 条；失败诊断: {len(diagnosis_map)} 条；执行模式: {mode}（来自运行元数据）")


if __name__ == "__main__":
    main()
