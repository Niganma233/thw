import os
import sys
import json
import urllib.request
import shutil
import ctypes
import winreg
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import atexit

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

# 基础目录与路径
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TouhouWallpaper")
FAVORITES_DIR = os.path.join(APP_DIR, "Favorites")
os.makedirs(FAVORITES_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(APP_DIR, "config.json")
TEMP_WALLPAPER_PATH = os.path.join(APP_DIR, "wallpaper_temp.jpg")

DEFAULT_CONFIG = {
    "auto_start": True,
    "refresh_on_startup": True,
    "interval_minutes": 30,
    "site": "all",
    "size": "pc",
    "original_wallpaper": ""
}

def get_current_windows_wallpaper():
    """获取当前系统壁纸路径"""
    buffer = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buffer), buffer, 0)
    return buffer.value

def set_wallpaper_windows(img_path):
    """设置 Windows 壁纸"""
    if not img_path or not os.path.exists(img_path):
        return False
    abs_path = os.path.abspath(img_path)
    ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)
    return True

def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def set_auto_start_registry(enable=True):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "TouhouWallpaperAutoChanger"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            python_exe = sys.executable
            pythonw = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = python_exe
            
            script_path = os.path.abspath(sys.argv[0])
            cmd = f'"{script_path}" --silent' if script_path.endswith(".exe") else f'"{pythonw}" "{script_path}" --silent'
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"自启注册表修改失败: {e}")

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
        self.root.geometry("480x520")
        self.root.resizable(False, False)
        
        self.cfg = load_config()
        self.is_downloading = False
        
        # 运行模式: "online" (在线轮播中) 或 "favorite" (锁定星标壁纸，停止定时刷新)
        self.mode = "online"
        self.current_applied_wallpaper = ""

        # 备份系统最初的原壁纸
        cur_wp = get_current_windows_wallpaper()
        if cur_wp and not cur_wp.lower().startswith(APP_DIR.lower()):
            self.cfg["original_wallpaper"] = cur_wp
            save_config(self.cfg)
        
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        
        self.init_ui()
        self.refresh_favorites_list()
        self.init_tray_icon()
        
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

        # 4. ★ 星标/收藏管理面板 ★
        fav_frame = ttk.LabelFrame(frame, text="⭐ 星标收藏夹管理 (使用星标壁纸时定时刷新自动暂停)", padding=8)
        fav_frame.pack(fill=tk.X, pady=6)

        # 收藏操作行
        fav_op_box = ttk.Frame(fav_frame)
        fav_op_box.pack(fill=tk.X, pady=2)
        ttk.Button(fav_op_box, text="⭐ 收藏当前壁纸", command=self.favorite_current_wallpaper).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(fav_op_box, text="📂 打开收藏文件夹", command=lambda: os.startfile(FAVORITES_DIR)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 收藏列表选择行
        fav_sel_box = ttk.Frame(fav_frame)
        fav_sel_box.pack(fill=tk.X, pady=4)
        ttk.Label(fav_sel_box, text="已收藏壁纸:").pack(side=tk.LEFT)
        self.fav_combo_var = tk.StringVar()
        self.fav_combo = ttk.Combobox(fav_sel_box, textvariable=self.fav_combo_var, state="readonly", width=22)
        self.fav_combo.pack(side=tk.LEFT, padx=5)

        fav_action_box = ttk.Frame(fav_frame)
        fav_action_box.pack(fill=tk.X, pady=2)
        ttk.Button(fav_action_box, text="应用选中的星标壁纸", command=self.apply_selected_favorite).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(fav_action_box, text="🗑️ 取消星标 (本地删除)", command=self.delete_selected_favorite).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 5. 底部主控制按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="🎲 换一张在线壁纸", command=self.fetch_and_set_wallpaper).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="💾 保存设置", command=self.apply_settings).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="🗕 最小化到托盘", command=self.hide_to_tray).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="❌ 退出并还原", command=self.quit_and_restore).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

    # ---------------- 收藏 / 星标逻辑 ----------------
    def refresh_favorites_list(self):
        """刷新收藏下拉框"""
        files = [f for f in os.listdir(FAVORITES_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        self.fav_combo['values'] = files
        if files:
            if not self.fav_combo_var.get() or self.fav_combo_var.get() not in files:
                self.fav_combo.current(0)
        else:
            self.fav_combo_var.set("暂无收藏壁纸")

    def favorite_current_wallpaper(self):
        """星标收藏当前壁纸"""
        if not self.current_applied_wallpaper or not os.path.exists(self.current_applied_wallpaper):
            messagebox.showwarning("提示", "当前没有正在显示的有效壁纸！")
            return
        
        # 如果当前壁纸已经在收藏夹中
        if os.path.dirname(os.path.abspath(self.current_applied_wallpaper)) == os.path.abspath(FAVORITES_DIR):
            messagebox.showinfo("提示", "这张壁纸已经在你的星标收藏夹中了！")
            return

        # 拷贝到收藏夹，以时间戳命名
        fav_filename = f"fav_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        fav_path = os.path.join(FAVORITES_DIR, fav_filename)
        shutil.copy2(self.current_applied_wallpaper, fav_path)
        
        # 切换当前壁纸引用为收藏目录下的文件，并转为星标锁定模式
        self.current_applied_wallpaper = fav_path
        set_wallpaper_windows(fav_path)
        self.mode = "favorite"
        
        self.refresh_favorites_list()
        self.fav_combo_var.set(fav_filename)
        self.status_var.set(f"状态: ⭐ 已收藏并锁定壁纸（定时轮播已暂停）")
        messagebox.showinfo("收藏成功", f"壁纸已加入星标收藏！\n定时轮播已暂停，将持续锁定本壁纸。")

    def apply_selected_favorite(self):
        """使用选中的星标壁纸（锁定并不被定时更换）"""
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            messagebox.showwarning("提示", "请先选择一张有效的星标壁纸！")
            return
        
        fav_path = os.path.join(FAVORITES_DIR, filename)
        if os.path.exists(fav_path):
            set_wallpaper_windows(fav_path)
            self.current_applied_wallpaper = fav_path
            self.mode = "favorite"  # 切换到星标模式：定时器将不再自动切图
            self.status_var.set(f"状态: ⭐ 使用星标壁纸 [{filename}]（定时轮播已暂停）")

    def delete_selected_favorite(self):
        """取消星标并从本地物理删除文件"""
        filename = self.fav_combo_var.get()
        if not filename or filename == "暂无收藏壁纸":
            return
        
        if not messagebox.askyesno("确认删除", f"确定要取消星标并从本地永久删除图片【{filename}】吗？"):
            return
        
        fav_path = os.path.join(FAVORITES_DIR, filename)
        try:
            # 如果当前桌面正好是这张被删除的壁纸，自动切换回在线壁纸
            is_current = (os.path.abspath(self.current_applied_wallpaper) == os.path.abspath(fav_path))
            if os.path.exists(fav_path):
                os.remove(fav_path)
            
            self.refresh_favorites_list()
            messagebox.showinfo("提示", "已取消星标并删除本地文件！")
            
            if is_current:
                self.fetch_and_set_wallpaper()
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    # ---------------- 在线拉取与壁纸设置 ----------------
    def fetch_and_set_wallpaper(self):
        """拉取在线壁纸（会自动重置为 online 模式并激活轮播）"""
        if self.is_downloading:
            return
        
        def _task():
            self.is_downloading = True
            self.status_var.set("状态: 正在下载新壁纸...")
            try:
                api_url = f"https://img.paulzzh.com/touhou/random?size={self.cfg['size']}&site={self.cfg['site']}"
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    img_data = response.read()
                
                with open(TEMP_WALLPAPER_PATH, "wb") as f:
                    f.write(img_data)
                
                set_wallpaper_windows(TEMP_WALLPAPER_PATH)
                self.current_applied_wallpaper = TEMP_WALLPAPER_PATH
                self.mode = "online" # 恢复在线轮播状态
                self.status_var.set(f"状态: 在线壁纸更换成功 ({time.strftime('%H:%M:%S')})")
            except Exception as e:
                self.status_var.set(f"状态: 更换失败 ({str(e)})")
            finally:
                self.is_downloading = False

        threading.Thread(target=_task, daemon=True).start()

    def timer_loop(self):
        """定时器循环检测"""
        interval = self.cfg.get("interval_minutes", 30)
        # 关键点：只有在 online 模式下才执行定时切换；favorite 模式下时间对其无效！
        if self.mode == "online" and interval > 0:
            now = time.time()
            if not hasattr(self, "_last_refresh_time"):
                self._last_refresh_time = now
            elif now - self._last_refresh_time >= interval * 60:
                self.fetch_and_set_wallpaper()
                self._last_refresh_time = now

        self.root.after(30 * 1000, self.timer_loop)

    # ---------------- 托盘与退出 ----------------
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
        save_config(self.cfg)
        set_auto_start_registry(self.cfg["auto_start"])
        if show_msg:
            messagebox.showinfo("成功", "设置已保存并生效！")

    def restore_original_wallpaper(self):
        orig_wp = self.cfg.get("original_wallpaper", "")
        if orig_wp and os.path.exists(orig_wp):
            set_wallpaper_windows(orig_wp)

    def quit_and_restore(self):
        try:
            self.tray_icon.stop()
        except Exception:
            pass
        self.restore_original_wallpaper()
        self.root.destroy()
        sys.exit(0)


if __name__ == "__main__":
    is_silent = "--silent" in sys.argv
    root = tk.Tk()
    app = WallpaperApp(root, silent=is_silent)
    root.mainloop()