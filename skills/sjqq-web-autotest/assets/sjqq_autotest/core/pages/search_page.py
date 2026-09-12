"""搜索结果页页面对象。"""

from __future__ import annotations

import config.settings as settings
from core.pages.base_page import BasePage


class SearchPage(BasePage):
    def wait_results(self, keyword: str, timeout: int | None = None) -> None:
        """等待搜索结果出现并渲染完成。

        先等待结果页框架（关键词文本或"没有找到/暂无"等提示），再显式等待
        包含关键词的结果链接可见，确保结果卡片已渲染（避免断言时卡片尚未加载）。
        """
        t = timeout or settings.DEFAULT_TIMEOUT
        # 1) 结果页框架已加载
        frame_candidates = [keyword, "没有找到", "暂无", "相关应用", "搜索结果", "结果"]
        self.loc.text(*frame_candidates).first.wait_for(state="visible", timeout=t)

        # 2) 结果链接渲染完成（卡片为 <a> 元素，文本含关键词）
        try:
            self.page.locator("a", has_text=keyword).first.wait_for(
                state="visible", timeout=t
            )
        except Exception:  # noqa: BLE001
            # 允许"确实无结果"的场景，交由 results_count 断言决定成败
            pass

    def results_count(self, keyword: str) -> int:
        """统计包含关键词的可点击链接数量，作为"有结果"的量化指标。"""
        return self.page.locator("a", has_text=keyword).count()

    def open_first_result(self, keyword: str):
        """点击第一个应用结果进入详情页。

        优先按详情页链接特征（href 含 appdetail）定位，避开页面里其它含关键词
        的链接（如导航/推荐位）；兜底再退回"含关键词的第一个 <a>"。
        """
        link = self.page.locator("a[href*='appdetail']").first
        if link.count() == 0:
            link = self.page.locator("a", has_text=keyword).first
        link.click()
        self.page.wait_for_load_state("domcontentloaded")
        from core.pages.app_detail_page import AppDetailPage

        return AppDetailPage(self.page)
