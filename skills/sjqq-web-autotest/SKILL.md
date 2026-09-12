---
name: sjqq-web-autotest
description: 应用宝官网(sj.qq.com) Web UI 自动化测试框架模板（pytest + Playwright + 动态识别）。当需要对应用宝或同类"UI 元素易变"的网页做自动化测试、生成 pytest 用例与 HTML 报告、或把动态识别方案复用到其它站点时使用。触发词：应用宝自动化、sj.qq.com 测试、网页 UI 自动化、Playwright 动态识别、pytest 网页用例、抗改版测试。
---

# 应用宝官网 Web 自动化测试（动态识别版）

面向"页面 UI 文案/结构可能变化"的网站，用 **pytest + Playwright + 动态识别** 做 Web UI 自动化。
业务人员只写中文用例（大白话即可），框架自动翻译执行；agent 按本文件步骤即可运行与维护。

## 何时使用

- 对 `https://sj.qq.com/` 做冒烟/回归测试。
- 业务/产品想快速新增、运行、查看 Web 用例报告。
- 需要"抗改版"网页自动化范式复用到其它站点。

## 一、落地（首次 / 换设备）

1. 把本 skill 内 `assets/sjqq_autotest/` 整个目录复制到工作目录；
2. 在该目录内建 venv 并装依赖：
   ```bash
   cd sjqq_autotest
   python -m venv venv
   ./venv/Scripts/python -m pip install -r requirements.txt
   ```
3. 本机装 Google Chrome（框架用 `channel="chrome"` 自动调用系统 Chrome，无需下载 Chromium）；
4. `./venv/Scripts/python -m pytest` 即可运行（默认**有头**，逐步可见）。

## 二、目录结构（可复用插件层）

```
sjqq_autotest/
├── conftest.py            # fixtures / 有头浏览器(channel=chrome)+slow_mo / 失败诊断+截图 / 结果&执行模式收集
├── pytest.ini             # 收集规则 + 重试 + 标记（报告由 report_builder 自研生成，无 pytest-html）
├── requirements.txt       # 仅 playwright / pytest / pytest-playwright / pytest-rerunfailures
├── config/settings.py     # ★ 全局配置 + 动态识别候选词库 + BASE_URL/RANKING_URL + 有头/无头开关
├── core/                  # ★ 可复用插件层
│   ├── paths.py           # 路径常量（报告/证据/用例文件/运行批次）
│   ├── case_reader.py     # ★ 解析 cases.md（按 TC0X 切分，提取 S/G/Wn/T）
│   ├── dynamic_locators.py# DynamicLocator：多候选 OR 定位引擎
│   ├── step_recorder.py   # ★ 步骤记录器：每步打印+截图+有效性校验，并写 steps.json
│   ├── diagnostics.py     # ★ 失败诊断：UI 元素失效 vs 接口失败（网络监听+页面探针+结论）
│   ├── step_executor.py   # ★ W 步骤→动作 解释器：受控关键字优先，未命中调用 nl_translator 翻译
│   ├── nl_translator.py    # ★ 自由自然语言→受控动作 翻译器（启发式+可选 LLM）
│   ├── report_builder.py  # ★ 生成内嵌截图的 Allure 风格报告（应用宝官网自动化测试报告.html）
│   └── pages/             # BasePage / HomePage / SearchPage / AppDetailPage
├── cases/                 # ★ 自然语言用例（业务大白话 + 规范）
│   ├── cases_business.md  # ★ 业务/产品用「大白话」写的源文件（零关键字学习），agent 翻译后执行
│   └── cases.md           # 自动生成的规范用例（TC01~TC0x），pytest 读取执行；也接受直接写大白话
├── translate_cases.py      # ★ agent 翻译工具：cases_business.md（NL）→ cases.md（规范），打印原文→译文
├── make_report.py         # 独立复生成报告（读取已有证据，无需重跑用例）
├── tests/                 # ★ 单一数据驱动入口（无需随用例增加）
│   └── test_cases_md.py   # 自动读取 cases.md 全部用例，逐条参数化执行（加用例只改 cases.md）
└── reports/
    ├── 应用宝官网自动化测试报告.html        # ★ 唯一报告：Allure 风格、内嵌每步截图、默认展开、可点击放大（自包含单文件）
├── results.json        # 本次用例结果（pass/fail/耗时）；其内 `__meta__.headed` 为执行模式权威来源
├── run_meta.json       # 运行元数据兜底（含 headed 有头/无头），曾被独立进程覆盖导致失真，现以 results.json.__meta__ 为准
    ├── cases_loaded.log    # 执行前读取到的用例摘要（先读用例留痕）
    ├── diagnosis.json      # 失败诊断结论，供独立复生成报告读取
    └── evidence/<批次>/<编号>/  # 每步证据：steps.log + steps.json + W1_*.png + FAIL_<编号>.png
```

> 报告**只有 `应用宝官网自动化测试报告.html` 一份**（早期的 pytest-html 传统报告 `pytest_应用宝官网自动化测试报告.html` 已移除，不再生成）。

## 三、运行与报告（默认有头 + 每步间隔，逐步可见）

```bash
cd sjqq_autotest
./venv/Scripts/python -m pytest                              # 全部用例（默认有头，每步间隔 1s，可观看）
./venv/Scripts/python -m pytest -m smoke                    # 仅冒烟用例

# 环境变量（不改代码即可临时切换）
SJQQ_HEADED=0    ./venv/Scripts/python -m pytest            # 无头：CI / 批量回归
SJQQ_SLOWMO=300  ./venv/Scripts/python -m pytest            # 加速观看（默认 1000ms = 1s）
SJQQ_SLOWMO=0    ./venv/Scripts/python -m pytest            # 关闭停顿（最快）
```

- 用例数量由 `cases/cases.md` 决定：每条 `## TC0X` 自动变成独立 pytest 节点，加用例只改 md 不碰代码。
- **执行模式标注自洽（权威来源 = results.json.__meta__）**：`conftest.py` 在 pytest 跑完时，把当时的
  `headed`（有头/无头）+ `slow_mo` **嵌入 `reports/results.json` 的 `__meta__` 字段**（与用例结果同源、
  同一次 sessionfinish 写出，永不脱钩）。`report_builder` 生成报告时**优先读 `results.json.__meta__.headed`**，
  `run_meta.json` 仅作兜底。因此无论事后用 `make_report.py`（甚至带不同 `SJQQ_HEADED` 环境变量）怎么重建报告，
  标注都与"产出这份结果的真实那次运行"一致，不会再有"实际开浏览器却标无头"或反之的矛盾。
- **⚠ 浏览器启动的反转细节（曾踩坑）**：`conftest.py` 里浏览器必须以 `headless=not settings.HEADED` 启动，
  **不要**写成 `headless=settings.HEADED`。原因：Playwright 的 `headless=True` 含义是"无窗口"、
  `headless=False` 才是"有窗口"，与本项目变量名 `HEADED=True=有头可见` 语义相反。写成后者会让
  "变量写有头、浏览器却无窗口"，并导致报告执行模式整体反转（有头实跑被错标无头）。`assets/sjqq_autotest/conftest.py`
  模板已同步此写法，换设备落地时勿改回。
- **报告默认展开所有用例卡片**，每个用例严格按 `S 场景 → G 前提 → W 步骤 → T 预期` 四段渲染，
  每步带截图与有效性徽章（✅/❌），双击截图可放大。报告附 `🔍 失败诊断` 区块（仅失败用例）。
- 逐步证据与有效性校验见 `reports/evidence/<批次>/<编号>/`（含 `steps.log`、`steps.json` 与每步 PNG）。

### 执行完成后 agent 必须主动反馈运行结果
运行（`pytest`）结束后，agent **必须**把本轮运行结果主动反馈给用户，不要只生成报告就结束。反馈需包含：
1. **汇总**：通过/失败/跳过 的用例数量与总耗时（取自 `reports/results.json` 或直接读 pytest 输出）；
2. **逐用例结论**：每条用例 TC0X 的 通过/失败 状态（如 `✅ TC01 首页加载 10.6s`、`❌ TC07 排行榜第一下载 30.6s`）；
3. **失败原因**：对失败用例，附上报告「❌ 失败原因」区块中的关键信息（失败步骤 + 真实原因，如 PC web 端不弹二维码等站点缺陷说明）；
4. **产物位置**：告知唯一报告 `reports/应用宝官网自动化测试报告.html` 已生成，并用 `present_files` 打开预览面板，让用户直接查看。
> 一句话原则：跑完用例 → 汇总结果 → 说明失败原因 → 打开 `应用宝官网自动化测试报告.html`，四步缺一不可。

## 四、动态识别引擎（抗改版核心）

`core/dynamic_locators.py` 的 `DynamicLocator` 用 Playwright 的 user-facing locator
（`get_by_text` / `get_by_role` / `get_by_placeholder` / `get_by_alt_text`）+ **多候选 OR**，
对单个语义目标给出一组等价定位，命中任一即可：

```python
from playwright.sync_api import Page
from core.dynamic_locators import DynamicLocator

loc = DynamicLocator(page)
box = loc.placeholder("元宝", "搜索", "搜索应用、游戏").first          # 搜索框：placeholder 多候选
dl = loc.button_visible("下载", "下载客户端", "立即下载").first        # 下载 CTA：多候选文本 OR
loc.text("精选", "推荐", "热门").first.wait_for("visible")
```

所有"易变"文案集中在 `config/settings.py` 的 `CandidatePools`（搜索框 placeholder、导航关键词、
logo alt、下载按钮文案、页脚栏目等）。**页面改版时只改这个文件。**

## 五、用例格式（S-G-W-T 四段式，G 前提必填）

`cases/cases.md` 用四段式中文描述全部用例，供业务/产品阅读、评审与维护，**不依赖代码**：

- **S（Scenario）场景**：要验证什么；
- **G（Given）前提条件**：执行前需满足的环境/状态（**必填**，缺失时报告该段显示 `—`）；
- **Wn（When 步骤）**：具体操作步骤（n 为顺序号，按此顺序执行；执行时在浏览器里逐步可见）；
- **T（Then）预期结果**：应达到的结果。

每个用例以 `## TC0X 标题` 二级标题分块，由 `core/case_reader.py` 解析。

**`cases_business.md`（业务源文件）写法**：

```markdown
## TC07 排行榜第一应用下载
场景：验证排行榜第一的应用，点击它的下载/安装入口后能否弹出二维码/扫码下载弹窗
前提条件：已在应用宝官网首页，排行榜页面可正常访问
步骤：
1. 打开排行榜
2. 点击排行榜第一的应用
3. 点击下载按钮
4. 观察二维码/扫码下载弹窗出现
预期：打开排行榜、点进首位应用、点击下载/安装入口后应弹出二维码/扫码下载弹窗
```

保存后让 agent 跑一次 `translate_cases.py`，新用例自动进入 `cases.md` 并被 `pytest` 执行。

## 六、受控动作清单（翻译器已支持）

业务里写的 W 步骤会先匹配受控关键字，未命中再走 `nl_translator` 自由语言翻译。已支持的核心动作：

| 受控文本（示例） | 对应动作 | 说明 |
|------|------|------|
| `打开首页` / `打开 "<url>"` | open | 打开应用宝官网或指定网址 |
| `打开排行榜` | ranking | 打开热门榜页（`settings.RANKING_URL = https://sj.qq.com/rank`） |
| `点击排行榜第一的应用` | ranking_first | 取榜单首位 app（`/appdetail/` 链接）进入其详情页 |
| `搜索 "<词>"` | search | 在搜索框输入并回车 |
| `点击导航` / `点击分类` | click | 点击导航/分类入口 |
| `点击下载按钮` | download | 智能定位真正的下载/安装 CTA 并点击，校验下载流程被触发 |
| `观察二维码出现` / `观察二维码/扫码下载弹窗出现` | observe_qr | 显式等待【可见】二维码元素，超时则如实记缺陷 |
| `等URL包含 "..."` | wait | 等待 URL 变化 |
| `统计 相关结果数量` / `观察 "搜索框" 是否可见` | count / observe | 数量统计与元素可见性断言 |
| `切到手机大小 375x667` | viewport | 切换视口（响应式校验） |
| `截图` | screenshot | 留痕截图 |

> 常用中文说法写法随意：打开应用宝官网 / 在搜索框输入微信并回车 / 搜一下微信 / 点开第一个结果进详情 /
> 等结果出现 / 看看搜索框在不在 / 品牌logo可见吗 / 移动端有没有横向滚动 / 下载按钮能看见吗 / 打开排行榜 /
> 点击排行榜第一的应用 / 观察二维码出现。

## 七、新增用例（维护指引：只写中文，不用写脚本/关键字）

业务/产品人员**不需要写任何代码、也不需要学关键字**，两种做法任选其一：

**做法 1（推荐）：在 `cases/cases_business.md` 用大白话加一段**（含 `场景 / 前提条件 / 步骤 / 预期`）。
保存后让 agent 跑 `translate_cases.py`，新用例自动进入 `cases.md` 并被 `pytest` 执行。

**做法 2（更快，免翻译脚本）：直接编辑 `cases.md`**，把 W 步骤写成大白话即可，
执行引擎运行时自动翻译（报告里能看到「自由语言→ 规范动作」对照）。

> 内部原理：`core/step_executor.py` 逐条处理 W 步骤——命中受控关键字直接执行；未命中则调用
> `core/nl_translator.translate_step` 把自由自然语言翻译成动作（启发式离线，可选 LLM 增强），
> 无需为每条用例写脚本。`translate_cases.py` 把整个业务源文件批量翻译为规范用例。

## 八、内置用例一览（业务源文件 cases_business.md，由 test_cases_md.py 数据驱动执行）

| 用例编号 | 标记 | 场景 |
|------|------|------|
| TC01 | smoke | 首页加载：标题/搜索框/logo/区块/导航可见 |
| TC02 | smoke | 搜"微信"返回结果 |
| TC03 | smoke | 点击分类导航跳转正常 |
| TC04 | smoke | 进入详情页且下载按钮可见 |
| TC05 | smoke | 页脚完整 + 移动端无横向溢出 |
| TC06 | smoke | 搜"王者荣耀"进详情且可下载（业务新增示例） |
| TC07 | smoke | 排行榜第一应用下载（点下载入口并观察二维码） |

> 全部用例由单一的 `tests/test_cases_md.py` 参数化驱动，**无需为每个用例写单独脚本**；
> 加用例 = 在 `cases_business.md` 增加 `## TC0x` 段落并跑 `translate_cases.py`。

## 九、踩坑经验（务必注意）

1. **React 受控输入框需先 click 再 fill**：只 `fill` 不 `click` 时，受控组件可能不触发输入事件。
2. **下载 CTA 不一定是 `<button>` 或带 `href` 的 `<a>`**：应用宝 PC 端真正的安装入口是
   **「微软商店安装」这个 `<div>` 按钮**（无 link/button 角色），定位要用
   `querySelectorAll('a,button,div')` 配合精确文本 + 可见尺寸，而不能只 `get_by_role`。
3. **页面存在大量 0 尺寸的隐藏重复节点**：详情页有 24 个 innerText 为「下载」的隐藏节点
   （祖先 `display:none`，`offset` 宽高为 0），`button[has_text=下载]` 会全中不可点元素，
   必须过滤可见尺寸或改用「微软商店安装」文本精确匹配。
4. **PC web 端点下载不会弹网页二维码**：实测点「微软商店安装」只唤起应用宝/微软商店**客户端协议**
   （headless 下可能触发一个下载事件，或无界面反应），**页面从不弹网页二维码**。因此"预期能看到二维码截图"
   在 PC web 端**无法满足**，属站点真实行为（失败用例报告中已如实标注原因）。
5. **避免 `.first` 命中隐藏元素**：等待/点击按钮时先 `.filter(visible=True)`。
6. **本机 Chrome 用 `channel="chrome"`**：在 `conftest.py` 覆盖 `browser` fixture 并加 `--no-sandbox`
   等启动参数（Windows 环境常见）。
7. **搜索结果需等渲染**：`wait_for` 不能只等"关键词文本出现"（首页也有该文本），
   要等"含关键词的结果链接 `a[has_text=关键词]` 可见"再断言数量。
8. **执行模式标注要用 results.json.__meta__**：报告生成时优先读 `reports/results.json` 的
   `__meta__.headed`（与用例结果同源、真实运行的权威来源），`run_meta.json` 仅作兜底；
   绝不能用"重建报告那一刻"的 `SJQQ_HEADED` 环境变量，避免"真实运行与报告标注"矛盾。

## 十、环境清理与失败诊断（自动化）

### 每次重跑自动清理（仅清日志/中间态，保留报告 + 截图）
`conftest.py` 的 `clean_environment`（session 级、最先执行）在每次测试任务启动时清理上一轮的
日志与中间产物：`reports/cases_loaded.log`、`reports/results.json`、`reports/diagnosis.json`，
以及各 `evidence/<批次>` 目录里的 `steps.log` / `steps.json`。
**保留** `reports/应用宝官网自动化测试报告.html` 与 `reports/evidence/<批次>/` 下的全部 PNG 截图。
证据按运行批次时间戳（`YYYYMMDD_HHMMSS`）分目录隔离，历史批次互不干扰。

### 用例失败自动诊断（UI 元素失效 vs 接口失败）
每个**失败用例的报告卡片内**都会内嵌失败原因，便于直接定位（不再依赖单独的说明文档）：
- **❌ 失败原因区块（每用例一张，醒目标红）**：取自真实执行证据中 `effective=False` 的 W 步骤，
  展示「失败步骤编号 + 步骤文本 + 执行器如实记录的原因」（如 PC web 端不弹二维码等站点缺陷说明）；
- **🔍 失败诊断区块（补充）**：`core/diagnostics.py` 做三层诊断（网络/接口监听、UI 元素探针、结构化结论），
  写入报告失败区块与 `reports/diagnosis.json`（供独立复生成报告读取）。

三层诊断细节：
1. **网络/接口监听**：捕获失败请求与 `HTTP>=400` 的响应（已过滤静态资源/扩展/第三方 SDK 噪音）；
2. **UI 元素探针**：失败时探测关键 UI 元素是否*存在且可见*，输出元素状态表；
3. **结构化结论**：综合异常中的定位器线索，给出如「关键 UI 元素缺失/接口网络异常」等结论。
