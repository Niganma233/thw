import os
import queue
import tempfile
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import config
import wallpaper_service
from core.scheduler import (
    ACTION_CYCLE_FAVORITE,
    ACTION_FETCH,
    BEHAVIOR_CAROUSEL,
    BEHAVIOR_PAUSE,
    BEHAVIORS,
    MODE_FAVORITE,
    MODE_ONLINE,
    RefreshScheduler,
    resolve_favorite_behavior,
)
from services.wallpaper_worker import EVENT_ERROR, EVENT_SUCCESS, WallpaperDownloadWorker
from source_manager import SourceManager
from ui import theme
from ui.dialogs import ask_wallpaper_name, show_data_dir_unwritable
from ui.favorite_view import FavoriteView
from ui.hotkeys import HotkeyManager
from ui.settings_view import SettingsView
from ui.source_manager_view import SourceManagerView
from ui.status_bar import StatusPresenter
from ui.tray import TrayController
from ui.widgets import open_folder


class WallpaperApp:
    """主窗口编排层：只负责生命周期、下载调度、托盘与视图之间的协调。

    "什么时候换"在 core.scheduler.RefreshScheduler，
    "怎么换"在 services.wallpaper_worker.WallpaperDownloadWorker，
    这里只负责把它们和界面接起来。
    """

    def __init__(self, root, silent=False):
        self.root = root
        self.root.title("Touhou Wallpaper")
        self.root.geometry("1040x900")
        self.root.minsize(940, 840)
        self.root.resizable(True, True)

        self.cfg = config.load_config()
        self.source_manager = SourceManager(self.cfg)
        self.scheduler = RefreshScheduler(
            interval_minutes=self.cfg.get("interval_minutes", 30),
            favorite_behavior=resolve_favorite_behavior(self.cfg),
        )
        self.scheduler.reset(time.time())
        self.current_applied_wallpaper = ""
        self.is_downloading = False
        self._ui_queue = queue.Queue()
        self.downloader = WallpaperDownloadWorker(self._ui_queue)
        self._closing = False
        self.tray = TrayController(self.root)
        # on_error 只在真正注册快捷键时才会被调用，那时状态栏已经建好了
        self.hotkeys = HotkeyManager(self.root, on_error=lambda text: self.set_status(text, "error"))

        self._backup_original_wallpaper()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.init_ui()
        # 窗口化运行时回调里的异常默认没人看得到，统一显示到状态栏，避免"点了没反应"。
        # 必须在 init_ui() 之后：状态栏由 StatusPresenter 负责。
        self.status.install_exception_hook(self.root)
        self.favorite_view.refresh()
        self.source_view.refresh()
        self.init_tray_icon()
        self.register_hotkeys()
        self._warn_if_data_dir_readonly(show_dialog=not silent)

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

    def init_ui(self):
        container = ctk.CTkFrame(self.root, fg_color="transparent")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        header = ctk.CTkFrame(container, corner_radius=16)
        header.pack(fill=tk.X, pady=(0, 14))
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20, pady=16)
        ctk.CTkLabel(brand, text="🌸  Touhou Wallpaper", font=theme.FONT_BRAND, anchor="w").pack(anchor=tk.W)
        ctk.CTkLabel(brand, text="自动更换东方 Project 壁纸 · 图源可自定义", font=theme.FONT_BODY, text_color=theme.COLOR_MUTED_STRONG, anchor="w").pack(anchor=tk.W, pady=(2, 0))

        self.status = StatusPresenter(header, initial_text="在线轮播就绪")

        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill=tk.X, pady=(0, 14))
        self.next_btn = ctk.CTkButton(actions, text="🎲  换一张", height=42, font=theme.FONT_COMBO, command=self.fetch_and_set_wallpaper)
        self.next_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ctk.CTkButton(actions, text="⭐  收藏当前", height=42, command=self.favorite_current_wallpaper).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ctk.CTkButton(actions, text="📂  打开收藏夹", height=42, command=lambda: open_folder(config.FAVORITES_DIR)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ctk.CTkButton(actions, text="🗕  托盘", height=42, command=self.hide_to_tray).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        self.tabview = ctk.CTkTabview(container)
        self.tabview.pack(fill=tk.BOTH, expand=True)
        general_tab = self.tabview.add("⚙  常规")
        source_tab = self.tabview.add("🌐  图源管理")
        favorite_tab = self.tabview.add("⭐  收藏")

        self.settings_view = SettingsView(general_tab, self.cfg, app=self)
        self.source_view = SourceManagerView(source_tab, self.cfg, manager=self.source_manager, on_changed=self._source_changed, on_status=self.set_status)
        self.favorite_view = FavoriteView(favorite_tab, self)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill=tk.X, pady=(12, 0))
        self.countdown_var = tk.StringVar(value="下次刷新：—")
        ctk.CTkLabel(footer, textvariable=self.countdown_var, font=("Microsoft YaHei", 11), text_color=("gray45", "gray60")).pack(side=tk.LEFT)
        ctk.CTkButton(footer, text="保存设置", width=120, height=34, command=self.apply_settings).pack(side=tk.RIGHT, padx=(8, 0))
        ctk.CTkButton(footer, text="退出并还原壁纸", width=140, height=34, fg_color="#b44", hover_color="#933", command=self.quit_and_restore).pack(side=tk.RIGHT)

    # ---------- 模式 ----------
    @property
    def mode(self):
        """当前是在线轮播还是收藏模式。

        mode 由调度器持有，这里只做转发：视图会写 ``app.mode = "favorite"``，
        如果两边各存一份就会各改一半，正是"星标轮播计时"反复出问题的根源。
        """
        return self.scheduler.mode

    @mode.setter
    def mode(self, value):
        self.scheduler.mode = value

    # ---------- 视图回调 ----------
    def on_favorite_behavior_changed(self, behavior):
        """收藏行为设置改变后立即更新当前模式的计时策略。"""
        if behavior not in BEHAVIORS:
            behavior = BEHAVIOR_PAUSE
        self.scheduler.favorite_behavior = behavior
        self.cfg["favorite_behavior"] = behavior
        self.cfg["favorite_carousel"] = behavior == BEHAVIOR_CAROUSEL
        if self.mode == MODE_FAVORITE:
            self.reset_refresh_timer()
        self._update_countdown()

    def _source_changed(self, save=False):
        # 图源是由 SourceManagerView 通过共享的 SourceManager 实例就地改的，
        # self.source_manager 始终看得到最新状态，不必重建（重建只会白跑一遍迁移）。
        if save:
            config.save_config(self.cfg)

    def set_status(self, text, kind="ready"):
        """更新状态栏。

        保留这个方法是刻意的：视图通过 ``on_status=self.set_status`` 拿到它，
        它是一个对外接口，而不是纯粹的转发包装。
        """
        self.status.set(text, kind)

    def _warn_if_data_dir_readonly(self, show_dialog=True):
        """数据目录不可写时立刻提示，否则收藏、缓存、设置都会静默失败。"""
        try:
            handle, probe = tempfile.mkstemp(prefix="write_test_", dir=config.APP_DIR)
            os.close(handle)
            os.remove(probe)
            return
        except OSError as exc:
            self.set_status(f"数据目录不可写：{exc}", "error")
            if show_dialog:
                show_data_dir_unwritable(self.root, config.APP_DIR)

    # ---------- 收藏 ----------
    def favorite_current_wallpaper(self):
        path = self.current_applied_wallpaper
        if not path or not os.path.isfile(path):
            messagebox.showwarning("提示", "当前没有可收藏的壁纸。", parent=self.root)
            return
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(config.FAVORITES_DIR):
            messagebox.showinfo("提示", "这张壁纸已经在收藏夹中了。", parent=self.root)
            return
        name = ask_wallpaper_name(f"fav_{time.strftime('%Y%m%d_%H%M%S')}")
        if name is None:
            return
        try:
            filename, fav_path = wallpaper_service.save_favorite(path, name)
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
        preferred = self._selected_source()
        candidates = self.source_manager.enabled_candidates(preferred.get("id") if preferred else None)
        if not candidates:
            self._download_result(False, "没有启用的图源")
            return
        self.is_downloading = True
        self.next_btn.configure(state="disabled", text="⏳  正在换图…")
        self.set_status("正在下载新壁纸…", "busy")
        # 回退循环与线程都在 worker 里；这里只等队列事件。
        self.downloader.start(candidates)

    def _download_result(self, success, payload, source_id=None, source_name=None):
        self.is_downloading = False
        self.next_btn.configure(state="normal", text="🎲  换一张")
        if success:
            self.current_applied_wallpaper = payload
            self.mode = MODE_ONLINE
            self.scheduler.on_success(time.time())
            self.set_status(f"在线壁纸已更新 · {source_name or ''} · {time.strftime('%H:%M:%S')}", "ready")
            if source_id and source_id != self.cfg.get("source_id"):
                # 失败回退到其他图源后，记录最终成功图源，后续优先使用它。
                self.cfg["source_id"] = source_id
                config.save_config(self.cfg)
            return
        self.scheduler.on_failure(time.time())
        self.set_status(f"换图失败：{payload}", "error")

    # ---------- 定时 ----------
    def _sync_scheduler_config(self):
        """把配置里会影响计时的项同步给调度器。"""
        self.scheduler.interval_minutes = self.cfg.get("interval_minutes", 30)
        self.scheduler.favorite_behavior = resolve_favorite_behavior(self.cfg)

    def reset_refresh_timer(self):
        self._sync_scheduler_config()
        self.scheduler.reset(time.time())

    def _update_countdown(self):
        self.countdown_var.set(
            self.scheduler.countdown_text(time.time(), downloading=self.is_downloading)
        )

    def timer_loop(self):
        if self._closing:
            return
        self._drain_download_events()
        if not self.is_downloading and self.scheduler.is_due(time.time()):
            action = self.scheduler.next_action()
            if action == ACTION_CYCLE_FAVORITE:
                self._cycle_favorite()
            elif action == ACTION_FETCH:
                self.fetch_and_set_wallpaper()
            else:
                self.scheduler.suspend()
        self._update_countdown()
        self.root.after(1000, self.timer_loop)

    def _drain_download_events(self):
        """把后台下载线程放进队列的结果取出来应用。"""
        while True:
            try:
                event = self._ui_queue.get_nowait()
            except queue.Empty:
                return
            if event[0] == EVENT_SUCCESS:
                self._download_result(True, event[1], event[2], event[3])
            elif event[0] == EVENT_ERROR:
                self._download_result(False, event[1])

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
        self.hotkeys.register([
            (self.cfg.get("hotkey_favorite", ""), self.favorite_current_wallpaper, "收藏"),
            (self.cfg.get("hotkey_switch", ""), self.fetch_and_set_wallpaper, "切换"),
        ])

    def init_tray_icon(self):
        self.tray.start([
            ("打开设置界面", self._restore_ui),
            ("🎲 换一张在线壁纸", self.fetch_and_set_wallpaper),
            ("⭐ 收藏当前壁纸", self.favorite_current_wallpaper),
            ("❌ 退出并还原壁纸", self.quit_and_restore),
        ])

    def _restore_ui(self):
        self.favorite_view.refresh()
        self.source_view.refresh()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        if self._closing:
            return
        # 保存失败时留在界面上并提示，而不是"点了没反应"
        if not self.apply_settings(show_msg=False):
            return
        self.root.withdraw()

    def apply_settings(self, show_msg=True):
        old_interval = self.cfg.get("interval_minutes", 30)
        old_favorite_behavior = self.cfg.get("favorite_behavior")
        try:
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
        except Exception as exc:
            self.set_status(f"保存设置失败：{exc}", "error")
            if show_msg:
                messagebox.showerror("保存设置失败", str(exc), parent=self.root)
            return False
        if old_interval != self.cfg["interval_minutes"] or old_favorite_behavior != self.cfg.get("favorite_behavior"):
            self.reset_refresh_timer()
        else:
            self._update_countdown()
        if show_msg:
            messagebox.showinfo("设置已保存", "设置已保存并生效。", parent=self.root)
        return True

    def quit_and_restore(self):
        if self._closing:
            return
        self._closing = True
        try:
            self.tray.stop()
            self.hotkeys.unregister()
            path = self.cfg.get("original_wallpaper", "")
            if path and os.path.isfile(path):
                wallpaper_service.set_wallpaper_windows(path)
            self.root.destroy()
        except Exception as exc:
            # 退出途中出错时把锁恢复，否则"退出/托盘"按钮会永久失效
            self._closing = False
            self.set_status(f"退出失败：{exc}", "error")
            messagebox.showerror("退出失败", str(exc), parent=self.root)
