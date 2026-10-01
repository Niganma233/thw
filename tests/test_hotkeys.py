"""ui.hotkeys：全局快捷键的注册与注销。

必须把 ``ui.hotkeys.keyboard`` 换成替身：真的调用 ``keyboard.add_hotkey`` 会在
测试进程里挂上系统级热键，污染开发者的桌面。
"""
import unittest
import unittest.mock as mock

from tests.helpers import FakeKeyboard
from ui.hotkeys import HotkeyManager


class HotkeyManagerTest(unittest.TestCase):
    def setUp(self):
        self.keyboard = FakeKeyboard()
        patcher = mock.patch("ui.hotkeys.keyboard", self.keyboard)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.errors = []
        self.root = mock.Mock()
        self.manager = HotkeyManager(self.root, on_error=self.errors.append)

    def _bindings(self, *items):
        return list(items)

    def test_available_reflects_the_library(self):
        self.assertTrue(self.manager.available)

    def test_registers_non_empty_bindings(self):
        registered = self.manager.register([
            ("ctrl+shift+f", lambda: None, "收藏"),
            ("ctrl+shift+s", lambda: None, "切换"),
        ])
        self.assertEqual(registered, ["ctrl+shift+f", "ctrl+shift+s"])
        self.assertEqual([text for text, _ in self.keyboard.added], ["ctrl+shift+f", "ctrl+shift+s"])

    def test_skips_blank_hotkeys(self):
        registered = self.manager.register([
            ("", lambda: None, "收藏"),
            ("   ", lambda: None, "切换"),
            (None, lambda: None, "别的"),
        ])
        self.assertEqual(registered, [])
        self.assertEqual(self.keyboard.added, [])

    def test_strips_whitespace(self):
        self.manager.register([("  ctrl+shift+f  ", lambda: None, "收藏")])
        self.assertEqual(self.keyboard.added[0][0], "ctrl+shift+f")

    def test_stale_bindings_are_removed_before_registering(self):
        self.manager.register([("ctrl+shift+f", lambda: None, "收藏")])
        self.assertEqual(self.keyboard.unhook_count, 1, "注册前应当先清掉旧的")
        self.assertEqual(len(self.keyboard.added), 1)

    def test_invalid_hotkey_is_reported_and_others_still_register(self):
        self.keyboard.fail_on = "bad+key"
        registered = self.manager.register([
            ("bad+key", lambda: None, "收藏"),
            ("ctrl+shift+s", lambda: None, "切换"),
        ])
        self.assertEqual(registered, ["ctrl+shift+s"])
        self.assertEqual(len(self.errors), 1)
        self.assertIn("收藏", self.errors[0])
        self.assertIn("无效的快捷键", self.errors[0])

    def test_callbacks_are_marshalled_to_the_main_thread(self):
        # keyboard 的回调跑在它自己的监听线程里，直接碰 Tk 控件会崩。
        called = []
        self.manager.register([("ctrl+shift+f", lambda: called.append(True), "收藏")])
        _, marshalled = self.keyboard.added[0]
        marshalled()
        self.assertEqual(called, [], "不应直接执行原回调")
        self.root.after.assert_called_once_with(0, mock.ANY)
        # 主线程真正执行时才调用原回调
        self.root.after.call_args.args[1]()
        self.assertEqual(called, [True])

    def test_unregister_calls_unhook(self):
        self.manager.unregister()
        self.assertEqual(self.keyboard.unhook_count, 1)

    def test_unregister_swallows_errors(self):
        self.keyboard.unhook_all_hotkeys = mock.Mock(side_effect=RuntimeError("炸了"))
        self.manager.unregister()  # 不应抛出

    def test_missing_keyboard_library_disables_everything(self):
        with mock.patch("ui.hotkeys.keyboard", None):
            manager = HotkeyManager(self.root)
            self.assertFalse(manager.available)
            self.assertEqual(manager.register([("ctrl+shift+f", lambda: None, "收藏")]), [])
            manager.unregister()  # 不应抛异常


if __name__ == "__main__":
    unittest.main()
