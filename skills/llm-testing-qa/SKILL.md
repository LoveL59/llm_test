---
name: llm-testing-qa
description: 为大模型 / RAG / Agent / AI 应用做功能测试时，提供"测试点全覆盖清单 + 高可信评测框架与数据集（含准确引用）+ 可直接执行的 pytest 用例模板"，确保评测不遗漏维度、不引用错误/虚构来源。当用户要梳理大模型测试点、选型评测框架或数据集、编写 LLM 测试用例、或做测试方案评审时使用。
agent_created: true
---

# 大模型测试 QA 指南

本技能服务于大模型 / AI 应用 / Agent 的功能测试工程师。目标：在评测任务中**测试点无遗漏**、**引用来源真实准确（不虚构）**。

## 何时使用
- 梳理大模型 / Agent / AI 应用的测试点、测试方案或测试用例
- 选型评测框架（能力 / RAG / 安全 / 幻觉）
- 引用或推荐 Benchmark 数据集、开源工具
- 编写可执行的 LLM 评测用例（pytest）
- 评审测试覆盖是否完整

## 核心原则（防遗漏 + 防错误）
1. **全维度覆盖**：任何评测任务先对照 `references/test_points.md` 的 11 模块逐条勾选，禁止只测功能 / 性能。
2. **来源必须真实可查**：推荐框架 / 数据集前，必须联网核实 GitHub 星标、论文 arXiv 编号、官方仓库；**禁止凭记忆编造星标数、论文编号、数据集规模或题目**。
3. **框架选型优先级**：优先选用 GitHub 高星、社区广泛采用的开源工程（见 `references/verified_frameworks.md`）。
4. **数据集准确引用**：引用数据集时附作者 / 会议 / arXiv 编号与题目，不要只写名字。
5. **阈值即质量决策**：判定阈值按模型档位与业务设定，不能照搬库默认值。
6. **框架 API 会随版本大改**：写代码前先确认所用版本（见 `references/executable_templates.md`）。例如 **RAGAS 在 v0.4.0（2025-12）废弃 `evaluate()` 与 `LangchainLLMWrapper`**，新项目必须以 v0.4+ 为准。

## 测试点清单（11 模块，逐条勾选；详细版见 `references/test_points.md`）
1. 评测数据集与离线能力评测：MMLU / C-Eval / CMMLU / FlagEval / SuperCLUE / OpenCompass / HELM
2. 数据质量与公平性：一致性 / 有效性 / 公平性（StereoSet / BOLD / BBQ / WinoBias / TrustLLM）
3. 鲁棒性 · 泛化 · 时效性：PromptBench / FreshQA / GLUE-X
4. Agent 专项：规划 / 死循环 / 短期记忆 / 记忆污染 / 越权 / 不可逆操作（AgentBench / GAIA / τ-bench / BFCL）
5. 功能 Checklist：Prompt 理解 / 参数边界 / 上下文 / 角色 / 异常输入 / 输出质量
6. 性能分层：TTFT / TPOT / Token·s / 并发 / 长上下文 / 稳定性 / 会话串扰
7. 安全三层：应用层（注入 / Jailbreak）/ 数据层（泄露 / 向量库攻击）/ 模型层（窃取 / 对抗 / 后门）；垂直 / 水平 / 功能越权
8. Prompt 工程与回归：有效性 / 一致性 / 鲁棒性 / 安全性（Promptfoo）
9. 合规：歧视性输出 / 隐私 / 不当建议 / 输出溯源 / 全球化合规（GDPR / GB-T 45288 / NIST AI RMF）
10. 部署 · 训练 · 业务：vLLM / LMDeploy / 数据污染 Min-K% / 过拟合 / 灰度 / 影子部署（训练过程测试见 `references/test_points.md` 模块 10 深化）
11. 原缺失标配维度：多模态（MMBench / VLMEvalKit）、Agent/工具（GAIA / OSWorld / SWE-bench）、长上下文（LongBench）、RAG（RAGAS）、幻觉（HaluEval / TruthfulQA）、指令遵循（IFEval）

## 高可信框架速查（含准确引用与星标；详细版见 `references/verified_frameworks.md`）
- **能力评测**：`EleutherAI/lm-evaluation-harness`（HF Open LLM Leaderboard 后端，NVIDIA/Cohere/BigScience 在用）→ MMLU(arXiv:2009.03300) + CMMLU(arXiv:2306.09212) + C-Eval(arXiv:2305.08322)
- **RAG 评测**：`explodinggradients/ragas`（canonical 现 `vibrantlabsai/ragas`，~1.1万★，最主流 RAG 评测）→ faithfulness / answer_relevancy / context_precision / context_recall。**注意 v0.4+ API 大改**
- **单测 / 安全 / 幻觉**：`confident-ai/deepeval`（~17k–18k★，"LLM 评测的 Pytest"，4.1.x）→ Faithfulness / AnswerRelevancy / Toxicity / Bias
- **红队 / 安全扫描**：`NVIDIA/garak`（~8.5k★，100+ 攻击探针）
- **Prompt / 模型对比**：`promptfoo/promptfoo`（~11.3k★，2026-03 被 OpenAI 收购、开源核心仍 MIT；含注入 / PII 红队探针）
- **Agent Eval（轨迹评估）**：`microsoft/AutoGen` 的 AgentEval（autogen.blog/2023/11/20/AgentEval，Critic/Quantifier/Verifier 三智能体任务效用评估）；`AgentEvalHQ/AgentEval`（github.com/AgentEvalHQ/AgentEval，StochasticRunner 随机化评估 + 行为护栏）。能力基线基准：AgentBench(arXiv:2308.03688, ICLR 2024) / GAIA(arXiv:2311.12983) / τ-bench(arXiv:2406.12045, ICLR 2025) / BFCL(Berkeley Gorilla 函数调用榜，v4, ICML 2025)
- **评测 + 压测全链路**：`modelscope/evalscope`（魔搭社区官方，评测 + 性能压测一体化；后端含 Native/OpenCompass/VLMEvalKit/RAGAS，与 ms-swift 训练打通，训练→评测全链路）
- **训练 / 微调平台**：`hiyouga/LLaMA-Factory`（~7.4万★，ACL 2024，零代码覆盖 SFT/DPO/PPO/KTO/ORPO，LlamaBoard/TensorBoard/MLflow 实时监控 Loss/资源，支持保留集回测查灾难性遗忘）

## 可执行用例与一键报告
`scripts/` 下为可直接运行的评测工程（`pip install -r scripts/requirements.txt`；ragas/deepeval 可选，缺依赖时对应用例自动 skip）：
- `conftest.py` — **全局公共 fixture**（必带）：`eval_env`（环境变量集中读取）、`openai_api_client`（被测端客户端）、`judge_config`（裁判配置）、`ragas_modules` / `deepeval_modules`（依赖守卫）。避免各脚本重复公共逻辑。
- `test_01_capability.py` — 能力评测，**API 模式**：默认轻量请求验证连通性/准确率；`EVAL_USE_HARNESS=1` 走 lm-evaluation-harness 跑 MMLU+CMMLU
- `test_02_rag.py` — RAGAS 忠实度与相关性（**已做 RAGAS v0.4 版本兼容**）
- `test_03_security_hallucination.py` — DeepEval 幻觉 / 毒性 / 注入拒绝
- `test_04_agent_trajectory.py` — Agent 轨迹评测：轨迹断言（工具名/参数/顺序/终态/无死循环）+ stochastic run×N 通过率门禁 + LLM-Judge 慢测（标记 `llm_judged`，复用 DeepEval GEval）
- `locustfile.py` — Locust 性能压测（TTFT / 并发 / 成功率 / RPS），结果导出 CSV + `locust_metrics.json`
- `run_eval.py` — 一键编排 pytest + locust（无 Allure），`USE_MOCK=1` 起本地 mock
- `mock_openai_server.py` — 本地 OpenAI 兼容 mock，仅用于离线验证流水线（演示，不代表真实模型）
API 用法与常见坑见 `references/executable_templates.md`。

## 工作流
1. 收口范围：明确被测对象是模型本身 / RAG 应用 / Agent / 通用 AI 应用。
2. 对照清单：打开 `references/test_points.md`，按 11 模块勾选本次需覆盖的测试点。
3. 选型与引用：从 `references/verified_frameworks.md` 选框架 + 数据集，复制经过核实的引用。
4. 落地用例：基于 `scripts/` 模板改写，替换样本为真实线上数据（建议 50–100 条）。
5. 复核：逐项确认无遗漏维度、无虚构引用、阈值合理。

## 常见错误（避免）
- 误用已废弃的 RAGAS `RAGAS()` 类 / `evaluate_retrieval()`（0.2+ 已移除），更要注意 **v0.4+ 已废弃 `evaluate()` 与 `LangchainLLMWrapper`**，应改用 `@experiment` + `ragas.llms.base.llm_factory()`。
- DeepEval `assert_test` 必须配合带 `threshold` 的 metric 才会在不达标时失败。
- lm-evaluation-harness 中文任务名用 `ceval` / `cmmlu`（代号随版本变化，先 `lm-eval --tasks list` 核实）。
- 把库默认阈值当作质量要求（如 faithfulness 默认 0.5 偏低，面向用户内容建议 ≥ 0.8）。
- 凭印象报框架星标或论文编号——必须先联网核实再写入。
