import os
import sys
import json
import winreg

# 基础目录与路径
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TouhouWallpaper")
FAVORITES_DIR = os.path.join(APP_DIR, "Favorites")
TEMP_WALLPAPER_PATH = os.path.join(APP_DIR, "wallpaper_temp.jpg")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "auto_start": True,
    "refresh_on_startup": True,
    "interval_minutes": 30,
    "site": "all",
    "size": "pc",
    "original_wallpaper": "",
    "favorite_carousel": False,
    "hotkey_favorite": "",
    "hotkey_switch": "",
    "wallpaper_style": "fill"
}


def ensure_dirs():
    """确保数据目录存在"""
    os.makedirs(FAVORITES_DIR, exist_ok=True)


def load_config():
    """加载配置，缺失的键使用默认值"""
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    """保存配置到磁盘"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


def set_auto_start_registry(enable=True):
    """设置/取消开机自启（HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run）"""
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


# 启动即确保数据目录存在（保持原有行为）
ensure_dirs()
