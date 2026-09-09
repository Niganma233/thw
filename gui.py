import os
import queue
import threading
import time
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
from favorite_view import FavoriteView
from settings_view import SettingsView
from source_manager_view import SourceManagerView
from source_manager import SourceManager

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


class WallpaperApp:
    """主窗口编排层：只负责生命周期、下载调度、托盘与视图之间的协调。"""

    def __init__(self, root, silent=False):
        self.root = root
        self.root.title("Touhou Wallpaper")
        self.root.geometry("1040x760")
        self.root.minsize(940, 840)
        self.root.resizable(True, True)

        self.cfg = config.load_config()
        self.source_manager = SourceManager(self.cfg)
        self.mode = "online"
        self.current_applied_wallpaper = ""
        self.is_downloading = False
        self._consecutive_failures = 0
        self._next_refresh_time = time.time() + max(0, int(self.cfg.get("interval_minutes", 30))) * 60
        self._ui_queue = queue.Queue()
        self._closing = False
        self.tray_icon = None

        self._backup_original_wallpaper()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.init_ui()
        self.favorite_view.refresh()
        self.source_view.refresh()
        self.init_tray_icon()
        self.register_hotkeys()
        self.set_status("在线轮播就绪", "ready")

        if self.cfg.get("refresh_on_startup", True):
            self.fetch_and_set_wallpaper()
        self.timer_loop()
        if silent:
            self.root.withdraw()

    # ---------- 窗口 ----------
    def _backup_original_wallpaper(self):
        cur_wp = wallpaper_service.get_current_windows_wallpaper()
        if cur_wp and not cur_wp.lower().startswith(config.APP_DIR.lower()):
            self.cfg["original_wallpaper"] = cur_wp
            config.save_config(self.cfg)

    def _make_card(self, parent, title, subtitle=None):
        card = ctk.CTkFrame(parent, corner_radius=14, border_width=1)
        ctk.CTkLabel(card, text=title, font=("Microsoft YaHei", 14, "bold"), anchor="w").pack(anchor=tk.W, padx=16, pady=(14, 2))
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=("Microsoft YaHei", 10), text_color=("gray45", "gray60"), justify="left").pack(anchor=tk.W, padx=16, pady=(0, 8))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(2, 14))
        return card, body

    def init_ui(self):
        container = ctk.CTkFrame(self.root, fg_color="transparent")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        header = ctk.CTkFrame(container, corner_radius=16)
        header.pack(fill=tk.X, pady=(0, 14))
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20, pady=16)
        ctk.CTkLabel(brand, text="🌸  Touhou Wallpaper", font=("Microsoft YaHei", 21, "bold"), anchor="w").pack(anchor=tk.W)
        ctk.CTkLabel(brand, text="自动更换东方 Project 壁纸 · 图源可自定义", font=("Microsoft YaHei", 11), text_color=("gray40", "gray65"), anchor="w").pack(anchor=tk.W, pady=(2, 0))

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
        general_tab = self.tabview.add("⚙  常规")
        source_tab = self.tabview.add("🌐  图源管理")
        favorite_tab = self.tabview.add("⭐  收藏")

        self.settings_view = SettingsView(general_tab, self.cfg, app=self)
        self.source_view = SourceManagerView(source_tab, self.cfg, on_changed=self._source_changed, on_status=self.set_status)
        self.favorite_view = FavoriteView(favorite_tab, self)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill=tk.X, pady=(12, 0))
        self.countdown_var = tk.StringVar(value="下次刷新：—")
        ctk.CTkLabel(footer, textvariable=self.countdown_var, font=("Microsoft YaHei", 11), text_color=("gray45", "gray60")).pack(side=tk.LEFT)
        ctk.CTkButton(footer, text="保存设置", width=120, height=34, command=self.apply_settings).pack(side=tk.RIGHT, padx=(8, 0))
        ctk.CTkButton(footer, text="退出并还原壁纸", width=140, height=34, fg_color="#b44", hover_color="#933", command=self.quit_and_restore).pack(side=tk.RIGHT)

    # ---------- 视图回调 ----------
    def _source_changed(self, save=False):
        self.source_manager = SourceManager(self.cfg)
        if save:
            config.save_config(self.cfg)

    def set_status(self, text, kind="ready"):
        colors = {"ready": ("#3a9d6b", "#5ec48d"), "busy": ("#d59b35", "#e9b95d"), "error": ("#d65a5a", "#f07a7a"), "favorite": ("#bf8c2e", "#e6b954")}
        self.status_var.set(text)
        self.status_dot.configure(text_color=colors.get(kind, colors["ready"]))

    # ---------- 收藏兼容入口 ----------
    def favorite_current_wallpaper(self):
        self._favorite_current_wallpaper()

    def _favorite_current_wallpaper(self):
        path = self.current_applied_wallpaper
        if not path or not os.path.isfile(path):
            messagebox.showwarning("提示", "当前没有可收藏的壁纸。", parent=self.root)
            return
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(config.FAVORITES_DIR):
            messagebox.showinfo("提示", "这张壁纸已经在收藏夹中了。", parent=self.root)
            return
        dialog = ctk.CTkInputDialog(text="给这张壁纸取一个名字：", title="⭐ 收藏壁纸")
        default_name = f"fav_{time.strftime('%Y%m%d_%H%M%S')}"
        dialog.after(80, lambda: dialog._entry.insert(0, default_name))
        name = dialog.get_input()
        if name is None:
            return
        name = name.strip() or default_name
        safe_name = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip().rstrip(".") or default_name
        try:
            filename, fav_path = wallpaper_service.save_favorite(path, safe_name)
            wallpaper_service.set_wallpaper_windows(fav_path)
            self.current_applied_wallpaper = fav_path
            self.mode = "favorite"
            self.reset_refresh_timer()
            self.favorite_view.refresh()
            self.favorite_view.fav_combo_var.set(filename)
            self.favorite_view.update_preview()
            self.set_status(f"⭐ 已收藏：{filename}", "favorite")
        except Exception as exc:
            messagebox.showerror("收藏失败", str(exc), parent=self.root)

    # ---------- 下载 ----------
    def _selected_source(self):
        sid = self.cfg.get("source_id", "all")
        source = self.source_manager.get(sid) or self.source_manager.get("all")
        return source

    def fetch_and_set_wallpaper(self):
        if self.is_downloading or self._closing:
            return
        self.is_downloading = True
        self.next_btn.configure(state="disabled", text="⏳  正在换图…")
        self.set_status("正在下载新壁纸…", "busy")
        preferred = self._selected_source()
        candidates = self.source_manager.enabled_candidates(preferred.get("id") if preferred else None)
        if not candidates:
            self._download_result(False, "没有启用的图源")
            return

        def task():
            errors = []
            for source in candidates:
                try:
                    path = wallpaper_service.download_wallpaper(source)
                    if not wallpaper_service.set_wallpaper_windows(path):
                        raise RuntimeError("Windows 没有成功应用壁纸")
                    self._ui_queue.put(("success", path, source["id"], source["name"]))
                    return
                except Exception as exc:
                    errors.append(f"{source['name']}: {exc}")
            self._ui_queue.put(("error", "\n".join(errors[:3])))

        threading.Thread(target=task, name="wallpaper-download", daemon=True).start()

    def _download_result(self, success, payload, source_id=None, source_name=None):
        self.is_downloading = False
        self.next_btn.configure(state="normal", text="🎲  换一张")
        if success:
            self.current_applied_wallpaper = payload
            self.mode = "online"
            self._consecutive_failures = 0
            self.reset_refresh_timer()
            self.set_status(f"在线壁纸已更新 · {source_name or ''} · {time.strftime('%H:%M:%S')}", "ready")
            if source_id and source_id != self.cfg.get("source_id"):
                # 失败回退到其他图源后，记录最终成功图源，后续优先使用它。
                self.cfg["source_id"] = source_id
                config.save_config(self.cfg)
            return
        self._consecutive_failures += 1
        self._schedule_failure_backoff(reset=False)
        self.set_status(f"换图失败：{payload}", "error")

    # ---------- 定时 ----------
    def reset_refresh_timer(self):
        interval = max(0, int(self.cfg.get("interval_minutes", 30)))
        self._next_refresh_time = time.time() + interval * 60 if interval > 0 else float("inf")

    def _schedule_failure_backoff(self, reset=True):
        if reset:
            self._consecutive_failures = 0
        base = max(60, int(self.cfg.get("interval_minutes", 30)) * 60)
        wait = min(30 * (2 ** max(0, self._consecutive_failures - 1)), base)
        self._next_refresh_time = time.time() + wait

    def timer_loop(self):
        if self._closing:
            return
        while True:
            try:
                event = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            if event[0] == "success":
                self._download_result(True, event[1], event[2], event[3])
            elif event[0] == "error":
                self._download_result(False, event[1])

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
                        self._cycle_favorite()
                    else:
                        self.fetch_and_set_wallpaper()
        self.root.after(1000, self.timer_loop)

    def _cycle_favorite(self):
        files = wallpaper_service.list_favorites()
        if not files:
            self.reset_refresh_timer()
            return
        current = self.favorite_view.fav_combo_var.get()
        idx = files.index(current) if current in files else -1
        self.favorite_view.fav_combo_var.set(files[(idx + 1) % len(files)])
        self.favorite_view.apply_selected()

    # ---------- 热键 / 托盘 ----------
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
                self.set_status(f"{label}快捷键无效：{exc}", "error")

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
        self.favorite_view.refresh()
        self.source_view.refresh()
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
        self.cfg.update(self.settings_view.collect())
        self.cfg.update(self.favorite_view.collect())
        config.save_config(self.cfg)
        config.set_auto_start_registry(self.cfg["auto_start"])
        self.register_hotkeys()
        # Windows 的 WallpaperStyle 注册表值通常要在重新应用壁纸后才会立即生效。
        wallpaper_service.set_wallpaper_style(self.cfg["wallpaper_style"])
        current = self.current_applied_wallpaper
        if current and os.path.isfile(current):
            wallpaper_service.set_wallpaper_windows(current)
        if old_interval != self.cfg["interval_minutes"]:
            self.reset_refresh_timer()
        if show_msg:
            messagebox.showinfo("设置已保存", "设置已保存并生效。", parent=self.root)

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
        path = self.cfg.get("original_wallpaper", "")
        if path and os.path.isfile(path):
            wallpaper_service.set_wallpaper_windows(path)
        self.root.destroy()
