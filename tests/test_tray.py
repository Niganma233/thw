"""ui.tray：托盘图标与菜单。

``pystray.Icon`` 被换成替身：真的建图标会往开发者的系统托盘里塞一个常驻图标，
并且 ``run_detached`` 会起一个后台消息循环。
"""
import unittest
import unittest.mock as mock

from tests.helpers import FakeTrayIcon as FakeIcon
from ui import tray
from ui.tray import TrayController, create_tray_image


class TrayImageTest(unittest.TestCase):
    def test_image_is_rgba_and_square(self):
        image = create_tray_image()
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (tray.ICON_SIZE, tray.ICON_SIZE))
        # 中心像素被圆填充，角落应当仍是透明的
        self.assertNotEqual(image.getpixel((32, 32))[3], 0)
        self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_image_is_not_shared_between_calls(self):
        self.assertIsNot(create_tray_image(), create_tray_image())


class TrayControllerTest(unittest.TestCase):
    def setUp(self):
        FakeIcon.instances = []
        patcher = mock.patch("ui.tray.pystray.Icon", FakeIcon)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = mock.Mock()
        self.controller = TrayController(self.root, title="Touhou Wallpaper")

    def _handlers(self):
        return [("打开设置界面", lambda: None), ("退出", lambda: None)]

    def test_not_running_before_start(self):
        self.assertFalse(self.controller.running)

    def test_start_creates_and_detaches_the_icon(self):
        controller = self.controller
        controller.start(self._handlers())
        icon = FakeIcon.instances[0]
        self.assertEqual(icon.name, tray.ICON_NAME)
        self.assertEqual(icon.title, "Touhou Wallpaper")
        self.assertTrue(icon.detached)
        self.assertTrue(controller.running)

    def test_menu_keeps_handler_order_and_marks_the_first_as_default(self):
        self.controller.start(self._handlers())
        menu = FakeIcon.instances[0].menu
        self.assertEqual([entry.text for entry in menu], ["打开设置界面", "退出"])
        self.assertTrue(menu[0].default)
        self.assertFalse(menu[1].default)

    def test_menu_callbacks_are_marshalled_to_the_main_thread(self):
        # pystray 的菜单回调跑在它自己的线程里，直接碰 Tk 会崩。
        called = []
        self.controller.start([("打开设置界面", lambda: called.append(True))])
        # MenuItem 把动作存在私有属性 _action 里（pystray 没有公开访问器）
        action = FakeIcon.instances[0].menu[0]._action
        action()
        self.assertEqual(called, [], "不应直接执行原回调")
        self.root.after.assert_called_once_with(0, mock.ANY)
        self.root.after.call_args.args[1]()
        self.assertEqual(called, [True])

    def test_stop_stops_the_icon_and_clears_state(self):
        self.controller.start(self._handlers())
        icon = FakeIcon.instances[0]
        self.controller.stop()
        self.assertTrue(icon.stopped)
        self.assertFalse(self.controller.running)

    def test_stop_is_safe_when_not_started(self):
        self.controller.stop()
        self.assertFalse(self.controller.running)

    def test_stop_is_idempotent(self):
        self.controller.start(self._handlers())
        self.controller.stop()
        self.controller.stop()
        self.assertFalse(self.controller.running)

    def test_stop_swallows_icon_errors(self):
        self.controller.start(self._handlers())
        FakeIcon.instances[0].stop = mock.Mock(side_effect=RuntimeError("炸了"))
        self.controller.stop()  # 不应抛出
        self.assertFalse(self.controller.running)


if __name__ == "__main__":
    unittest.main()
