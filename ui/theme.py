"""全局外观、共享字体与配色。

原来 ``ctk.set_appearance_mode()`` 写在 gui.py 的**模块顶层**——只要 import gui
就会改掉全局外观模式，"什么时候生效"完全藏在 import 副作用里。现在改成显式调用
``apply()``，由入口（wallpaper_changer.main）在创建任何控件之前调用一次。
"""
import customtkinter as ctk

APPEARANCE_MODE = "system"
COLOR_THEME = "blue"

FONT_FAMILY = "Microsoft YaHei"

FONT_BRAND = (FONT_FAMILY, 21, "bold")     # 顶栏主标题
FONT_HEADING = (FONT_FAMILY, 16, "bold")   # 卡片/编辑器大标题
FONT_TITLE = (FONT_FAMILY, 14, "bold")     # 卡片标题
FONT_BODY = (FONT_FAMILY, 11)              # 正文
FONT_BODY_BOLD = (FONT_FAMILY, 11, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 10)          # 卡片副标题
FONT_COMBO = (FONT_FAMILY, 12)

FONT_ICON = ("Arial", 13, "bold")          # 状态指示灯

# 次要文字色（浅色外观, 深色外观）
COLOR_MUTED = ("gray45", "gray60")
COLOR_MUTED_STRONG = ("gray40", "gray65")

# 凹陷/浮起面板底色
COLOR_SURFACE = ("gray92", "gray18")

# 状态指示灯颜色，按 StatusPresenter.set(kind=...) 的取值取用
STATUS_COLORS = {
    "ready": ("#3a9d6b", "#5ec48d"),
    "busy": ("#d59b35", "#e9b95d"),
    "error": ("#d65a5a", "#f07a7a"),
    "favorite": ("#bf8c2e", "#e6b954"),
}


def apply():
    """设置全局外观模式与配色主题。

    必须在创建任何 CTk 控件之前调用。重复调用是安全的（幂等）。
    """
    ctk.set_appearance_mode(APPEARANCE_MODE)
    ctk.set_default_color_theme(COLOR_THEME)
