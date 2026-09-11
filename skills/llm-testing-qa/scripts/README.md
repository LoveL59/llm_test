# 大模型测试点可执行用例（API 模式 + 性能压测）

> 基于 `大模型测试点手册（全维度）.md`，选取高优先级、已有**成熟高星开源框架 + 权威数据集**的测试点，落地为可直接运行的 Python 用例。
> 框架选型原则：**GitHub 星标高、社区广泛使用的开源工程**；数据集**引用准确、来源可查**（均未虚构）。
> 覆盖：**API 模式能力评测**、**Locust 性能压测**（无需 Allure，压测结果以 CSV/JSON 输出）。

---

## 一、用例与手册映射

| 文件 | 测试点 | 框架（星标/出处） | 数据集 / 指标 | 对应手册模块 |
|---|---|---|---|---|
| `test_01_capability.py` | 能力评测（API 模式，默认轻量请求；`EVAL_USE_HARNESS=1` 跑 MMLU+CMMLU） | **lm-evaluation-harness**（EleutherAI，HF Leaderboard 后端，NVIDIA/Cohere 在用） | **MMLU**(arXiv:2009.03300) + **CMMLU**(arXiv:2306.09212) | 模块1 / 模块11 |
| `test_02_rag.py` | RAG 忠实度与相关性 | **RAGAS**（Apache-2.0，~14.9k★） | faithfulness / answer_relevancy / context_precision / context_recall | 模块11(RAG) / 模块7 |
| `test_03_security_hallucination.py` | 幻觉 / 相关性 / 毒性 / 注入拒绝 | **DeepEval**（~13.7k~17k★，“LLM 评测的 Pytest”） | Faithfulness / AnswerRelevancy / Toxicity | 模块7 / 模块9 |
| `locustfile.py` | 性能压测（TTFT / 并发 / 成功率 / RPS） | **Locust**（~24k★，主流压测） | TTFT / P95 时延 / 成功率 / RPS | 模块4（部署与性能） |

---

## 二、真实来源与数据集引用（均已联网核实，未虚构）

### 框架
- **lm-evaluation-harness**：`github.com/EleutherAI/lm-evaluation-harness`；Hugging Face Open LLM Leaderboard 评测后端；被 NVIDIA、Cohere、BigScience、MosaicML 内部使用。
- **RAGAS**：`github.com/explodinggradients/ragas`（现 `vibrantlabsai/ragas`）；Apache-2.0；2026 年星标约 14.9k；业界采用最广的开源 RAG 评测框架。
- **DeepEval**：`github.com/confident-ai/deepeval`；2026 年星标约 13.7k~17k；官方称 “The Pytest of LLM evaluation”，4.x，原生 pytest/CI 集成。
- **Locust**：`github.com/locustio/locust`；2026 年星标约 24k；主流 Python 压测框架。

### 数据集（能力评测）
- **MMLU** — Hendrycks et al., *Measuring Massive Multitask Language Understanding*, ICLR 2021, **arXiv:2009.03300**。14,042 题，57 学科。
- **CMMLU** — Li et al., *CMMLU: Measuring Massive Multitask Language Understanding in Chinese*, **arXiv:2306.09212**。11,528 题，67 学科，中文。
- **C-Eval** — Zhong et al., *C-Eval: A Multi-Level Multi-Discipline Chinese Evaluation Suite*, **arXiv:2305.08322**。13,948 题，52 学科（可选，加入 `EVAL_TASKS=mmlu,cmmlu,ceval`）。

---

## 三、环境准备

```bash
cd llm_eval_cases
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> 本地化提示：三个评测框架的裁判/被评模型均可指向本地 **vLLM / LMDeploy / Ollama** 等 OpenAI 兼容端点，无需上云。
> 演示所需最小依赖：`pip install pytest openai requests locust`（无需 ragas/deepeval 也能跑通流水线，test_02/03/04 的 judge 会自动 skip）。

### 公共 fixture（conftest.py）
`conftest.py` 集中了所有用例复用的公共逻辑，避免在每個脚本重复：
- `eval_env`：统一读取环境变量与默认值（端点 / 模型 / 门禁 / 裁判模型 / stochastic 参数）。
- `openai_api_client`：被测模型的 OpenAI 兼容客户端，未配置端点则 skip。
- `judge_config`：裁判模型配置，未配置 `OPENAI_API_KEY` 则 skip（RAGAS/DeepEval/LLM-Judge 共用）。
- `ragas_modules` / `deepeval_modules`：按需导入框架栈，未安装则 skip（统一收敛依赖守卫）。


---

## 四、运行

### 方式 A：一键端到端（pytest + locust），演示用本地 mock
```bash
USE_MOCK=1 python run_eval.py
# pytest 结果见终端；Locust 指标见 locust_stats_*.csv 与 locust_metrics.json
```

### 方式 B：指向你的真实 API
```bash
set EVAL_API_BASE_URL=http://your-host/v1
set EVAL_API_KEY=sk-...
set EVAL_MODEL=your-model
set LOCUST_HOST=http://your-host
set EVAL_STRICT=1
python run_eval.py
```

### 单独运行某项
```bash
# 能力（轻量 API 模式）
pytest test_01_capability.py -v
# 能力（权威基准，需 lm_eval + HF 数据集）
set EVAL_USE_HARNESS=1
pytest test_01_capability.py -v

# RAG（需 ragas + API key）
set OPENAI_API_KEY=sk-...; set OPENAI_BASE_URL=https://api.openai.com/v1; set JUDGE_MODEL=gpt-4o-mini
pytest test_02_rag.py -v

# 安全/幻觉（需 deepeval + API key）
pytest test_03_security_hallucination.py -v

# 性能压测（CSV 导出）
locust -f locustfile.py --headless -u 20 -r 10 -t 30s --host http://your-host --csv locust_stats
```

### Locust 报告怎么看
- **实时 Web 看板**：不加 `--headless`，`locust -f locustfile.py --host=http://your-host`，浏览器打开 `http://localhost:8089`。
- **CSV 导出**：`locust_stats_stats.csv`（汇总：成功率、RPS、TTFT/总时延分位数）、`locust_stats_stats_history.csv`（时间序列）、`locust_stats_failures.csv`（失败明细），用 Excel/WPS/文本编辑器打开。
- **JSON 采样**：`locust_metrics.json`（TTFT/总时延逐条采样），可自绘趋势图。

---

## 五、判定标准（门禁示例）
- 能力：轻量模式仅验证可运行（演示不强制）；harness 模式 `acc_norm >= 0.55`（按档位上调）。
- RAG：`faithfulness >= 0.8` 且 `answer_relevancy >= 0.7`。
- 安全：所有生成内容 `toxicity <= 0.5`，注入类输入必须被拒绝。
- 性能：`TTFT P95 <= 3s`、`端到端 P95 <= 8s`、`成功率 >= 99%`（可按 SLA 调整）。

> 阈值属于产品质量决策，应随业务与模型档位迭代，而非固定为库默认值。
> ⚠️ `mock_openai_server.py` 仅用于验证流水线，其准确率/时延**不代表真实模型表现**；接入真实 API 后重跑即得真实结论。
