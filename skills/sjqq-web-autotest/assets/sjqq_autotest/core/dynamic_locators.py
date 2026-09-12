"""动态识别核心引擎（可复用插件）。

痛点：被测页面 UI 元素（文案、结构、class）会随版本迭代变化，传统硬编码
CSS/XPath 极易失效。本模块提供 DynamicLocator：用 Playwright 的
user-facing locator（get_by_text / get_by_role / get_by_placeholder ...）
+ 「多候选 OR」策略，对单个语义目标给出一组等价定位，只要任一候选命中即可，
从而显著提升用例对页面改版的容错能力。

用法示例：
    loc = DynamicLocator(page)
    # 搜索框：placeholder 可能是多种文案之一
    search_box = loc.placeholder("搜索应用、游戏、小说等", "搜索", "应用搜索")
    await search_box.fill("微信")
    # 点击任意包含"下载"的按钮
    await loc.button("下载", "立即下载").first.click()
"""

from __future__ import annotations

import config.settings as settings
from playwright.sync_api import Locator, Page


class DynamicLocator:
    """抗 DOM 变化的动态定位器。所有方法返回 Playwright Locator。"""

    def __init__(self, page: Page) -> None:
        self.page = page

    # -- 内部工具 ----------------------------------------------------------
    @staticmethod
    def _or(locators: list[Locator]) -> Locator:
        """将多个候选 Locator 用 OR 合并为单个容错 Locator。"""
        if not locators:
            raise ValueError("DynamicLocator: 至少需要一个候选定位器")
        combined = locators[0]
        for loc in locators[1:]:
            combined = combined.or_(loc)
        return combined

    # -- 语义定位（优先使用，最抗变化）-----------------------------------
    def text(self, *candidates: str, exact: bool = False) -> Locator:
        """按可见文本定位，支持多个候选（命中任一即可）。

        exact=False 时使用子串/忽略大小写匹配，容错更强；
        exact=True 时要求整段文本精确相等（用于需要严格区分的场景）。
        """
        return self._or([self.page.get_by_text(c, exact=exact) for c in candidates])

    def role(self, role: str, *names: str) -> Locator:
        """按可访问性角色 + 名称定位（如 button / link / heading）。"""
        return self._or([self.page.get_by_role(role, name=n) for n in names])

    def placeholder(self, *candidates: str) -> Locator:
        """按输入框 placeholder 定位。"""
        return self._or([self.page.get_by_placeholder(c) for c in candidates])

    def search_input(self) -> Locator:
        """定位搜索框（多重容错）：

        1) 优先按 placeholder 候选（如"元宝"/"搜索..."）；
        2) 兜底按 class 含 search 关键字的 <input>（应对 CSS-module 哈希 class）；
        3) 再兜底取首个文本输入框。
        任一命中即可，极大降低因搜索框重命名导致的失效。
        """
        candidates = [self.placeholder(*settings.POOLS.search_placeholders)]
        candidates.append(self.page.locator("input[class*='search' i]"))
        candidates.append(self.page.locator("input[type='text']").first)
        return self._or(candidates)

    def alt(self, *candidates: str) -> Locator:
        """按图片 alt 文本定位（如 logo）。"""
        return self._or([self.page.get_by_alt_text(c) for c in candidates])

    def label(self, *candidates: str) -> Locator:
        """按表单 label 文本定位。"""
        return self._or([self.page.get_by_label(c) for c in candidates])

    # -- 常用组合快捷方式 --------------------------------------------------
    def button(self, *candidates: str) -> Locator:
        """定位按钮/链接（a 或 button 元素，文本含候选词）。

        说明：站点下载 CTA 可能是 <button>、带 href 的 <a>，也可能是不带 href
        的 <a>（无 link 角色）。用 "a, button + 文本" 定位可覆盖所有情况，比仅按
        role=button/link 更稳。
        """
        locators = [self.page.locator("a, button", has_text=c) for c in candidates]
        return self._or(locators)

    def button_visible(self, *candidates: str) -> Locator:
        """仅匹配"可见"的按钮/链接（避免 .first 命中隐藏元素导致等待超时）。"""
        locators = [
            self.page.locator("a, button", has_text=c).filter(visible=True)
            for c in candidates
        ]
        return self._or(locators)

    def link(self, *candidates: str) -> Locator:
        """按链接文本定位。"""
        return self.role("link", *candidates)

    def heading(self, *candidates: str) -> Locator:
        """按标题文本定位。"""
        return self.role("heading", *candidates)

    # -- 容错探测 ---------------------------------------------------------
    def count_any(self, *candidates: str) -> int:
        """统计页面上可见且匹配任一候选文本的元素总数（用于存在性断言）。"""
        total = 0
        for c in candidates:
            total += self.page.get_by_text(c).count()
        return total
