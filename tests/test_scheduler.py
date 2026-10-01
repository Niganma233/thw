"""core.scheduler：换壁纸的定时策略。

这些用例原本是针对 ``gui.WallpaperApp`` 的特征测试（那时计时逻辑还混在界面类
里，只能靠 ``object.__new__`` 绕过构造来测）。Phase 4 抽出 RefreshScheduler 后
迁移到这里——不再需要任何 Tk 或 App 的脚手架。
"""
import unittest

from core.scheduler import (
    ACTION_CYCLE_FAVORITE,
    ACTION_FETCH,
    ACTION_NONE,
    BEHAVIOR_CAROUSEL,
    BEHAVIOR_ONLINE,
    BEHAVIOR_PAUSE,
    DISABLED_TEXT,
    DOWNLOADING_TEXT,
    HOLDING_TEXT,
    MODE_FAVORITE,
    MODE_ONLINE,
    PAUSED_TEXT,
    RefreshScheduler,
    resolve_favorite_behavior,
)

NOW = 1_700_000_000.0


def scheduler(interval_minutes=30, behavior=BEHAVIOR_PAUSE, mode=MODE_ONLINE):
    return RefreshScheduler(interval_minutes=interval_minutes, favorite_behavior=behavior, mode=mode)


class ResolveFavoriteBehaviorTest(unittest.TestCase):
    def test_new_style_key_wins(self):
        for behavior in (BEHAVIOR_PAUSE, BEHAVIOR_CAROUSEL, BEHAVIOR_ONLINE):
            with self.subTest(behavior=behavior):
                self.assertEqual(resolve_favorite_behavior({"favorite_behavior": behavior}), behavior)

    def test_legacy_true_maps_to_carousel(self):
        cfg = {"favorite_behavior": None, "favorite_carousel": True}
        self.assertEqual(resolve_favorite_behavior(cfg), BEHAVIOR_CAROUSEL)

    def test_legacy_false_maps_to_online(self):
        cfg = {"favorite_behavior": None, "favorite_carousel": False}
        self.assertEqual(resolve_favorite_behavior(cfg), BEHAVIOR_ONLINE)

    def test_missing_keys_default_to_online(self):
        self.assertEqual(resolve_favorite_behavior({}), BEHAVIOR_ONLINE)

    def test_unknown_value_falls_back_to_legacy_flag(self):
        self.assertEqual(
            resolve_favorite_behavior({"favorite_behavior": "nonsense", "favorite_carousel": True}),
            BEHAVIOR_CAROUSEL,
        )
        self.assertEqual(resolve_favorite_behavior({"favorite_behavior": "nonsense"}), BEHAVIOR_ONLINE)


class ResetTest(unittest.TestCase):
    def test_online_uses_interval_minutes(self):
        s = scheduler(interval_minutes=30)
        s.reset(NOW)
        self.assertEqual(s.next_refresh_time, NOW + 30 * 60)

    def test_zero_interval_disables_refresh(self):
        s = scheduler(interval_minutes=0)
        s.reset(NOW)
        self.assertEqual(s.next_refresh_time, float("inf"))

    def test_favorite_pause_suspends(self):
        s = scheduler(interval_minutes=30, behavior=BEHAVIOR_PAUSE, mode=MODE_FAVORITE)
        s.reset(NOW)
        self.assertEqual(s.next_refresh_time, float("inf"))
        self.assertTrue(s.paused)

    def test_favorite_carousel_keeps_interval(self):
        s = scheduler(interval_minutes=15, behavior=BEHAVIOR_CAROUSEL, mode=MODE_FAVORITE)
        s.reset(NOW)
        self.assertEqual(s.next_refresh_time, NOW + 15 * 60)
        self.assertFalse(s.paused)

    def test_favorite_online_behavior_keeps_interval(self):
        s = scheduler(interval_minutes=15, behavior=BEHAVIOR_ONLINE, mode=MODE_FAVORITE)
        s.reset(NOW)
        self.assertEqual(s.next_refresh_time, NOW + 15 * 60)

    def test_pause_only_applies_in_favorite_mode(self):
        s = scheduler(interval_minutes=30, behavior=BEHAVIOR_PAUSE, mode=MODE_ONLINE)
        s.reset(NOW)
        self.assertEqual(s.next_refresh_time, NOW + 30 * 60)

    def test_reset_does_not_touch_failure_count(self):
        s = scheduler()
        s.consecutive_failures = 4
        s.reset(NOW)
        self.assertEqual(s.consecutive_failures, 4)

    def test_interval_seconds_clamps_negative(self):
        self.assertEqual(scheduler(interval_minutes=-5).interval_seconds, 0)


class FailureBackoffTest(unittest.TestCase):
    def test_exponential_growth(self):
        expected = {1: 30, 2: 60, 3: 120, 4: 240, 5: 480}
        for failures, wait in expected.items():
            with self.subTest(failures=failures):
                s = scheduler(interval_minutes=30)
                s.consecutive_failures = failures - 1
                s.on_failure(NOW)
                self.assertEqual(s.next_refresh_time, NOW + wait)

    def test_increments_failure_count(self):
        s = scheduler()
        s.on_failure(NOW)
        s.on_failure(NOW)
        self.assertEqual(s.consecutive_failures, 2)

    def test_capped_at_interval(self):
        s = scheduler(interval_minutes=30)
        s.consecutive_failures = 19
        s.on_failure(NOW)
        self.assertEqual(s.next_refresh_time, NOW + 30 * 60)

    def test_base_floor_is_60_seconds_when_interval_is_zero(self):
        # 间隔为 0（不自动更换）时上限只有 60 秒——有点反直觉，但这是既有行为
        s = scheduler(interval_minutes=0)
        s.consecutive_failures = 19
        s.on_failure(NOW)
        self.assertEqual(s.next_refresh_time, NOW + 60)

    def test_success_clears_count_and_reschedules(self):
        s = scheduler(interval_minutes=30)
        s.consecutive_failures = 5
        s.on_success(NOW)
        self.assertEqual(s.consecutive_failures, 0)
        self.assertEqual(s.next_refresh_time, NOW + 30 * 60)


class CountdownTextTest(unittest.TestCase):
    def test_downloading_takes_priority(self):
        s = scheduler(interval_minutes=30)
        s.next_refresh_time = NOW + 100
        self.assertEqual(s.countdown_text(NOW, downloading=True), DOWNLOADING_TEXT)

    def test_favorite_pause_message(self):
        s = scheduler(interval_minutes=30, behavior=BEHAVIOR_PAUSE, mode=MODE_FAVORITE)
        s.reset(NOW)
        self.assertEqual(s.countdown_text(NOW), PAUSED_TEXT)

    def test_disabled_message(self):
        s = scheduler(interval_minutes=0)
        s.reset(NOW)
        self.assertEqual(s.countdown_text(NOW), DISABLED_TEXT)

    def test_formats_remaining_time(self):
        s = scheduler(interval_minutes=30)
        s.next_refresh_time = NOW + 125
        self.assertEqual(s.countdown_text(NOW), "下次刷新：02:05")

    def test_clamps_past_deadline_to_zero(self):
        s = scheduler(interval_minutes=30)
        s.next_refresh_time = NOW - 500
        self.assertEqual(s.countdown_text(NOW), "下次刷新：00:00")

    def test_infinite_deadline_does_not_crash(self):
        # Phase 0 用 expectedFailure 钉住的脆弱点：next_refresh_time 为 inf 时
        # 直接 int() 会 OverflowError，而这段代码跑在 Tk 定时器回调里。
        # 现在的实现显式判断 isinf，所以它不再抛异常。
        s = scheduler(interval_minutes=30, mode=MODE_ONLINE)
        s.next_refresh_time = float("inf")
        self.assertEqual(s.countdown_text(NOW), HOLDING_TEXT)

    def test_hour_long_countdown(self):
        s = scheduler(interval_minutes=240)
        s.next_refresh_time = NOW + 3 * 3600 + 59 * 60 + 59
        self.assertEqual(s.countdown_text(NOW), "下次刷新：239:59")


class NextActionTest(unittest.TestCase):
    def test_online_fetches(self):
        s = scheduler(mode=MODE_ONLINE)
        self.assertEqual(s.next_action(), ACTION_FETCH)

    def test_favorite_carousel_cycles(self):
        s = scheduler(behavior=BEHAVIOR_CAROUSEL, mode=MODE_FAVORITE)
        self.assertEqual(s.next_action(), ACTION_CYCLE_FAVORITE)

    def test_favorite_online_fetches(self):
        s = scheduler(behavior=BEHAVIOR_ONLINE, mode=MODE_FAVORITE)
        self.assertEqual(s.next_action(), ACTION_FETCH)

    def test_favorite_pause_does_nothing(self):
        s = scheduler(behavior=BEHAVIOR_PAUSE, mode=MODE_FAVORITE)
        self.assertEqual(s.next_action(), ACTION_NONE)

    def test_favorite_pause_does_not_mutate_state(self):
        # next_action 是纯查询，副作用留给显式的 suspend()
        s = scheduler(behavior=BEHAVIOR_PAUSE, mode=MODE_FAVORITE)
        s.next_refresh_time = NOW
        s.next_action()
        self.assertEqual(s.next_refresh_time, NOW)


class DueAndSuspendTest(unittest.TestCase):
    def test_is_due(self):
        s = scheduler(interval_minutes=30)
        s.reset(NOW)
        self.assertFalse(s.is_due(NOW + 1799))
        self.assertTrue(s.is_due(NOW + 1800))
        self.assertTrue(s.is_due(NOW + 5000))

    def test_never_due_after_suspend(self):
        s = scheduler(interval_minutes=1)
        s.reset(NOW)
        s.suspend()
        self.assertEqual(s.next_refresh_time, float("inf"))
        self.assertFalse(s.is_due(NOW + 10 ** 9))


if __name__ == "__main__":
    unittest.main()
