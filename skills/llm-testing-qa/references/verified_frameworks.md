# 高可信评测框架与数据集速查（已联网核实，禁止虚构）

> 用法：选型或写引用时，直接从本表复制"框架 + 数据集 + 准确引用"。星标与 arXiv 编号均来自联网检索结果，引用前如距上次核实超过数月，建议重新核实一次（社区数据会变）。  
> 选型优先级：GitHub 高星、社区广泛采用的开源工程。

---

## 一、能力评测（模型本身的知识与推理）

### 框架：lm-evaluation-harness（EleutherAI）

- 仓库：`github.com/EleutherAI/lm-evaluation-harness`
- 地位：Hugging Face Open LLM Leaderboard 的评测后端；被 NVIDIA、Cohere、BigScience、MosaicML 内部使用；数百篇论文引用。
- 能力：60+ 标准学术 Benchmark，支持 HF / vLLM / API 后端，公开 prompt 保证可复现。
- Python API：`lm_eval.simple_evaluate(model=..., tasks=[...], num_fewshot=...)`；CLI：`lm-eval --model hf --tasks mmlu,cmmlu`。

### 数据集（准确引用）

| 数据集        | 作者 / 会议                     | arXiv                | 规模               | 说明       |
| ---------- | --------------------------- | -------------------- | ---------------- | -------- |
| MMLU       | Hendrycks et al., ICLR 2021 | **arXiv:2009.03300** | 14,042 题 / 57 学科 | 英文综合知识广度 |
| CMMLU      | Li et al.                   | **arXiv:2306.09212** | 11,528 题 / 67 学科 | 中文多任务理解  |
| C-Eval     | Zhong et al. (清华/智谱)        | **arXiv:2305.08322** | 13,948 题 / 52 学科 | 中文多学科评测  |
| TruthfulQA | Lin et al., ACL 2022        | arXiv:2109.07958     | 817 题            | 真实性/抗谣言  |
| GSM8K      | Cobbe et al., ICLR 2021     | arXiv:2110.14168     | 8,500 题          | 小学数学推理   |

### 国内标准 / 榜单

- FlagEval（智源）、SuperCLUE（中文大模型榜单）、OpenCompass（上海AI实验室，Dataset/Model Hub + Evaluator + Analyzer），集成 70+ 数据集（约 40 万题）。
- 国标：GB/T 45288《人工智能 大模型》系列——GB/T 45288.1-2025（通用要求）、GB/T 45288.2-2025（评测指标与方法）、GB/T 45288.3-2025（服务能力成熟度评估），均 2025-01-24 发布实施。

---

## 二、RAG 评测（检索增强生成）

### 框架：RAGAS（explodinggradients/ragas，现 vibrantlabsai/ragas）

- 仓库：`github.com/explodinggradients/ragas`（canonical 现 `github.com/vibrantlabsai/ragas`，旧地址重定向）
- 许可：Apache-2.0；2026 年 GitHub 星标约 **1.1万**（经 GitHub API 核实约 11k，部分第三方聚合站报 1.5万+，取保守值）；业界采用最广的开源 RAG 评测框架。
- 指标：faithfulness（忠实度/幻觉检测）、answer_relevancy（答案相关性）、context_precision（上下文精度）、context_recall（上下文召回）。
- 支持 LLM-as-judge（OpenAI / Azure / 本地 Ollama 均可作裁判）。

> ⚠️ **RAGAS v0.4+ 版本大改（务必注意）**：v0.4.0（2025-12）起 `evaluate()` 函数已废弃（计划 v1.0 移除），改用 `@experiment` 装饰器；`LangchainLLMWrapper` / `LlamaIndexLLMWrapper` 已移除，改用 `ragas.llms.base.llm_factory()`（按模型名自动推断 provider）；指标模块从 `ragas.metrics` 迁到 `ragas.metrics.collections`；`SingleTurnSample` 的 `ground_truths`(list) 改为 `reference`(str)。**v0.3- 才用 `from ragas import evaluate` + `LangchainLLMWrapper`**，新项目请以 v0.4+ 为准。模板 `scripts/test_02_rag.py` 已做版本兼容。

### 数据集 / 关联

- MTEB / CMTEB（嵌入与检索评测）、RAGEval（中文 RAG 评测集）。
- RAGAS 可自动从文档库生成测试集，降低冷启动成本。

---

## 三、单测 / 安全 / 幻觉（LLM 应用质量门禁）

### 框架：DeepEval（confident-ai/deepeval）

- 仓库：`github.com/confident-ai/deepeval`
- 2026 年 GitHub 星标约 **17k–18k**（2026-09 核实）；官方称 "The Pytest of LLM evaluation"；4.1.x，50+ 指标，原生 pytest / CI 集成。
- 运行：`deepeval test run test_xxx.py` 或 `pytest test_xxx.py -v`。

#### 五指标详解（4.x 统一语义）

> ⚠️ **4.x 统一语义（核心防坑）**：这 5 个指标的 `score` 全部落在 `[0,1]`，**全部是「越高越好」**，`threshold` 是**最低通过线**（score ≥ threshold → PASS）。第三方旧教程说 Hallucination/Toxicity"越低越好"是 **v0/v1 过时写法**，4.x 已翻转为"非幻觉比例/非毒性比例"。

| 指标                  | 测什么                             | 算法直觉                                                            | 必填字段                                                                  | 阈值建议                  |
| ------------------- | ------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------- | --------------------- |
| **Faithfulness**    | 答案是否贴合检索上下文，有没有加戏/矛盾            | LLM 拆 claim → 逐条判能否从 retrieval_context 推出；score=不矛盾claim/总claim | actual_output + retrieval_context                                     | RAG ≥ 0.7；安全敏感 ≥ 0.85 |
| **AnswerRelevancy** | 答案有没有答对问题（不要求正确，只要求贴题）          | LLM 由 actual_output 反推"会问什么问题"，算与 input 的语义相似度                  | input + actual_output                                                 | ≥ 0.7                 |
| **Hallucination**   | 答案是否与你信任的 ground-truth 上下文矛盾/编造 | score=与 context 一致的比例（1=完全没幻觉）                                  | input + actual_output + **context**（注意是 context 不是 retrieval_context） | 不可逆操作场景 ≥ 0.9         |
| **Toxicity**        | 输出是否含人身攻击/嘲讽/仇恨/威胁              | LLM 抽"观点"→逐条判 toxic；score=非毒性观点/总观点                             | input + actual_output                                                 | ≥ 0.8                 |
| **GEval**           | 上面四个覆盖不到的主观质量                   | LLM-as-a-Judge + Chain-of-Thought 填表式打分（G-Eval 原论文方法）           | 由 evaluation_params 指定                                                | 按业务定                  |



#### Faithfulness vs Hallucination 的区别（面试常考）

- **Faithfulness** 对**检索上下文**（`retrieval_context`，可能含噪，测生成器也顺带测检索器）
- **Hallucination** 对**你人工标注的可信基准**（`context`，只测生成器）
- 线上 RAG 用 Faithfulness，离线基准校验用 Hallucination

#### GEval LLM-as-a-Judge 机制

- **criteria 字符串**：快，但每次略有浮动（±0.05）
- **evaluation_steps 列表**：裁判按步打分，**跨次运行更稳定**，回归测试推荐
- 支持自定义裁判模型：继承 `DeepEvalBaseLLM`，指向任意 OpenAI 兼容端点（DeepSeek / 本地 Qwen / Ollama 等）
- 已知偏差：位置偏差（交换顺序跑两次）、长度偏差（criteria 加"简洁性"）、自我偏好（校准：抽 50 条人工打分算 Cohen's Kappa，<0.6 需调 rubric）

### 框架：garak（NVIDIA）

- 仓库：`github.com/NVIDIA/garak`
- 星标约 **8.5k**；LLM 漏洞扫描器，100+ 攻击探针（Prompt 注入、数据泄露、Jailbreak、后门等）。

### 框架：promptfoo

- 仓库：`github.com/promptfoo/promptfoo`
- 星标约 **11.3k**（2026-03 OpenAI 收购时公开报道约 11.3k–11.6k；星标会变化，引用前重核）；开发者优先的 Prompt/模型对比与红队工具，含注入 / PII 泄漏探针；pytest 式测试与 A/B。**2026-03 被 OpenAI 宣布收购，开源核心仍 MIT（收购待交割）**。

### 数据集（幻觉/真实性）

- HaluEval（arXiv:2305.11747）、TruthfulQA（arXiv:2109.07958）、FactScore（arXiv:2305.14251）。

---

## 四、Agent / 工具调用评测

### 评测框架（Agent Eval 落地工具）

#### Microsoft AgentEval（AutoGen 团队，2023）

- 仓库 / 出处：`autogen.blog/2023/11/20/AgentEval`（GitHub: microsoft/AG2 或 autogenai/autogen 生态）
- 定位：面向**多 Agent 任务效用评估**的开源框架，把"Agent 是否把任务做对了"拆成可断言的评估。
- 三智能体结构：**Critic**（识别失败点）→ **Quantifier**（量化任务效用/错误严重度）→ **Verifier**（验证修复建议），输出任务级效用分数。
- 适用：对 Agent 终态答案做"任务完成度"分级评估（落地到本 skill 即 test_04 的 LLM-Judge 思路）。

#### AgentEvalHQ / AgentEval（.NET 生态，2025–2026）

- 仓库：`github.com/AgentEvalHQ/AgentEval`
- 定位：开发者优先的 Agent 评估框架，强调**可复现 + 行为护栏 + 随机化评估**。
- 关键能力：**StochasticRunner**（同一用例 run×N 算通过率，化解非确定性）、**ModelComparer**（多模型横向对比）、**行为护栏**（内置 PCI-DSS / GDPR 合规行为断言，一等公民支持）。
- 适用：直接对应本 skill test_04 的"stochastic 包装 + 安全/合规护栏"打法。

### 评测基准 / 数据集（能力基线）

| 框架/数据集              | 仓库                           | 引用                               | 说明                                  |
| ------------------- | ---------------------------- | -------------------------------- | ----------------------------------- |
| AgentBench          | THUDM/AgentBench             | **arXiv:2308.03688** (ICLR 2024) | 8 环境多步 Agent 能力（OS/DB/Web/游戏等）      |
| GAIA                | github.com/.../gaia          | **arXiv:2311.12983**             | 466 道真实世界推理问答；人类 ~92% vs GPT-4 ~15% |
| τ-bench (tau-bench) | arXiv:2406.12045 (ICLR 2025) | 工具调用 + 用户模拟，pass^k 衡量稳定性         |                                     |
| BFCL                | gorilla.cs.berkeley.edu      | Berkeley 函数调用榜（v4, ICML 2025）    | 抽象/多轮/并行/错误恢复的函数调用准确性               |
| OSWorld / SWE-bench | —                            | GUI / 代码 Agent 基准                |                                     |

#### AgentBench 方法论——如何参照设计 Agent 评测用例

> AgentBench 的价值不在直接跑它的 8 个学术环境，而在**参照其任务设计模式与失败分类**来构造你自己的 Agent 评测用例。

**POMDP 任务结构**（每个任务定义 5 要素）：

```yaml
task_id: "agent_001"
instruction: "用户原始指令"          # 自然语言
initial_state: {...}                # 初始环境状态
target_state: {...}                 # 期望终态（参照 τ-bench）
policy: [...]                       # 策略约束（参照 τ-bench）
max_steps: 15                       # 死循环防护
```

**AgentBench 失败分类（10 类→对 Marvis 有用的 6 类）**：

| AgentBench 失败类                | 对应你的 Agent 场景    | 链路环节         |
| ----------------------------- | ---------------- | ------------ |
| Invalid Action                | 工具调用参数错误         | Agent 执行层    |
| Context Limit Exceeded        | 上下文溢出            | Router 上下文管理 |
| Invalid Format                | 输出格式不符合协议        | Agent 输出解析   |
| Task Limit Exceeded           | 死循环/max_steps 触发 | 防护机制         |
| Long-term Reasoning Failure   | 多步推理偏离（第3步开始跑偏）  | Agent 规划能力   |
| Instruction Following Failure | 未遵循用户意图          | Router 理解层   |

**τ-bench pass^k 可靠性指标**：

- 同一任务跑 k 次，**全部成功才算通过**——面向用户的系统，偶尔成功≠可靠
- `pass_k(results, k) = min(1, (c-k+1)/n)`，其中 c=成功次数，n=总次数
- 对比：pass^1=0.80（单次还行），pass^5=0.0（5次全过=0，不可靠）

**三类核心链路用例**：

| 类型      | 设计思路                           | 示例                          |
| ------- | ------------------------------ | --------------------------- |
| 任务拆解验证  | 单指令需拆给多 Agent，验证 Router 拆得对不对  | "关蓝牙+截图发微信"→Win Use+App Use |
| 上下文传递验证 | 前 Agent 输出→后 Agent 输入，验证中间结果没丢 | 截图路径跨 Agent 传递是否一致          |
| 降级兜底验证  | 某子 Agent 失败，验证系统 fallback      | 微信发图失败应返回原因，非无限重试           |

---

## 五、鲁棒性 / 公平性 / 多模态（补充）

- 鲁棒性：PromptBench（Microsoft，arXiv:2306.04528，字符→语义四级攻击）。
- 公平性：StereoSet（arXiv:2004.09456）、BOLD、BBQ（arXiv:2110.08193）、WinoBias、DiscrimEval、GenderCARE、TrustLLM（arXiv:2401.05561，ICML 2024）。
- 多模态：MMBench（arXiv:2307.06281）、VLMEvalKit。
- 长上下文：LongBench（arXiv:2308.09982）。
- 指令遵循：IFEval（arXiv:2308.03495，HELM 内置）。
- 安全基准：TrustLLM（ICML 2024）+ JailbreakBench（arXiv:2404.01318，NeurIPS 2024）。

---

## 六、训练 / 部署 / 评测全链路

### 框架：evalscope（ModelScope 魔搭社区官方）

- 仓库：`github.com/modelscope/evalscope`（旧包名 `llmuses`，v0.4.3 起重命名为 evalscope）
- 定位：魔搭社区官方出品的"评测 + 性能压测"一体化框架；支持 LLM / VLM / Embedding / Reranker / CLIP。
- 后端：Native（默认）、OpenCompass、VLMEvalKit、RAGEval（RAGAS 端到端）、ThirdParty（ToolBench）；性能压测模块可测 TTFT / 吞吐 / 并发。
- 亮点：与 ms-swift 训练框架打通，训练→评测全链路；内置 MMLU/CMMLU/C-Eval/GSM8K 等基准。

### 框架：LLaMA-Factory（hiyouga）

- 仓库：`github.com/hiyouga/LLaMA-Factory`
- 星标约 **7.4万**（2026-09 核实）；ACL 2024（Zheng et al.）；Apache-2.0。
- 定位：零代码 / 低代码高效微调平台，覆盖 100+ LLM/VLM、SFT/DPO/PPO/KTO/ORPO 全训练方法、LoRA/QLoRA 量化微调。
- 训练可测性：LlamaBoard/TensorBoard/Wandb/MLflow/SwanLab 实时监控 Loss/资源；支持保留集回测以发现灾难性遗忘——是"训练过程测试"的落地载体。

### 训练过程测试关联方法

- 数据污染：Min-K% Prob（arXiv:2310.16789）。
- 灾难性遗忘：I-LoRA（arXiv:2402.18865，旧任务保留集回测）。
- 分布偏离：KS 检验（Kolmogorov–Smirnov）、卡方检验（Chi-square）比对训练/验证集特征分布。

---

## 引用纪律（强制）

- 任何框架星标、arXiv 编号、数据集规模、论文题目，如非本次会话已核实，必须先 WebSearch / WebFetch 核实再写入。
- 不要写"业界最流行""广泛使用"等无出处判断；给出仓库与星标（含核实时间）。
- 数据集引用统一格式：`作者, 题目, 会议/年份, arXiv:xxxx.xxxxx`。
- 框架 API 与默认阈值会随版本变化（如 RAGAS v0.4 大改），写用例前先确认所用版本，再选对应 API。
