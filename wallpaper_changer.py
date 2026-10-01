"""程序入口：单实例检查、全局外观、启动主窗口。

这个文件只是一层引导——真正的编排在 ``app.WallpaperApp``，
单实例锁在 ``services.single_instance``。

    python wallpaper_changer.py            正常启动
    python wallpaper_changer.py --silent   直接最小化到托盘
"""
import sys

import customtkinter as ctk

from app import WallpaperApp
from core.paths import ensure_dirs
from services import single_instance
from ui import theme

APP_TITLE = "Touhou Wallpaper"
ALREADY_RUNNING_MESSAGE = "程序已经在运行中。"


def _warn_already_running():
    """已经在运行时弹一个提示（静默启动则不打扰用户）。"""
    from tkinter import messagebox

    root = ctk.CTk()
    root.withdraw()
    messagebox.showinfo(APP_TITLE, ALREADY_RUNNING_MESSAGE)
    root.destroy()


def main():
    silent = "--silent" in sys.argv

    # 必须在创建任何 CTk 控件之前设置全局外观。
    # 以前这一步写在 gui.py 的模块顶层，靠 import 副作用生效。
    theme.apply()

    if not single_instance.acquire():
        if not silent:
            _warn_already_running()
        return

    # 目录创建改为显式调用：原来写在 config 模块的导入副作用里。
    ensure_dirs()

    root = ctk.CTk()
    WallpaperApp(root, silent=silent)
    root.mainloop()


if __name__ == "__main__":
    main()
