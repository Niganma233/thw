"""入口引导：theme / 单实例锁 / ensure_dirs / 启动主窗口的顺序与分支。

app.py 的装配由 tests/test_app_wiring.py 覆盖，这里只管 wallpaper_changer.main()
这一层引导——尤其是**顺序**：全局外观必须在任何控件创建之前设置好。
"""
import sys
import unittest
import unittest.mock as mock

import wallpaper_changer
from tests.helpers import IsolatedDataDir


class MainTest(unittest.TestCase):
    def _run(self, argv=None, acquired=True):
        """在打桩环境下跑一次 main()，返回调用顺序与各个打桩对象。"""
        events = []
        roots = []

        def make_root():
            # 返回一个固定的替身，否则无法断言"传给 WallpaperApp 的就是它"
            events.append("root")
            root = mock.MagicMock()
            roots.append(root)
            return root

        mocks = {}
        with mock.patch.object(sys, "argv", argv or ["wallpaper_changer.py"]), \
                mock.patch.object(wallpaper_changer.theme, "apply",
                                  side_effect=lambda: events.append("theme")), \
                mock.patch.object(wallpaper_changer.single_instance, "acquire",
                                  side_effect=lambda: (events.append("lock"), acquired)[1]), \
                mock.patch.object(wallpaper_changer, "ensure_dirs",
                                  side_effect=lambda: events.append("dirs")), \
                mock.patch.object(wallpaper_changer.ctk, "CTk", side_effect=make_root) as root_factory, \
                mock.patch.object(wallpaper_changer, "WallpaperApp") as app_cls, \
                mock.patch.object(wallpaper_changer, "_warn_already_running") as warn:
            wallpaper_changer.main()

        mocks.update(events=events, roots=roots, root_factory=root_factory, app_cls=app_cls, warn=warn)
        return mocks

    def test_theme_is_applied_before_the_root_window_exists(self):
        with IsolatedDataDir():
            result = self._run()
        self.assertEqual(result["events"], ["theme", "lock", "dirs", "root"])

    def test_startup_passes_the_root_window_and_silent_flag(self):
        with IsolatedDataDir():
            result = self._run()
        self.assertEqual(result["app_cls"].call_count, 1)
        self.assertEqual(result["app_cls"].call_args.kwargs["silent"], False)
        self.assertIs(result["app_cls"].call_args.args[0], result["roots"][0])

    def test_mainloop_is_entered(self):
        with IsolatedDataDir():
            result = self._run()
        result["roots"][0].mainloop.assert_called_once()

    def test_silent_flag_is_read_from_argv(self):
        with IsolatedDataDir():
            result = self._run(argv=["wallpaper_changer.py", "--silent"])
        self.assertTrue(result["app_cls"].call_args.kwargs["silent"])

    def test_second_instance_does_not_start_the_app(self):
        with IsolatedDataDir():
            result = self._run(acquired=False)
        result["app_cls"].assert_not_called()
        result["root_factory"].assert_not_called()
        result["warn"].assert_called_once()

    def test_second_instance_in_silent_mode_does_not_warn(self):
        with IsolatedDataDir():
            result = self._run(argv=["wallpaper_changer.py", "--silent"], acquired=False)
        result["warn"].assert_not_called()

    def test_second_instance_does_not_create_directories(self):
        # 被拒绝启动时不留痕迹
        with IsolatedDataDir():
            result = self._run(acquired=False)
        self.assertNotIn("dirs", result["events"])


if __name__ == "__main__":
    unittest.main()
