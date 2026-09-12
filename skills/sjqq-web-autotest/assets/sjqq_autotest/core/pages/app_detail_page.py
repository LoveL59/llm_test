"""应用详情页页面对象。"""

from __future__ import annotations

import config.settings as settings
from core.pages.base_page import BasePage


class AppDetailPage(BasePage):
    def expect_loaded(self, keyword: str | None = None, timeout: int | None = None) -> None:
        """断言详情页已加载：应出现（可见的）下载按钮；可选校验应用名可见。"""
        t = timeout or settings.DEFAULT_TIMEOUT
        self.loc.button_visible(*settings.POOLS.download_keywords).first.wait_for(
            state="visible", timeout=t
        )
        if keyword:
            self.wait_text_visible(keyword, timeout=t)

    @property
    def has_download_button(self) -> bool:
        return self.loc.button_visible(*settings.POOLS.download_keywords).first.is_visible()

    def click_download(self) -> None:
        self.loc.button_visible(*settings.POOLS.download_keywords).first.click()
