# 可执行用例模板（API 用法 + 常见坑）

> 三个 pytest 文件在 `scripts/` 下，可直接 `pytest` 运行。被评/裁判模型均可指向本地 vLLM / LMDeploy / Ollama 等 OpenAI 兼容端点，无需上云。
> 本文件记录各框架的**正确当前 API** 与易错点，避免写出跑不起来的代码。
> **版本提示**：框架 API 与默认阈值会随版本变化（如 RAGAS v0.4 大改），写用例前先确认所用版本，再选对应 API。

---

## 用例 1：能力评测 — lm-evaluation-harness（`scripts/test_01_capability.py`）

正确用法：
```python
import lm_eval
results = lm_eval.simple_evaluate(
    model="hf",                      # 或 "local-completions" 评测私有端点
    model_args="pretrained=Qwen/Qwen2.5-7B-Instruct",
    tasks=["mmlu", "cmmlu"],         # 中文任务名：ceval / cmmlu
    num_fewshot=0,
    batch_size="auto",
)
acc = results["results"]["mmlu"]["acc_norm"]   # 优先 acc_norm，回退 acc
```

易错点：
- 中文任务名用 `ceval` / `cmmlu`；代号随版本变化，先 `lm-eval --tasks list` 核实，不要硬编码旧代号（如 `ceval-valid`）。
- 评测 OpenAI 兼容端点用 `model="local-completions"`，`model_args="base_url=...,model=..."`。
- 聚合任务返回 `acc` 与 `acc_norm` 两个键，取分前先判断存在性。
- 阈值（如 0.55）是能力准入门禁，按模型档位设定，不是库默认值。

---

## 用例 2：RAG 评测 — RAGAS（`scripts/test_02_rag.py`）

> ⚠️ **RAGAS 在 v0.4.0（2025-12）做了大改**：`evaluate()` 函数废弃（v1.0 移除），改用 `@experiment` 装饰器；`LangchainLLMWrapper` / `LlamaIndexLLMWrapper` 已移除，改用 `ragas.llms.base.llm_factory()`；指标从 `ragas.metrics` 迁到 `ragas.metrics.collections`；`SingleTurnSample.ground_truths`(list) 改为 `reference`(str)。下面给 **v0.4+ 写法**；v0.3- 才用 `from ragas import evaluate` + `LangchainLLMWrapper`（旧项目兼容见文末）。

正确用法（v0.4+，当前 2026）：
```python
import asyncio
from openai import AsyncOpenAI
from ragas.llms.base import llm_factory
from ragas.metrics.collections import (Faithfulness, AnswerRelevancy,
                                       ContextPrecision, ContextRecall)
from ragas.dataset_schema import SingleTurnSample

llm = llm_factory("gpt-4o-mini",
                 client=AsyncOpenAI(api_key=KEY, base_url=BASE))
metrics = [Faithfulness(llm=llm), AnswerRelevancy(llm=llm),
           ContextPrecision(llm=llm), ContextRecall(llm=llm)]

sample = SingleTurnSample(
    user_input="RAGAS 是什么？",
    response="RAGAS 是一个用于评测检索增强生成（RAG）系统的开源框架。",
    retrieved_contexts=["RAGAS（Retrieval-Augmented Generation Assessment）是用于评测 RAG 系统的开源框架。"],
    reference="RAGAS 是用于评测 RAG 系统的开源框架。",
)

async def _score(m, s):
    return await m.ascore(user_input=s.user_input, response=s.response,
                          retrieved_contexts=s.retrieved_contexts, reference=s.reference)

scores = asyncio.run(asyncio.gather(*[_score(m, sample) for m in metrics]))
# scores[i] 为各 MetricResult（含 .value / .reason）；断言 .value
assert scores[0].value >= 0.8   # faithfulness
```

> 数据集级评测（替代旧 `evaluate()`）：用 `@experiment` 装饰器 + `ExperimentDataset`，详见 RAGAS v0.4 文档。脚本 `test_02_rag.py` 内置版本检测，自动在 v0.4+ / v0.3- 两套 API 间切换，离线缺依赖时整体 skip。

易错点（避免写成跑不起来的旧代码）：
- **v0.4+ 不要再** `from ragas import evaluate` 或 `LangchainLLMWrapper`——前者废弃、后者已移除。统一用 `ragas.llms.base.llm_factory()` + `ragas.metrics.collections`。
- `SingleTurnSample` 仍在 `ragas.dataset_schema`，其 `ground_truths`(list) 在 v0.4 改为 `reference`(str)。
- `faithfulness` 为 reference-free（无需 ground truth 也能跑，用 `retrieved_contexts` 即可），生产流量也能跑；`context_precision/recall` 诊断检索，`answer_relevancy` 需 embeddings。
- 把真实 RAG 系统的线上样本（建议 50–100 条）替换 `SAMPLES`。

<details><summary>v0.3- 旧写法（仅旧项目兼容，新项目勿用）</summary>

```python
from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", temperature=0,
                                     openai_api_key=KEY, openai_api_base=BASE))
emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model="text-embedding-3-small",
                                                  openai_api_key=KEY, openai_api_base=BASE))
dataset = EvaluationDataset(samples=[SingleTurnSample(
    user_input="...", response="...", retrieved_contexts=["..."], reference="...")])
result = evaluate(dataset=dataset,
                  metrics=[Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall()],
                  llm=llm, embeddings=emb)
assert result.to_pandas()["faithfulness"].mean() >= 0.8
```
</details>

---

## 用例 3：安全 / 幻觉评测 — DeepEval（`scripts/test_03_security_hallucination.py`）

正确用法（4.1.x，当前 2026）：
```python
from deepeval import assert_test
from deepeval.metrics import (FaithfulnessMetric, AnswerRelevancyMetric,
                              HallucinationMetric, ToxicityMetric, GEval)
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

test_case = LLMTestCase(
    input="中国的首都是哪里？",
    actual_output="中国的首都是北京。",
    expected_output="北京",
    retrieval_context=["北京是中华人民共和国的首都。"],
)
assert_test(test_case, [
    FaithfulnessMetric(threshold=0.8),
    AnswerRelevancyMetric(threshold=0.7),
    ToxicityMetric(threshold=0.5),
])
```

Hallucination（对人工标注的可信基准，区别于 Faithfulness 的检索上下文）：
```python
hall_case = LLMTestCase(
    input="蓝牙开关在哪里？",
    actual_output="蓝牙开关位于 设置→蓝牙→关闭。",
    context=["蓝牙开关位于 设置→蓝牙→关闭。"],  # context 不是 retrieval_context
)
metric = HallucinationMetric(threshold=0.8)
metric.measure(hall_case)
assert metric.score >= 0.8
```

GEval（LLM-as-a-Judge，自定义 rubric 评判主观质量）：
```python
clarity = GEval(
    name="步骤清晰度",
    criteria="评估回答是否给出了清晰、可操作的操作指引。",
    evaluation_steps=[                   # 推荐写法：裁判按步打分，回归更稳定
        "检查回答是否包含具体操作路径",
        "检查操作路径是否与 context 一致",
        "评估语气是否专业、步骤是否简洁",
    ],
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT,
                       LLMTestCaseParams.CONTEXT],
    threshold=0.7,
)
assert_test(LLMTestCase(input="帮我关掉蓝牙",
                        actual_output="已关闭蓝牙。设置→蓝牙→关闭。",
                        context=["蓝牙开关位于 设置→蓝牙→关闭。"]),
            [clarity])
```

易错点：
- **4.x 统一语义**：5 个指标 score 全部越高越好，threshold 是最低通过线。**Hallucination score = 非幻觉比例（1=完全没幻觉），不是旧版的"越低越好"**。
- Faithfulness 对 `retrieval_context`（检索上下文，可能含噪），Hallucination 对 `context`（人工标注的可信基准）——面试常考区别。
- `assert_test` 必须配合**带 `threshold` 的 metric** 才会在不达标时失败；不带阈值的 metric 只打分不拦截。
- 最新版本 `assert_test` 在 0.21.0+ 行为有变化：保险写法是对关键指标单独 `metric.measure(test_case)` 后 `assert metric.score >= metric.threshold`。
- 默认裁判用 OpenAI；离线改本地 judge（Ollama 等）按其文档配置，不要硬编码 `OPENAI_API_KEY`。
- 阈值即质量决策：面向用户内容 faithfulness 建议 ≥ 0.8，不要沿用库默认 0.5。
- GEval `criteria` 跨次运行有 ±0.05 浮动；回归测试推荐用 `evaluation_steps` 列表，更稳定。
- 自定义裁判模型：继承 `DeepEvalBaseLLM`，指向任意 OpenAI 兼容端点（DeepSeek / Qwen / Ollama）。
- LLM-as-a-Judge 已知偏差：位置偏差（交换顺序跑两次）、长度偏差（criteria 加"简洁性"）、自我偏好（校准：抽 50 条人工打分算 Cohen's Kappa，<0.6 需调 rubric）。

---

## 工程规范：conftest.py 公共 fixture 模式

> 该模式已落地在 `scripts/conftest.py`，所有 test_*.py 复用同一份公共 fixture。新增用例**不要**在脚本里重复写环境变量读取与各框架 import 守卫。

### 为什么收敛到 conftest.py
- 每个 test_*.py 都需要的公共逻辑（读环境变量、建 OpenAI 客户端、各框架 import 守卫、裁判模型配置）不应重复书写，否则易漏改、易漂移。
- 集中到 conftest.py 后，用例脚本只 `def test_xxx(openai_api_client, eval_env):` 声明依赖即可，可读性与可维护性双升。
- 依赖守卫统一用 `try/except + pytest.skip`，缺包时整条 skip 而非 ERROR，回归套件**离线也能跑**（离线验证形态：`5 passed + 6 skipped`）。

### 提供的公共 fixture
| fixture | scope | 作用 | 未就绪时 |
|---|---|---|---|
| `eval_env` | session | 集中读取全部环境变量+默认值，返回 dict | — |
| `openai_api_client` | function | 被测模型 OpenAI 兼容客户端 | 未配端点 / 未装 `openai` → skip |
| `judge_config` | function | 裁判模型配置（复用 `eval_env`） | 未配 `OPENAI_API_KEY` → skip |
| `ragas_modules` | function | 懒导入 RAGAS 全栈，返回 `SimpleNamespace` | 未装 `ragas`/`langchain` → skip |
| `deepeval_modules` | function | 懒导入 DeepEval 全栈，返回 `SimpleNamespace` | 未装 `deepeval` → skip |

### 环境契约（由 `eval_env` 统一读取，单点维护）
- `EVAL_API_BASE_URL` / `EVAL_API_KEY` / `EVAL_MODEL`：被测端点（API 模式必填，端点含 `/v1`）
- `EVAL_USE_HARNESS=1`：走 lm-evaluation-harness 跑 MMLU+CMMLU
- `EVAL_ACC_THRESHOLD`（默认 0.5）/ `EVAL_STRICT`（默认 1，置 0 = 仅记录不阻断，用于摸底/演示）
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `JUDGE_MODEL`（默认 `gpt-4o-mini`）：裁判模型（RAGAS/DeepEval/LLM-Judge 共用）
- `AGENT_STOCHASTIC_N`（默认 5）/ `AGENT_PASS_RATE`（默认 0.8）：Agent 随机性通过率门禁

### 用法示例（test_02 只需声明依赖，本地 import 守卫已移除）
```python
def test_rag_faithfulness(ragas_modules, judge_config, eval_env):
    llm = ragas_modules.llm_factory(  # v0.4+：替代已移除的 LangchainLLMWrapper
        ragas_modules.ChatOpenAI(model=eval_env["judge_model"], temperature=0,
                                 openai_api_key=eval_env["openai_api_key"],
                                 openai_api_base=eval_env["openai_base_url"]))
    ...
```

### 核心纪律
- 环境变量**只在一处读取**（`eval_env`）；阈值/端点改动单点维护，避免脚本间漂移。
- 新增框架（如 promptfoo、Giskard、LLM-AS-Judge SDK）按同模式补充 fixture，不要在用例里散落 `import` 与 `os.getenv`。
- 被评模型与裁判模型分离：能力评测被评模型可用私有端点；RAGAS/DeepEval 的裁判模型另选强模型。

---

## 运行依赖（`scripts/requirements.txt`）
```
lm-eval-harness[api]>=0.4
ragas>=0.4          # 注意：v0.4+ API 已大改，模板已做版本兼容；不要降到 0.2/0.3 旧 API
langchain-openai
datasets
deepeval>=4.0
pytest
```

## 通用纪律
- 所有框架的 API 与默认阈值会随版本变化；写用例前先确认所用版本，再选对应 API（本文件以 2026 年主流版本为准，RAGAS 以 v0.4+ 为准）。
- 被评模型与裁判模型分离：能力评测的被评模型可用私有端点；RAGAS/DeepEval 的裁判模型可另选强模型。
- 样本必须用真实业务数据，避免使用与训练集重叠的公开题，防止评测失真。
