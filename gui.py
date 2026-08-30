import os
import sys
import re
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw, ImageTk

try:
    import keyboard
except ImportError:
    keyboard = None

import config
import wallpaper_service


def create_tray_icon_image():
    """绘制托盘小图标"""
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([4, 4, 60, 60], fill="#3498db", outline="#2980b9", width=2)
    dc.polygon([(16, 44), (28, 22), (40, 44)], fill="#ffffff")
    dc.polygon([(34, 44), (44, 30), (52, 44)], fill="#ffffff")
    return image


class WallpaperApp:
    def __init__(self, root, silent=False):
        self.root = root
        self.root.title("TH wallpaper")
        self.root.geometry("480x840")
        self.root.resizable(False, False)

        self.cfg = config.load_config()
        self.is_downloading = False

        # 运行模式: "online" (在线轮播中) 或 "favorite" (锁定星标壁纸，停止定时刷新)
        self.mode = "online"
        self.current_applied_wallpaper = ""
        # 连续下载失败次数（用于失败后的指数退避重试）
        self._consecutive_failures = 0
        # 下次自动轮播的绝对时间戳（成功下载/点击换一张后重新计时）
        self._next_refresh_time = time.time() + self.cfg.get("interval_minutes", 30) * 60

        # 备份系统最初的原壁纸
        cur_wp = wallpaper_service.get_current_windows_wallpaper()
        if cur_wp and not cur_wp.lower().startswith(config.APP_DIR.lower()):
            self.cfg["original_wallpaper"] = cur_wp
            config.save_config(self.cfg)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.init_ui()
        self.refresh_favorites_list()
        self.init_tray_icon()
        self.register_hotkeys()

        if self.cfg.get("refresh_on_startup", True):
            self.fetch_and_set_wallpaper()

        self.timer_loop()

        if silent:
            self.root.withdraw()

    def init_ui(self):
        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # 1. 顶部状态
        self.status_var = tk.StringVar(value="状态: 在线轮播就绪")
        ttk.Label(frame, textvariable=self.status_var, font=("Microsoft YaHei", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))

        # 2. 刷新条件设置
        cond_frame = ttk.LabelFrame(frame, text="自动轮播设置", padding=8)
        cond_frame.pack(fill=tk.X, pady=4)

        self.var_startup = tk.BooleanVar(value=self.cfg["refresh_on_startup"])
        ttk.Checkbutton(cond_frame, text="开机 / 启动时立即刷新一次", variable=self.var_startup).pack(anchor=tk.W)

        self.var_autostart = tk.BooleanVar(value=self.cfg["auto_start"])
        ttk.Checkbutton(cond_frame, text="开机时自动启动本程序", variable=self.var_autostart).pack(anchor=tk.W)

        interval_box = ttk.Frame(cond_frame)
        interval_box.pack(fill=tk.X, pady=2)
        ttk.Label(interval_box, text="定时刷新间隔:").pack(side=tk.LEFT)

        intervals = {
            "不自动定时": 0, "每 5 分钟": 5, "每 15 分钟": 15,
            "每 30 分钟": 30, "每 1 小时": 60, "每 2 小时": 120, "每 4 小时": 240
        }
        self.interval_map = intervals
        cur_text = "每 30 分钟"
        for k, v in intervals.items():
            if v == self.cfg["interval_minutes"]:
                cur_text = k
                break
        self.interval_var = tk.StringVar(value=cur_text)
        self.combo_interval = ttk.Combobox(interval_box, textvariable=self.interval_var, values=list(intervals.keys()), state="readonly", width=12)
        self.combo_interval.pack(side=tk.LEFT, padx=8)

        # 3. 在线偏好设置
        api_frame = ttk.LabelFrame(frame, text="在线图片偏好", padding=8)
        api_frame.pack(fill=tk.X, pady=4)

        row_box = ttk.Frame(api_frame)
        row_box.pack(fill=tk.X)
        ttk.Label(row_box, text="图源:").pack(side=tk.LEFT)
        self.site_var = tk.StringVar(value=self.cfg["site"])
        ttk.Combobox(row_box, textvariable=self.site_var, values=["all", "konachan", "yandere"], state="readonly", width=10).pack(side=tk.LEFT, padx=(5, 15))

        ttk.Label(row_box, text="尺寸:").pack(side=tk.LEFT)
        self.size_var = tk.StringVar(value=self.cfg["size"])
        ttk.Combobox(row_box, textvariable=self.size_var, values=["pc", "mobile"], state="readonly", width=8).pack(side=tk.LEFT, padx=5)

        style_row = ttk.Frame(api_frame)
        style_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(style_row, text="显示方式:").pack(side=tk.LEFT)
        self.style_map = {
            "fill": "填充 (Fill)",
            "fit": "适应 (Fit)",
            "center": "居中 (Center)",
            "stretch": "拉伸 (Stretch)",
        }
        cur_style = self.cfg.get("wallpaper_style", "fill")
        cur_style_text = self.style_map.get(cur_style, self.style_map["fill"])
        self.style_var = tk.StringVar(value=cur_style_text)
        ttk.Combobox(style_row, textvariable=self.style_var, values=list(self.style_map.values()), state="readonly", width=12).pack(side=tk.LEFT, padx=5)

        # 4. ★ 星标/收藏管理面板 ★
        fav_frame = ttk.LabelFrame(frame, text="⭐ 星标收藏夹管理", padding=8)
        fav_frame.pack(fill=tk.X, pady=6)

        # 收藏操作行
        fav_op_box = ttk.Frame(fav_frame)
        fav_op_box.pack(fill=tk.X, pady=2)
        ttk.Button(fav_op_box, text="⭐ 收藏当前壁纸", command=self.favorite_current_wallpaper).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(fav_op_box, text="📂 打开收藏文件夹", command=lambda: os.startfile(config.FAVORITES_DIR)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.var_fav_carousel = tk.BooleanVar(value=self.cfg.get("favorite_carousel", False))
        ttk.Checkbutton(fav_frame, text="定时轮播星标壁纸（开启后收藏夹内壁纸按设置间隔自动切换）",
                        variable=self.var_fav_carousel).pack(anchor=tk.W, pady=(2, 0))

        # 收藏列表选择行
        fav_sel_box = ttk.Frame(fav_frame)
        fav_sel_box.pack(fill=tk.X, pady=4)
        ttk.Label(fav_sel_box, text="已收藏壁纸:").pack(side=tk.LEFT)
        self.fav_combo_var = tk.StringVar()
        self.fav_combo = ttk.Combobox(fav_sel_box, textvariable=self.fav_combo_var, state="readonly", width=22)
        self.fav_combo.pack(side=tk.LEFT, padx=5)
        self.fav_combo.bind("<<ComboboxSelected>>", lambda e: self.update_favorite_preview())

        fav_action_box = ttk.Frame(fav_frame)
        fav_action_box.pack(fill=tk.X, pady=2)
        ttk.Button(fav_action_box, text="应用选中的星标壁纸", command=self.apply_selected_favorite).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(fav_action_box, text="🗑️ 取消星标 (本地删除)", command=self.delete_selected_favorite).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 星标壁纸预览图
        self.preview_canvas = tk.Canvas(fav_frame, width=400, height=180, bg="#f0f0f0",
                                        highlightthickness=1, highlightbackground="#c0c0c0")
        self.preview_canvas.pack(fill=tk.X, pady=4)
        self._preview_img = None
        self.update_favorite_preview()

        # 5. 全局快捷键设置（默认不设置，需用户自行填写）
        hk_frame = ttk.LabelFrame(frame, text="⌨ 全局快捷键（默认不设置，需自行填写）", padding=8)
        hk_frame.pack(fill=tk.X, pady=4)

        hk_row1 = ttk.Frame(hk_frame)
        hk_row1.pack(fill=tk.X, pady=2)
        ttk.Label(hk_row1, text="收藏当前壁纸:").pack(side=tk.LEFT)
        self.hk_fav_var = tk.StringVar(value=self.cfg.get("hotkey_favorite", ""))
        ttk.Entry(hk_row1, textvariable=self.hk_fav_var, width=24).pack(side=tk.LEFT, padx=5)

        hk_row2 = ttk.Frame(hk_frame)
        hk_row2.pack(fill=tk.X, pady=2)
        ttk.Label(hk_row2, text="切换在线壁纸:").pack(side=tk.LEFT)
        self.hk_switch_var = tk.StringVar(value=self.cfg.get("hotkey_switch", ""))
        ttk.Entry(hk_row2, textvariable=self.hk_switch_var, width=24).pack(side=tk.LEFT, padx=5)

        ttk.Label(hk_frame, text="提示：例如 ctrl+shift+s / ctrl+shift+f，点击保存设置后生效。",
                  foreground="#888888").pack(anchor=tk.W)

        # 6. 底部主控制按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="🎲 换一张在线壁纸", command=self.fetch_and_set_wallpaper).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="💾 保存设置", command=self.apply_settings).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="🗕 最小化到托盘", command=self.hide_to_tray).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="❌ 退出并还原", command=self.quit_and_restore).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

    # ---------------- 收藏 / 星标逻辑 ----------------
    def refresh_favorites_list(self):
        """刷新收藏下拉框"""
        files = wallpaper_service.list_favorites()
        self.fav_combo['values'] = files
        if files:
            if not self.fav_combo_var.get() or self.fav_combo_var.get() not in files:
                self.fav_combo.current(0)
        else:
            self.fav_combo_var.set("暂无收藏壁纸")
        self.update_favorite_preview()

    def update_favorite_preview(self):
        """刷新星标壁纸预览图"""
        self.preview_canvas.delete("all")
        self._preview_img = None

        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            self.preview_canvas.create_text(200, 90, text="暂无预览", fill="#888888")
            return

        fav_path = os.path.join(config.FAVORITES_DIR, filename)
        if not os.path.exists(fav_path):
            self.preview_canvas.create_text(200, 90, text="文件不存在", fill="#888888")
            return

        try:
            img = Image.open(fav_path)
            img.thumbnail((398, 178))
            self._preview_img = ImageTk.PhotoImage(img)
            self.preview_canvas.create_image((400 - img.width) // 2, (180 - img.height) // 2,
                                             anchor=tk.NW, image=self._preview_img)
        except Exception:
            self.preview_canvas.create_text(200, 90, text="无法预览", fill="#888888")

    def favorite_current_wallpaper(self):
        """星标收藏当前壁纸（收藏时可为壁纸重命名）"""
        if not self.current_applied_wallpaper or not os.path.exists(self.current_applied_wallpaper):
            messagebox.showwarning("提示", "当前没有正在显示的有效壁纸！")
            return

        # 如果当前壁纸已经在收藏夹中
        if os.path.dirname(os.path.abspath(self.current_applied_wallpaper)) == os.path.abspath(config.FAVORITES_DIR):
            messagebox.showinfo("提示", "这张壁纸已经在你的星标收藏夹中了！")
            return

        # 收藏时弹出命名对话框，为壁纸重命名
        default_name = f"fav_{time.strftime('%Y%m%d_%H%M%S')}"
        new_name = simpledialog.askstring(
            "星标命名",
            "为这张星标壁纸命名（将作为收藏夹中的文件名）:",
            initialvalue=default_name,
            parent=self.root
        )
        if new_name is None:  # 用户取消收藏
            return
        new_name = new_name.strip() or default_name
        # 清洗非法文件名字符
        new_name = re.sub(r'[\\/:*?"<>|]', "_", new_name)

        # 拷贝到收藏夹，以用户命名保存
        fav_filename, fav_path = wallpaper_service.save_favorite(self.current_applied_wallpaper, new_name)

        # 切换当前壁纸引用为收藏目录下的文件，并转为星标锁定模式
        self.current_applied_wallpaper = fav_path
        wallpaper_service.set_wallpaper_windows(fav_path)
        self.mode = "favorite"

        self.refresh_favorites_list()
        self.fav_combo_var.set(fav_filename)
        self.update_favorite_preview()
        self.reset_refresh_timer()
        self.status_var.set(f"状态: ⭐ 已收藏并锁定壁纸 [{fav_filename}]（定时轮播已暂停）")
        messagebox.showinfo("收藏成功", f"壁纸已加入星标收藏！\n定时轮播已暂停，将持续锁定本壁纸。")

    def apply_selected_favorite(self):
        """使用选中的星标壁纸（进入星标模式）"""
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            messagebox.showwarning("提示", "请先选择一张有效的星标壁纸！")
            return

        fav_path = os.path.join(config.FAVORITES_DIR, filename)
        if os.path.exists(fav_path):
            wallpaper_service.set_wallpaper_windows(fav_path)
            self.current_applied_wallpaper = fav_path
            self.mode = "favorite"  # 切换到星标模式：定时器不再拉取在线壁纸
            self.reset_refresh_timer()
            if self.cfg.get("favorite_carousel", False):
                self.status_var.set(f"状态: ⭐ 使用星标壁纸 [{filename}]（开启星标轮播）")
            else:
                self.status_var.set(f"状态: ⭐ 使用星标壁纸 [{filename}]（定时轮播已暂停）")
            self.update_favorite_preview()

    def cycle_favorite(self):
        """星标轮播：切换到收藏夹中的下一张壁纸"""
        files = wallpaper_service.list_favorites()
        if not files:
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
        """取消星标并从本地物理删除文件"""
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            return

        if not messagebox.askyesno("确认删除", f"确定要取消星标并从本地永久删除图片【{filename}】吗？"):
            return

        fav_path = os.path.join(config.FAVORITES_DIR, filename)
        try:
            # 如果当前桌面正好是这张被删除的壁纸，自动切换回在线壁纸
            is_current = (os.path.abspath(self.current_applied_wallpaper) == os.path.abspath(fav_path))
            wallpaper_service.delete_favorite(filename)

            self.refresh_favorites_list()
            self.update_favorite_preview()
            messagebox.showinfo("提示", "已取消星标并删除本地文件！")

            if is_current:
                self.fetch_and_set_wallpaper()
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    # ---------------- 在线拉取与壁纸设置 ----------------
    def reset_refresh_timer(self):
        """重置轮播计时器（以当前时间为基准重新计时）"""
        self._consecutive_failures = 0
        interval = self.cfg.get("interval_minutes", 30)
        self._next_refresh_time = time.time() + interval * 60

    def _schedule_failure_backoff(self):
        """下载失败后按指数退避安排下次自动重试，避免频繁请求服务器"""
        self._consecutive_failures += 1
        cap = max(self.cfg.get("interval_minutes", 30) * 60, 60)
        wait = min(30 * (2 ** (self._consecutive_failures - 1)), cap)
        self._next_refresh_time = time.time() + wait

    def fetch_and_set_wallpaper(self):
        """拉取在线壁纸（成功后会重置轮播计时，失败则退避重试）"""
        if self.is_downloading:
            return

        def _task():
            self.is_downloading = True
            self.status_var.set("状态: 正在下载新壁纸...")
            try:
                img_path = wallpaper_service.download_wallpaper(self.cfg['site'], self.cfg['size'])
                wallpaper_service.set_wallpaper_windows(img_path)
                self.current_applied_wallpaper = img_path
                self.mode = "online"  # 恢复在线轮播状态
                self.status_var.set(f"状态: 在线壁纸更换成功 ({time.strftime('%H:%M:%S')})")
                # 仅下载成功才重新计时（含手动点击"换一张"触发的情况）
                self.reset_refresh_timer()
            except Exception as e:
                self.status_var.set(f"状态: 更换失败 ({str(e)})")
                # 下载失败：不重置为完整间隔，改为指数退避等待，降低服务器压力
                self._schedule_failure_backoff()
            finally:
                self.is_downloading = False

        threading.Thread(target=_task, daemon=True).start()

    def timer_loop(self):
        """定时器循环检测（基于绝对时间戳判断）"""
        interval = self.cfg.get("interval_minutes", 30)
        # 关键点：online 模式按绝对时间戳触发在线下载；favorite 模式仅在开启星标轮播时
        # 自动切换收藏夹壁纸。判断依据均为 _next_refresh_time。
        if interval > 0 and time.time() >= self._next_refresh_time:
            if self.mode == "online":
                self.fetch_and_set_wallpaper()
            elif self.mode == "favorite" and self.cfg.get("favorite_carousel", False):
                self.cycle_favorite()

        self.root.after(30 * 1000, self.timer_loop)

    # ---------------- 托盘与退出 ----------------
    def register_hotkeys(self):
        """注册全局快捷键（默认不设置，为空则跳过；回调切换到主线程执行）"""
        try:
            if keyboard is not None:
                keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        if keyboard is None:
            return

        hotkey_fav = self.cfg.get("hotkey_favorite", "").strip()
        hotkey_switch = self.cfg.get("hotkey_switch", "").strip()

        if hotkey_fav:
            try:
                keyboard.add_hotkey(hotkey_fav, lambda: self.root.after(0, self.favorite_current_wallpaper))
            except Exception as e:
                print(f"收藏快捷键注册失败 [{hotkey_fav}]: {e}")
                self.status_var.set(f"状态: 收藏快捷键注册失败 [{hotkey_fav}]")

        if hotkey_switch:
            try:
                keyboard.add_hotkey(hotkey_switch, lambda: self.root.after(0, self.fetch_and_set_wallpaper))
            except Exception as e:
                print(f"切换壁纸快捷键注册失败 [{hotkey_switch}]: {e}")
                self.status_var.set(f"状态: 切换快捷键注册失败 [{hotkey_switch}]")

    def init_tray_icon(self):
        menu = (
            item('打开设置界面', lambda: self.root.after(0, self._restore_ui), default=True),
            item('🎲 换一张在线壁纸', lambda: self.fetch_and_set_wallpaper()),
            item('⭐ 收藏当前壁纸', lambda: self.root.after(0, self.favorite_current_wallpaper)),
            item('❌ 退出并还原壁纸', lambda: self.root.after(0, self.quit_and_restore))
        )
        self.tray_icon = pystray.Icon("TouhouWallpaper", create_tray_icon_image(), "TH wallpaper", menu)
        self.tray_icon.run_detached()

    def _restore_ui(self):
        self.refresh_favorites_list()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        self.apply_settings(show_msg=False)
        self.root.withdraw()

    def apply_settings(self, show_msg=True):
        self.cfg["refresh_on_startup"] = self.var_startup.get()
        self.cfg["auto_start"] = self.var_autostart.get()
        self.cfg["interval_minutes"] = self.interval_map[self.interval_var.get()]
        self.cfg["site"] = self.site_var.get()
        self.cfg["size"] = self.size_var.get()
        for k, v in self.style_map.items():
            if v == self.style_var.get():
                self.cfg["wallpaper_style"] = k
                break
        else:
            self.cfg["wallpaper_style"] = "fill"
        self.cfg["favorite_carousel"] = self.var_fav_carousel.get()
        self.cfg["hotkey_favorite"] = self.hk_fav_var.get().strip()
        self.cfg["hotkey_switch"] = self.hk_switch_var.get().strip()
        config.save_config(self.cfg)
        config.set_auto_start_registry(self.cfg["auto_start"])
        self.register_hotkeys()
        self.apply_wallpaper_style(self.cfg["wallpaper_style"])
        if show_msg:
            messagebox.showinfo("成功", "设置已保存并生效！")

    def apply_wallpaper_style(self, style_key=None):
        """将壁纸显示方式写入注册表，并刷新当前壁纸使其立即生效"""
        style_key = style_key or self.cfg.get("wallpaper_style", "fill")
        if wallpaper_service.set_wallpaper_style(style_key):
            cur = self.current_applied_wallpaper
            if cur and os.path.exists(cur):
                wallpaper_service.set_wallpaper_windows(cur)

    def restore_original_wallpaper(self):
        orig_wp = self.cfg.get("original_wallpaper", "")
        if orig_wp and os.path.exists(orig_wp):
            wallpaper_service.set_wallpaper_windows(orig_wp)

    def quit_and_restore(self):
        try:
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
        sys.exit(0)
