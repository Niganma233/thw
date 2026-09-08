import json
import os
import sys
import tempfile
import winreg

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TouhouWallpaper")
FAVORITES_DIR = os.path.join(APP_DIR, "Favorites")
CACHE_DIR = os.path.join(APP_DIR, "Cache")
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
    "wallpaper_style": "fill",
    "source_id": "all",
    "custom_sources": [],
    "sources": [],
}


def ensure_dirs():
    os.makedirs(FAVORITES_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    if not isinstance(cfg.get("custom_sources"), list):
        cfg["custom_sources"] = []
    if not isinstance(cfg.get("sources"), list):
        cfg["sources"] = []
    return cfg


def save_config(cfg):
    ensure_dirs()
    fd, temp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=APP_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CONFIG_FILE)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def set_auto_start_registry(enable=True):
    key = None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        name = "TouhouWallpaperAutoChanger"
        if enable:
            python_exe = sys.executable
            pythonw = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = python_exe
            script_path = os.path.abspath(sys.argv[0])
            cmd = f'"{script_path}" --silent' if script_path.lower().endswith(".exe") else f'"{pythonw}" "{script_path}" --silent'
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
    except OSError as exc:
        print(f"设置开机自启失败: {exc}")
    finally:
        if key is not None:
            winreg.CloseKey(key)


ensure_dirs()
