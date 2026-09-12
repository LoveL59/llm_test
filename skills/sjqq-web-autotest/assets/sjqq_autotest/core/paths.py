"""项目路径常量，集中管理，避免多处重复计算。

所有与磁盘路径相关的常量都放这里，conftest / step_recorder / 报告生成等统一引用，
避免路径不一致。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# 项目根目录（sjqq_autotest/）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 报告目录
REPORTS_DIR = PROJECT_ROOT / "reports"

# 唯一测试报告的 HTML 文件名（中文命名，便于业务/产品同学直接识别）
REPORT_FILENAME = "应用宝官网自动化测试报告.html"

# 证据根目录：reports/evidence/（其下按运行批次时间戳分子目录）
EVIDENCE_ROOT = REPORTS_DIR / "evidence"

# 本次运行的批次时间戳（同一 pytest 进程内恒定），用于：
#  - 证据截图按批次隔离（reports/evidence/<RUN_TS>/<case_id>/...），
#  - 报告头部标注运行批次，便于追溯「截图+日期」。
# 每次重新执行测试都会生成新的 RUN_TS，旧批次的截图仍保留（仅清理日志/中间态），
# 因此不会污染历史证据，同时满足「只保留测试报告 + 截图(+日期)」。
RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")

# 本次运行的写入目录（StepRecorder 逐步骤截图、失败诊断截图等写到这里）。
# 注意：这是「写入」路径，仅在实时 pytest 进程内恒定；独立运行 make_report.py
# 时不能再用它来「读取」旧证据（进程重启会重新生成 RUN_TS 指向空目录），
# 读取请一律用 get_latest_evidence_dir()。
EVIDENCE_DIR = EVIDENCE_ROOT / RUN_TS

# 自然语言用例目录（S/G/W/T，供非自动化人员维护）
CASES_DIR = PROJECT_ROOT / "cases"

# 单一用例文件（所有用例集中于此，自动化执行前先读取并按其执行）
CASES_FILE = CASES_DIR / "cases.md"

# 失败诊断落盘文件（session 级，供报告渲染 / 独立复生成报告读取）
DIAGNOSIS_FILE = REPORTS_DIR / "diagnosis.json"

# 运行批次目录名格式：YYYYMMDD_HHMMSS（用于识别合法的 dated 证据目录，
# 排除历史上遗留的 flat 结构目录如 TC01/TC02/...）
_TS_RE = re.compile(r"^\d{8}_\d{6}$")


def get_latest_evidence_dir() -> Path:
    """返回【读取证据】用的目录：evidence/ 下最新的 dated 子目录。

    实时运行时它等于当前 RUN_TS 目录；用 make_report.py 事后复生成报告时，
    也能正确指向最近一次执行产生的截图，而不会因重新 import 生成新的 RUN_TS
    而指向空目录。找不到任何合法 dated 目录时，兜底回退到当前 RUN_TS 目录并建好。
    """
    if EVIDENCE_ROOT.exists():
        subs = [p for p in EVIDENCE_ROOT.iterdir() if p.is_dir() and _TS_RE.match(p.name)]
        if subs:
            # 目录名即时间戳，字典序 == 时间序，直接取最大即可
            return max(subs, key=lambda p: p.name)
    d = EVIDENCE_ROOT / RUN_TS
    d.mkdir(parents=True, exist_ok=True)
    return d


def case_evidence_dir(case_id: str) -> Path:
    """返回某用例在本批次的证据目录（写入用），并确保目录存在。"""
    d = EVIDENCE_DIR / case_id
    d.mkdir(parents=True, exist_ok=True)
    return d
