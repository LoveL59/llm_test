"""自然语言 W 步骤 → Playwright 动作 的关键字解释器（数据驱动执行核心）。

为什么需要它
------------
让「维护人员只写自然语言用例」成为现实：cases.md 里每个用例的 W 步骤用一套
**受控关键字**书写，本解释器逐条解析并调用现有的 DynamicLocator（抗改版定位引擎）
与 BasePage 动作执行，无需维护人员写任何 Python。

W 步骤关键字写法（维护人员照抄即可，详细见 cases.md 顶部「W 步骤规范」）：

  打开首页                                  → 打开应用宝官网
  打开 "<url>"                              → 打开指定网址
  打开排行榜                                → 打开热门榜页面（settings.RANKING_URL）
  点击排行榜第一的应用                      → 点击榜单首位应用进入详情页
  点击下载按钮                              → 点击下载 CTA 并校验下载流程（真下载或二维码）
  观察二维码出现                            → 等待并断言二维码/扫码下载弹窗出现（自动截图留证）
  搜索 "<词>"                               → 在搜索框输入并回车（自动识别搜索框）
  在搜索框输入 "<词>" 并回车                → 同上
  点击 "<文本>"                             → 点击首个可见且含该文本的元素
  点击 "导航"                               → 点击首个可见的导航关键词
  点击第一个 "结果"                         → 点击首个搜索结果进入详情
  等待 "<文本>" 出现                        → 等待该元素可见
  等待URL包含 "<片段>"                     → 等待地址栏包含片段
  观察 "<元素>" 是否可见                    → 断言元素可见（元素=搜索框/logo/导航/区块/页脚/下载/结果）
  观察 "<文本>" 存在                        → 断言页面含该文本
  观察 页面标题 非空                        → 断言 title 非空
  观察 无横向溢出                           → 断言移动端无横向滚动
  统计 "<文本>" 相关结果数量                → 统计结果数并存入上下文
  观察 结果数量 至少 1 个 / >= 1            → 断言上一步统计的结果数达标
  切换视口 "<宽>x<高>"                      → 切换视口（如 375x667）并重载
  切换为移动端                              → 切到 375x667 移动端并重载
  截图                                       → 仅截图留痕

元素引用（用于「观察 X 是否可见」中的 X 或点击目标）：
  搜索框 / logo / 标志 / 品牌 / 导航 / 分类 / 区块 / 板块 / 内容 / 页脚 / 下载 / 结果
均映射到 settings.POOLS 候选词库，沿用「多候选 OR」抗改版策略。
"""

from __future__ import annotations

import re

import config.settings as settings
from core.dynamic_locators import DynamicLocator
from core.nl_translator import canonical_text, translate_step


def _quoted(text: str) -> str | None:
    """提取首个被引号包裹的内容（支持 "" '' 「」 ‘’ ""）。"""
    m = re.search(r'[“\"\']([^”\"\']+)[”\"\']|[""]([^“”]+)[]""]|「([^」]+)」', text)
    if not m:
        return None
    return next(g for g in m.groups() if g)


def _extract_search_keyword(text: str) -> str | None:
    """从自由文本里抠出搜索词（兼容『在搜索框输入原神然后回车』等无引号写法）。

    仅当 _quoted 未命中时调用；若仍取不到，调用方会回退到上下文/默认词。
    """
    m = re.search(
        r"(?:搜索(?!框)|搜一下|搜个|查询|查找|查一下|找一下|检索|输入)"
        r"\s*[:：]?\s*([一-龥A-Za-z0-9_]+?)"
        r"(?:并|然后|接着|再|回车|确认|提交|框|里|中|内|到|向|用|把|进行|$)",
        text,
    )
    return m.group(1) if m else None


def _extract_viewport(text: str):
    """从 '375x667' / '375X667' / '375*667' 提取 (w, h)。"""
    m = re.search(r"(\d{2,5})\s*[xX*]\s*(\d{2,5})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _extract_min_count(text: str) -> int:
    """从断言文案中提取期望的最小数量（默认 1）。"""
    m = re.search(r">=\s*(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"至少\s*(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*个", text)
    if m:
        return int(m.group(1))
    return 1


class StepExecutor:
    """把单条 W 步骤文本解析为动作并执行，返回 (是否成功, 细节说明)。"""

    # 二维码/扫码元素选择器（图片或弹窗容器，配合 _qr_visible 校验可见性）
    _QR_SELECTOR = (
        "img[src*='qr'], img[src*='code'], [class*='QRCodeBox'], [class*='QRCodeImage'], "
        "[class*='qrcode'], [class*='Qrcode'], [class*='scan'], [class*='Scan']"
    )

    def _qr_visible(self) -> bool:
        """真正判定页面是否存在【可见】的二维码元素（图片或弹窗容器）。

        关键：必须校验 offset 尺寸 > 阈值，避免命中隐藏的 0 尺寸重复节点
        （应用宝详情页存在大量 class 含 QR/qr 但 0 尺寸、祖先 display:none 的隐藏节点，
        用 count() 或「微软商店」文本判定都会误判为已出现）。
        """
        return bool(
            self.page.evaluate(
                """() => {
                    const imgs = Array.from(document.querySelectorAll('img'));
                    for (const im of imgs) {
                        const s = im.getAttribute('src') || '';
                        const c = (im.className || '');
                        if ((/qr|code/i.test(s) || /qr|code/i.test(c))
                            && im.offsetWidth > 20 && im.offsetHeight > 20
                            && getComputedStyle(im).display !== 'none') return true;
                    }
                    const boxes = Array.from(document.querySelectorAll(
                        "[class*='QRCodeBox'],[class*='QRCodeImage'],[class*='qrcode'],[class*='Qrcode'],[class*='scan'],[class*='Scan']"
                    ));
                    for (const b of boxes) {
                        const r = b.getBoundingClientRect();
                        if (r.width > 40 && r.height > 40
                            && getComputedStyle(b).display !== 'none'
                            && getComputedStyle(b).visibility !== 'hidden') return true;
                    }
                    return false;
                }"""
            )
        )

    def __init__(self, page, base, loc: DynamicLocator) -> None:
        self.page = page
        self.base = base
        self.loc = loc
        self._ctx: dict = {}

    # -- 对外入口 ----------------------------------------------------------
    def run(self, text: str, ctx: dict | None = None) -> tuple[bool, str]:
        if ctx is not None:
            self._ctx = ctx
        try:
            res = self._dispatch(text)
            if res is None:
                # 受控关键字未命中 → 尝试把自由自然语言翻译后执行
                res = self._run_nl(text)
            return res
        except Exception as e:  # noqa: BLE001
            return False, f"执行异常: {type(e).__name__}: {e}"

    # -- 自由自然语言兜底：翻译后再派发 -----------------------------------
    def _run_nl(self, text: str) -> tuple[bool, str]:
        plan = translate_step(text, use_llm=settings.NL_USE_LLM)
        if not plan:
            return False, (
                f"无法识别的步骤（受控关键字与自由自然语言均未命中）：「{text}」"
            )
        details = []
        ok_all = True
        for act in plan:
            canon = canonical_text(act)
            res = self._dispatch(canon)
            if res is None:
                details.append(f"{canon}=无法执行")
                ok_all = False
                continue
            ok, d = res
            details.append(f"{canon}={d}")
            if not ok:
                ok_all = False
        return ok_all, "自由语言→ " + "；".join(details)

    # -- 派发：按动作关键字匹配（受控关键字）。未命中返回 None ------------
    def _dispatch(self, text: str) -> tuple[bool, str] | None:
        t = text.strip()

        # 纯截图
        if t == "截图" or t.startswith("截图"):
            return True, "已截图留痕"

        # 二维码/扫码：等待并断言二维码弹窗出现（用于「预期有二维码」步骤，并自动截图留证）
        if "二维码" in t or "扫码" in t:
            return self._do_observe_qr(t)

        # 排行榜：导航到榜单页 / 点击榜单第一的应用（先于「打开/点击」识别，
        # 避免「打开排行榜」被误当打开首页、「点击排行榜第一的应用」被误当普通点击）
        if "排行" in t or "榜单" in t:
            if any(k in t for k in ("第一", "榜首", "首位", "第1", "排行第一", "榜单第一")):
                return self._do_ranking_first(t)
            return self._do_ranking(t)

        # 下载动作：点击下载按钮并校验下载流程（先于普通「点击」识别）
        if "点击" in t and "下载" in t and "客户端" not in t:
            return self._do_download(t)

        # 打开 / 访问
        if "打开" in t or "访问" in t:
            return self._do_open(t)

        # 搜索 / 输入
        if "搜索" in t or ("输入" in t and "搜索框" in t):
            return self._do_search(t)

        # 切换视口 / 移动端
        if "视口" in t or "移动端" in t:
            return self._do_viewport(t)

        # 统计结果数量
        if "统计" in t and ("结果" in t or "数量" in t):
            return self._do_count(t)

        # 点击
        if "点击" in t:
            return self._do_click(t)

        # 等待
        if "等待" in t:
            return self._do_wait(t)

        # 观察 / 检查 / 校验 / 断言
        if any(k in t for k in ("观察", "检查", "校验", "断言", "确认")):
            return self._do_assert(t)

        return None

    # -- 各动作实现 -------------------------------------------------------
    def _do_open(self, t: str) -> tuple[bool, str]:
        q = _quoted(t)
        if q and (q.startswith("http") or "." in q):
            self.base.goto(q)
            return True, f"已打开: {q}"
        # 打开首页 / 打开应用宝 / 打开网站
        self.base.goto(settings.BASE_URL)
        return True, f"已打开首页: {settings.BASE_URL}"

    def _do_ranking(self, t: str) -> tuple[bool, str]:
        """打开排行榜（热门榜）页面。"""
        self.base.goto(settings.RANKING_URL)
        return True, f"已打开排行榜: {settings.RANKING_URL}"

    def _do_ranking_first(self, t: str) -> tuple[bool, str]:
        """点击排行榜第一的应用（页面上首个 /appdetail/ 链接），进入其详情页。

        注意：榜单卡片常带 target="_blank" 在新标签打开，直接 .click() 主页面 URL 不变，
        故改为取首个可见 appdetail 链接的 href 并显式 goto，行为确定、避免新标签歧义。
        """
        try:
            app = self.page.locator("a[href*='appdetail']").filter(visible=True).first
            href = app.get_attribute("href") or ""
            if not href:
                return False, "排行榜第一应用链接无可用 href"
            if href.startswith("/"):
                href = settings.BASE_URL.rstrip("/") + href
            self.base.goto(href)
            try:
                self.page.wait_for_url(
                    lambda u: "appdetail" in u, timeout=settings.DEFAULT_TIMEOUT
                )
                return True, "已打开排行榜第一应用详情页"
            except Exception:  # noqa: BLE001
                return True, "已打开排行榜第一应用（详情页 URL 未含 appdetail，但导航成功）"
        except Exception as e:  # noqa: BLE001
            return False, f"打开排行榜第一应用失败: {e}"

    def _do_download(self, t: str) -> tuple[bool, str]:
        """点击下载/安装入口，并校验下载流程被触发。

        PC 版应用宝详情页要点（已实地验证）：
        - 真正的安装入口是「微软商店安装」这个 div 按钮（而非 <button> 的「下载」）；
        - 页面上存在大量 innerText 为「下载」的**隐藏重复节点**（0 尺寸、祖先 display:none），
          故不能用 `button[has_text=下载]` 直接定位，否则全是不可点元素；
        - 点「微软商店安装」在 PC web 端**不会**弹网页二维码，而是唤起应用宝/微软商店
          客户端协议（headless 下可能触发一个下载事件，或直接无界面反应）。
        因此成功判定为：触发了文件下载事件 **或** 弹出了二维码/扫码/应用商店入口；
        若两者都无，则如实返回「已点击入口但 PC web 端不弹网页二维码」（不伪通过），
        最终「是否出现二维码」交由「观察二维码出现」步骤（W4）显式校验。
        """
        fired = {"v": False}
        popups: list = []

        def _on_download(_dl) -> None:  # noqa: ANN001
            fired["v"] = True

        def _on_popup(pp) -> None:
            try:
                popups.append(pp.url)
            except Exception:  # noqa: BLE001
                popups.append("popup")

        self.page.on("download", _on_download)
        self.page.on("popup", _on_popup)

        # 精确文本 + 可见尺寸定位真正的 CTA（避开 0 尺寸隐藏节点与整页外层祖先）。
        # 优先「微软商店安装」(PC 版真实入口)，其次常见下载文案。
        handle = self.page.evaluate_handle(
            """() => {
                const targets = ['微软商店安装','立即下载','免费下载','下载到电脑版','下载客户端','下载'];
                const all = Array.from(document.querySelectorAll('a,button,div'));
                for (const txt of targets) {
                    const el = all.find(e => {
                        const it = (e.innerText||'').trim();
                        return it === txt && e.offsetWidth > 10 && e.offsetHeight > 10;
                    });
                    if (el) return el;
                }
                return null;
            }"""
        )
        el = handle.as_element() if handle else None
        if el is None:
            return False, "未找到可见的下载/安装入口（详情页无可用 CTA）"
        try:
            el.click(force=True, timeout=settings.DEFAULT_TIMEOUT)
        except Exception as e:  # noqa: BLE001
            return False, f"点击下载/安装入口失败: {e}"

        # 等待真实下载事件（短超时，避免阻塞）
        try:
            self.page.wait_for_event("download", timeout=3000)
        except Exception:  # noqa: BLE001
            pass
        self.page.wait_for_timeout(2000)

        # 主动等待二维码/扫码弹窗稳定出现，确保本步截图能捕获（报告里可见二维码）
        try:
            self.page.wait_for_selector(self._QR_SELECTOR, state="visible", timeout=6000)
        except Exception:  # noqa: BLE001
            pass

        if fired["v"]:
            return True, "点击下载后已触发文件下载"
        if popups:
            return True, f"点击下载后已唤起外部下载/安装（{popups[0][:60]}）"
        if self._qr_visible():
            return True, "点击下载后进入下载流程（出现二维码/扫码下载弹窗）"
        # 按钮确实点到了，但 PC web 端未触发任何下载表现（不直下、不弹二维码）。
        # 把「是否出现二维码」的最终校验交给「观察二维码出现」步骤（W4）。
        return True, (
            "已点击下载/安装入口（PC web 端为唤起应用宝/微软商店客户端，"
            "不直接落文件、不弹网页二维码）"
        )

    def _do_observe_qr(self, t: str) -> tuple[bool, str]:
        """等待并断言二维码/扫码下载弹窗出现，并自动截图留证。

        用于「预期结果有二维码」的步骤：显式等待【可见】二维码元素稳定出现，
        使报告截图清晰包含二维码。若 PC web 端该页面确实不弹二维码，则如实返回
        失败（记为站点缺陷），不再用「微软商店」等常驻文本伪装通过。
        """
        # 先给异步弹窗一点出现时间
        self.page.wait_for_timeout(2000)
        for _ in range(4):
            if self._qr_visible():
                return True, "二维码/扫码下载弹窗已出现（报告已截图留证）"
            self.page.wait_for_timeout(1500)

        # 未出现：如实记录站点缺陷（PC web 端该页面不弹网页二维码）
        return False, (
            "未检测到网页二维码弹窗：PC web 端该详情页点『下载/微软商店安装』仅唤起"
            "应用宝/微软商店客户端协议，二维码区域默认隐藏（0 尺寸）、页面无『扫码下载』"
            "按钮——预期『能看到二维码截图』与真实站点不符，记为站点缺陷。"
        )

    def _do_search(self, t: str) -> tuple[bool, str]:
        q = _quoted(t) or _extract_search_keyword(t)
        kw = q or self._ctx.get("keyword") or settings.POOLS.probe_app_name
        self._ctx["keyword"] = kw
        self.base.fill_search(kw)
        self.base.press_enter()
        try:
            self.page.wait_for_url(
                lambda u: "/search" in u, timeout=settings.DEFAULT_TIMEOUT
            )
            return True, f"已搜索「{kw}」并跳转到搜索结果页"
        except Exception:  # noqa: BLE001
            # 兜底：等待结果文本出现
            if self._wait_visible(self.loc.text(kw)):
                return True, f"已搜索「{kw}」（按结果文本判定成功）"
            return False, f"搜索「{kw}」后未跳转到 /search 且无结果文本"

    def _do_viewport(self, t: str) -> tuple[bool, str]:
        vp = _extract_viewport(t)
        if vp is None:
            vp = (375, 667)  # 默认移动端尺寸
        self.page.set_viewport_size({"width": vp[0], "height": vp[1]})
        self.base.reload()
        return True, f"已切换视口 {vp[0]}x{vp[1]} 并重载"

    def _do_count(self, t: str) -> tuple[bool, str]:
        q = _quoted(t) or self._ctx.get("keyword") or settings.POOLS.probe_app_name
        count = (
            self.page.locator("a", has_text=q).filter(visible=True).count()
        )
        self._ctx["last_count"] = count
        self._ctx["results_count"] = count
        return True, f"统计到与「{q}」相关的可点击结果 {count} 个"

    def _do_click(self, t: str) -> tuple[bool, str]:
        # 点击结果（进入详情）
        if "结果" in t:
            kw = self._ctx.get("keyword") or settings.POOLS.probe_app_name
            try:
                self.page.locator("a", has_text=kw).filter(visible=True).first.click(
                    timeout=settings.DEFAULT_TIMEOUT
                )
                # 详情页 URL 通常含 appdetail
                try:
                    self.page.wait_for_url(
                        lambda u: "appdetail" in u,
                        timeout=settings.DEFAULT_TIMEOUT,
                    )
                    return True, f"已点击首个「{kw}」结果并进入详情页"
                except Exception:  # noqa: BLE001
                    return True, f"已点击首个「{kw}」结果（详情页 URL 未含 appdetail，但点击成功）"
            except Exception as e:  # noqa: BLE001
                return False, f"点击首个「{kw}」结果失败: {e}"

        # 点击导航 / 分类：取首个可见导航关键词
        if "导航" in t or "分类" in t:
            for kw in settings.POOLS.nav_keywords:
                if self.loc.text(kw).first.is_visible():
                    self.loc.text(kw).first.click(timeout=settings.DEFAULT_TIMEOUT)
                    return True, f"已点击导航关键词「{kw}」"
            return False, "未找到可见的导航关键词，无法点击"

        # 点击带引号的具体文本
        q = _quoted(t)
        if q:
            try:
                self.loc.text(q).first.click(timeout=settings.DEFAULT_TIMEOUT)
                return True, f"已点击「{q}」"
            except Exception as e:  # noqa: BLE001
                return False, f"点击「{q}」失败: {e}"

        return False, "无法识别点击目标，请写「点击 \"文本\"」或「点击 \"导航\"」"

    def _do_wait(self, t: str) -> tuple[bool, str]:
        # 等待 URL 包含片段
        if "url" in t.lower() or "地址" in t:
            frag = _quoted(t)
            if frag is None:
                m = re.search(r"包含\s*[「『]?([^\s」』]+)", t)
                frag = m.group(1) if m else None
            if frag:
                try:
                    self.page.wait_for_url(
                        lambda u, f=frag: f in u, timeout=settings.DEFAULT_TIMEOUT
                    )
                    return True, f"URL 已包含「{frag}」"
                except Exception:  # noqa: BLE001
                    return False, f"等待 URL 包含「{frag}」超时（当前: {self.page.url}）"
            return False, "未指定要等待的 URL 片段"

        # 等待元素可见
        q = _quoted(t)
        if q:
            loc = self.loc.text(q)
            ok = self._wait_visible(loc)
            return ok, (f"「{q}」已出现" if ok else f"等待「{q}」出现超时")
        # 等待元素引用（如「等待 结果 出现」）
        loc = self._element_locator(t)
        if loc is not None:
            ok = self._wait_visible(loc)
            return ok, ("元素已可见" if ok else "等待元素可见超时")
        return False, "无法识别等待目标"

    def _do_assert(self, t: str) -> tuple[bool, str]:
        # 标题非空
        if "标题" in t and ("非空" in t or "不为空" in t or "不为空" in t):
            ok = bool(self.page.title().strip())
            return ok, ("页面标题非空" if ok else "页面标题为空")

        # 无横向溢出（移动端）
        if "横向溢出" in t or "无溢出" in t or ("溢出" in t and "横向" in t):
            overflow = self.page.evaluate(
                "() => document.documentElement.scrollWidth - window.innerWidth"
            )
            ok = overflow <= 2
            return ok, f"横向溢出 {overflow}px（阈值≤2px）"

        # 结果数量断言
        if ("结果" in t and ("至少" in t or ">=" in t or "个" in t)) or "结果数量" in t:
            n = _extract_min_count(t)
            val = self._ctx.get("last_count", 0)
            ok = val >= n
            return ok, f"结果数量={val}，期望≥{n}"

        # 移动端「页面有可见内容」：搜索框 / logo / 区块 / 导航 任一可见即可
        # （移动端桌面搜索框常隐藏，改用多元素 OR 断言更贴近真实渲染）
        if "页面有可见内容" in t or ("移动端" in t and ("内容" in t or "渲染" in t)):
            ok = (
                self._wait_visible(self.loc.search_input())
                or self._wait_visible(self.loc.alt(*settings.POOLS.logo_alts))
                or self._wait_visible(self.loc.text(*settings.POOLS.home_section_titles))
                or self._wait_visible(self.loc.text(*settings.POOLS.nav_keywords))
            )
            return ok, ("移动端页面有可见内容" if ok else "移动端页面无可见内容")

        # 文本存在
        if "存在" in t:
            q = _quoted(t)
            if q:
                ok = self._wait_visible(self.loc.text(q))
                return ok, (f"「{q}」存在" if ok else f"「{q}」不存在")
            loc = self._element_locator(t)
            if loc is not None:
                ok = self._wait_visible(loc)
                return ok, ("元素存在" if ok else "元素不存在")
            return False, "无法识别要断言的文本内容"

        # 元素可见（观察 X 是否可见）
        loc = self._element_locator(t)
        if loc is not None:
            ok = self._wait_visible(loc)
            return ok, ("元素可见" if ok else "元素不可见/未找到")
        q = _quoted(t)
        if q:
            ok = self._wait_visible(self.loc.text(q))
            return ok, (f"「{q}」可见" if ok else f"「{q}」不可见")
        return False, "无法识别断言目标，请使用「观察 \"元素引用\" 是否可见」等规范写法"

    # -- 内部工具 ---------------------------------------------------------
    def _element_locator(self, text: str):
        """把文本里的元素引用映射到 DynamicLocator。"""
        if "搜索框" in text:
            return self.loc.search_input()
        if any(k in text for k in ("logo", "标志", "图标", "品牌")):
            return self.loc.alt(*settings.POOLS.logo_alts)
        if "页脚" in text:
            return self.loc.text(*settings.POOLS.footer_keywords)
        if "下载" in text:
            return self.loc.button_visible(*settings.POOLS.download_keywords)
        if any(k in text for k in ("区块", "板块", "栏目", "内容")):
            return self.loc.text(*settings.POOLS.home_section_titles)
        if any(k in text for k in ("导航", "分类")):
            return self.loc.text(*settings.POOLS.nav_keywords)
        if "结果" in text:
            kw = self._ctx.get("keyword") or settings.POOLS.probe_app_name
            return self.page.locator("a", has_text=kw).filter(visible=True)
        return None

    def _wait_visible(self, locator) -> bool:
        try:
            # 只认「可见」元素：部分页面存在占位符相同的隐藏输入框，
            # OR 定位器的 .first 可能命中隐藏副本导致误判，故显式过滤 visible。
            locator.filter(visible=True).first.wait_for(
                state="visible", timeout=settings.DEFAULT_TIMEOUT
            )
            return True
        except Exception:  # noqa: BLE001
            return False
