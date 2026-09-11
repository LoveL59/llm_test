# -*- coding: utf-8 -*-
"""
本地 Mock OpenAI 兼容服务（仅用于流水线演示，不评测真实能力）
============================================================
提供 /v1/chat/completions：
  - stream=false -> 返回单条 JSON（供 test_01 轻量请求模式）
  - stream=true  -> 返回 SSE 流式（供 locust 测 TTFT）
自问自答返回固定内容；演示报告中准确率/时延不代表真实模型表现。
真实评测请把 EVAL_API_BASE_URL / LOCUST_HOST 指向你的模型 API。
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("MOCK_PORT", "8080"))


def _safe_write(handler, data: bytes):
    """客户端可能提前断开（如 locust 取到首 token 即关闭），忽略断开异常。"""
    try:
        handler.wfile.write(data)
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


class Handler(BaseHTTPRequestHandler):
    def _answer(self, messages):
        # 演示用固定回复；test_01 的多选题预期答案多为 B，整体准确率约 66%（演示用）
        return "The answer is B. (demo) 这是本地 mock 模型生成的演示回复，用于验证评测流水线连通性。"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        stream = body.get("stream", False)
        content = self._answer(body.get("messages", []))
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            tokens = list(content)
            for i, t in enumerate(tokens):
                chunk = {"choices": [{"delta": {"content": t}, "index": 0}]}
                if i == len(tokens) - 1:
                    chunk["choices"][0]["delta"] = {}
                    chunk["choices"][0]["finish_reason"] = "stop"
                _safe_write(self, f"data: {json.dumps(chunk)}\n\n".encode())
                time.sleep(0.002)
            _safe_write(self, b"data: [DONE]\n\n")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _safe_write(self, json.dumps({
                "choices": [{"message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}],
                "model": body.get("model", "demo-model"),
            }).encode())

    def log_message(self, *a):  # 静默
        pass


if __name__ == "__main__":
    print(f"[mock] OpenAI-compatible server on http://127.0.0.1:{PORT}/v1/chat/completions")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
