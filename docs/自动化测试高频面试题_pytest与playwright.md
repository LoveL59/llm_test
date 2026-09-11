# 自动化测试高频面试题（Pytest + Playwright 版）

> 适用场景：自动化测试岗位求职面试复习。第〇部分为 Pytest Fixture 与 conftest.py 概念速查（补充），第一部分为 Pytest 高频题，第二部分为 Playwright 高频题，第三部分为 Selenium vs Playwright 对比（加分项）。

---

## 第0部分、Pytest Fixture 与 conftest.py 概念速查（补充）

### 1. Fixture 是什么

Fixture 是 Pytest 专属的**前置后置固件**，用于在用例执行前完成 setup、teardown、全局数据准备、初始化资源等操作；功能上替代并强于 unittest 的 `setUp/tearDown`。

### 2. Fixture 基础用法

```python
import pytest

@pytest.fixture
def login():
    # 前置：准备登录态
    token = "xxx"
    yield token          # 用例拿到的值
    # 后置：yield 之后的代码为 teardown
    print("用例结束清理")
```

在用例中直接当参数注入即可使用：

```python
def test_x(login):
    assert login == "xxx"
```

### 3. Fixture 作用域（scope）

通过 `scope` 参数控制 fixture 的作用范围：

```python
@pytest.fixture(scope="function")   # 每个用例执行一次（默认）
def case_setup(): ...

@pytest.fixture(scope="class")      # 整个测试类执行一次
def class_setup(): ...

@pytest.fixture(scope="module")     # 整个 .py 模块执行一次
def module_setup(): ...

@pytest.fixture(scope="session")    # 整个测试会话执行一次
def db(): ...
```

> 记忆口诀：**function → class → module → session**，颗粒度由小到大。

### 4. autouse 自动调用

```python
@pytest.fixture(autouse=True)
def each_case():
    print("每个用例自动执行前后置")
```

打上 `autouse=True` 后，无需在用例参数中显式传入，pytest 自动注入。

### 5. fixture 之间可互相调用

```python
@pytest.fixture
def admin_user(login):   # 直接拿 login 的返回值
    return {"user": "admin", "token": login}
```

### 6. 什么是 conftest.py

conftest.py 是 Pytest 的**全局公共固件配置文件**，专门存放项目中所有测试脚本都需要复用的公共 fixture，不用在每个脚本里重复写公共逻辑。

### 7. conftest 四大黄金规则

- **第一条**：文件名固定死，**只能叫 conftest.py**。
- **第二条**：不需要手动 `import` 导入，项目下所有 `test_` 开头的脚本会**自动识别文件内全部 fixture**。
- **第三条**：文件**只允许写 fixture 函数**，禁止存放 `test_` 开头的测试用例，否则会出现用例重复执行、执行顺序错乱。
- **第四条**：支持分层生效：**项目根目录的 conftest 对全局所有脚本生效**；**子文件夹内的 conftest 仅对当前文件夹下脚本生效（就近原则）**。

---

## 一、Pytest 高频面试题（保留 + 补充）

**Q1. pytest 默认如何发现用例？**  
文件 `test_*.py` / `*_test.py`、函数/方法 `test_*`、类 `Test*`（且**不能有 `__init__` 构造方法**）。

**Q2. 如何让用例按指定顺序执行？**  
装 `pytest-ordering`，用 `@pytest.mark.run(order=n)`；或用 `conftest.py` 的 `pytest_collection_modifyitems` 钩子自定义排序。

**Q3. 失败用例如何重跑？**  
用 `pytest-rerunfailures` 插件：`pytest --reruns 3` 或 `@pytest.mark.flaky(reruns=3)`，可加 `reruns_delay` 设置间隔。

**Q4. skip 和 xfail 区别？**  
`skip` 直接跳过不执行；`xfail` 会执行，但预期失败，失败显示为 `xfailed` 不计入错误，意外通过则显示 `xpassed`（可配 `strict=True` 让它变失败）。

**Q5. `-k` 和 `-m` 区别？**  
`-k` 按**用例名关键字**过滤；`-m` 按**自定义 mark 标记**过滤，两者可叠加（如 `pytest -m smoke -k login`）。

**Q6. 如何自定义 marker 并避免告警？**  
在 `pytest.ini` 的 `[pytest] markers =` 下注册（如 `smoke: 冒烟`），再用 `@pytest.mark.smoke` 打标记，运行 `pytest -m smoke` 选择。

**Q7. Playwright 和 pytest 什么关系？**  
Playwright 是浏览器自动化库，不是测试框架；通过 `pytest-playwright` 插件接入 pytest，由 pytest 负责调度，Playwright 负责操作浏览器。

**Q8. 什么是 fixture？和 unittest 的 setUp/tearDown 有什么区别？**  
fixture 是 Pytest 的前置后置固件，用 `yield` 把用例分成「前置 → 用例 → 后置」三段；比 unittest 的 `setUp/tearDown` 更强：

- 支持 `scope`（function/class/module/session）控制颗粒度；
- fixture 之间可互相调用、组合（fixture 依赖 fixture）；
- 可参数化（`params`），同一 fixture 给不同用例返回不同数据；
- 支持 `autouse=True` 自动注入，省去每个用例都传参。  
  unittest 的 setUp/tearDown 只能写类里、颗粒度只能到方法，fixture 则可全局共享、跨脚本复用。

**Q9. 什么是 conftest.py？有什么"四大黄金规则"？**  
conftest.py 是 Pytest 的**全局公共固件配置文件**，专门存放所有脚本都要复用的公共 fixture。四大黄金规则：

- ① 文件名固定死，**只能叫 conftest.py**；
- ② **不需要手动 import**，项目下所有 `test_` 开头的脚本会自动识别文件内全部 fixture；
- ③ 文件**只允许写 fixture 函数**，禁止写 `test_` 用例（否则会重复收集、执行顺序错乱）；
- ④ **分层生效、就近原则**：根目录的 conftest 对全局生效，子目录的 conftest 只对当前目录及子目录生效。

---

## 二、Playwright 高频面试题（新增）

**Q10. Playwright 和 Selenium 的核心区别？**

- 架构：Selenium 基于 WebDriver 协议（HTTP 通信，较慢）；Playwright 通过浏览器 DevTools 协议（CDP）直驱，更快更稳。
- 等待：Selenium 常需显式等待或硬编码 `sleep`；Playwright 内置自动等待 + 重试，`expect` 自带轮询。
- 浏览器：Selenium 需各浏览器单独装驱动；Playwright 自带 Chromium/Firefox/WebKit 内核，一条命令安装。
- 定位：Playwright 提供 `get_by_role`/`get_by_text` 等语义定位，对结构变化更鲁棒。

**Q11. Playwright 的自动等待（Auto-waiting）是什么？**  
执行点击、填充等操作前，Playwright 自动检查元素是否"可操作"（可见、稳定、可接收事件、已启用），不满足则轮询直到超时（默认 30s），大幅减少 flaky 失败；`expect()` 断言同样自动重试。

**Q12. Playwright 有哪些定位方式？推荐哪种？**

- CSS：`page.locator("#id .class")`
- XPath：`page.locator("//button")`
- 语义定位（推荐）：`get_by_role`、`get_by_text`、`get_by_label`、`get_by_placeholder`、`get_by_alt_text`、`get_by_title`  
  推荐语义定位，可读性强且对 DOM 结构变动更稳健。

**Q13. browser / context / page 三个 fixture 的关系？context 的作用是什么？**  
层级为 `browser(session)` > `context(function)` > `page(function)`。context 是独立的浏览器上下文，隔离 cookie、localStorage、缓存，相当于一个"隐身窗口"；每个测试用独立 context 可保证用例间互不污染。

**Q14. 如何处理新窗口 / 弹窗（popup）？**  
用上下文管理器捕获新页面对象：

```python
with page.expect_popup() as popup_info:
    page.click("a[target='_blank']")
new_page = popup_info.value
```

也可监听 `page.on("popup", handler)`。

**Q15. 如何处理 iframe？**  
先定位 frame，再在内部定位元素：

```python
frame = page.frame_locator("#myframe")
frame.locator("button").click()
```

**Q16. 文件上传 / 下载怎么做？**

- 上传：`page.set_input_files("input[type=file]", "path.txt")`
- 下载：`with page.expect_download() as dl: page.click("#download"); path = dl.value.path()`

**Q17. 失败截图和录屏怎么做？**

- 截图：在 fixture 的 teardown 中按用例结果调用 `page.screenshot(path="fail.png")`。
- 录屏：创建 context 时设 `record_video_dir="videos/"`。
- 追踪：用 `context.tracing.start(screenshots=True, snapshots=True)`，结束 `context.tracing.stop(path="trace.zip")`，再 `playwright show-trace trace.zip` 回放。

**Q18. codegen 是什么，有什么用？**  
`playwright codegen URL` 会打开浏览器，你手动操作它自动生成 Playwright 代码，是快速产出定位脚本、降低写用例门槛的利器（面试加分点）。

**Q19. 同步 API 和异步 API 的区别？**

- 同步：`from playwright.sync_api import sync_playwright`，顺序执行，配合 pytest 最常用。
- 异步：`from playwright.async_api import async_playwright`，用 `async/await`，适合高并发或异步框架。

**Q20. 如何在 CI 中无头运行？**  
本地用 `pytest --headed` 有头调试；CI 默认无头。CI 机器需先执行 `playwright install --with-deps`（安装浏览器及系统依赖），否则会报缺库错误。

**Q21. 如何参数化多浏览器运行？**  
命令行：`pytest --browser chromium --browser firefox --browser webkit`；或在用例中用 `@pytest.mark.parametrize("browser_name", ["chromium","firefox","webkit"])` 配合 `browser` fixture 切换。

**Q22. Playwright 的 `expect` 和普通 `assert` 区别？**  
`expect(...)` 带自动等待与重试，适合异步渲染的 Web 页面（元素晚到也不会误判）；`assert` 是即时判断，元素未加载完就断言可能直接失败。

**Q23. 如何拦截 / mock 网络请求？**

```python
page.route("**/api/**", lambda route: route.fulfill(
    status=200, body='{"mock": true}'))
```

可用于 mock 接口返回、屏蔽第三方请求、模拟弱网或错误响应。

---

## 三、加分对比：Selenium vs Playwright

| 维度    | Selenium                 | Playwright              |
| ----- | ------------------------ | ----------------------- |
| 通信协议  | WebDriver（HTTP）          | CDP（直驱浏览器）              |
| 执行速度  | 较慢                       | 更快                      |
| 等待机制  | 需显式等待 / sleep            | 自动等待 + 重试               |
| 浏览器驱动 | 各浏览器单独安装                 | 自带内核，一键安装               |
| 定位方式  | 主要靠 CSS/XPath            | 语义定位 + CSS/XPath        |
| 多浏览器  | Chrome/Firefox/IE/Edge 等 | Chromium/Firefox/WebKit |
| 调试能力  | 弱                        | trace 追踪 / codegen 录制   |
| 网络拦截  | 较弱                       | 原生 route 拦截             |
| 上下文隔离 | 依赖 profile               | 原生 context 隔离           |
| 学习成本  | 经典、资料多                   | 新、API 现代                |

> 一句话总结：**Playwright 在速度、稳定性（自动等待）、调试（trace/codegen）和现代化 API 上全面优于 Selenium，是新项目的首选；但 Selenium 生态成熟、资料多、对老浏览器（含 IE）支持更好。**

---

## 四、速背口诀

- **pytest 发现用例**：文件 `test_` 开头、函数 `test_` 开头、类 `Test` 开头且没 `__init__`。
- **顺序**：`run(order=n)` 或 `conftest` 钩子。
- **重跑**：`--reruns 3` / `@pytest.mark.flaky`。
- **跳过 vs 预期失败**：`skip` 不跑，`xfail` 跑但预期挂。
- **选用例**：`-k` 按名，`-m` 按标记。
- **fixture**：前置后置固件，`yield` 切分前后；`scope` 从小到大 `function → class → module → session`。
- **conftest**：固定文件名、自动 import、只写 fixture、就近原则分层生效。
- **Playwright 定位**：语义优先（`get_by_*`），少写 XPath。
- **隔离**：每个用例独立 `context`，互不污染。
- **调稳定**：靠自动等待，别手写 `sleep`。
- **调试三件套**：codegen 录、trace 回放、expect 重试。
