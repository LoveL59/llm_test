# -*- coding: utf-8 -*-
"""
端到端执行编排：pytest + locust（无 Allure 报告）
================================================
演示模式：USE_MOCK=1 自动起本地 OpenAI 兼容 mock 端点（mock_openai_server.py）。
真实模式：设置以下环境变量指向你的 API，不带 USE_MOCK 即可：
    EVAL_API_BASE_URL  http://your-host/v1
    EVAL_API_KEY       sk-...
    EVAL_MODEL         your-model
    LOCUST_HOST        http://your-host   （不含 /v1）
    EVAL_STRICT        1  (对能力准确率做硬门禁；0=只记录不阻断)

用法：
    USE_MOCK=1 python run_eval.py
    python run_eval.py        # 真实 API 模式
"""
import os
import sys
import time
import subprocess

# 复用当前解释器（即已安装 pytest/locust 的 venv python），避免路径风格问题
PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))


def _run(cmd, **kw):
    print(">>>", " ".join(cmd))
    return subprocess.run(cmd, cwd=HERE, **kw)


def main():
    mock = None
    if os.getenv("USE_MOCK") == "1":
        mock = subprocess.Popen([PY, "mock_openai_server.py"], cwd=HERE)
        time.sleep(1.5)
        os.environ.setdefault("EVAL_API_BASE_URL", "http://127.0.0.1:8080/v1")
        os.environ.setdefault("EVAL_API_KEY", "EMPTY")
        os.environ.setdefault("EVAL_MODEL", "demo-model")
        os.environ.setdefault("LOCUST_HOST", "http://127.0.0.1:8080")
        os.environ.setdefault("EVAL_STRICT", "0")  # 演示模式不强制准确率门禁

    try:
        _run([PY, "-m", "pytest", "-q"], check=False)
        _run([
            PY, "-m", "locust", "-f", "locustfile.py", "--headless",
            "-u", "10", "-r", "5", "-t", "20s", "--csv", "locust_stats",
            "--host", os.getenv("LOCUST_HOST", "http://127.0.0.1:8080"),
        ], check=False)
        print("[run_eval] 完成：pytest 结果见终端；"
              "Locust 指标见 locust_stats_*.csv 与 locust_metrics.json")
    finally:
        if mock:
            mock.terminate()


if __name__ == "__main__":
    main()
