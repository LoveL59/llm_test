# llm_test

大模型测试相关仓库，汇集评测 skill、实战手册与评估文档，供测试工程师快速上手大模型 / RAG / Agent 的功能、安全、鲁棒性与性能评测。

个人学习使用，仅供参考

## 仓库结构

```
llm_test/
├── skills/
│   └── llm-testing-qa/                 # WorkBuddy 评测 Skill（可直接复制到 ~/.workbuddy/skills/ 使用）
│       ├── SKILL.md                    # Skill 入口：测试点清单 + 高可信框架速查 + 引用纪律
│       ├── references/
│       │   ├── test_points.md          # 测试点全覆盖清单（能力/安全/鲁棒性/合规/训练过程等模块）
│       │   ├── verified_frameworks.md  # 已核实框架/数据集（含星标、版本、官方地址，禁止虚构）
│       │   └── executable_templates.md # 可直接执行的 pytest 用例模板（RAGAS v0.4 兼容）
│       └── scripts/                    # 可运行评测脚本（conftest + 4 类用例 + Locust 压测 + mock 服务）
└── docs/
    ├── 大模型测试工程师实战手册.md       # 单篇实战手册：从无到有的大模型测试知识（含 1.13 实战路线图）
    ├── 自动化测试高频面试题_pytest与playwright.md  # pytest + Playwright 自动化测试面试高频题（含 fixture/conftest 速查）
    ├── 测试岗_高频面试题.md              # 测试岗通用面试题：SQL / 网络(HTTP·HTTPS·WebSocket) / 综合实战场景
    └── 大模型评估/                      # 精简评估知识大纲
        ├── 大模型评估.md
        └── 图片和附件/                  # 文中引用的配图
```

## 阅读文档

- 想系统上手：读 `docs/大模型测试工程师实战手册.md`
- 想快速查评估框架/数据集：读 `skills/llm-testing-qa/references/verified_frameworks.md`
- 想了解精简评估知识：读 `docs/大模型评估/大模型评估.md`
- 想复习自动化测试（pytest / Playwright）面试：读 `docs/自动化测试高频面试题_pytest与playwright.md`
- 想复习测试岗通用面试题（SQL / 网络 / WebSocket / 综合实战场景）：读 `docs/测试岗_高频面试题.md`

## 引用纪律
所有框架 / 数据集 / arXiv 编号 / 星标均经联网核实，禁止虚构；版本相关 API（如 RAGAS v0.4）以 `verified_frameworks.md` 与 `executable_templates.md` 标注为准。
