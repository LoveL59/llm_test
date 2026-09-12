"""从单一的 cases/cases.md 解析出全部用例（S/G/W/T）。

设计目标
--------
非自动化人员（业务 / 产品）只维护 **一份** 用例文件 `cases/cases.md`，
采用四段式自然语言格式。自动化在 *开始前先读取该文件*，再按其中的
S（场景）/ G（前提）/ W1..Wn（步骤）/ T（预期）逐条执行，并逐步截图、做
有效性校验。文件即「用例的唯一真相源」。

文件格式约定（每个用例一个二级标题块）：

    ## TC01 首页加载冒烟
    **S 场景**：验证应用宝官网首页能够正常打开……
    **G 前提**：浏览器可正常访问 https://sj.qq.com/，网络连通。
    **W1**：打开应用宝官网首页
    **W2**：观察页面 <title> 是否已加载（非空）
    **T 预期**：页面标题非空；搜索框 / logo / 区块 / 导航均可见。

说明：S/G/T 各占一行；W 步骤以 **W<数字>** 开头，数字即执行顺序。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.paths import CASES_FILE


@dataclass
class TestCase:
    """一条用例的解析结果。"""

    case_id: str
    title: str
    scenario: str = ""
    given: str = ""
    steps: list = field(default_factory=list)  # [{"no": int, "text": str}, ...]
    then: str = ""

    def get_step(self, no: int) -> str:
        """按序号取 W 步骤文案；找不到返回空串。"""
        for s in self.steps:
            if s["no"] == no:
                return s["text"]
        return ""


def parse_cases(path: Path = CASES_FILE) -> dict[str, TestCase]:
    """解析用例文件，返回 {case_id: TestCase}。

    文件不存在时抛出 FileNotFoundError，交由调用方处理（确保「先读用例」真正生效）。
    """
    if not path.exists():
        raise FileNotFoundError(f"未找到用例文件: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    cases: dict[str, TestCase] = {}
    cur: TestCase | None = None
    cur_key: str | None = None

    # 匹配：## TC01 首页加载冒烟
    re_header = re.compile(r"^##\s+(TC\d+)\s*(.*)$")
    # 匹配：**S 场景**：文本  或  **G 前提**：文本  或  **T 预期**：文本
    re_sgt = re.compile(r"^\*\*(S|G|T)[^*]*\*\*\s*[：:]\s*(.*)$")
    # 匹配：**W1**：文本
    re_w = re.compile(r"^\*\*W(\d+)[^*]*\*\*\s*[：:]\s*(.*)$")

    for ln in lines:
        m = re_header.match(ln)
        if m:
            cur = TestCase(case_id=m.group(1), title=m.group(2).strip())
            cases[cur.case_id] = cur
            cur_key = None
            continue

        if cur is None:
            continue

        m = re_sgt.match(ln)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == "S":
                cur.scenario = val
            elif key == "G":
                cur.given = val
            elif key == "T":
                cur.then = val
            cur_key = key
            continue

        m = re_w.match(ln)
        if m:
            no = int(m.group(1))
            val = m.group(2).strip()
            cur.steps.append({"no": no, "text": val})
            cur_key = f"W{no}"
            continue

        # 续行：若当前行非空且不是新标题/标记，则追加到上一个字段（容忍多行描述）
        if ln.strip() and cur_key is not None and not ln.startswith("#"):
            append_to(cur, cur_key, ln.strip())

    return cases


def append_to(tc: TestCase, key: str, text: str) -> None:
    """把续行文本追加到对应字段。"""
    if key == "S":
        tc.scenario = (tc.scenario + " " + text).strip()
    elif key == "G":
        tc.given = (tc.given + " " + text).strip()
    elif key == "T":
        tc.then = (tc.then + " " + text).strip()
    elif isinstance(key, str) and key.startswith("W"):
        for s in tc.steps:
            if f"W{s['no']}" == key:
                s["text"] = (s["text"] + " " + text).strip()
                break


def dump(cases: dict[str, TestCase]) -> str:
    """把解析结果渲染为可读文本，便于在测试开始前打印（先读用例、按此执行）。"""
    lines = []
    for cid, tc in cases.items():
        lines.append(f"  {cid} {tc.title}")
        if tc.scenario:
            lines.append(f"    S 场景：{tc.scenario}")
        if tc.given:
            lines.append(f"    G 前提：{tc.given}")
        for s in tc.steps:
            lines.append(f"    W{s['no']}：{s['text']}")
        if tc.then:
            lines.append(f"    T 预期：{tc.then}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    cs = parse_cases()
    print(f"共解析到 {len(cs)} 条用例:\n")
    print(dump(cs))
