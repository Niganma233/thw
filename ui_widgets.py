"""跨视图共享的界面小工具。

三个视图（常规设置、图源管理、收藏）原本各自复制了一份 ``_make_card``/``_card``，
版式要调整就得改三遍、还容易改漏，所以集中到这里。

Phase 7 迁入包结构后本模块会变成 ``ui/widgets.py``。
"""
import os
import tkinter as tk

import customtkinter as ctk

# 副标题统一使用的次要文字色（浅色外观 / 深色外观）
SUBTITLE_COLOR = ("gray45", "gray60")


def make_card(parent, title, subtitle=None):
    """建立一个带标题（可选副标题）的卡片，返回 ``(card, body)``。

    ``card`` 是外层卡片，用它做 grid/pack；``body`` 是透明的内层容器，
    往里放实际控件，已经带好统一的内边距。
    """
    card = ctk.CTkFrame(parent, corner_radius=14, border_width=1)
    ctk.CTkLabel(
        card, text=title, font=("Microsoft YaHei", 14, "bold"), anchor="w"
    ).pack(anchor=tk.W, padx=16, pady=(14, 2))
    if subtitle:
        ctk.CTkLabel(
            card,
            text=subtitle,
            font=("Microsoft YaHei", 10),
            text_color=SUBTITLE_COLOR,
            justify="left",
        ).pack(anchor=tk.W, padx=16, pady=(0, 8))
    body = ctk.CTkFrame(card, fg_color="transparent")
    body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(2, 14))
    return card, body


def open_folder(path):
    """用系统文件管理器打开目录（仅 Windows）。

    两个视图都要"打开收藏夹"，集中在这里以便将来统一处理失败情况
    （``os.startfile`` 在非 Windows 上不存在）。
    """
    os.startfile(path)
