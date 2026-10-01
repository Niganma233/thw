"""ui.dialogs：收藏命名对话框与数据目录告警。

``CTkInputDialog`` 被换成替身：真的构造它并调用 ``get_input()`` 会弹出模态窗口
并**阻塞等待用户点击**，在自动化测试里会直接挂死。
"""
import unittest
import unittest.mock as mock

from ui import dialogs


class FakeInputDialog:
    """替身：记录 after/insert 调用，不真正弹窗。

    用例通过 ``FakeInputDialog.next_result`` 指定"用户输入了什么"。
    """

    instances = []
    next_result = "用户输入"

    def __init__(self, text=None, title=None):
        self.text = text
        self.title = title
        self.after_calls = []
        self._entry = mock.Mock()
        self.result = FakeInputDialog.next_result
        FakeInputDialog.instances.append(self)

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        return "after-id"

    def get_input(self):
        # 真实实现里窗口已建好，after 回调已经跑过；这里模拟同样的时序
        for _, callback in self.after_calls:
            callback()
        return self.result


class AskWallpaperNameTest(unittest.TestCase):
    def setUp(self):
        FakeInputDialog.instances = []
        FakeInputDialog.next_result = "用户输入"
        patcher = mock.patch("ui.dialogs.ctk.CTkInputDialog", FakeInputDialog)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_the_typed_name(self):
        self.assertEqual(dialogs.ask_wallpaper_name("fav_default"), "用户输入")

    def test_strips_surrounding_whitespace(self):
        FakeInputDialog.next_result = "  我的壁纸  "
        self.assertEqual(dialogs.ask_wallpaper_name("fav_default"), "我的壁纸")

    def test_blank_input_falls_back_to_the_default(self):
        FakeInputDialog.next_result = "   "
        self.assertEqual(dialogs.ask_wallpaper_name("fav_default"), "fav_default")

    def test_cancel_returns_none(self):
        FakeInputDialog.next_result = None
        self.assertIsNone(dialogs.ask_wallpaper_name("fav_default"))

    def test_default_name_is_prefilled_after_the_window_exists(self):
        # 直接构造后立刻 insert 是无效的（输入框还没建好），必须走 after 延迟。
        dialogs.ask_wallpaper_name("fav_20250101")
        dialog = FakeInputDialog.instances[0]
        self.assertEqual(len(dialog.after_calls), 1)
        delay, _ = dialog.after_calls[0]
        self.assertEqual(delay, dialogs.DEFAULT_FILL_DELAY_MS)
        dialog._entry.insert.assert_called_once_with(0, "fav_20250101")

    def test_dialog_text_and_title(self):
        dialogs.ask_wallpaper_name("x")
        dialog = FakeInputDialog.instances[0]
        self.assertEqual(dialog.title, dialogs.FAVORITE_DIALOG_TITLE)
        self.assertEqual(dialog.text, dialogs.FAVORITE_DIALOG_TEXT)


class ShowDataDirUnwritableTest(unittest.TestCase):
    def test_warning_names_the_directory(self):
        with mock.patch("tkinter.messagebox.showwarning") as warning:
            dialogs.show_data_dir_unwritable("parent-widget", r"C:\data\TouhouWallpaper")
        warning.assert_called_once()
        title, message = warning.call_args.args
        self.assertEqual(title, "数据目录不可写")
        self.assertIn(r"C:\data\TouhouWallpaper", message)

    def test_warning_is_parented_so_it_stays_on_top(self):
        with mock.patch("tkinter.messagebox.showwarning") as warning:
            dialogs.show_data_dir_unwritable("parent-widget", r"C:\data")
        self.assertEqual(warning.call_args.kwargs["parent"], "parent-widget")


if __name__ == "__main__":
    unittest.main()
