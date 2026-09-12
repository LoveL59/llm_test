# 应用宝官网自动化测试（sj.qq.com）

基于 **pytest + Playwright** 的 Web UI 自动化测试框架，核心特性是**动态识别**：
被测页面 UI 文案/结构变化时，用例无需改动即可继续运行。

## 目录结构

```
sjqq_autotest/
├── conftest.py                 # pytest fixtures / 有头浏览器配置 / 失败截图 / 报告增强
├── pytest.ini                  # pytest 配置（收集规则、HTML 报告、重试、标记）
├── requirements.txt           # 依赖清单
├── config/
│   └── settings.py             # 全局配置 + 动态识别候选词库 + 有头/无头开关（改版时只改这里）
├── core/                       # ★ 可复用动态识别插件层（重复步骤沉淀于此）
│   ├── paths.py                # 路径常量（报告 / 证据 / 用例目录）
│   ├── case_reader.py          # 解析 cases.md（按 TC0X 切分，提取 S/G/Wn/T）
│   ├── dynamic_locators.py     # DynamicLocator：多候选 OR 定位引擎
│   ├── step_recorder.py        # ★ 步骤记录器：每步打印+截图+有效性校验，并写 steps.json
│   ├── diagnostics.py          # ★ 失败诊断：UI 元素失效 vs 接口失败（含网络监听、页面探针）
│   ├── step_executor.py        # ★ 自然语言 W 步骤→动作 的关键字解释器（数据驱动执行核心）；未命中时调用 nl_translator 翻译自由语言
│   ├── nl_translator.py          # ★ 自由自然语言→受控动作 翻译器（启发式+可选 LLM），业务大白话的核心
│   ├── report_builder.py       # ★ 生成内嵌截图的 Allure 风格报告（应用宝官网自动化测试报告.html）
│   └── pages/                  # 页面对象（BasePage / HomePage / SearchPage / AppDetailPage）
├── cases/                      # ★ 自然语言用例（S/G/W/T）
│   ├── cases_business.md       # ★ 业务/产品用「大白话」写的源文件（零关键字学习成本），agent 翻译后执行
│   └── cases.md               # 自动生成的规范用例（TC01~TC0x），pytest 真正读取执行；也接受直接写大白话
├── translate_cases.py          # ★ agent 翻译工具：cases_business.md（NL）→ cases.md（规范），并打印原文→译文
├── make_report.py              # 独立复生成报告（读取已有证据，无需重跑用例）
├── tests/                      # ★ 单一数据驱动入口（无需随用例增加）
│   └── test_cases_md.py       # 自动读取 cases.md 全部用例，逐条参数化执行（加用例只改 cases.md）
├── reports/                    # 测试报告(应用宝官网自动化测试报告.html) / 用例读取留痕(cases_loaded.log) / 逐步证据(evidence/<批次>/)
│   ├── 应用宝官网自动化测试报告.html             # ★ 优化报告：Allure 风格、内嵌每步截图、可点击放大（自包含单文件）
│   ├── results.json            # 本次用例结果（pass/fail/耗时），供独立复生成报告
│   └── evidence/<编号>/        # 每步证据：steps.log + steps.json + W1_*.png
└── (本框架即应用宝 Web 自动化测试技能 sjqq-web-autotest 的运行本体；用例/报告运行时生成)
```

## 环境准备（任意设备通用，不依赖任何特定安装路径）

本框架只需「系统 Python ≥ 3.10」+「本机已装 Google Chrome」。为隔离依赖，使用项目内 venv
（**不写死任何绝对路径**，换设备 / 换用户名直接复用下面命令即可）：

```bash
# 在项目根目录内创建隔离 venv（仅首次）
python -m venv venv

# 安装依赖（Playwright + pytest 全家桶）
#   Windows:
.\venv\Scripts\python -m pip install -r requirements.txt
#   macOS / Linux:
./venv/bin/python -m pip install -r requirements.txt

# 浏览器说明：本框架通过 channel="chrome" 复用本机已安装的 Google Chrome，
# 无需 `playwright install chromium`（部分网络环境 CDN 不可达）。
# 只需保证本机已装 Chrome 即可；路径不限，框架会自动用系统 Chrome 启动。
```

> 若本机未装 Chrome，也可改为 `playwright install chromium` 并去掉 conftest 里的 `channel="chrome"`。

## 运行测试（默认有头，逐步可见）

```bash
cd sjqq_autotest
# Windows 用 .\venv\Scripts\python；macOS / Linux 用 ./venv/bin/python
.\venv\Scripts\python -m pytest                       # 全部用例（默认打开可见 Chrome，可观看每一步）
.\venv\Scripts\python -m pytest -m smoke              # 只跑冒烟用例（所有用例默认带 smoke 标记）
SJQQ_HEADED=0 .\venv\Scripts\python -m pytest        # 无头模式（CI / 批量回归）
SJQQ_SLOWMO=1000 .\venv\Scripts\python -m pytest     # 调慢每步停顿，便于观看
```

### 业务改完用例后：翻译 → 执行

```bash
# 业务在 cases_business.md 用大白话改/加用例后，由 agent（或你）跑一次翻译：
.\venv\Scripts\python translate_cases.py     # cases_business.md（NL）→ cases.md（规范），并打出原文→译文
# 或直接把大白话写进 cases.md，跳过翻译，pytest 运行时自动识别：
.\venv\Scripts\python -m pytest             # 执行引擎会把自由语言步骤实时翻译成动作
```

> 用例数量由 `cases/cases.md` 决定：`tests/test_cases_md.py` 在收集阶段自动读取该文件，
> 每一条 TC0x 都会变成一个独立的测试节点。**新增用例只需在 cases.md 加一段，无需动代码。**
>
> 有头 / 无头由 `config/settings.py` 的 `HEADED`（或环境变量 `SJQQ_HEADED`）控制，
> 默认**有头**；`slow_mo` 默认 1000ms（每步 1 秒，便于观看），可用 `SJQQ_SLOWMO` 调整。

## 查看报告与逐步证据

- **优化报告 `reports/应用宝官网自动化测试报告.html`（推荐）**：参考 Allure 开源报告风格的自包含单文件。
  - 顶部汇总条（总数 / 通过 / 失败 / 总耗时）；
  - 每个用例一张卡片，左侧状态色条 + 状态徽章（通过/失败），点击卡片头部可折叠/展开；
  - 卡片内含 S 场景 / G 前提 / T 预期，以及**步骤时间线**：每步显示编号、中文描述、
    有效性徽章（✅有效 / ❌无效 / 未校验），并**内嵌该步的浏览器截图（base64，点击可放大）**；
  - 直接双击用浏览器打开即可，所有截图已内嵌，无需附带任何目录，可原样发给业务人员。
- **独立复生成报告**（无需重跑用例）：
  ```bash
  .\venv\Scripts\python make_report.py          # 读取已有 evidence + results.json 重新生成 应用宝官网自动化测试报告.html
  ```
- **逐步证据**（供人工逐条核验）：`reports/evidence/<批次>/<编号>/`
  - `steps.log`：可读的执行轨迹（S/G/W/T + 每步 ✅有效性校验）；
  - `steps.json`：结构化步骤数据（含截图文件名、有效性），供报告生成器读取；
  - `W1_*.png …`：每个 W 步骤的浏览器截图原文件；
  - `FAIL_<编号>.png`：该用例失败瞬间的全页截图（仅失败用例生成）。

## 环境清理与失败诊断

### 每次重跑自动清理（仅清日志/中间态，保留报告 + 截图）

框架在每次测试任务启动时（`clean_environment` session 级 fixture，最先执行）会清理上一轮的
日志与中间产物，确保环境不被污染：

- **清理**：`reports/cases_loaded.log`、`reports/results.json`、`reports/diagnosis.json`，
  以及各 `evidence/<批次>` 目录里的 `steps.log` / `steps.json`（中间态）。
- **保留**：`reports/应用宝官网自动化测试报告.html`（测试报告）与 `reports/evidence/<批次>/` 下的全部 PNG 截图。
  证据按**运行批次时间戳（YYYYMMDD_HHMMSS）**分目录隔离，天然实现「截图 + 日期」，
  历史批次互不干扰、不会污染。

### 用例失败自动诊断（UI 元素失效 vs 接口失败）

当某用例失败时，框架会自动做三层诊断并在报告中标记原因：

1. **网络/接口监听**：每个用例挂载 Playwright 网络监听，捕获失败的请求与 `HTTP>=400` 的
   接口/网络响应（已过滤静态资源、浏览器扩展、第三方 SDK 噪音），记录为「接口诊断」；
2. **UI 元素探针**：失败时探测关键 UI 元素（搜索框 / 搜索按钮 / 结果区 / 下载按钮等）是否
   *存在且可见*，输出一张元素状态表；
3. **结构化结论**：综合异常文案中的定位器线索，给出结论，例如
   「关键 UI 元素缺失，疑似页面改版/文案变更」「接口/网络异常，疑似后端或网关问题」等。

诊断结果同时写入报告失败区块（UI 状态表 + 接口异常列表 + 失败瞬间截图）和
`reports/diagnosis.json`（供独立复生成报告读取）。

## 自然语言用例（业务写大白话，agent 翻译执行）

用例以两个文件协作，把「维护成本」压到最低：

- **`cases/cases_business.md`（业务源文件）**：业务 / 产品人员用**纯中文大白话**写，
  **完全不用学任何关键字**。例：`在搜索框输入微信并回车`、`看看搜索框在不在`、
  `点开第一个结果进详情`、`切到手机大小375x667`。
- **`cases/cases.md`（pytest 真正读取的规范文件）**：由 agent 运行 `translate_cases.py`
  从业务源文件**自动翻译生成**，也可直接在其中写大白话（执行引擎会在运行时自动翻译）。

**两种工作方式，任选其一（都「只写中文」）：**

| 方式 | 谁翻译 | 流程 |
|------|------|------|
| A. agent 翻译（推荐） | agent / 具备 LLM 的环境 | 业务改 `cases_business.md` → agent 跑 `translate_cases.py` → 生成 `cases.md` → `pytest` |
| B. 运行时翻译 | 执行引擎（启发式，离线） | 直接在 `cases.md` 的 W 步骤里写大白话 → `pytest`（StepExecutor 自动翻译执行） |

方式 B 的开销最低：业务/你甚至可以把中文直接写进 `cases.md`，连翻译脚本都不用跑。
`core/nl_translator.py` 是唯一桥梁——把自由中文拆成「受控动作」；可选开启 LLM
（`SJQQ_NL_LLM=1` + `SJQQ_LLM_KEY`）可进一步提升长难句的翻译准确率，未配置时自动回退启发式。

**执行时序（先读用例，再按用例执行）**：
1. 测试启动（session 级 fixture）先读取 `cases/cases.md`，把全部用例的
   S/G/W/T 打印到控制台，并留存到 `reports/cases_loaded.log`；
2. `tests/test_cases_md.py` 在收集阶段就解析该文件，每一条 TC0x 自动变成一个独立的测试节点
   （用例增删只改源文件，脚本无需改动）；
3. 执行时，`core/step_executor.StepExecutor` 逐条处理每条 W 步骤：
   - 命中**受控关键字** → 直接翻译成 Playwright 动作；
   - 未命中 → 调用 `core/nl_translator.translate_step` 把**自由自然语言**翻译成动作，
     并在报告里打印「自由语言→ 规范动作」对照，确保过程透明；
   均复用 DynamicLocator 抗改版定位 + BasePage 动作 + settings.POOLS 候选词库；
4. 有头浏览器会逐步演示所有操作，且每个 W 步骤后都做有效性校验（✅有效 / ❌无效）
   并保存截图，确保你能看到「浏览器是否真的有效执行」。

> **维护人员只需改 `cases/cases_business.md`（或直接在 `cases.md`）这一个文件即可**，
> 完全不用写任何代码。若页面改版导致某元素定位失效，在 `config/settings.py` 的候选词库里
> 增删词即可，用例文本通常都不用动。

## 如何新增用例（维护指引：只写中文）

**你（非自动化人员）不需要写脚本、也不需要学关键字。** 两种做法：

**做法 1（推荐，最省心）：在 `cases/cases_business.md` 末尾加一段**
```markdown
## TC07 我想验证的新功能
场景：用大白话描述要验证什么
预期：期望达到什么结果
步骤：
1. 在搜索框输入微信并回车
2. 看看搜索框在不在
3. 点开第一个结果进详情
4. 下载按钮能看见吗
```
保存后让 agent 跑一次 `translate_cases.py`，新用例会自动进入 `cases.md` 并被 `pytest` 执行。

**做法 2（更快，免翻译脚本）：直接编辑 `cases/cases.md`**，把 W 步骤写成大白话即可，
执行引擎会在运行时自动翻译（报告里能看到「自由语言→ 规范动作」对照）。

常用中文说法（翻译器都认得，写法随意）：

| 你想做的操作 | 业务可写的自然语言示例 |
|------|------|
| 打开网站 | `打开应用宝官网` |
| 搜索 | `在搜索框输入微信并回车` / `搜一下微信` |
| 点击某文字 | `点一下软件` |
| 点击导航/分类 | `点击导航` / `点软件分类` |
| 点击搜索结果进详情 | `点开第一个结果进详情` |
| 等待元素/网址 | `等结果出现` / `等页面跳到 /search` |
| 检查元素可见 | `看看搜索框在不在` / `品牌logo可见吗` |
| 检查标题非空 | `看看页面标题是否正常` |
| 检查移动端无横滚 | `移动端有没有横向滚动` |
| 统计并断言结果数 | `数一下微信相关的有多少个结果` → `确认结果数量至少有1个` |
| 切换手机视口 | `切到手机大小375x667` |
| 只截图留痕 | `截图` |

元素引用（`搜索框`·`logo`·`导航`·`分类`·`内容区块`·`页脚`·`下载`·`结果`）均自动走
「多候选 OR」容错定位，所以页面文案小改也不易失效。

## 设计要点：为什么能抗 UI 变化

- **语义定位优先**：使用 `get_by_text` / `get_by_role` / `get_by_placeholder` /
  `get_by_alt_text`，而非脆弱的 CSS 路径。
- **多候选 OR**：同一语义目标给出一组等价候选（如搜索框 placeholder 历史上
  可能是多种文案），命中任一即可。
- **集中配置**：所有易变文案集中在 `config/settings.py`，改版只改一处。
