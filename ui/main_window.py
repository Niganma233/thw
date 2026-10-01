"""主窗口的控件树。

只负责"把控件建出来并暴露引用"，不处理业务：按钮点了做什么、状态文字怎么变，
都由 ``gui.WallpaperApp`` 决定。所有回调都以关键字参数强制传入，因此不存在
"按钮忘了接命令、点了没反应"这种漏接。
"""
import tkinter as tk

import customtkinter as ctk

from ui import theme
from ui.status_bar import StatusPresenter

APP_TITLE = "Touhou Wallpaper"
WINDOW_SIZE = "1040x900"
MIN_WINDOW_SIZE = (940, 840)

INITIAL_STATUS = "在线轮播就绪"
INITIAL_COUNTDOWN = "下次刷新：—"

TAB_GENERAL = "⚙  常规"
TAB_SOURCES = "🌐  图源管理"
TAB_FAVORITES = "⭐  收藏"


class MainWindow:
    """主窗口外壳：顶栏、动作按钮、三个标签页容器与底栏。"""

    def __init__(
        self,
        root,
        *,
        on_next_wallpaper,
        on_favorite_current,
        on_open_favorites,
        on_hide_to_tray,
        on_save_settings,
        on_quit_and_restore,
    ):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(*MIN_WINDOW_SIZE)
        self.root.resizable(True, True)

        self._on_next_wallpaper = on_next_wallpaper
        self._on_hide_to_tray = on_hide_to_tray
        self._build(
            on_favorite_current=on_favorite_current,
            on_open_favorites=on_open_favorites,
            on_save_settings=on_save_settings,
            on_quit_and_restore=on_quit_and_restore,
        )

    def _build(self, *, on_favorite_current, on_open_favorites, on_save_settings, on_quit_and_restore):
        container = ctk.CTkFrame(self.root, fg_color="transparent")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        header = ctk.CTkFrame(container, corner_radius=16)
        header.pack(fill=tk.X, pady=(0, 14))
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20, pady=16)
        ctk.CTkLabel(brand, text="🌸  Touhou Wallpaper", font=theme.FONT_BRAND, anchor="w").pack(anchor=tk.W)
        ctk.CTkLabel(
            brand,
            text="自动更换东方 Project 壁纸 · 图源可自定义",
            font=theme.FONT_BODY,
            text_color=theme.COLOR_MUTED_STRONG,
            anchor="w",
        ).pack(anchor=tk.W, pady=(2, 0))

        self.status = StatusPresenter(header, initial_text=INITIAL_STATUS)

        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill=tk.X, pady=(0, 14))
        # 换一张按钮要能改文字/禁用，所以留引用
        self.next_btn = ctk.CTkButton(
            actions, text="🎲  换一张", height=42, font=theme.FONT_COMBO,
            command=self._on_next_wallpaper,
        )
        self.next_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ctk.CTkButton(actions, text="⭐  收藏当前", height=42, command=on_favorite_current).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ctk.CTkButton(actions, text="📂  打开收藏夹", height=42, command=on_open_favorites).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ctk.CTkButton(actions, text="🗕  托盘", height=42, command=self._on_hide_to_tray).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0)
        )

        self.tabview = ctk.CTkTabview(container)
        self.tabview.pack(fill=tk.BOTH, expand=True)
        self.general_tab = self.tabview.add(TAB_GENERAL)
        self.source_tab = self.tabview.add(TAB_SOURCES)
        self.favorite_tab = self.tabview.add(TAB_FAVORITES)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill=tk.X, pady=(12, 0))
        self.countdown_var = tk.StringVar(value=INITIAL_COUNTDOWN)
        ctk.CTkLabel(
            footer, textvariable=self.countdown_var, font=theme.FONT_BODY, text_color=theme.COLOR_MUTED
        ).pack(side=tk.LEFT)
        ctk.CTkButton(footer, text="保存设置", width=120, height=34, command=on_save_settings).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ctk.CTkButton(
            footer, text="退出并还原壁纸", width=140, height=34,
            fg_color="#b44", hover_color="#933", command=on_quit_and_restore,
        ).pack(side=tk.RIGHT)
