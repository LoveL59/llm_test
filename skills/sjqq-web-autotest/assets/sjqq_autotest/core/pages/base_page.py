"""页面对象基类 + 通用动作封装（重复步骤的可复用插件层）。

所有具体页面（首页/搜索页/详情页）都继承 BasePage，复用这里的导航、点击、
填写、等待、截图等动作，避免在每个用例里重复编写 Playwright 调用。
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

import config.settings as settings
from core.dynamic_locators import DynamicLocator


class BasePage:
    """所有页面对象的基类。"""

    # 子类可覆盖：进入该页面所需的 URL
    URL: str = settings.BASE_URL

    def __init__(self, page: Page) -> None:
        self.page = page
        self.loc = DynamicLocator(page)

    # -- 导航 -------------------------------------------------------------
    def goto(self, url: str | None = None, **kwargs) -> "BasePage":
        target = url or self.URL
        self.page.goto(target, wait_until="domcontentloaded", timeout=settings.NAVIGATION_TIMEOUT, **kwargs)
        return self

    def reload(self) -> "BasePage":
        self.page.reload(wait_until="domcontentloaded", timeout=settings.NAVIGATION_TIMEOUT)
        return self

    # -- 通用动作（重复步骤沉淀于此）-------------------------------------
    def click_text(self, *candidates: str, exact: bool = False, timeout: int | None = None) -> "BasePage":
        """点击任意匹配文本的可见元素（自动等待）。"""
        self.loc.text(*candidates, exact=exact).first.click(timeout=timeout or settings.DEFAULT_TIMEOUT)
        return self

    def click_button(self, *candidates: str, timeout: int | None = None) -> "BasePage":
        """点击任意匹配文本且可见的按钮/链接。"""
        self.loc.button_visible(*candidates).first.click(timeout=timeout or settings.DEFAULT_TIMEOUT)
        return self

    def fill_search(self, value: str, timeout: int | None = None) -> "BasePage":
        """在搜索框（动态识别，多候选容错）中填入关键词。

        注意：先 click 聚焦再 fill，确保 React 受控输入框正确触发输入事件，
        否则后续回车无法提交搜索（实测关键）。
        """
        box = self.loc.search_input().filter(visible=True).first
        box.wait_for(state="visible", timeout=timeout or settings.DEFAULT_TIMEOUT)
        box.click()
        box.fill(value)
        return self

    def press_enter(self) -> "BasePage":
        self.page.keyboard.press("Enter")
        return self

    def wait_text_visible(self, *candidates: str, timeout: int | None = None) -> "BasePage":
        """等待任一候选文本可见（用于「页面已加载某区块」断言）。"""
        self.loc.text(*candidates).first.wait_for(state="visible", timeout=timeout or settings.DEFAULT_TIMEOUT)
        return self

    def expect_text_visible(self, *candidates: str, timeout: int | None = None) -> None:
        """断言：页面上应当可见任一候选文本。"""
        expect(self.loc.text(*candidates).first).to_be_visible(timeout=timeout or settings.DEFAULT_TIMEOUT)

    def screenshot(self, path: str) -> str:
        """保存当前页面截图（相对项目根目录的路径）。"""
        self.page.screenshot(path=path, full_page=False)
        return path

    @property
    def current_url(self) -> str:
        return self.page.url

    @property
    def title(self) -> str:
        return self.page.title()
