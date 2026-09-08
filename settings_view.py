import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

import config
import wallpaper_service


class SettingsView:
    def __init__(self, parent, cfg, app=None):
        self.cfg = cfg
        self.parent = parent
        self.app = app
        self.interval_map = {"不自动更换": 0, "每 5 分钟": 5, "每 15 分钟": 15, "每 30 分钟": 30, "每 1 小时": 60, "每 2 小时": 120, "每 4 小时": 240}
        self.style_map = {"fill": "填充：铺满并裁剪", "fit": "适应：完整显示", "center": "居中", "stretch": "拉伸"}
        self.size_map = {"pc": "电脑壁纸", "mobile": "手机壁纸"}
        self._build()

    def _card(self, parent, title, subtitle=None):
        card = ctk.CTkFrame(parent, corner_radius=14, border_width=1)
        ctk.CTkLabel(card, text=title, font=("Microsoft YaHei", 14, "bold"), anchor="w").pack(anchor=tk.W, padx=16, pady=(14, 2))
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=("Microsoft YaHei", 10), text_color=("gray45", "gray60"), justify="left").pack(anchor=tk.W, padx=16, pady=(0, 8))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(2, 14))
        return card, body

    def _build(self):
        self.parent.grid_columnconfigure(0, weight=1)
        self.parent.grid_columnconfigure(1, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_rowconfigure(2, weight=0)
        card, body = self._card(self.parent, "自动轮播", "控制启动行为与自动换图频率。")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
        self.var_startup = tk.BooleanVar(value=self.cfg.get("refresh_on_startup", True))
        self.var_autostart = tk.BooleanVar(value=self.cfg.get("auto_start", True))
        ctk.CTkCheckBox(body, text="启动程序时立即换一张", variable=self.var_startup).pack(anchor=tk.W, pady=6)
        ctk.CTkCheckBox(body, text="Windows 开机自动启动", variable=self.var_autostart).pack(anchor=tk.W, pady=6)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill=tk.X, pady=(13, 0))
        ctk.CTkLabel(row, text="自动更换间隔").pack(side=tk.LEFT)
        cur = next((k for k,v in self.interval_map.items() if v == self.cfg.get("interval_minutes",30)), "每 30 分钟")
        self.interval_var = tk.StringVar(value=cur)
        ctk.CTkComboBox(row, variable=self.interval_var, values=list(self.interval_map), state="readonly", width=160).pack(side=tk.RIGHT)

        card, body = self._card(self.parent, "壁纸显示", "Windows 桌面壁纸缩放方式。")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill=tk.X, pady=6)
        ctk.CTkLabel(row, text="显示方式").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value=self.style_map.get(self.cfg.get("wallpaper_style", "fill"), self.style_map["fill"]))
        ctk.CTkComboBox(row, variable=self.style_var, values=list(self.style_map.values()), state="readonly", width=180).pack(side=tk.RIGHT)
        ctk.CTkLabel(body, text="推荐“填充”。切换样式后会立即重新应用当前壁纸。", text_color=("gray45", "gray60"), justify="left").pack(anchor=tk.W, pady=(12, 0))

        card, body = self._card(self.parent, "缓存管理", "程序会缓存最近下载的图片；清理时会保护当前正在使用的壁纸。")
        card.grid(row=2, column=0, sticky="nsew", padx=(0, 8), pady=(8, 8))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill=tk.X, pady=4)
        self.cache_info_var = tk.StringVar(value="缓存：正在读取…")
        ctk.CTkLabel(row, textvariable=self.cache_info_var).pack(side=tk.LEFT)
        ctk.CTkButton(row, text="刷新", width=70, height=30, command=self.refresh_cache_info).pack(side=tk.RIGHT)
        ctk.CTkButton(body, text="🧹 清理缓存图片", height=36, command=self.clear_cache).pack(fill=tk.X, pady=(8, 2))
        self.refresh_cache_info()

        card, body = self._card(self.parent, "全局快捷键", "留空即可关闭；保存后重新注册。")
        card.grid(row=2, column=1, sticky="nsew", padx=(8, 0), pady=(8, 8))
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill=tk.X, pady=4)
        ctk.CTkLabel(row1, text="收藏当前壁纸", width=110, anchor="w").pack(side=tk.LEFT)
        self.hotkey_favorite = tk.StringVar(value=self.cfg.get("hotkey_favorite", ""))
        ctk.CTkEntry(row1, textvariable=self.hotkey_favorite, placeholder_text="例如 ctrl+shift+s").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 20))
        ctk.CTkLabel(row1, text="切换在线壁纸", width=110, anchor="w").pack(side=tk.LEFT)
        self.hotkey_switch = tk.StringVar(value=self.cfg.get("hotkey_switch", ""))
        ctk.CTkEntry(row1, textvariable=self.hotkey_switch, placeholder_text="例如 ctrl+shift+f").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

    def refresh_cache_info(self):
        count, total = wallpaper_service.get_cache_info()
        self.cache_info_var.set(f"缓存：{count} 张图片 · {wallpaper_service.format_bytes(total)}")

    def clear_cache(self):
        count, total = wallpaper_service.get_cache_info()
        if count == 0:
            messagebox.showinfo("缓存清理", "当前没有可清理的缓存图片。", parent=self.parent)
            return
        if not messagebox.askyesno(
            "清理缓存",
            f"确定清理缓存中的 {count} 张图片（约 {wallpaper_service.format_bytes(total)}）吗？\n\n当前正在使用的壁纸会保留。",
            parent=self.parent,
        ):
            return
        deleted, freed, failed = wallpaper_service.clear_cache(getattr(self.app, "current_applied_wallpaper", None))
        self.refresh_cache_info()
        if failed:
            messagebox.showwarning(
                "缓存清理完成",
                f"已清理 {deleted} 张图片，释放约 {wallpaper_service.format_bytes(freed)}。\n{failed} 个文件无法删除（可能正在被其他程序使用）。",
                parent=self.parent,
            )
        else:
            messagebox.showinfo(
                "缓存清理完成",
                f"已清理 {deleted} 张图片，释放约 {wallpaper_service.format_bytes(freed)}。",
                parent=self.parent,
            )

    def collect(self):
        return {
            "refresh_on_startup": self.var_startup.get(),
            "auto_start": self.var_autostart.get(),
            "interval_minutes": self.interval_map.get(self.interval_var.get(), 30),
            "wallpaper_style": next((k for k,v in self.style_map.items() if v == self.style_var.get()), "fill"),
            "hotkey_favorite": self.hotkey_favorite.get().strip(),
            "hotkey_switch": self.hotkey_switch.get().strip(),
        }
