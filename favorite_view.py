import os
import re
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

import config
import wallpaper_service


class FavoriteView:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.cfg = app.cfg
        self._preview_img = None
        self._build()

    def _card(self, parent, title, subtitle=None):
        card = ctk.CTkFrame(parent, corner_radius=14, border_width=1)
        ctk.CTkLabel(card, text=title, font=("Microsoft YaHei", 14, "bold"), anchor="w").pack(anchor=tk.W, padx=16, pady=(14, 2))
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=("Microsoft YaHei", 10), text_color=("gray45", "gray60")).pack(anchor=tk.W, padx=16, pady=(0, 8))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(2, 14))
        return card, body

    def _build(self):
        self.parent.grid_columnconfigure(0, weight=0, minsize=350)
        self.parent.grid_columnconfigure(1, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)
        card, body = self._card(self.parent, "收藏管理", "收藏、选择、应用、删除都集中在这里。")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
        ctk.CTkButton(body, text="⭐ 收藏当前壁纸", height=38, command=self.app.favorite_current_wallpaper).pack(fill=tk.X, pady=4)
        ctk.CTkButton(body, text="📂 打开收藏夹", height=38, command=lambda: os.startfile(config.FAVORITES_DIR)).pack(fill=tk.X, pady=4)
        ctk.CTkLabel(body, text="已收藏壁纸", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W, pady=(13, 4))
        self.fav_combo_var = tk.StringVar()
        self.fav_combo = ctk.CTkComboBox(body, variable=self.fav_combo_var, state="readonly", command=lambda _: self.update_preview())
        self.fav_combo.pack(fill=tk.X, pady=3)
        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill=tk.X, pady=(10, 4))
        ctk.CTkButton(btns, text="应用", height=36, command=self.apply_selected).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ctk.CTkButton(btns, text="删除", height=36, fg_color="#8c4b4b", hover_color="#6d3838", command=self.delete_selected).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self.var_fav_carousel = tk.BooleanVar(value=self.cfg.get("favorite_carousel", False))
        ctk.CTkCheckBox(body, text="收藏模式也自动轮播", variable=self.var_fav_carousel, command=self._mark_dirty).pack(anchor=tk.W, pady=(10, 5))

        card, body = self._card(self.parent, "预览", "当前选中收藏的预览图。")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.preview_label = ctk.CTkLabel(body, text="暂无预览", corner_radius=12, font=("Microsoft YaHei", 12), fg_color=("gray92", "gray18"))
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    def _mark_dirty(self):
        self.app.cfg["favorite_carousel"] = self.var_fav_carousel.get()

    def refresh(self):
        files = wallpaper_service.list_favorites()
        self.fav_combo.configure(values=files)
        if files:
            if self.fav_combo_var.get() not in files:
                self.fav_combo.set(files[0])
        else:
            self.fav_combo_var.set("暂无收藏壁纸")
        self.update_preview()

    def update_preview(self):
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            self._preview_img = None
            self.preview_label.configure(image=None, text="暂无预览")
            return
        path = os.path.join(config.FAVORITES_DIR, os.path.basename(filename))
        try:
            with Image.open(path) as source:
                img = source.convert("RGB")
                img.thumbnail((680, 470))
            self._preview_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.preview_label.configure(image=self._preview_img, text="")
        except Exception:
            self.preview_label.configure(image=None, text="无法预览")

    def apply_selected(self):
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            messagebox.showwarning("提示", "请先选择收藏壁纸。", parent=self.parent)
            return
        path = os.path.join(config.FAVORITES_DIR, os.path.basename(filename))
        if not wallpaper_service.set_wallpaper_windows(path):
            messagebox.showerror("应用失败", "Windows 没有成功应用这张壁纸。", parent=self.parent)
            return
        self.app.current_applied_wallpaper = path
        self.app.mode = "favorite"
        self.app.reset_refresh_timer()
        self.app.set_status(f"⭐ 使用收藏：{filename}", "favorite")

    def delete_selected(self):
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            return
        if not messagebox.askyesno("确认删除", f"确定删除收藏“{filename}”吗？", parent=self.parent):
            return
        path = os.path.join(config.FAVORITES_DIR, os.path.basename(filename))
        current = os.path.abspath(self.app.current_applied_wallpaper) == os.path.abspath(path)
        try:
            if not wallpaper_service.delete_favorite(filename):
                raise FileNotFoundError("文件不存在")
            self.refresh()
            if current:
                self.app.fetch_and_set_wallpaper()
            else:
                self.app.set_status("已删除收藏", "ready")
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.parent)

    def collect(self):
        return {"favorite_carousel": self.var_fav_carousel.get()}
