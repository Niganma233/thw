"""WallpaperApp 与调度器 / 下载 worker 的接线。

计时策略本身在 tests/test_scheduler.py，回退循环在 tests/test_wallpaper_worker.py；
这里只验证 App 把两者接对了：状态怎么改、什么时候起线程、到点了分发哪条分支。
"""
import queue
import time
import unittest
import unittest.mock as mock

import config
from core.scheduler import ACTION_NONE, BEHAVIOR_CAROUSEL, BEHAVIOR_PAUSE, MODE_FAVORITE
from tests.helpers import IsolatedDataDir, default_cfg, make_bare_app

NOW = 1_700_000_000.0


class FakeRoot:
    """记录 after() 调用的假 Tk root，避免定时器递归重排。"""

    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        return "after-id"


class DownloadResultTest(unittest.TestCase):
    def test_success_updates_state_and_status(self):
        with IsolatedDataDir():
            app = make_bare_app(default_cfg(interval_minutes=30))
            app.scheduler.consecutive_failures = 3
            with mock.patch("time.time", return_value=NOW), \
                    mock.patch.object(config, "save_config"):
                app._download_result(True, "C:/cache/a.png", "konachan", "Konachan")
        self.assertFalse(app.is_downloading)
        self.assertEqual(app.current_applied_wallpaper, "C:/cache/a.png")
        self.assertEqual(app.mode, "online")
        self.assertEqual(app.scheduler.consecutive_failures, 0)
        self.assertEqual(app.scheduler.next_refresh_time, NOW + 30 * 60)
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
        self.assertEqual(app.scheduler.consecutive_failures, 1)
        self.assertEqual(app.scheduler.next_refresh_time, NOW + 30)
        self.assertEqual(app.status_log[-1][1], "error")
        self.assertIn("全部图源都失败了", app.status_log[-1][0])

    def test_repeated_failures_back_off_further(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        waits = []
        with mock.patch("time.time", return_value=NOW):
            for _ in range(3):
                app._download_result(False, "失败")
                waits.append(app.scheduler.next_refresh_time - NOW)
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


class CountdownDelegationTest(unittest.TestCase):
    def test_countdown_comes_from_the_scheduler(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app.scheduler.next_refresh_time = NOW + 125
        with mock.patch("time.time", return_value=NOW):
            app._update_countdown()
        self.assertEqual(app.countdown_var.last, "下次刷新：02:05")

    def test_downloading_state_is_passed_to_the_scheduler(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app.is_downloading = True
        app._update_countdown()
        self.assertEqual(app.countdown_var.last, "正在获取下一张壁纸…")


class ResetRefreshTimerTest(unittest.TestCase):
    def test_reads_interval_from_cfg(self):
        app = make_bare_app(default_cfg(interval_minutes=45))
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app.scheduler.next_refresh_time, NOW + 45 * 60)

    def test_picks_up_a_changed_interval(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app.cfg["interval_minutes"] = 5
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app.scheduler.next_refresh_time, NOW + 5 * 60)

    def test_picks_up_legacy_behavior_from_cfg(self):
        app = make_bare_app(default_cfg(interval_minutes=30, favorite_behavior=None, favorite_carousel=True))
        app.mode = MODE_FAVORITE
        with mock.patch("time.time", return_value=NOW):
            app.reset_refresh_timer()
        self.assertEqual(app.scheduler.next_refresh_time, NOW + 30 * 60)


class ModePropertyTest(unittest.TestCase):
    def test_mode_is_stored_on_the_scheduler(self):
        app = make_bare_app()
        app.mode = MODE_FAVORITE
        self.assertEqual(app.scheduler.mode, MODE_FAVORITE)
        self.assertEqual(app.mode, MODE_FAVORITE)

    def test_favorite_pause_follows_mode_change(self):
        app = make_bare_app(default_cfg(interval_minutes=30, favorite_behavior=BEHAVIOR_PAUSE))
        self.assertFalse(app.scheduler.paused)
        app.mode = MODE_FAVORITE
        self.assertTrue(app.scheduler.paused)

    def test_on_favorite_behavior_changed_updates_scheduler(self):
        app = make_bare_app(default_cfg(interval_minutes=30, favorite_behavior=BEHAVIOR_PAUSE))
        app.mode = MODE_FAVORITE
        with mock.patch("time.time", return_value=NOW):
            app.on_favorite_behavior_changed(BEHAVIOR_CAROUSEL)
        self.assertEqual(app.scheduler.favorite_behavior, BEHAVIOR_CAROUSEL)
        self.assertFalse(app.scheduler.paused)
        self.assertEqual(app.scheduler.next_refresh_time, NOW + 30 * 60)
        self.assertEqual(app.cfg["favorite_behavior"], BEHAVIOR_CAROUSEL)
        self.assertTrue(app.cfg["favorite_carousel"])

    def test_on_favorite_behavior_changed_rejects_unknown_value(self):
        app = make_bare_app(default_cfg(interval_minutes=30))
        app.mode = MODE_FAVORITE
        with mock.patch("time.time", return_value=NOW):
            app.on_favorite_behavior_changed("nonsense")
        self.assertEqual(app.cfg["favorite_behavior"], BEHAVIOR_PAUSE)


class FetchAndSetWallpaperTest(unittest.TestCase):
    def _app(self, source_id="all"):
        app = make_bare_app(default_cfg(source_id=source_id))
        app.downloader = mock.Mock()
        return app

    def test_no_enabled_candidates_reports_immediately(self):
        app = self._app()

        class EmptyManager:
            def get(self, _sid):
                return None

            def enabled_candidates(self, _sid=None):
                return []

        app.source_manager = EmptyManager()
        app.fetch_and_set_wallpaper()
        self.assertEqual(app.status_log[-1], ("换图失败：没有启用的图源", "error"))
        app.downloader.start.assert_not_called()
        self.assertFalse(app.is_downloading)

    def test_candidates_are_handed_to_the_worker(self):
        from source_manager import SourceManager
        app = self._app()
        app.source_manager = SourceManager(app.cfg)
        app.fetch_and_set_wallpaper()
        app.downloader.start.assert_called_once()
        candidates = app.downloader.start.call_args.args[0]
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["id"], "all")
        self.assertTrue(app.is_downloading)
        self.assertEqual(app.next_btn.calls[-1]["state"], "disabled")
        self.assertEqual(app.status_log[-1], ("正在下载新壁纸…", "busy"))

    def test_reraises_nothing_when_already_downloading(self):
        app = self._app()
        app.source_manager = mock.Mock()
        app.is_downloading = True
        app.fetch_and_set_wallpaper()
        app.downloader.start.assert_not_called()
        app.source_manager.enabled_candidates.assert_not_called()

    def test_does_nothing_while_closing(self):
        app = self._app()
        app.source_manager = mock.Mock()
        app._closing = True
        app.fetch_and_set_wallpaper()
        app.downloader.start.assert_not_called()


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
        app.scheduler.next_refresh_time = time.time() + 10 ** 6

    @staticmethod
    def _due(app):
        app.scheduler.next_refresh_time = time.time() - 1

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

    def test_unknown_event_is_ignored(self):
        app = self._app()
        self._not_due(app)
        app._ui_queue.put(("something-else", "x"))
        app.timer_loop()
        self.assertEqual(app.results, [])

    def test_not_due_does_nothing(self):
        app = self._app(interval_minutes=30)
        self._not_due(app)
        app.timer_loop()
        self.assertEqual(app.actions, [])

    def test_due_online_triggers_download(self):
        app = self._app(interval_minutes=30)
        self._due(app)
        app.timer_loop()
        self.assertEqual(app.actions, ["online"])

    def test_due_favorite_pause_suspends_without_action(self):
        app = self._app(interval_minutes=30, favorite_behavior=BEHAVIOR_PAUSE)
        app.mode = MODE_FAVORITE
        self._due(app)
        app.timer_loop()
        self.assertEqual(app.actions, [])
        self.assertEqual(app.scheduler.next_refresh_time, float("inf"))
        self.assertEqual(app.scheduler.next_action(), ACTION_NONE)

    def test_due_favorite_carousel_cycles(self):
        app = self._app(interval_minutes=30, favorite_behavior=BEHAVIOR_CAROUSEL)
        app.mode = MODE_FAVORITE
        self._due(app)
        app.timer_loop()
        self.assertEqual(app.actions, ["carousel"])

    def test_downloading_blocks_dispatch_but_still_reschedules(self):
        app = self._app(interval_minutes=30)
        app.is_downloading = True
        self._due(app)
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


if __name__ == "__main__":
    unittest.main()
