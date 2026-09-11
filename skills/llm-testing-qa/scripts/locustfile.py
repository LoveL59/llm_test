# -*- coding: utf-8 -*-
"""
Locust 性能压测：面向 OpenAI 兼容 /v1/chat/completions 端点
=========================================================
测量指标：
  - TTFT（Time To First Token，首 token 时延）
  - 端到端响应时延（total）
  - 请求成功率、吞吐 RPS、并发用户数

运行（由 run_eval.py 统一编排；也可单独执行）：
    locust -f locustfile.py --headless -u 20 -r 10 -t 30s \
           --host http://127.0.0.1:8080 --csv locust_stats
环境变量：LOCUST_HOST（默认 http://127.0.0.1:8080）、EVAL_MODEL、EVAL_API_KEY
压测结束后本文件会写出 locust_metrics.json（TTFT/总时延采样），供本地分析或 CSV 查看。
"""
import os
import time
import json
import random

from locust import HttpUser, task, between, events

HOST = os.getenv("LOCUST_HOST", "http://127.0.0.1:8080")
MODEL = os.getenv("EVAL_MODEL", "demo-model")
API_KEY = os.getenv("EVAL_API_KEY", "EMPTY")

PROMPTS = [
    "用一句话解释什么是 Retrieval-Augmented Generation。",
    "列举三种常见的模型量化方法并简述。",
    "把这句话翻译成英文：今天天气真好。",
    "给出一个 Python 快速排序的实现。",
    "什么是提示注入攻击？如何防御？",
]

TTFT_SAMPLES = []
TOTAL_SAMPLES = []


class LLMUser(HttpUser):
    wait_time = between(0.2, 1.0)
    host = HOST

    @task
    def chat_completion(self):
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": random.choice(PROMPTS)}],
            "stream": True,
            "max_tokens": 48,
            "temperature": 0.7,
        }
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        start = time.time()
        ttft = None
        with self.client.post(
            "/v1/chat/completions", json=payload, headers=headers,
            stream=True, name="chat/completions", catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                TOTAL_SAMPLES.append(time.time() - start)
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                if ttft is None:
                    ttft = time.time() - start
                    break
        if ttft is not None:
            TTFT_SAMPLES.append(ttft)
        TOTAL_SAMPLES.append(time.time() - start)


@events.test_stop.add_listener
def _on_stop(environment, **kwargs):
    data = {
        "ttft": TTFT_SAMPLES,
        "total": TOTAL_SAMPLES,
        "user_count": environment.runner.user_count if environment.runner else 0,
        "host": HOST,
        "model": MODEL,
    }
    with open("locust_metrics.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
