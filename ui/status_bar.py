"""状态栏：把"当前发生了什么"显示给用户。

包含三件相关的事，原来都散在 ``gui.WallpaperApp`` 里：

1. 状态框控件（指示灯 + 文字）的搭建；
2. 状态文字与指示灯颜色的对应关系；
3. 未捕获的回调异常如何到达状态栏 —— 窗口化运行时（pythonw / PyInstaller -w）
   回调里的异常默认没人看得到，表现为"点了没反应"，所以统一显示出来。
"""
import tkinter as tk
import traceback

import customtkinter as ctk

from ui import theme

DEFAULT_KIND = "ready"


def status_color(kind):
    """按 kind 取指示灯颜色；未知 kind 一律退回 ready。"""
    return theme.STATUS_COLORS.get(kind, theme.STATUS_COLORS[DEFAULT_KIND])


class StatusPresenter:
    """状态栏组件。``set()`` 是唯一的写入口。"""

    def __init__(self, parent, initial_text="就绪"):
        box = ctk.CTkFrame(parent, corner_radius=12, fg_color=theme.COLOR_SURFACE)
        box.pack(side=tk.RIGHT, padx=18, pady=14)

        self._dot = ctk.CTkLabel(box, text="●", font=theme.FONT_ICON)
        self._dot.pack(side=tk.LEFT, padx=(12, 4), pady=10)

        self.var = tk.StringVar(value=initial_text)
        ctk.CTkLabel(box, textvariable=self.var, font=theme.FONT_BODY_BOLD).pack(
            side=tk.LEFT, padx=(0, 12)
        )

        self._text = initial_text
        self.set(initial_text, DEFAULT_KIND)

    # ---------- 写入口 ----------
    def set(self, text, kind=DEFAULT_KIND):
        """更新状态文字与指示灯颜色。"""
        self._text = text
        self.var.set(text)
        self._dot.configure(text_color=status_color(kind))

    @property
    def text(self):
        return self._text

    # ---------- 异常上报 ----------
    def install_exception_hook(self, root):
        """把 Tk 回调里未处理的异常显示到状态栏。"""
        root.report_callback_exception = self._report_callback_exception

    def _report_callback_exception(self, exc_type, exc_value, exc_traceback):
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        try:
            self.set(f"操作失败：{exc_type.__name__}: {exc_value}", "error")
        except Exception:
            # 状态栏本身就坏了的话不要再往外抛，否则会陷入递归报错
            pass
