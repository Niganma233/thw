"""收藏面板：收藏管理、预览、收藏轮播。

与外部世界的接口是显式的 ``FavoriteViewHooks``，而不是一个 ``WallpaperApp`` 引用。
原来的写法是双向耦合：视图读改 ``app.cfg`` / ``app.mode`` /
``app.current_applied_wallpaper``，App 又反过来操作 ``view.fav_combo_var``。
结果是两边都无法脱离对方构造，而且 ``mode``、``current_applied_wallpaper``
被两个类各改一半——正是"星标轮播计时"反复出问题的结构性原因。
"""
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk
from PIL import Image

from core import paths
from core.scheduler import BEHAVIOR_CAROUSEL, BEHAVIOR_PAUSE
from services import favorites as favorites_service
from ui.fixed_combobox import FixedHeightComboBox
from ui.widgets import make_card, open_folder

# 下拉列表在界面上最多显示几项（其余滚动查看）
MAX_VISIBLE_FAVORITES = 8
# 预览图的最大边长
PREVIEW_MAX_SIZE = (680, 470)

NO_FAVORITES_PLACEHOLDER = "暂无收藏壁纸"

BEHAVIOR_CHOICES = (
    (BEHAVIOR_PAUSE, "⏸ 暂停自动刷新（保持当前收藏壁纸）"),
    (BEHAVIOR_CAROUSEL, "⭐ 星标壁纸轮播（按设置间隔切换收藏）"),
    ("online", "🌐 继续在线轮播（收藏仅保存图片）"),
)


@dataclass(frozen=True)
class FavoriteViewHooks:
    """收藏面板需要外部提供的动作。

    ``on_apply`` 返回是否真的应用成功，视图据此决定要不要报错。
    """

    set_status: Callable[[str, str], None]
    on_behavior_changed: Callable[[str], None]
    on_favorite_current: Callable[[], None]
    on_apply: Callable[[str], bool]
    on_is_current: Callable[[str], bool]
    on_refresh_requested: Callable[[], None]


class FavoriteView:
    def __init__(self, parent, hooks, initial_behavior=BEHAVIOR_PAUSE):
        self.parent = parent
        self.hooks = hooks
        self._preview_img = None
        self._build(initial_behavior)

    # ---------- 构建 ----------
    def _build(self, initial_behavior):
        self.parent.grid_columnconfigure(0, weight=0, minsize=350)
        self.parent.grid_columnconfigure(1, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)
        card, body = make_card(self.parent, "收藏管理", "收藏、选择、应用、删除都集中在这里。")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
        ctk.CTkButton(body, text="⭐ 收藏当前壁纸", height=38, command=self.hooks.on_favorite_current).pack(fill=tk.X, pady=4)
        ctk.CTkButton(body, text="📂 打开收藏夹", height=38, command=lambda: open_folder(paths.FAVORITES_DIR)).pack(fill=tk.X, pady=4)
        ctk.CTkLabel(body, text="已收藏壁纸", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W, pady=(13, 4))
        self.fav_combo_var = tk.StringVar()
        # 收藏数量再多，下拉列表也只显示固定高度的 8 项（其余滚动查看），
        # 列表宽度与控件一致，左右边缘和上方按钮对齐。
        self.fav_combo = FixedHeightComboBox(
            body,
            variable=self.fav_combo_var,
            state="readonly",
            max_visible_items=MAX_VISIBLE_FAVORITES,
            dropdown_font=("Microsoft YaHei", 12),
            command=lambda _: self.update_preview(),
        )
        self.fav_combo.pack(fill=tk.X, pady=3)
        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill=tk.X, pady=(10, 4))
        ctk.CTkButton(btns, text="应用", height=36, command=self.apply_selected).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ctk.CTkButton(btns, text="删除", height=36, fg_color="#8c4b4b", hover_color="#6d3838", command=self.delete_selected).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        # 收藏后的自动刷新行为：
        # pause    = 暂停自动刷新，保持当前收藏壁纸
        # carousel = 在收藏夹中按间隔轮播
        # online   = 继续在线轮播（兼容旧版本行为）
        ctk.CTkLabel(body, text="收藏后自动刷新行为", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W, pady=(13, 5))
        self.favorite_behavior_var = tk.StringVar(value=initial_behavior)
        radio_box = ctk.CTkFrame(body, fg_color="transparent")
        radio_box.pack(fill=tk.X, pady=(0, 4))
        for key, label in BEHAVIOR_CHOICES:
            ctk.CTkRadioButton(
                radio_box, text=label, value=key, variable=self.favorite_behavior_var,
                command=self._mark_dirty,
            ).pack(anchor=tk.W, pady=3)

        card, body = make_card(self.parent, "预览", "当前选中收藏的预览图。")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.preview_label = ctk.CTkLabel(body, text="暂无预览", corner_radius=12, font=("Microsoft YaHei", 12), fg_color=("gray92", "gray18"))
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    # ---------- 对外接口 ----------
    def current_selection(self):
        """当前选中的收藏文件名；没有选中时返回空串。"""
        name = self.fav_combo_var.get()
        return "" if name == NO_FAVORITES_PLACEHOLDER else name

    def select(self, filename):
        """选中指定收藏并刷新预览。"""
        self.fav_combo_var.set(filename)
        self.update_preview()

    def refresh(self):
        """按磁盘上的实际收藏重新填充列表。"""
        files = favorites_service.list_favorites()
        self.fav_combo.configure(values=files)
        if files:
            if self.current_selection() not in files:
                self.fav_combo.set(files[0])
        else:
            self.fav_combo_var.set(NO_FAVORITES_PLACEHOLDER)
        self.update_preview()

    def select_next(self):
        """选中并应用下一张收藏；收藏夹为空时返回 False。

        收藏轮播靠它推进，App 不需要知道下拉框是怎么实现的。
        """
        files = favorites_service.list_favorites()
        if not files:
            return False
        current = self.current_selection()
        index = files.index(current) if current in files else -1
        self.select(files[(index + 1) % len(files)])
        self.apply_selected()
        return True

    def collect(self):
        """返回需要写回配置的字段。"""
        behavior = self.favorite_behavior_var.get()
        return {
            "favorite_behavior": behavior,
            "favorite_carousel": behavior == BEHAVIOR_CAROUSEL,
        }

    def apply_selected(self):
        path = self._selected_path()
        if path is None:
            messagebox.showwarning("提示", "请先选择收藏壁纸。", parent=self.parent)
            return False
        if not self.hooks.on_apply(path):
            messagebox.showerror("应用失败", "Windows 没有成功应用这张壁纸。", parent=self.parent)
            return False
        return True

    def delete_selected(self):
        filename = self.current_selection()
        if not filename:
            return False
        if not messagebox.askyesno("确认删除", f"确定删除收藏“{filename}”吗？", parent=self.parent):
            return False
        path = self._path_for(filename)
        was_current = self.hooks.on_is_current(path)
        try:
            if not favorites_service.delete_favorite(filename):
                raise FileNotFoundError("文件不存在")
            self.refresh()
            if was_current:
                # 当前壁纸被删了，换一张在线壁纸顶上
                self.hooks.on_refresh_requested()
            else:
                self.hooks.set_status("已删除收藏", "ready")
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.parent)
            return False
        return True

    # ---------- 内部 ----------
    def _mark_dirty(self):
        # cfg 的写入由 App 负责（on_favorite_behavior_changed 会同步新键与旧键），
        # 视图不再自己动 cfg。
        self.hooks.on_behavior_changed(self.favorite_behavior_var.get())

    @staticmethod
    def _path_for(filename):
        return os.path.join(paths.FAVORITES_DIR, os.path.basename(filename))

    def _selected_path(self):
        filename = self.current_selection()
        return None if not filename else self._path_for(filename)

    def update_preview(self):
        path = self._selected_path()
        if path is None:
            self._preview_img = None
            self.preview_label.configure(image=None, text="暂无预览")
            return
        try:
            with Image.open(path) as source:
                img = source.convert("RGB")
                img.thumbnail(PREVIEW_MAX_SIZE)
            self._preview_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.preview_label.configure(image=self._preview_img, text="")
        except Exception:
            self.preview_label.configure(image=None, text="无法预览")
