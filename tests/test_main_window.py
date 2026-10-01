"""ui.main_window：主窗口外壳与按钮接线。

最有价值的一条是 test_every_button_has_a_command：所有回调都以关键字参数强制
传入，所以"按钮忘了接命令、点了没反应"这种漏接会在这里被抓到。
三个视图不在这层创建，因此根控件下应当只有外壳自己的 6 个按钮。
"""
import unittest

from tests.helpers import collect_widgets, tk_root
from ui.main_window import (
    INITIAL_COUNTDOWN,
    INITIAL_STATUS,
    MIN_WINDOW_SIZE,
    TAB_FAVORITES,
    TAB_GENERAL,
    TAB_SOURCES,
    WINDOW_SIZE,
    MainWindow,
)


def _ctk():
    import customtkinter as ctk
    return ctk


class MainWindowTest(unittest.TestCase):
    def _build(self, root):
        self.fired = []

        def handler(name):
            return lambda: self.fired.append(name)

        self.window = MainWindow(
            root,
            on_next_wallpaper=handler("next"),
            on_favorite_current=handler("favorite"),
            on_open_favorites=handler("open_favorites"),
            on_hide_to_tray=handler("hide"),
            on_save_settings=handler("save"),
            on_quit_and_restore=handler("quit"),
        )
        return self.window

    def _buttons(self, root):
        return collect_widgets(root, _ctk().CTkButton)

    def test_window_basics(self):
        with tk_root() as root:
            self._build(root)
            self.assertEqual(root.title(), "Touhou Wallpaper")
            self.assertEqual(root.geometry().split("+")[0], WINDOW_SIZE)
            # CustomTkinter 会把最小尺寸按 DPI 缩放系数放大再交给 Tk
            # （100% 缩放时才是原值），所以这里只断言"不小于声明值"。
            min_width, min_height = root.wm_minsize()
            self.assertGreaterEqual(min_width, MIN_WINDOW_SIZE[0])
            self.assertGreaterEqual(min_height, MIN_WINDOW_SIZE[1])

    def test_three_tabs_are_created(self):
        with tk_root() as root:
            window = self._build(root)
            self.assertIsNotNone(window.general_tab)
            self.assertIsNotNone(window.source_tab)
            self.assertIsNotNone(window.favorite_tab)
            self.assertEqual(len({id(window.general_tab), id(window.source_tab), id(window.favorite_tab)}), 3)
            self.assertEqual(window.tabview.get(), TAB_GENERAL)

    def test_tab_labels(self):
        with tk_root() as root:
            self._build(root)
            self.assertEqual((TAB_GENERAL, TAB_SOURCES, TAB_FAVORITES), ("⚙  常规", "🌐  图源管理", "⭐  收藏"))

    def test_status_starts_ready(self):
        with tk_root() as root:
            window = self._build(root)
            self.assertEqual(window.status.var.get(), INITIAL_STATUS)
            self.assertEqual(window.status.text, INITIAL_STATUS)

    def test_countdown_starts_placeholder(self):
        with tk_root() as root:
            window = self._build(root)
            self.assertEqual(window.countdown_var.get(), INITIAL_COUNTDOWN)

    def test_next_button_is_exposed_for_enabling(self):
        with tk_root() as root:
            window = self._build(root)
            window.next_btn.configure(state="disabled", text="⏳")
            self.assertEqual(window.next_btn.cget("state"), "disabled")

    def test_every_button_has_a_command(self):
        with tk_root() as root:
            self._build(root)
            buttons = self._buttons(root)
            self.assertEqual(len(buttons), 6, "外壳应当只有 6 个按钮")
            for button in buttons:
                with self.subTest(text=button.cget("text")):
                    self.assertIsNotNone(button.cget("command"))

    def test_every_button_reaches_its_handler(self):
        with tk_root() as root:
            self._build(root)
            for button in self._buttons(root):
                button.invoke()
        self.assertEqual(
            sorted(self.fired),
            ["favorite", "hide", "next", "open_favorites", "quit", "save"],
        )

    def test_handlers_are_not_called_at_construction(self):
        with tk_root() as root:
            self._build(root)
        self.assertEqual(self.fired, [])


if __name__ == "__main__":
    unittest.main()
