"""gui.WallpaperApp 定时与下载结果逻辑的特征测试（characterization test）。

这些测试固定的是**当前**行为，而不是理想行为——目的是在后续把这段逻辑
抽成 core/scheduler.py 与 services/downloader.py 时，能够证明语义没有漂移。

所有用例都通过 ``object.__new__`` 绕过 WallpaperApp.__init__，
因此不会启动下载线程、托盘图标、全局热键或 Tk 窗口。
"""
import queue
import time
import unittest
import unittest.mock as mock

from tests.helpers import IsolatedDataDir, default_cfg, make_bare_app
import config

NOW = 1_700_000_000.0


class FakeRoot:
    """记录 after() 调用的假 Tk root，避免递归重排定时器。"""

    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        return "after-id"


class FavoriteBehaviorTest(unittest.TestCase):
    def test_new_style_key_wins(self):
        for behavior in ("pause", "carousel", "online"):
            with self.subTest(behavior=behavior):
                app = make_bare_app(default_cfg(favorite_behavior=behavior))
                self.assertEqual(app._favorite_behavior(), behavior)

    def test_legacy_true_maps_to_carousel(self):
        cfg = default_cfg(favorite_behavior=None, favorite_carousel=True)
        app = make_bare_app(cfg)
        self.assertEqual(app._favorite_behavior(), "carousel")

    def test_legacy_false_maps_to_online(self):
        cfg = default_cfg(favorite_behavior=None, favorite_carousel=False)
        app = make_bare_app(cfg)
        self.assertEqual(app._favorite_behavior(), "online")

    def test_unknown_value_falls_back_to_online(self):
        app = make_bare_app(default_cfg(favorite_behavior="nonsense"))
        self.assertEqual(app._favorite_behavior(), "online")


class ResetRefreshTimerTest(unittest.TestCase):
    def test_online_uses_interval_minutes(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app._next_refresh_time, NOW + 30 * 60)

    def test_zero_interval_disables_refresh(self):
        app = make_bare_app(default_cfg(interval_minutes=0))
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app._next_refresh_time, float("inf"))

    def test_favorite_pause_uses_infinity(self):
        app = make_bare_app(default_cfg(interval_minutes=30, favorite_behavior="pause"), mode="favorite")
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app._next_refresh_time, float("inf"))

    def test_favorite_carousel_keeps_interval(self):
        app = make_bare_app(default_cfg(interval_minutes=15, favorite_behavior="carousel"), mode="favorite")
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app._next_refresh_time, NOW + 15 * 60)

    def test_favorite_online_behavior_keeps_interval(self):
        app = make_bare_app(default_cfg(interval_minutes=15, favorite_behavior="online"), mode="favorite")
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app._next_refresh_time, NOW + 15 * 60)

    def test_pause_only_applies_in_favorite_mode(self):
        app = make_bare_app(default_cfg(interval_minutes=30, favorite_behavior="pause"), mode="online")
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app._next_refresh_time, NOW + 30 * 60)


class FailureBackoffTest(unittest.TestCase):
    def test_exponential_growth(self):
        expected = {1: 30, 2: 60, 3: 120, 4: 240, 5: 480}
        for failures, wait in expected.items():
            with self.subTest(failures=failures):
                app = make_bare_app(default_cfg(interval_minutes=30))
                app._consecutive_failures = failures
                with mock.patch("time.time", return_value=NOW):
                    app._schedule_failure_backoff(reset=False)
                self.assertEqual(app._next_refresh_time, NOW + wait)

    def test_capped_at_base_interval(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app._consecutive_failures = 20
        with mock.patch("time.time", return_value=NOW):
            app._schedule_failure_backoff(reset=False)
        self.assertEqual(app._next_refresh_time, NOW + 30 * 60)

    def test_base_floor_is_60_seconds_when_interval_is_zero(self):
        # interval_minutes=0 时 base = max(60, 0) = 60，所以退避上限只有 60 秒
        app = make_bare_app(default_cfg(interval_minutes=0))
        app._consecutive_failures = 20
        with mock.patch("time.time", return_value=NOW):
            app._schedule_failure_backoff(reset=False)
        self.assertEqual(app._next_refresh_time, NOW + 60)

    def test_reset_clears_counter_and_waits_30s(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app._consecutive_failures = 5
        with mock.patch("time.time", return_value=NOW):
            app._schedule_failure_backoff(reset=True)
        self.assertEqual(app._consecutive_failures, 0)
        self.assertEqual(app._next_refresh_time, NOW + 30)


class CountdownTextTest(unittest.TestCase):
    def _text(self, app, now=NOW):
        with mock.patch("time.time", return_value=now):
            app._update_countdown()
        return app.countdown_var.last

    def test_downloading_takes_priority(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app.is_downloading = True
        app._next_refresh_time = NOW + 100
        self.assertEqual(self._text(app), "正在获取下一张壁纸…")

    def test_favorite_pause_message(self):
        app = make_bare_app(default_cfg(interval_minutes=30, favorite_behavior="pause"), mode="favorite")
        app._next_refresh_time = float("inf")
        self.assertEqual(self._text(app), "收藏模式：已暂停自动刷新")

    def test_disabled_message(self):
        app = make_bare_app(default_cfg(interval_minutes=0))
        self.assertEqual(self._text(app), "自动刷新：已关闭")

    def test_formats_remaining_time(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app._next_refresh_time = NOW + 125
        self.assertEqual(self._text(app), "下次刷新：02:05")

    def test_clamps_past_deadline_to_zero(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app._next_refresh_time = NOW - 500
        self.assertEqual(self._text(app), "下次刷新：00:00")

    @unittest.expectedFailure
    def test_infinite_deadline_does_not_crash(self):
        # 已知脆弱点：_update_countdown 用 int() 换算剩余秒数，而 _next_refresh_time
        # 在「收藏暂停」与「间隔为 0」两种情况下会被设成 inf。
        # 目前这两个前提各自有前置守卫挡着（is_downloading / favorite+pause /
        # interval<=0），所以 GUI 走不到这一行；但守卫条件与 inf 的产生条件是两处
        # 独立重复的判断，一旦将来新增第三种 inf 情况就会 OverflowError 崩在
        # 定时器回调里。Phase 4 抽出 RefreshScheduler 时改成显式 isinf 判断，
        # 届时删掉这个装饰器。
        app = make_bare_app(default_cfg(interval_minutes=30))  # mode=online
        app._next_refresh_time = float("inf")
        self._text(app)


class DownloadResultTest(unittest.TestCase):
    def test_success_updates_state_and_status(self):
        with IsolatedDataDir():
            app = make_bare_app(default_cfg(interval_minutes=30))
            app._consecutive_failures = 3
            with mock.patch("time.time", return_value=NOW), \
                    mock.patch.object(config, "save_config"):
                app._download_result(True, "C:/cache/a.png", "konachan", "Konachan")
        self.assertFalse(app.is_downloading)
        self.assertEqual(app.current_applied_wallpaper, "C:/cache/a.png")
        self.assertEqual(app.mode, "online")
        self.assertEqual(app._consecutive_failures, 0)
        self.assertEqual(app._next_refresh_time, NOW + 30 * 60)
        self.assertEqual(app.status_log[-1][1], "ready")
        self.assertIn("Konachan", app.status_log[-1][0])
        # 回退到别的图源后记录最终成功图源
        self.assertEqual(app.cfg["source_id"], "konachan")

    def test_success_with_same_source_does_not_rewrite_config(self):
        with IsolatedDataDir():
            app = make_bare_app(default_cfg(interval_minutes=30, source_id="all"))
            with mock.patch("time.time", return_value=NOW), \
                    mock.patch.object(config, "save_config") as saver:
                app._download_result(True, "C:/cache/a.png", "all", "全部")
        saver.assert_not_called()

    def test_success_without_source_id_does_not_rewrite_config(self):
        with IsolatedDataDir():
            app = make_bare_app(default_cfg(interval_minutes=30))
            with mock.patch("time.time", return_value=NOW), \
                    mock.patch.object(config, "save_config") as saver:
                app._download_result(True, "C:/cache/a.png")
        saver.assert_not_called()

    def test_failure_increments_counter_and_reports_error(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        with mock.patch("time.time", return_value=NOW):
            app._download_result(False, "全部图源都失败了")
        self.assertFalse(app.is_downloading)
        self.assertEqual(app._consecutive_failures, 1)
        self.assertEqual(app._next_refresh_time, NOW + 30)
        self.assertEqual(app.status_log[-1][1], "error")
        self.assertIn("全部图源都失败了", app.status_log[-1][0])

    def test_repeated_failures_back_off_further(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        waits = []
        with mock.patch("time.time", return_value=NOW):
            for _ in range(3):
                app._download_result(False, "失败")
                waits.append(app._next_refresh_time - NOW)
        self.assertEqual(waits, [30, 60, 120])

    def test_reenables_next_button_on_both_paths(self):
        with IsolatedDataDir():
            for success in (True, False):
                with self.subTest(success=success):
                    app = make_bare_app(default_cfg(interval_minutes=30))
                    app.is_downloading = True
                    with mock.patch("time.time", return_value=NOW), \
                            mock.patch.object(config, "save_config"):
                        app._download_result(success, "x")
                    self.assertEqual(app.next_btn.calls[-1]["state"], "normal")


class TimerLoopDispatchTest(unittest.TestCase):
    def _app(self, **cfg_overrides):
        app = make_bare_app(default_cfg(**cfg_overrides))
        app.root = FakeRoot()
        app._ui_queue = queue.Queue()
        app.actions = []
        app.fetch_and_set_wallpaper = lambda: app.actions.append("online")
        app._cycle_favorite = lambda: app.actions.append("carousel")
        app.results = []
        app._download_result = lambda success, payload, sid=None, name=None: app.results.append((success, payload, sid, name))
        return app

    @staticmethod
    def _not_due(app):
        """把下次刷新推到很远的未来，模拟"还没到时间"。

        刻意不用 float("inf")：真实运行里 inf 只在"收藏暂停/不自动更换"时出现，
        而那时 _update_countdown 有守卫提前返回；这里只是想让调度判定为未到期。
        """
        app._next_refresh_time = time.time() + 10 ** 6

    def test_reschedules_itself_every_second(self):
        app = self._app()
        self._not_due(app)
        app.timer_loop()
        self.assertEqual(app.root.after_calls, [(1000, app.timer_loop)])

    def test_stops_when_closing(self):
        app = self._app()
        app._closing = True
        app.timer_loop()
        self.assertEqual(app.root.after_calls, [])

    def test_drains_success_events(self):
        app = self._app()
        self._not_due(app)
        app._ui_queue.put(("success", "C:/a.png", "all", "全部"))
        app.timer_loop()
        self.assertEqual(app.results, [(True, "C:/a.png", "all", "全部")])

    def test_drains_error_events(self):
        app = self._app()
        self._not_due(app)
        app._ui_queue.put(("error", "全都失败了"))
        app.timer_loop()
        self.assertEqual(app.results, [(False, "全都失败了", None, None)])

    def test_drains_all_pending_events(self):
        app = self._app()
        self._not_due(app)
        app._ui_queue.put(("success", "a", "all", "n"))
        app._ui_queue.put(("error", "b"))
        app.timer_loop()
        self.assertEqual(len(app.results), 2)

    def test_not_due_does_nothing(self):
        app = self._app(interval_minutes=30)
        with mock.patch("time.time", return_value=NOW):
            app._next_refresh_time = NOW + 60
            app.timer_loop()
        self.assertEqual(app.actions, [])

    def test_due_online_triggers_download(self):
        app = self._app(interval_minutes=30)
        with mock.patch("time.time", return_value=NOW):
            app._next_refresh_time = NOW - 1
            app.timer_loop()
        self.assertEqual(app.actions, ["online"])

    def test_due_favorite_pause_suspends_without_action(self):
        app = self._app(interval_minutes=30, favorite_behavior="pause")
        app.mode = "favorite"
        with mock.patch("time.time", return_value=NOW):
            app._next_refresh_time = NOW - 1
            app.timer_loop()
        self.assertEqual(app.actions, [])
        self.assertEqual(app._next_refresh_time, float("inf"))

    def test_due_favorite_carousel_cycles(self):
        app = self._app(interval_minutes=30, favorite_behavior="carousel")
        app.mode = "favorite"
        with mock.patch("time.time", return_value=NOW):
            app._next_refresh_time = NOW - 1
            app.timer_loop()
        self.assertEqual(app.actions, ["carousel"])

    def test_downloading_blocks_dispatch_but_still_reschedules(self):
        app = self._app(interval_minutes=30)
        app.is_downloading = True
        with mock.patch("time.time", return_value=NOW):
            app._next_refresh_time = NOW - 1
            app.timer_loop()
        self.assertEqual(app.actions, [])
        self.assertEqual(len(app.root.after_calls), 1)


class SelectCandidatesTest(unittest.TestCase):
    def test_selected_source_is_used(self):
        from source_manager import SourceManager
        app = make_bare_app(default_cfg(source_id="yandere"))
        app.source_manager = SourceManager(app.cfg)
        self.assertEqual(app._selected_source()["id"], "yandere")

    def test_unknown_selection_falls_back_to_all(self):
        from source_manager import SourceManager
        app = make_bare_app(default_cfg(source_id="ghost"))
        app.source_manager = SourceManager(app.cfg)
        self.assertEqual(app._selected_source()["id"], "all")


class FetchAndSetWallpaperGuardTest(unittest.TestCase):
    def test_no_enabled_candidates_reports_immediately(self):
        from source_manager import SourceManager
        app = make_bare_app(default_cfg(source_id="ghost"))
        app.source_manager = SourceManager(app.cfg)

        class EmptyManager:
            def get(self, _sid):
                return None

            def enabled_candidates(self, _sid=None):
                return []

        app.source_manager = EmptyManager()
        app.next_btn = app.next_btn
        app._download_result = lambda success, payload, sid=None, name=None: app.status_log.append(("result", success, payload))
        started = []
        with mock.patch("threading.Thread", side_effect=lambda **kw: started.append(kw)):
            app.fetch_and_set_wallpaper()
        self.assertEqual(started, [], "没有候选图源时不应启动线程")
        self.assertEqual(app.status_log[-1], ("result", False, "没有启用的图源"))


if __name__ == "__main__":
    unittest.main()
