# -*- coding: utf-8 -*-
"""
用例 1：大模型能力评测（API 模式）
=================================
两种运行模式（均面向 OpenAI 兼容端点，契合手册“部署·API 测试”）：

A. 轻量请求模式（默认，无需下载基准）：
   用 openai 客户端对内置多选题集打分，验证「连通性 / 响应可解析 / 准确率」。
   适合每次迭代快速回归、或对一个只给 API 的模型做首轮摸底。

B. 权威基准模式（EVAL_USE_HARNESS=1）：
   调用 lm-evaluation-harness 的 openai-chat-completions 后端，跑 MMLU + CMMLU
   （需安装 lm_eval 且能访问 HuggingFace 数据集）。

框架   ：EleutherAI/lm-evaluation-harness（HF Open LLM Leaderboard 后端，被 NVIDIA/Cohere 使用）
数据集 ：MMLU  —— Hendrycks et al., ICLR 2021, arXiv:2009.03300（14,042 题，57 学科）
        CMMLU —— Li et al., arXiv:2306.09212（11,528 题，67 学科，中文）
对应手册：模块 1 评测数据集与离线能力评测 / 模块 11 原缺失标配维度

环境变量
--------
EVAL_API_BASE_URL   OpenAI 兼容端点（含 /v1），必填
EVAL_API_KEY        密钥
EVAL_MODEL          模型名
EVAL_ACC_THRESHOLD  准确率门禁（默认 0.5）
EVAL_STRICT         1=硬断言门禁（默认）；0=只记录不阻断（演示/摸底用）
EVAL_USE_HARNESS    1=走 harness 跑 MMLU+CMMLU
EVAL_TASKS          harness 任务（默认 mmlu,cmmlu）
EVAL_LIMIT          harness 单任务样本上限（默认 10）
"""
import os

import pytest

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

BASE_URL = os.environ.get("EVAL_API_BASE_URL")
API_KEY = os.environ.get("EVAL_API_KEY", "EMPTY")
MODEL = os.environ.get("EVAL_MODEL", "demo-model")
THRESHOLD = float(os.getenv("EVAL_ACC_THRESHOLD", "0.5"))
STRICT = os.getenv("EVAL_STRICT", "1") == "1"

# 内置演示多选题（真实 MMLU 风格；演示端点不保证答对，仅验证流程连通与可解析）
DEMO_QUESTIONS = [
    {"q": "Which planet is known as the Red Planet? (A) Venus (B) Mars (C) Jupiter (D) Saturn", "a": "B"},
    {"q": "What is 2 + 2? (A) 3 (B) 4 (C) 5 (D) 6", "a": "B"},
    {"q": "Who wrote 'Hamlet'? (A) Dickens (B) Shakespeare (C) Twain (D) Poe", "a": "B"},
    {"q": "Speed of light is about? (A) 3e8 m/s (B) 3e5 m/s (C) 3e3 m/s (D) 3e10 m/s", "a": "A"},
    {"q": "Largest ocean on Earth? (A) Atlantic (B) Indian (C) Pacific (D) Arctic", "a": "C"},
    {"q": "H2O is the formula for? (A) salt (B) water (C) acid (D) base", "a": "B"},
]


def _parse_choice(text):
    if not text:
        return None
    m = __import__("re").search(r"[A-D]", text.strip().upper())
    return m.group(0) if m else None


@pytest.fixture(scope="module")
def client():
    if not BASE_URL:
        pytest.skip("未设置 EVAL_API_BASE_URL，跳过能力评测（请配置 OpenAI 兼容端点）")
    if OpenAI is None:
        pytest.skip("未安装 openai 客户端（pip install openai）")
    return OpenAI(base_url=BASE_URL, api_key=API_KEY)


def test_capability_api(client):
    correct = 0
    details = []
    for item in DEMO_QUESTIONS:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": item["q"]}],
            temperature=0,
            max_tokens=16,
        )
        ans = resp.choices[0].message.content
        got = _parse_choice(ans)
        ok = got == item["a"]
        correct += int(ok)
        details.append(f"Q={item['q'][:34]}... | exp={item['a']} got={got} {'OK' if ok else 'X'}")
    acc = correct / len(DEMO_QUESTIONS)
    if STRICT:
        assert acc >= THRESHOLD, f"准确率 {acc:.2%} 低于门禁 {THRESHOLD:.0%}"
    else:
        assert acc >= 0.0  # 演示/摸底模式：仅验证可运行，不阻断


@pytest.mark.skipif(os.getenv("EVAL_USE_HARNESS") != "1",
                    reason="仅 EVAL_USE_HARNESS=1 时跑权威基准（需 lm_eval + HF 数据集访问）")
def test_capability_harness():
    try:
        import lm_eval  # noqa: F401
    except Exception as e:  # pragma: no cover
        pytest.skip(f"未安装 lm_eval: {e}")
    import glob
    import json
    import subprocess
    import sys

    tasks = [t for t in os.environ.get("EVAL_TASKS", "mmlu,cmmlu").split(",") if t]
    limit = os.environ.get("EVAL_LIMIT", "10")
    out_dir = "harness_out"
    cmd = [
        sys.executable, "-m", "lm_eval",
        "--model", "openai-chat-completions",
        "--model_args", f"base_url={BASE_URL},api_key={API_KEY or 'EMPTY'},model={MODEL}",
        "--tasks", ",".join(tasks),
        "--limit", limit,
        "--output_path", out_dir,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"harness 执行失败:\n{r.stderr[-2000:]}"
    files = glob.glob(os.path.join(out_dir, "*.json")) or glob.glob("outputs/**/*.json", recursive=True)
    assert files, "harness 未产出结果文件"
    with open(files[0], encoding="utf-8") as f:
        data = json.load(f)
    results = data.get("results", {})
    for task in tasks:
        acc = results.get(task, {}).get("acc_norm") or results.get(task, {}).get("acc")
        assert acc is not None, f"任务 {task} 未找到 acc/acc_norm"
        assert acc >= THRESHOLD, f"{task} 准确率 {acc:.4f} 低于门禁 {THRESHOLD}"
