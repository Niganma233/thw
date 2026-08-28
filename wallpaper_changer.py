import os
import sys
import json
import urllib.request
import ctypes
import winreg
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import atexit

# 配置文件与壁纸缓存路径
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TouhouWallpaper")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
WALLPAPER_PATH = os.path.join(APP_DIR, "wallpaper.jpg")

DEFAULT_CONFIG = {
    "auto_start": True,             # 开机自启
    "refresh_on_startup": True,     # 启动时刷新一次
    "interval_minutes": 30,         # 定时间隔（分钟，0为不自动定时刷新）
    "site": "all",                  # konachan, yandere, all
    "size": "pc",                   # pc (横屏), mobile (竖屏)
    "original_wallpaper": ""        # 记录用户的原始壁纸路径
}

def get_current_windows_wallpaper():
    """读取 Windows 当前正在使用的壁纸文件路径"""
    buffer = ctypes.create_unicode_buffer(512)
    # 0x0073 即 SPI_GETDESKWALLPAPER
    ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buffer), buffer, 0)
    return buffer.value

def set_wallpaper_windows(img_path):
    """调用 Windows API 设置桌面壁纸"""
    if not img_path or not os.path.exists(img_path):
        return
    abs_path = os.path.abspath(img_path)
    # 20 = SPI_SETDESKWALLPAPER, 3 = SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)

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
    """写入/删除注册表实现开机自启"""
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
            if script_path.endswith(".exe"):
                cmd = f'"{script_path}" --silent'
            else:
                cmd = f'"{pythonw}" "{script_path}" --silent'
                
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"自启注册表修改失败: {e}")


class WallpaperApp:
    def __init__(self, root, silent=False):
        self.root = root
        self.root.title("TH wallpaper")
        self.root.geometry("450x390")
        self.root.resizable(False, False)
        
        self.cfg = load_config()
        self.is_downloading = False
        
        # 1. 备份原壁纸：
        cur_wp = get_current_windows_wallpaper()
        if cur_wp and not cur_wp.lower().endswith("wallpaper.jpg"):
            self.cfg["original_wallpaper"] = cur_wp
            save_config(self.cfg)
        
        # 注册程序退出钩子（双重保障）
        atexit.register(self.restore_original_wallpaper)
        
        # 拦截右上角 [X] 关闭按钮
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)
        
        self.init_ui()
        
        # 启动时根据配置刷新
        if self.cfg.get("refresh_on_startup", True):
            self.fetch_and_set_wallpaper()
            
        self.timer_loop()
        
        if silent:
            self.root.withdraw()

    def init_ui(self):
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="状态: 运行中")
        ttk.Label(frame, textvariable=self.status_var, font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=5)

        # 刷新条件设置
        cond_frame = ttk.LabelFrame(frame, text="刷新条件设置", padding=10)
        cond_frame.pack(fill=tk.X, pady=8)

        self.var_startup = tk.BooleanVar(value=self.cfg["refresh_on_startup"])
        ttk.Checkbutton(cond_frame, text="开机 / 启动时立即刷新一次", variable=self.var_startup).pack(anchor=tk.W, pady=2)

        self.var_autostart = tk.BooleanVar(value=self.cfg["auto_start"])
        ttk.Checkbutton(cond_frame, text="开机时自动启动本程序", variable=self.var_autostart).pack(anchor=tk.W, pady=2)

        interval_box = ttk.Frame(cond_frame)
        interval_box.pack(fill=tk.X, pady=4)
        ttk.Label(interval_box, text="定时刷新间隔:").pack(side=tk.LEFT)
        
        self.interval_var = tk.StringVar()
        intervals = {
            "不自动定时": 0,
            "每 5 分钟": 5,
            "每 15 分钟": 15,
            "每 30 分钟": 30,
            "每 1 小时": 60,
            "每 2 小时": 120,
            "每 4 小时": 240
        }
        self.interval_map = intervals
        cur_text = "每 30 分钟"
        for k, v in intervals.items():
            if v == self.cfg["interval_minutes"]:
                cur_text = k
                break
        self.interval_var.set(cur_text)
        
        self.combo_interval = ttk.Combobox(interval_box, textvariable=self.interval_var, values=list(intervals.keys()), state="readonly", width=12)
        self.combo_interval.pack(side=tk.LEFT, padx=10)

        # 图片偏好
        api_frame = ttk.LabelFrame(frame, text="图片偏好设置", padding=10)
        api_frame.pack(fill=tk.X, pady=5)

        ttk.Label(api_frame, text="图源选择:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.site_var = tk.StringVar(value=self.cfg["site"])
        site_combo = ttk.Combobox(api_frame, textvariable=self.site_var, values=["all", "konachan", "yandere"], state="readonly", width=12)
        site_combo.grid(row=0, column=1, padx=10, sticky=tk.W)

        ttk.Label(api_frame, text="尺寸类型:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.size_var = tk.StringVar(value=self.cfg["size"])
        size_combo = ttk.Combobox(api_frame, textvariable=self.size_var, values=["pc", "mobile"], state="readonly", width=12)
        size_combo.grid(row=1, column=1, padx=10, sticky=tk.W)

        # 底部控制按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=12)

        ttk.Button(btn_frame, text="立即换一张", command=self.fetch_and_set_wallpaper).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="隐藏到后台", command=self.hide_to_background).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_frame, text="退出并还原壁纸", command=self.quit_and_restore).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

    def apply_settings(self):
        """保存配置"""
        self.cfg["refresh_on_startup"] = self.var_startup.get()
        self.cfg["auto_start"] = self.var_autostart.get()
        self.cfg["interval_minutes"] = self.interval_map[self.interval_var.get()]
        self.cfg["site"] = self.site_var.get()
        self.cfg["size"] = self.size_var.get()
        save_config(self.cfg)
        set_auto_start_registry(self.cfg["auto_start"])

    def hide_to_background(self):
        """隐藏窗口（保持轮播）"""
        self.apply_settings()
        self.root.withdraw()

    def restore_original_wallpaper(self):
        """还原为原壁纸"""
        orig_wp = self.cfg.get("original_wallpaper", "")
        if orig_wp and os.path.exists(orig_wp):
            set_wallpaper_windows(orig_wp)

    def quit_and_restore(self):
        """彻底退出程序并恢复原壁纸"""
        self.restore_original_wallpaper()
        self.root.destroy()
        sys.exit(0)

    def on_close_window(self):
        """点击右上角 X 时的行为选择"""
        # 弹窗询问是退出还是最小化后台
        ans = messagebox.askyesnocancel("关闭确认", "是否完全退出软件并恢复原来的壁纸？\n\n【是】：彻底退出并还原原壁纸\n【否】：仅隐藏到后台继续轮播壁纸\n【取消】：不进行任何操作")
        if ans is True:
            self.quit_and_restore()
        elif ans is False:
            self.hide_to_background()

    def fetch_and_set_wallpaper(self):
        """异步拉取图片并设为壁纸"""
        if self.is_downloading:
            return
        
        def _task():
            self.is_downloading = True
            self.status_var.set("状态: 正在下载壁纸...")
            try:
                api_url = f"https://img.paulzzh.com/touhou/random?size={self.cfg['size']}&site={self.cfg['site']}"
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                
                with urllib.request.urlopen(req, timeout=15) as response:
                    img_data = response.read()
                
                with open(WALLPAPER_PATH, "wb") as f:
                    f.write(img_data)
                
                set_wallpaper_windows(WALLPAPER_PATH)
                self.status_var.set(f"状态: 壁纸更换成功 ({time.strftime('%H:%M:%S')})")
            except Exception as e:
                self.status_var.set(f"状态: 更换失败 ({str(e)})")
            finally:
                self.is_downloading = False

        threading.Thread(target=_task, daemon=True).start()

    def timer_loop(self):
        interval = self.cfg.get("interval_minutes", 30)
        if interval > 0:
            now = time.time()
            if not hasattr(self, "_last_refresh_time"):
                self._last_refresh_time = now
            elif now - self._last_refresh_time >= interval * 60:
                self.fetch_and_set_wallpaper()
                self._last_refresh_time = now

        self.root.after(30 * 1000, self.timer_loop)


if __name__ == "__main__":
    is_silent = "--silent" in sys.argv
    root = tk.Tk()
    app = WallpaperApp(root, silent=is_silent)
    root.mainloop()