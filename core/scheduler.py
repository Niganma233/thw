"""换壁纸的定时策略。

负责四件事，全部是纯逻辑——只依赖调用方传入的 ``now``，不读时钟、不碰 Tk、
不碰网络，因此可以直接单测：

1. 下次该在什么时候刷新（间隔、收藏暂停、间隔为 0 关闭）；
2. 下载失败后的指数退避；
3. 到点之后该做什么（在线换图 / 收藏轮播 / 什么都不做）；
4. 状态栏的倒计时文案。

这段逻辑历史上最容易出问题——git log 里"星标轮播计时"修过三次——把它从界面类
里拿出来单独测试，是这次重构收益最大的一步。
"""
import math

# 运行模式
MODE_ONLINE = "online"
MODE_FAVORITE = "favorite"

# 收藏之后的自动刷新行为
BEHAVIOR_PAUSE = "pause"
BEHAVIOR_CAROUSEL = "carousel"
BEHAVIOR_ONLINE = "online"
BEHAVIORS = (BEHAVIOR_PAUSE, BEHAVIOR_CAROUSEL, BEHAVIOR_ONLINE)

# 到点之后要做什么
ACTION_NONE = "none"
ACTION_FETCH = "fetch"
ACTION_CYCLE_FAVORITE = "cycle_favorite"

# 失败退避：首次等 30 秒，之后翻倍，上限是刷新间隔（但至少 60 秒）
BACKOFF_FIRST_SECONDS = 30
BACKOFF_BASE_FLOOR = 60
SECONDS_PER_MINUTE = 60

# 状态栏文案
DOWNLOADING_TEXT = "正在获取下一张壁纸…"
PAUSED_TEXT = "收藏模式：已暂停自动刷新"
DISABLED_TEXT = "自动刷新：已关闭"
HOLDING_TEXT = "自动刷新：已暂停"


def resolve_favorite_behavior(cfg):
    """从配置里取"收藏之后的自动刷新行为"，兼容旧版的 ``favorite_carousel``。

    这个映射原本在两个地方各写了一份（gui 和 favorite_view），容易改漏。
    """
    behavior = cfg.get("favorite_behavior")
    if behavior in BEHAVIORS:
        return behavior
    return BEHAVIOR_CAROUSEL if cfg.get("favorite_carousel", False) else BEHAVIOR_ONLINE


class RefreshScheduler:
    """决定"什么时候换下一张壁纸"，不关心怎么换。"""

    def __init__(self, interval_minutes=30, favorite_behavior=BEHAVIOR_PAUSE, mode=MODE_ONLINE):
        self.interval_minutes = interval_minutes
        self.favorite_behavior = favorite_behavior
        self.mode = mode
        self.consecutive_failures = 0
        # 初始为无穷远：调用方应当在构造后立刻 reset(now) 定下第一个截止时间
        self.next_refresh_time = float("inf")

    # ---------- 查询 ----------
    @property
    def paused(self):
        """收藏模式下选择了"暂停自动刷新"。"""
        return self.mode == MODE_FAVORITE and self.favorite_behavior == BEHAVIOR_PAUSE

    @property
    def interval_seconds(self):
        return max(0, int(self.interval_minutes)) * SECONDS_PER_MINUTE

    def is_due(self, now):
        return now >= self.next_refresh_time

    def next_action(self):
        """到点之后该做什么。纯查询，不改任何状态。"""
        if self.paused:
            return ACTION_NONE
        if self.mode == MODE_FAVORITE and self.favorite_behavior == BEHAVIOR_CAROUSEL:
            return ACTION_CYCLE_FAVORITE
        return ACTION_FETCH

    def countdown_text(self, now, downloading=False):
        if downloading:
            return DOWNLOADING_TEXT
        if self.paused:
            return PAUSED_TEXT
        if int(self.interval_minutes) <= 0:
            return DISABLED_TEXT
        # 防御：next_refresh_time 可能是 inf，此时 int() 会抛 OverflowError，
        # 而这段代码跑在 Tk 的定时器回调里。上面的 paused 与 interval<=0 两条
        # 各自独立地把两种已知的 inf 来源挡住了，但那是两处重复判断；
        # 这里再显式挡一道，将来新增第三种 inf 情况也不会崩。
        if math.isinf(self.next_refresh_time):
            return HOLDING_TEXT
        remain = max(0, int(self.next_refresh_time - now))
        return f"下次刷新：{remain // 60:02d}:{remain % 60:02d}"

    # ---------- 命令 ----------
    def reset(self, now):
        """按当前模式与间隔重算下次刷新时间（不改变失败计数）。"""
        if self.paused or int(self.interval_minutes) <= 0:
            self.next_refresh_time = float("inf")
            return
        self.next_refresh_time = now + self.interval_seconds

    def suspend(self):
        """挂起计时：不再自动换图。"""
        self.next_refresh_time = float("inf")

    def on_success(self, now):
        """下载成功：清零失败计数并按间隔重排下一次。"""
        self.consecutive_failures = 0
        self.reset(now)

    def on_failure(self, now):
        """下载失败：指数退避，上限为刷新间隔（至少 60 秒）。

        间隔为 0（不自动更换）时上限是 60 秒——这是个有点反直觉但被测试钉住的
        既有行为。
        """
        self.consecutive_failures += 1
        base = max(BACKOFF_BASE_FLOOR, int(self.interval_minutes) * SECONDS_PER_MINUTE)
        exponent = max(0, self.consecutive_failures - 1)
        wait = min(BACKOFF_FIRST_SECONDS * (2 ** exponent), base)
        self.next_refresh_time = now + wait
