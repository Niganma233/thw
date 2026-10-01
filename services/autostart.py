"""开机自启：写 HKCU 的 Run 键。

单独成模块是因为它是**注册表**操作——放这里之后 core/ 完全不碰 Windows 注册表。
"""
import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "TouhouWallpaperAutoChanger"


def _launch_command():
    """构造开机自启要执行的命令行。

    打包成 exe 时直接指向 exe；否则用 pythonw.exe 跑脚本（避免每次开机弹黑框）。
    """
    python_exe = sys.executable
    pythonw = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = python_exe
    script_path = os.path.abspath(sys.argv[0])
    if script_path.lower().endswith(".exe"):
        return f'"{script_path}" --silent'
    return f'"{pythonw}" "{script_path}" --silent'


def set_auto_start_registry(enable=True):
    """开启/关闭开机自启。失败只打印，不打断调用方。"""
    key = None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    except OSError as exc:
        print(f"设置开机自启失败: {exc}")
    finally:
        if key is not None:
            winreg.CloseKey(key)
