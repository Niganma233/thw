"""ui.status_bar：状态栏组件与未捕获回调异常的呈现。"""
import sys
import unittest
import unittest.mock as mock

from tests.helpers import tk_root
from ui import theme
from ui.status_bar import StatusPresenter, status_color


class StatusColorTest(unittest.TestCase):
    """颜色选择是纯函数，不需要 Tk 就能测。"""

    def test_known_kinds(self):
        for kind in ("ready", "busy", "error", "favorite"):
            with self.subTest(kind=kind):
                self.assertEqual(status_color(kind), theme.STATUS_COLORS[kind])

    def test_unknown_kind_falls_back_to_ready(self):
        self.assertEqual(status_color("nonsense"), theme.STATUS_COLORS["ready"])
        self.assertEqual(status_color(None), theme.STATUS_COLORS["ready"])

    def test_every_status_color_has_light_and_dark_variant(self):
        for kind, value in theme.STATUS_COLORS.items():
            with self.subTest(kind=kind):
                self.assertIsInstance(value, tuple)
                self.assertEqual(len(value), 2)


class StatusPresenterTest(unittest.TestCase):
    def _presenter(self, root, text="就绪"):
        import customtkinter as ctk
        return StatusPresenter(ctk.CTkFrame(root), initial_text=text)

    def test_initial_text(self):
        with tk_root() as root:
            presenter = self._presenter(root, "在线轮播就绪")
            self.assertEqual(presenter.var.get(), "在线轮播就绪")
            self.assertEqual(presenter.text, "在线轮播就绪")

    def test_set_updates_text_and_memory(self):
        with tk_root() as root:
            presenter = self._presenter(root)
            presenter.set("正在下载新壁纸…", "busy")
            self.assertEqual(presenter.var.get(), "正在下载新壁纸…")
            self.assertEqual(presenter.text, "正在下载新壁纸…")

    def test_set_accepts_every_known_kind(self):
        with tk_root() as root:
            presenter = self._presenter(root)
            for kind in ("ready", "busy", "error", "favorite", "unknown"):
                with self.subTest(kind=kind):
                    presenter.set(f"状态 {kind}", kind)

    def test_install_exception_hook_takes_over_the_root(self):
        with tk_root() as root:
            presenter = self._presenter(root)
            presenter.install_exception_hook(root)
            # 绑定方法是每次访问属性时新建的对象，只能用 assertEqual（比较
            # __self__ 与 __func__），assertIs 会失败。
            self.assertEqual(root.report_callback_exception, presenter._report_callback_exception)
            self.assertIs(root.report_callback_exception.__self__, presenter)

    def test_exception_hook_writes_the_failure_to_the_status_bar(self):
        # 窗口化运行时回调异常默认不可见（表现为"点了没反应"），
        # 所以这里断言它确实被写进了状态栏。
        with tk_root() as root:
            presenter = self._presenter(root)
            try:
                raise ValueError("壁纸炸了")
            except ValueError:
                with mock.patch("traceback.print_exception") as printer:
                    presenter._report_callback_exception(*sys.exc_info())
        self.assertIn("ValueError", presenter.var.get())
        self.assertIn("壁纸炸了", presenter.var.get())
        printer.assert_called_once()

    def test_exception_hook_still_traces_when_status_bar_is_broken(self):
        # 状态栏本身坏掉时不能往外抛，否则会陷入递归报错。
        with tk_root() as root:
            presenter = self._presenter(root)
            presenter.set = mock.Mock(side_effect=RuntimeError("状态栏坏了"))
            try:
                raise ValueError("原始错误")
            except ValueError:
                with mock.patch("traceback.print_exception"):
                    presenter._report_callback_exception(*sys.exc_info())  # 不应抛出


if __name__ == "__main__":
    unittest.main()
