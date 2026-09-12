"""全局配置：URL、超时、浏览器参数、动态识别候选词库。

设计目标：页面 UI 文案/结构可能变化，因此所有"易变"的定位信息都集中放
在 CANDIDATE_POOLS 中，以「多候选 OR」方式参与定位。后续页面改版时，
只需在此处增删候选词，无需改动用例代码。
"""

import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 基础环境配置
# ---------------------------------------------------------------------------
BASE_URL = "https://sj.qq.com/"

# 排行榜（热门榜）页面。PC 版应用宝该页会渲染「热门榜」并列出首位应用。
RANKING_URL = "https://sj.qq.com/rank"

# 默认超时（毫秒）。动态网页加载较慢，给足余量。
DEFAULT_TIMEOUT = 15000
NAVIGATION_TIMEOUT = 30000

# 浏览器启动参数（Windows/GitBash 环境常需 --no-sandbox）
BROWSER_ARGS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]

# 视口（桌面端基准）
VIEWPORT = {"width": 1366, "height": 768}

# 是否在失败时自动截图（截图保存到 reports/）
CAPTURE_ON_FAILURE = True

# ---------------------------------------------------------------------------
# 执行模式：有头 / 无头（供业务人员观看每一步时设为有头）
# ---------------------------------------------------------------------------
# HEADED=True  → 打开可见浏览器窗口，逐步操作可被人工观看（默认）。
# HEADED=False → 后台无头执行，适合 CI / 批量回归。
# 可用环境变量临时切换，无需改代码：
#   SJQQ_HEADED=0 关闭有头；SJQQ_HEADED=1 开启有头。
_HEADED_ENV = os.getenv("SJQQ_HEADED", "1").strip().lower()
HEADED: bool = _HEADED_ENV not in ("0", "false", "no", "off")

# slow_mo：每一步操作之间的停顿（毫秒），让人工能看清浏览器里的动作。
# 默认 1000ms（1 秒），便于业务/非自动化人员逐步观看；
# 想更快可用环境变量缩短，如 SJQQ_SLOWMO=300；CI/批量回归可用 SJQQ_SLOWMO=0。
try:
    SLOW_MO: int = int(os.getenv("SJQQ_SLOWMO", "1000"))
except ValueError:
    SLOW_MO = 1000


# ---------------------------------------------------------------------------
# 自然语言翻译（自由语言 → 受控动作）可选 LLM 增强
# ---------------------------------------------------------------------------
# 默认关闭：StepExecutor 用内置「启发式规则」离线理解自由中文，无需联网 / 密钥，
# 业务人员可直接在 cases.md 的 W 步骤里写任意中文（如「在搜索框输入微信并回车」）。
# 当由具备 LLM 的 agent 调用 translate_cases.py 做「业务 NL → 规范用例」批量翻译时，
# 可开启以获得更高准确率；未配置密钥时自动回退到启发式。
NL_USE_LLM: bool = os.getenv("SJQQ_NL_LLM", "0").strip().lower() in ("1", "true", "yes")
LLM_BASE_URL: str = os.getenv("SJQQ_LLM_BASE", "https://api.openai.com/v1")
LLM_API_KEY: str = os.getenv("SJQQ_LLM_KEY", "")
LLM_MODEL: str = os.getenv("SJQQ_LLM_MODEL", "gpt-4o-mini")


# ---------------------------------------------------------------------------
# 动态识别候选词库
# ---------------------------------------------------------------------------
# 每个字段是一组「同义/历史」候选，定位时取并集（OR）。
# 例：搜索框 placeholder 历史上可能是以下任意一种，只要命中其一即可。
@dataclass
class CandidatePools:
    # 搜索框 placeholder 候选（实测当前站点搜索框 placeholder 为"元宝"，
    # 但历史上/其他环境可能是通用文案，故保留多候选容错）
    search_placeholders: list = field(default_factory=lambda: [
        "元宝",
        "搜索应用、游戏、小说等",
        "搜索应用、游戏",
        "搜索",
        "应用搜索",
        "找应用、游戏",
    ])
    # 顶部导航/分类区可能出现的文案（用于校验导航存在）
    nav_keywords: list = field(default_factory=lambda: [
        "软件", "游戏", "应用", "榜单", "分类", "排行", "专题", "必备",
    ])
    # 品牌 logo 的 alt 文本候选（实测站点 logo alt 为以下完整文案之一，
    # 同时保留短词容错。get_by_alt_text 以子串/精确匹配，命中其一即可）
    logo_alts: list = field(default_factory=lambda: [
        "应用宝", "应用宝logo", "QQ应用宝", "腾讯应用宝",
        "应用宝电脑版", "应用宝2026官方新版图标", "扫码下载应用宝APP", "应用宝官网",
    ])
    # 首页应出现的区块标题候选（用于校验首页加载）
    home_section_titles: list = field(default_factory=lambda: [
        "精选", "推荐", "热门", "排行榜", "新品", "专题", "今日推荐",
        "榜", "游戏", "软件", "书籍", "下载",
    ])
    # 下载/客户端相关按钮文案
    download_keywords: list = field(default_factory=lambda: [
        "下载", "立即下载", "下载客户端", "PC版下载", "免费下载",
    ])
    # 页脚常见栏目
    footer_keywords: list = field(default_factory=lambda: [
        "关于我们", "联系我们", "商务合作", "隐私政策", "用户协议",
        "帮助中心", "侵权投诉", "友情链接",
    ])
    # 一个用于搜索验证的、长期稳定存在的应用名
    probe_app_name: str = "微信"


# 单例，供各 page object 直接引用
POOLS = CandidatePools()
