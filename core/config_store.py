"""配置文件的读写。

只碰 JSON 文件，不碰注册表（那在 services/autostart.py）也不碰界面。
"""
import copy
import json
import os
import tempfile

from core import paths

DEFAULT_CONFIG = {
    "auto_start": True,
    "refresh_on_startup": True,
    "interval_minutes": 30,
    "site": "all",
    "size": "pc",
    "original_wallpaper": "",
    "favorite_carousel": False,
    "favorite_behavior": "pause",
    "hotkey_favorite": "",
    "hotkey_switch": "",
    "wallpaper_style": "fill",
    "source_id": "all",
    "custom_sources": [],
    "sources": [],
}


def load_config():
    """读取配置；文件缺失/损坏时回退到默认值。"""
    # 必须深拷贝：浅拷贝时 cfg["sources"] 与 DEFAULT_CONFIG["sources"] 是同一个
    # 列表对象，没有配置文件的情况下 SourceManager 往里 append 就会污染默认值，
    # 之后每次 load_config 都会带着上一次运行残留的图源。
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.isfile(paths.CONFIG_FILE):
        try:
            with open(paths.CONFIG_FILE, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
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
    """原子地写配置：先写临时文件再 os.replace，避免中途失败留下半个 JSON。"""
    paths.ensure_dirs()
    fd, temp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=paths.APP_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, indent=4, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, paths.CONFIG_FILE)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
