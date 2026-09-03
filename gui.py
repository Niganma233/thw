import os
import re
import time
import threading
import queue
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

try:
    import keyboard
except ImportError:
    keyboard = None

import config
import wallpaper_service

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


class WallpaperApp:
    def __init__(self, root, silent=False):
        self.root = root
        self.root.title("Touhou Wallpaper")
        self.root.geometry("1000x740")
        self.root.minsize(900, 680)
        self.root.resizable(True, True)

        self.cfg = config.load_config()
        self.mode = "online"
        self.current_applied_wallpaper = ""
        self.is_downloading = False
        self._consecutive_failures = 0
        self._next_refresh_time = time.time() + max(0, int(self.cfg.get("interval_minutes", 30))) * 60
        self._ui_queue = queue.Queue()
        self._preview_img = None
        self._closing = False
        self.tray_icon = None
        self._source_display_map = {}

        cur_wp = wallpaper_service.get_current_windows_wallpaper()
        if cur_wp and not cur_wp.lower().startswith(config.APP_DIR.lower()):
            self.cfg["original_wallpaper"] = cur_wp
            config.save_config(self.cfg)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.init_ui()
        self.refresh_favorites_list()
        self.refresh_source_list()
        self.init_tray_icon()
        self.register_hotkeys()

        self._set_status("在线轮播就绪", "ready")
        if self.cfg.get("refresh_on_startup", True):
            self.fetch_and_set_wallpaper()
        self.timer_loop()
        if silent:
            self.root.withdraw()

    # ---------------- UI ----------------
    def _make_card(self, parent, title, subtitle=None):
        card = ctk.CTkFrame(parent, corner_radius=14, border_width=1)
        ctk.CTkLabel(card, text=title, font=("Microsoft YaHei", 14, "bold"), anchor="w").pack(anchor=tk.W, padx=18, pady=(14, 2))
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=("Microsoft YaHei", 11), anchor="w",
                         text_color=("gray45", "gray65"), justify="left").pack(anchor=tk.W, padx=18, pady=(0, 7))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(4, 14))
        return card, body

    def init_ui(self):
        container = ctk.CTkFrame(self.root, fg_color="transparent")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        header = ctk.CTkFrame(container, corner_radius=16)
        header.pack(fill=tk.X, pady=(0, 14))
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20, pady=16)
        ctk.CTkLabel(brand, text="🌸  Touhou Wallpaper", anchor="w", font=("Microsoft YaHei", 21, "bold")).pack(anchor=tk.W)
        ctk.CTkLabel(brand, text="自动更换东方 Project 壁纸 · 收藏喜欢的图片", anchor="w",
                     font=("Microsoft YaHei", 11), text_color=("gray40", "gray65")).pack(anchor=tk.W, pady=(2, 0))

        status_box = ctk.CTkFrame(header, corner_radius=12, fg_color=("gray92", "gray18"))
        status_box.pack(side=tk.RIGHT, padx=18, pady=14)
        self.status_dot = ctk.CTkLabel(status_box, text="●", font=("Arial", 13, "bold"))
        self.status_dot.pack(side=tk.LEFT, padx=(12, 4), pady=10)
        self.status_var = tk.StringVar(value="在线轮播就绪")
        ctk.CTkLabel(status_box, textvariable=self.status_var, font=("Microsoft YaHei", 11, "bold")).pack(side=tk.LEFT, padx=(0, 12))

        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill=tk.X, pady=(0, 14))
        self.next_btn = ctk.CTkButton(actions, text="🎲  换一张", height=42, font=("Microsoft YaHei", 13, "bold"), command=self.fetch_and_set_wallpaper)
        self.next_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ctk.CTkButton(actions, text="⭐  收藏当前", height=42, command=self.favorite_current_wallpaper).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ctk.CTkButton(actions, text="📂  打开收藏夹", height=42, command=lambda: os.startfile(config.FAVORITES_DIR)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ctk.CTkButton(actions, text="🗕  托盘", height=42, command=self.hide_to_tray).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        self.tabview = ctk.CTkTabview(container)
        self.tabview.pack(fill=tk.BOTH, expand=True)
        self.tabview.add("⚙  常规")
        self.tabview.add("🌐  图源")
        self.tabview.add("⭐  收藏")
        self._build_tab_general(self.tabview.tab("⚙  常规"))
        self._build_tab_source(self.tabview.tab("🌐  图源"))
        self._build_tab_favorite(self.tabview.tab("⭐  收藏"))

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill=tk.X, pady=(12, 0))
        self.countdown_var = tk.StringVar(value="下次刷新：—")
        ctk.CTkLabel(footer, textvariable=self.countdown_var, font=("Microsoft YaHei", 11), text_color=("gray45", "gray65")).pack(side=tk.LEFT)
        ctk.CTkButton(footer, text="保存设置", width=120, height=34, command=self.apply_settings).pack(side=tk.RIGHT, padx=(8, 0))
        ctk.CTkButton(footer, text="退出并还原壁纸", width=140, height=34, fg_color="#b44", hover_color="#933", command=self.quit_and_restore).pack(side=tk.RIGHT)

    def _build_tab_general(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        card, body = self._make_card(tab, "自动轮播", "控制启动行为与自动换图频率。")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
        self.var_startup = tk.BooleanVar(value=self.cfg.get("refresh_on_startup", True))
        ctk.CTkCheckBox(body, text="启动程序时立即换一张", variable=self.var_startup).pack(anchor=tk.W, pady=6)
        self.var_autostart = tk.BooleanVar(value=self.cfg.get("auto_start", True))
        ctk.CTkCheckBox(body, text="Windows 开机自动启动", variable=self.var_autostart).pack(anchor=tk.W, pady=6)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill=tk.X, pady=(13, 4))
        ctk.CTkLabel(row, text="自动更换间隔").pack(side=tk.LEFT)
        self.interval_map = {"不自动更换": 0, "每 5 分钟": 5, "每 15 分钟": 15, "每 30 分钟": 30, "每 1 小时": 60, "每 2 小时": 120, "每 4 小时": 240}
        cur = next((k for k, v in self.interval_map.items() if v == self.cfg.get("interval_minutes", 30)), "每 30 分钟")
        self.interval_var = tk.StringVar(value=cur)
        ctk.CTkComboBox(row, variable=self.interval_var, values=list(self.interval_map), state="readonly", width=160).pack(side=tk.RIGHT)
        ctk.CTkLabel(body, text="手动换图后会重新开始计时；设为“不自动更换”即可关闭轮播。",
                     justify="left", text_color=("gray45", "gray60")).pack(anchor=tk.W, pady=(12, 0))

        card, body = self._make_card(tab, "壁纸显示", "Windows 桌面壁纸的缩放方式。")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.style_map = {"fill": "填充：铺满并裁剪", "fit": "适应：完整显示", "center": "居中：原始尺寸", "stretch": "拉伸：铺满屏幕"}
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill=tk.X, pady=7)
        ctk.CTkLabel(row, text="显示方式").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value=self.style_map.get(self.cfg.get("wallpaper_style", "fill"), self.style_map["fill"]))
        ctk.CTkComboBox(row, variable=self.style_var, values=list(self.style_map.values()), state="readonly", width=185).pack(side=tk.RIGHT)
        ctk.CTkLabel(body, text="推荐“填充”。不同宽高比的图片会自动裁剪边缘。",
                     justify="left", text_color=("gray45", "gray60")).pack(anchor=tk.W, pady=(12, 0))

    def _build_tab_source(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=0)

        card, body = self._make_card(tab, "当前图源", "内置图源与你自己添加的图源都可以直接选择。")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill=tk.X, pady=6)
        ctk.CTkLabel(row, text="使用图源").pack(side=tk.LEFT)
        self.source_var = tk.StringVar()
        self.source_combo = ctk.CTkComboBox(row, variable=self.source_var, state="readonly", width=250, command=self.on_source_selected)
        self.source_combo.pack(side=tk.RIGHT)

        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill=tk.X, pady=6)
        ctk.CTkLabel(row2, text="尺寸").pack(side=tk.LEFT)
        self.size_map = {"pc": "电脑壁纸", "mobile": "手机壁纸"}
        self.size_var = tk.StringVar(value=self.size_map.get(self.cfg.get("size", "pc"), "电脑壁纸"))
        ctk.CTkComboBox(row2, variable=self.size_var, values=list(self.size_map.values()), state="readonly", width=150).pack(side=tk.RIGHT)

        self.source_hint_var = tk.StringVar(value="")
        ctk.CTkLabel(body, textvariable=self.source_hint_var, justify="left", wraplength=360,
                     text_color=("gray45", "gray60")).pack(anchor=tk.W, pady=(12, 0))

        card, body = self._make_card(tab, "自定义图源", "填写一个能直接返回图片、302 跳转到图片，或返回 {\"url\": \"图片地址\"} 的接口。")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)

        name_row = ctk.CTkFrame(body, fg_color="transparent")
        name_row.pack(fill=tk.X, pady=5)
        ctk.CTkLabel(name_row, text="名称").pack(side=tk.LEFT)
        self.custom_name_var = tk.StringVar()
        self.custom_name_entry = ctk.CTkEntry(name_row, textvariable=self.custom_name_var, placeholder_text="例如：我的随机壁纸")
        self.custom_name_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(12, 0))

        url_row = ctk.CTkFrame(body, fg_color="transparent")
        url_row.pack(fill=tk.X, pady=5)
        ctk.CTkLabel(url_row, text="地址").pack(side=tk.LEFT)
        self.custom_url_var = tk.StringVar()
        self.custom_url_entry = ctk.CTkEntry(url_row, textvariable=self.custom_url_var, placeholder_text="https://example.com/random")
        self.custom_url_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(12, 0))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill=tk.X, pady=(12, 4))
        ctk.CTkButton(btns, text="测试图源", width=100, command=self.test_custom_source).pack(side=tk.LEFT)
        ctk.CTkButton(btns, text="添加 / 更新", width=110, command=self.save_custom_source).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(btns, text="删除自定义图源", width=130, fg_color="#8c4b4b", hover_color="#6d3838", command=self.delete_custom_source).pack(side=tk.RIGHT)

        ctk.CTkLabel(body, text="可用占位符：{size}=pc/mobile，{site}=all。也可以完全不使用占位符。",
                     justify="left", text_color=("gray45", "gray60")).pack(anchor=tk.W, pady=(9, 0))

        card, body = self._make_card(tab, "全局快捷键", "留空即可关闭；保存设置后重新注册。")
        card.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8))
        for label, attr, value in [
            ("收藏当前壁纸", "hk_fav_var", self.cfg.get("hotkey_favorite", "")),
            ("切换在线壁纸", "hk_switch_var", self.cfg.get("hotkey_switch", "")),
        ]:
            r = ctk.CTkFrame(body, fg_color="transparent")
            r.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
            ctk.CTkLabel(r, text=label).pack(side=tk.LEFT)
            var = tk.StringVar(value=value)
            setattr(self, attr, var)
            ctk.CTkEntry(r, textvariable=var, width=170, placeholder_text="ctrl+shift+s").pack(side=tk.RIGHT, padx=(10, 0))

    def _build_tab_favorite(self, tab):
        # 修复截图中的关键问题：不再上下硬切两张卡片，左侧改为一张紧凑控制卡，避免“收藏列表”底部被裁切。
        tab.grid_columnconfigure(0, weight=0, minsize=350)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        card, body = self._make_card(tab, "收藏管理", "收藏、选择、应用、删除全部集中在这里，不再让下方按钮被窗口裁掉。")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)

        ctk.CTkButton(body, text="⭐ 收藏当前壁纸", height=38, command=self.favorite_current_wallpaper).pack(fill=tk.X, pady=4)
        ctk.CTkButton(body, text="📂 打开收藏夹", height=38, command=lambda: os.startfile(config.FAVORITES_DIR)).pack(fill=tk.X, pady=4)

        ctk.CTkLabel(body, text="已收藏壁纸", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W, pady=(13, 4))
        self.fav_combo_var = tk.StringVar()
        self.fav_combo = ctk.CTkComboBox(body, variable=self.fav_combo_var, state="readonly", command=lambda _: self.update_favorite_preview())
        self.fav_combo.pack(fill=tk.X, pady=3)

        fav_buttons = ctk.CTkFrame(body, fg_color="transparent")
        fav_buttons.pack(fill=tk.X, pady=(10, 4))
        ctk.CTkButton(fav_buttons, text="应用", height=36, command=self.apply_selected_favorite).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ctk.CTkButton(fav_buttons, text="删除", height=36, fg_color="#8c4b4b", hover_color="#6d3838", command=self.delete_selected_favorite).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        self.var_fav_carousel = tk.BooleanVar(value=self.cfg.get("favorite_carousel", False))
        ctk.CTkCheckBox(body, text="收藏模式也自动轮播", variable=self.var_fav_carousel).pack(anchor=tk.W, pady=(10, 5))

        self.favorite_mode_hint = ctk.CTkLabel(body, text="选择收藏并应用后，程序会进入收藏模式。", justify="left",
                                               wraplength=290, text_color=("gray45", "gray60"))
        self.favorite_mode_hint.pack(anchor=tk.W, pady=(5, 0))

        card, body = self._make_card(tab, "预览", "当前选中收藏的预览图。")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.preview_label = ctk.CTkLabel(body, text="暂无预览", corner_radius=12, font=("Microsoft YaHei", 12), fg_color=("gray92", "gray18"))
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    # ---------------- 图源管理 ----------------
    def refresh_source_list(self):
        custom = self.cfg.get("custom_sources", [])
        display = []
        self._source_display_map = {}
        for key, source in wallpaper_service.BUILTIN_SOURCES.items():
            label = f"内置 · {source['name']}"
            display.append(label)
            self._source_display_map[label] = ("builtin", key, source)
        for idx, source in enumerate(custom):
            label = f"自定义 · {source['name']}"
            # 同名也不覆盖 map：给重复名称加序号显示。
            if label in self._source_display_map:
                label = f"自定义 · {source['name']} #{idx + 1}"
            display.append(label)
            self._source_display_map[label] = ("custom", idx, source)
        self.source_combo.configure(values=display)

        source_id = self.cfg.get("source_id", self.cfg.get("site", "all"))
        selected = None
        if source_id in wallpaper_service.BUILTIN_SOURCES:
            selected = next((x for x, v in self._source_display_map.items() if v[0] == "builtin" and v[1] == source_id), None)
        elif isinstance(source_id, str) and source_id.startswith("custom:"):
            try:
                idx = int(source_id.split(":", 1)[1])
                selected = next((x for x, v in self._source_display_map.items() if v[0] == "custom" and v[1] == idx), None)
            except ValueError:
                pass
        if selected is None and display:
            selected = display[0]
            self.cfg["source_id"] = self._source_display_map[selected][1] if self._source_display_map[selected][0] == "builtin" else f"custom:{self._source_display_map[selected][1]}"
        if selected:
            self.source_combo.set(selected)
            self.on_source_selected(selected)

    def on_source_selected(self, choice):
        info = self._source_display_map.get(choice)
        if not info:
            return
        kind, ident, source = info
        if kind == "builtin":
            self.custom_name_var.set("")
            self.custom_url_var.set("")
            self.custom_name_entry.configure(state="normal")
            self.custom_url_entry.configure(state="normal")
            self.source_hint_var.set(f"当前使用：{source['name']}\n地址：{source['url']}")
        else:
            self.custom_name_var.set(source.get("name", ""))
            self.custom_url_var.set(source.get("url", ""))
            self.source_hint_var.set(f"当前使用自定义图源：{source.get('name', '')}\n地址：{source.get('url', '')}")

    def _find_selected_custom_index(self):
        info = self._source_display_map.get(self.source_var.get())
        return info[1] if info and info[0] == "custom" else None

    def save_custom_source(self):
        name = self.custom_name_var.get().strip()
        url = self.custom_url_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请填写图源名称。", parent=self.root)
            return
        try:
            wallpaper_service.build_source_url(url, site="all", size="pc")
        except ValueError as exc:
            messagebox.showwarning("图源地址无效", str(exc), parent=self.root)
            return
        custom = self.cfg.get("custom_sources", [])
        idx = self._find_selected_custom_index()
        item_data = {"name": name, "url": url}
        if idx is None:
            custom.append(item_data)
            idx = len(custom) - 1
        else:
            custom[idx] = item_data
        self.cfg["custom_sources"] = custom
        self.cfg["source_id"] = f"custom:{idx}"
        self.cfg["site"] = "all"
        try:
            config.save_config(self.cfg)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return
        self.refresh_source_list()
        self._set_status(f"图源已保存：{name}", "ready")

    def delete_custom_source(self):
        idx = self._find_selected_custom_index()
        if idx is None:
            messagebox.showinfo("提示", "请先在“使用图源”中选中一个自定义图源。", parent=self.root)
            return
        custom = self.cfg.get("custom_sources", [])
        if not (0 <= idx < len(custom)):
            self.refresh_source_list()
            return
        name = custom[idx].get("name", "自定义图源")
        if not messagebox.askyesno("确认删除", f"确定删除自定义图源“{name}”吗？", parent=self.root):
            return
        custom.pop(idx)
        self.cfg["custom_sources"] = custom
        self.cfg["source_id"] = "all"
        try:
            config.save_config(self.cfg)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return
        self.refresh_source_list()
        self._set_status("已删除自定义图源", "ready")

    def get_selected_source(self):
        choice = self.source_var.get()
        info = self._source_display_map.get(choice)
        if not info:
            return "all", wallpaper_service.BUILTIN_SOURCES["all"]["url"]
        kind, ident, source = info
        if kind == "builtin":
            return ident, source["url"]
        return "all", source["url"]

    def test_custom_source(self):
        url = self.custom_url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先填写图源地址。", parent=self.root)
            return
        size = next((k for k, v in self.size_map.items() if v == self.size_var.get()), "pc")
        try:
            final_url = wallpaper_service.build_source_url(url, site="all", size=size)
        except ValueError as exc:
            messagebox.showerror("图源地址无效", str(exc), parent=self.root)
            return
        self._set_status("正在测试图源…", "busy")
        def task():
            try:
                data = wallpaper_service.fetch_source_image(final_url, timeout=12, retries=2)
                # 测试只验证可解析为图片，不写入桌面。
                from PIL import Image
                Image.open(__import__("io").BytesIO(data)).verify()
                self._ui_queue.put(("source_test_ok", "图源测试成功，可以正常获取图片。"))
            except Exception as exc:
                self._ui_queue.put(("source_test_error", str(exc)))
        threading.Thread(target=task, name="source-test", daemon=True).start()

    # ---------------- 状态 / 异步 ----------------
    def _set_status(self, text, kind="ready"):
        colors = {"ready": ("#3a9d6b", "#5ec48d"), "busy": ("#d59b35", "#e9b95d"), "error": ("#d65a5a", "#f07a7a"), "favorite": ("#bf8c2e", "#e6b954")}
        self.status_var.set(text)
        self.status_dot.configure(text_color=colors.get(kind, colors["ready"]))

    def _drain_ui_queue(self):
        while True:
            try:
                event, payload = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            if event == "success":
                self.is_downloading = False
                self.current_applied_wallpaper = payload
                self.mode = "online"
                self.reset_refresh_timer()
                self._set_status(f"在线壁纸已更新 · {time.strftime('%H:%M:%S')}", "ready")
                self._set_busy(False)
            elif event == "error":
                self.is_downloading = False
                self._consecutive_failures += 1
                self._schedule_failure_backoff(reset=False)
                self._set_status(f"换图失败：{payload}", "error")
                self._set_busy(False)
            elif event == "source_test_ok":
                self._set_status("图源测试成功", "ready")
                messagebox.showinfo("测试成功", payload, parent=self.root)
            elif event == "source_test_error":
                self._set_status("图源测试失败", "error")
                messagebox.showerror("图源测试失败", payload, parent=self.root)

    def _set_busy(self, busy):
        self.next_btn.configure(state="disabled" if busy else "normal", text="⏳  正在换图…" if busy else "🎲  换一张")

    # ---------------- 收藏 ----------------
    def refresh_favorites_list(self):
        files = wallpaper_service.list_favorites()
        self.fav_combo.configure(values=files)
        if files:
            if self.fav_combo_var.get() not in files:
                self.fav_combo.set(files[0])
        else:
            self.fav_combo_var.set("暂无收藏壁纸")
        self.update_favorite_preview()

    def update_favorite_preview(self):
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            self._preview_img = None
            self.preview_label.configure(image=None, text="暂无预览")
            return
        fav_path = os.path.join(config.FAVORITES_DIR, os.path.basename(filename))
        if not os.path.isfile(fav_path):
            self._preview_img = None
            self.preview_label.configure(image=None, text="文件不存在")
            return
        try:
            with Image.open(fav_path) as src:
                img = src.convert("RGB")
                img.thumbnail((700, 460))
            self._preview_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.preview_label.configure(image=self._preview_img, text="")
        except Exception:
            self._preview_img = None
            self.preview_label.configure(image=None, text="无法预览")

    def favorite_current_wallpaper(self):
        path = self.current_applied_wallpaper
        if not path or not os.path.isfile(path):
            messagebox.showwarning("提示", "当前没有可收藏的壁纸。", parent=self.root)
            return
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(config.FAVORITES_DIR):
            messagebox.showinfo("提示", "这张壁纸已经在收藏夹中了。", parent=self.root)
            return
        default_name = f"fav_{time.strftime('%Y%m%d_%H%M%S')}"
        dialog = ctk.CTkInputDialog(text="给这张壁纸取一个名字：", title="⭐ 收藏壁纸")
        dialog.after(80, lambda: dialog._entry.insert(0, default_name))
        new_name = dialog.get_input()
        if new_name is None:
            return
        new_name = re.sub(r'[\\/:*?"<>|]', "_", new_name.strip()) or default_name
        try:
            fav_filename, fav_path = wallpaper_service.save_favorite(path, new_name)
            wallpaper_service.set_wallpaper_windows(fav_path)
            self.current_applied_wallpaper = fav_path
            self.mode = "favorite"
            self.reset_refresh_timer()
            self.refresh_favorites_list()
            self.fav_combo_var.set(fav_filename)
            self.update_favorite_preview()
            self._set_status(f"⭐ 已收藏：{fav_filename}", "favorite")
        except Exception as exc:
            messagebox.showerror("收藏失败", str(exc), parent=self.root)

    def apply_selected_favorite(self):
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            messagebox.showwarning("提示", "请先选择一张收藏壁纸。", parent=self.root)
            return
        fav_path = os.path.join(config.FAVORITES_DIR, os.path.basename(filename))
        if not os.path.isfile(fav_path):
            messagebox.showerror("错误", "收藏文件不存在。", parent=self.root)
            self.refresh_favorites_list()
            return
        if wallpaper_service.set_wallpaper_windows(fav_path):
            self.current_applied_wallpaper = fav_path
            self.mode = "favorite"
            self.reset_refresh_timer()
            self._set_status(f"⭐ 使用收藏：{filename}", "favorite")
            self.update_favorite_preview()

    def cycle_favorite(self):
        files = wallpaper_service.list_favorites()
        if not files:
            self.reset_refresh_timer()
            return
        cur = self.fav_combo_var.get()
        try:
            idx = files.index(cur)
            nxt = files[(idx + 1) % len(files)]
        except ValueError:
            nxt = files[0]
        self.fav_combo_var.set(nxt)
        self.apply_selected_favorite()

    def delete_selected_favorite(self):
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            return
        if not messagebox.askyesno("确认删除", f"确定删除收藏【{filename}】吗？\n此操作会删除本地文件。", parent=self.root):
            return
        fav_path = os.path.join(config.FAVORITES_DIR, os.path.basename(filename))
        is_current = os.path.abspath(self.current_applied_wallpaper) == os.path.abspath(fav_path)
        try:
            if not wallpaper_service.delete_favorite(filename):
                raise FileNotFoundError("文件不存在")
            self.refresh_favorites_list()
            self._set_status("已删除收藏", "ready")
            if is_current:
                self.fetch_and_set_wallpaper()
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    # ---------------- 下载 / 定时 ----------------
    def reset_refresh_timer(self):
        self._consecutive_failures = 0
        interval = max(0, int(self.cfg.get("interval_minutes", 30)))
        self._next_refresh_time = time.time() + interval * 60 if interval > 0 else float("inf")

    def _schedule_failure_backoff(self, reset=True):
        if reset:
            self._consecutive_failures = 0
        base = max(60, int(self.cfg.get("interval_minutes", 30)) * 60)
        wait = min(30 * (2 ** max(0, self._consecutive_failures - 1)), base)
        self._next_refresh_time = time.time() + wait

    def fetch_and_set_wallpaper(self):
        if self.is_downloading or self._closing:
            return
        self.is_downloading = True
        self._set_busy(True)
        self._set_status("正在下载新壁纸…", "busy")
        site, source_url = self.get_selected_source()
        size = next((k for k, v in self.size_map.items() if v == self.size_var.get()), self.cfg.get("size", "pc"))

        def task():
            try:
                path = wallpaper_service.download_wallpaper(site, size, source_url=source_url)
                if not wallpaper_service.set_wallpaper_windows(path):
                    raise RuntimeError("Windows 没有成功应用这张壁纸")
                self._ui_queue.put(("success", path))
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))
        threading.Thread(target=task, name="wallpaper-download", daemon=True).start()

    def timer_loop(self):
        if self._closing:
            return
        self._drain_ui_queue()
        if self.is_downloading:
            self.countdown_var.set("正在获取下一张壁纸…")
        else:
            interval = int(self.cfg.get("interval_minutes", 30))
            if interval <= 0:
                self.countdown_var.set("自动刷新：已关闭")
            else:
                remain = max(0, int(self._next_refresh_time - time.time()))
                self.countdown_var.set(f"下次刷新：{remain // 60:02d}:{remain % 60:02d}")
                if time.time() >= self._next_refresh_time:
                    if self.mode == "favorite" and self.cfg.get("favorite_carousel", False):
                        self.cycle_favorite()
                    else:
                        self.fetch_and_set_wallpaper()
        self.root.after(1000, self.timer_loop)

    # ---------------- 托盘 / 设置 / 退出 ----------------
    def register_hotkeys(self):
        if keyboard is None:
            return
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        pairs = [
            (self.cfg.get("hotkey_favorite", "").strip(), self.favorite_current_wallpaper, "收藏"),
            (self.cfg.get("hotkey_switch", "").strip(), self.fetch_and_set_wallpaper, "切换"),
        ]
        for hotkey_text, callback, label in pairs:
            if not hotkey_text:
                continue
            try:
                keyboard.add_hotkey(hotkey_text, lambda cb=callback: self.root.after(0, cb))
            except Exception as exc:
                self._set_status(f"{label}快捷键无效：{exc}", "error")

    def init_tray_icon(self):
        menu = (
            item("打开设置界面", lambda: self.root.after(0, self._restore_ui), default=True),
            item("🎲 换一张在线壁纸", lambda: self.root.after(0, self.fetch_and_set_wallpaper)),
            item("⭐ 收藏当前壁纸", lambda: self.root.after(0, self.favorite_current_wallpaper)),
            item("❌ 退出并还原壁纸", lambda: self.root.after(0, self.quit_and_restore)),
        )
        self.tray_icon = pystray.Icon("TouhouWallpaper", self._create_tray_icon_image(), "Touhou Wallpaper", menu)
        self.tray_icon.run_detached()

    @staticmethod
    def _create_tray_icon_image():
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse([4, 4, 60, 60], fill="#3b82f6", outline="#2563eb", width=2)
        dc.polygon([(16, 44), (28, 22), (40, 44)], fill="white")
        dc.polygon([(34, 44), (44, 30), (52, 44)], fill="white")
        return image

    def _restore_ui(self):
        self.refresh_favorites_list()
        self.refresh_source_list()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        if self._closing:
            return
        self.apply_settings(show_msg=False)
        self.root.withdraw()

    def apply_settings(self, show_msg=True):
        old_interval = self.cfg.get("interval_minutes", 30)
        self.cfg["refresh_on_startup"] = self.var_startup.get()
        self.cfg["auto_start"] = self.var_autostart.get()
        self.cfg["interval_minutes"] = self.interval_map.get(self.interval_var.get(), 30)
        self.cfg["size"] = next((k for k, v in self.size_map.items() if v == self.size_var.get()), "pc")
        self.cfg["wallpaper_style"] = next((k for k, v in self.style_map.items() if v == self.style_var.get()), "fill")
        self.cfg["favorite_carousel"] = self.var_fav_carousel.get()
        self.cfg["hotkey_favorite"] = self.hk_fav_var.get().strip()
        self.cfg["hotkey_switch"] = self.hk_switch_var.get().strip()

        info = self._source_display_map.get(self.source_var.get())
        if info:
            if info[0] == "builtin":
                self.cfg["source_id"] = info[1]
                self.cfg["site"] = info[1]
            else:
                self.cfg["source_id"] = f"custom:{info[1]}"
                self.cfg["site"] = "all"
        try:
            config.save_config(self.cfg)
            config.set_auto_start_registry(self.cfg["auto_start"])
            self.register_hotkeys()
            self.apply_wallpaper_style(self.cfg["wallpaper_style"])
            if old_interval != self.cfg["interval_minutes"]:
                self.reset_refresh_timer()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return
        if show_msg:
            messagebox.showinfo("设置已保存", "新设置已生效。", parent=self.root)

    def apply_wallpaper_style(self, style_key=None):
        style_key = style_key or self.cfg.get("wallpaper_style", "fill")
        if wallpaper_service.set_wallpaper_style(style_key):
            cur = self.current_applied_wallpaper
            if cur and os.path.isfile(cur):
                wallpaper_service.set_wallpaper_windows(cur)

    def restore_original_wallpaper(self):
        path = self.cfg.get("original_wallpaper", "")
        if path and os.path.isfile(path):
            wallpaper_service.set_wallpaper_windows(path)

    def quit_and_restore(self):
        if self._closing:
            return
        self._closing = True
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            if keyboard is not None:
                keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self.restore_original_wallpaper()
        self.root.destroy()
