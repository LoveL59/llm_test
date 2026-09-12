"""应用宝首页页面对象。继承 BasePage，复用通用动作。"""

from __future__ import annotations

import config.settings as settings
from core.pages.base_page import BasePage


class HomePage(BasePage):
    URL = settings.BASE_URL

    # -- 业务动作（基于动态识别，文案变化不影响定位）----------------------
    def search(self, keyword: str) -> "SearchPage":
        """在搜索框输入关键词并提交，跳转到搜索结果页。

        提交方式：在输入框上直接 press Enter（与实测一致可触发跳转），
        并以 URL 包含 /search 作为跳转完成的可靠信号。
        """
        self.fill_search(keyword)
        self.loc.search_input().first.press("Enter")
        self.page.wait_for_function(
            "() => location.href.includes('/search')",
            timeout=settings.DEFAULT_TIMEOUT,
        )
        self.page.wait_for_load_state("domcontentloaded")
        from core.pages.search_page import SearchPage

        return SearchPage(self.page)

    # -- 存在性探针（供断言使用）-----------------------------------------
    def logo_visible(self) -> bool:
        """品牌 logo 可见（任一候选 alt 命中且可见即通过，取首个可见元素）。"""
        loc = self.loc.alt(*settings.POOLS.logo_alts)
        for i in range(loc.count()):
            if loc.nth(i).is_visible():
                return True
        return False

    def nav_present(self) -> bool:
        return self.loc.count_any(*settings.POOLS.nav_keywords) > 0

    def has_section(self) -> bool:
        return self.loc.count_any(*settings.POOLS.home_section_titles) > 0

    def click_nav(self, keyword: str | None = None) -> None:
        """点击顶部导航/分类中的某个关键词（默认点第一个可见候选）。

        用于分类导航用例；点击后页面通常会切换到对应分类内容。
        """
        if keyword:
            target = self.loc.text(keyword).first
        else:
            # 取第一个可见的导航候选
            for kw in settings.POOLS.nav_keywords:
                if self.loc.text(kw).first.is_visible():
                    target = self.loc.text(kw).first
                    break
            else:
                raise AssertionError("未找到任何可见的导航关键词")
        target.click()
        self.page.wait_for_load_state("domcontentloaded")
