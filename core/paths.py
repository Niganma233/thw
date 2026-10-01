"""程序数据目录的位置。

只回答"路径在哪"，不做任何文件 I/O。原来的 config.py 把路径常量、配置读写、
开机自启注册表都塞在一起，而且 ``ensure_dirs()`` 写在**模块顶层**——只要
``import config`` 就会去创建目录。现在创建目录是显式的，由入口调用。
"""
import os

APP_NAME = "TouhouWallpaper"

# 全部数据都放在 %APPDATA%\TouhouWallpaper 下
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
FAVORITES_DIR = os.path.join(APP_DIR, "Favorites")
CACHE_DIR = os.path.join(APP_DIR, "Cache")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")


def ensure_dirs():
    """创建需要的子目录（幂等）。

    目录建不出来时不抛异常：界面启动后会通过 ``_warn_if_data_dir_readonly``
    明确提示"数据目录不可写"，比在这里崩掉友好得多。
    """
    for path in (FAVORITES_DIR, CACHE_DIR):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
