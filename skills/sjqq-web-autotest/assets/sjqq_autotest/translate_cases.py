"""业务自然语言用例 → 规范用例 的生成器（agent 翻译工作流）。

用途
----
业务 / 产品人员只需要在 `cases/cases_business.md` 里用大白话写用例
（场景 / 预期 / 步骤），本脚本由 agent（或具备 LLM 的环境）调用，
把每一句步骤翻译成 `step_executor` 能直接执行的「受控关键字」格式，
并生成 / 刷新 `cases/cases.md`（pytest 真正读取执行的文件）。

这样维护人员**完全不用碰代码、不用学关键字**：写中文 → 跑本脚本 → pytest。

运行
----
    # 默认读取 cases/cases_business.md，生成 cases/cases.md
    ./venv/Scripts/python translate_cases.py

    # 指定源 / 目标文件
    ./venv/Scripts/python translate_cases.py --src 我的用例.md --dst cases/cases.md

    # 开启 LLM 增强（需设置 SJQQ_LLM_KEY 等环境变量；未设置自动回退启发式）
    SJQQ_NL_LLM=1 ./venv/Scripts/python translate_cases.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import config.settings as settings
from core.nl_translator import canonical_step_text, translate_step

ROOT = Path(__file__).resolve().parent
DEFAULT_SRC = ROOT / "cases" / "cases_business.md"
DEFAULT_DST = ROOT / "cases" / "cases.md"


# ---------------------------------------------------------------------------
# 解析业务源文件
# ---------------------------------------------------------------------------
def _after(s: str) -> str:
    """取冒号 / 空格后的正文。"""
    m = re.match(r"^[一-龥A-Za-z]+\s*[：:]\s*(.*)$", s)
    return m.group(1).strip() if m else s.strip()


def _strip_tc_prefix(title: str) -> str:
    return re.sub(r"^TC\d+\s*", "", title).strip()


def parse_business(path: Path) -> list[dict]:
    """把 cases_business.md 解析为用例列表。

    每用例：{title, scenario, given, then, steps[]}
    步骤识别：数字序号（1. 1、1)）、项目符号（-/*），或「步骤：」之后的续行。
    """
    text = path.read_text(encoding="utf-8")
    # 去掉文件级前言（第一个 '## ' 之前的内容）
    blocks = re.split(r"^##\s+", text, flags=re.M)
    cases: list[dict] = []

    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        lines = blk.splitlines()
        title = _strip_tc_prefix(lines[0].strip())
        scenario = given = then = ""
        steps: list[str] = []
        in_steps = False

        for ln in lines[1:]:
            s = ln.strip()
            if not s:
                continue
            if s.startswith(("场景", "S ", "S：", "S:")):
                scenario = _after(s)
            elif s.startswith(("前提", "假设", "G ", "G：", "G:")):
                given = _after(s)
            elif s.startswith(("预期", "期望", "结果", "T ", "T：", "T:")):
                then = _after(s)
            elif s.startswith(("步骤", "Steps", "steps")):
                in_steps = True
            else:
                m = re.match(r"^\d+[.、)]\s*(.+)$", s)
                if m:
                    steps.append(m.group(1).strip())
                    in_steps = True
                    continue
                m = re.match(r"^[-*]\s+(.+)$", s)
                if m:
                    steps.append(m.group(1).strip())
                    in_steps = True
                    continue
                if in_steps:  # 步骤续行
                    steps.append(s)

        if not steps and not (scenario or then):
            continue  # 空块忽略
        cases.append({
            "title": title,
            "scenario": scenario,
            "given": given,
            "then": then,
            "steps": steps,
        })
    return cases


# ---------------------------------------------------------------------------
# 生成规范用例文件
# ---------------------------------------------------------------------------
HEADER = """# 应用宝官网自动化测试用例集（由 cases_business.md 自动翻译生成）

> 本文件由 `translate_cases.py` 从 `cases_business.md`（业务大白话）自动翻译生成，
> **请勿手工修改**——改 `cases_business.md` 后重跑生成器即可。
> 执行引擎本身也能直接读懂自由自然语言（运行时自动翻译），所以你甚至可以把大白话
> 直接写在这里的 W 步骤里。

"""


def generate(cases: list[dict], dst: Path) -> list[tuple[str, str, str]]:
    """写出 cases.md，并返回 (case_id, 原步骤, 译文) 映射用于打印。"""
    out = [HEADER]
    mapping: list[tuple[str, str, str]] = []

    for i, c in enumerate(cases, 1):
        cid = f"TC{i:02d}"
        out.append(f"## {cid} {c['title']}\n")
        if c["scenario"]:
            out.append(f"**S 场景**：{c['scenario']}\n")
        if c["given"]:
            out.append(f"**G 前提**：{c['given']}\n")
        for j, st in enumerate(c["steps"], 1):
            plan = translate_step(st, use_llm=settings.NL_USE_LLM)
            canon = canonical_step_text(plan) if plan else f"（未能翻译：{st}）"
            out.append(f"**W{j}**：{canon}\n")
            mapping.append((cid, st, canon))
        if c["then"]:
            out.append(f"**T 预期**：{c['then']}\n")
        out.append("\n")

    dst.write_text("".join(out), encoding="utf-8")
    return mapping


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="业务 NL 用例 → 规范用例 生成器")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="业务源文件")
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST, help="生成的规范用例文件")
    args = ap.parse_args(argv)

    if not args.src.exists():
        print(f"[错误] 找不到业务源文件: {args.src}", file=sys.stderr)
        return 2

    cases = parse_business(args.src)
    if not cases:
        print(f"[错误] 未能从 {args.src} 解析到任何用例", file=sys.stderr)
        return 1

    mapping = generate(cases, args.dst)

    print(f"已从 {args.src.name} 解析 {len(cases)} 条用例，生成 {args.dst.name}\n")
    print("原文 → 译文 对照：")
    print("-" * 60)
    for cid, src, dst in mapping:
        print(f"[{cid}] {src}\n      → {dst}")
    print("-" * 60)
    print("下一步：pytest  （执行引擎会直接运行上述规范用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
