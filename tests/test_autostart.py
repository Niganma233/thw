"""services.autostart：开机自启的命令行构造与注册表容错。

注册表操作全部打桩——绝不能真的改开发者的开机启动项。
"""
import unittest
import unittest.mock as mock

from services import autostart


class LaunchCommandTest(unittest.TestCase):
    def _command(self, argv0, pythonw_exists=True, executable=r"C:\Python\python.exe"):
        def fake_exists(path):
            return pythonw_exists and path.lower().endswith("pythonw.exe")

        with mock.patch("sys.argv", [argv0]), \
                mock.patch("sys.executable", executable), \
                mock.patch("os.path.exists", side_effect=fake_exists):
            return autostart._launch_command()

    def test_packaged_exe_runs_itself_with_silent(self):
        self.assertEqual(self._command(r"C:\Apps\thw.exe"), r'"C:\Apps\thw.exe" --silent')

    def test_script_uses_pythonw_to_avoid_a_console_window(self):
        command = self._command(r"C:\proj\wallpaper_changer.py")
        self.assertEqual(command, r'"C:\Python\pythonw.exe" "C:\proj\wallpaper_changer.py" --silent')

    def test_falls_back_to_python_when_pythonw_is_missing(self):
        command = self._command(r"C:\proj\wallpaper_changer.py", pythonw_exists=False)
        self.assertEqual(command, r'"C:\Python\python.exe" "C:\proj\wallpaper_changer.py" --silent')

    def test_exe_detection_is_case_insensitive(self):
        self.assertTrue(self._command(r"C:\Apps\THW.EXE").startswith(r'"C:\Apps\THW.EXE"'))


class SetAutoStartRegistryTest(unittest.TestCase):
    def test_enable_writes_the_command(self):
        with mock.patch("winreg.OpenKey", return_value="key"), \
                mock.patch("winreg.SetValueEx") as setter, \
                mock.patch("winreg.CloseKey"), \
                mock.patch.object(autostart, "_launch_command", return_value="COMMAND"):
            autostart.set_auto_start_registry(True)
        setter.assert_called_once_with("key", autostart.VALUE_NAME, 0, mock.ANY, "COMMAND")

    def test_disable_deletes_the_value(self):
        with mock.patch("winreg.OpenKey", return_value="key"), \
                mock.patch("winreg.DeleteValue") as deleter, \
                mock.patch("winreg.CloseKey"):
            autostart.set_auto_start_registry(False)
        deleter.assert_called_once_with("key", autostart.VALUE_NAME)

    def test_missing_value_is_tolerated(self):
        with mock.patch("winreg.OpenKey", return_value="key"), \
                mock.patch("winreg.DeleteValue", side_effect=FileNotFoundError), \
                mock.patch("winreg.CloseKey"):
            autostart.set_auto_start_registry(False)  # 不应抛出

    def test_registry_failure_is_swallowed(self):
        # 拿不到写权限时只打印，不该打断"保存设置"
        with mock.patch("winreg.OpenKey", side_effect=OSError("拒绝访问")), \
                mock.patch("builtins.print") as printer:
            autostart.set_auto_start_registry(True)
        self.assertTrue(printer.called)

    def test_key_is_closed_even_on_failure(self):
        with mock.patch("winreg.OpenKey", return_value="key"), \
                mock.patch("winreg.SetValueEx", side_effect=OSError("x")), \
                mock.patch("winreg.CloseKey") as closer, \
                mock.patch("builtins.print"):
            autostart.set_auto_start_registry(True)
        closer.assert_called_once_with("key")

    def test_key_is_closed_when_opening_failed(self):
        with mock.patch("winreg.OpenKey", side_effect=OSError("x")), \
                mock.patch("winreg.CloseKey") as closer, \
                mock.patch("builtins.print"):
            autostart.set_auto_start_registry(True)
        closer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
