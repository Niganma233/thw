"""界面上用到的对话框。

单独成模块的理由不只是"放得整齐"：

* ``ask_wallpaper_name`` 依赖 ``CTkInputDialog._entry`` 这个**私有属性**，和
  ui/fixed_combobox 一样是 CustomTkinter 升级时最容易失效的地方；
* 编排层（gui.WallpaperApp）通过这里的函数弹窗，因此它自己**完全不 import
  tkinter**——tests/test_layering.py 会守住这一点。
"""
from tkinter import messagebox

import customtkinter as ctk

# 默认值必须在对话框的输入框真正建好之后再插入
DEFAULT_FILL_DELAY_MS = 80

FAVORITE_DIALOG_TEXT = "给这张壁纸取一个名字："
FAVORITE_DIALOG_TITLE = "⭐ 收藏壁纸"


def show_info(parent, title, message):
    """提示弹窗（信息）。"""
    messagebox.showinfo(title, message, parent=parent)


def show_warning(parent, title, message):
    """提示弹窗（警告）。"""
    messagebox.showwarning(title, message, parent=parent)


def show_error(parent, title, message):
    """报错弹窗。"""
    messagebox.showerror(title, message, parent=parent)


def ask_wallpaper_name(default_name):
    """弹出"给壁纸取名字"对话框。

    返回用户输入的名字，留空则返回 ``default_name``；用户取消时返回 ``None``。
    """
    dialog = ctk.CTkInputDialog(text=FAVORITE_DIALOG_TEXT, title=FAVORITE_DIALOG_TITLE)
    # CTkInputDialog 是同步构造的，输入框要等窗口建好才能写入
    dialog.after(DEFAULT_FILL_DELAY_MS, lambda: dialog._entry.insert(0, default_name))
    name = dialog.get_input()
    if name is None:
        return None
    return name.strip() or default_name


def show_data_dir_unwritable(parent, app_dir):
    """数据目录不可写时的警告。"""
    messagebox.showwarning(
        "数据目录不可写",
        f"无法写入：\n{app_dir}\n\n收藏、缓存和设置都无法保存。\n"
        "请检查该目录的写入权限（安全软件拦截、以受限权限运行、程序被限制在工作区里都可能造成）。",
        parent=parent,
    )
