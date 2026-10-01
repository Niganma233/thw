"""测试公共设施：隔离数据目录、构造不带副作用的 WallpaperApp。

隔离是必须的，原因有两条：

1. ``config`` 在**导入时**就计算并创建 ``%APPDATA%\\TouhouWallpaper``；
2. ``services.cache`` / ``services.favorites`` 用
   ``from config import CACHE_DIR / FAVORITES_DIR`` 把路径**按值**绑定进了
   自己的模块命名空间。

所以只改 ``config`` 上的常量不够，必须同时改这两个模块里那份副本，
否则测试会动到用户真实的收藏与缓存。
"""
from __future__ import annotations

import contextlib
import copy
import email.message
import io
import shutil
import sys
import unittest
import unittest.mock as mock
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 隔离用的临时根目录。刻意**不用** tempfile.mkdtemp：在受限的 Windows 沙箱里，
# mkdtemp 建出来的目录 ACL 不允许在其下继续创建子目录（WinError 5），
# 而普通的 Path.mkdir(parents=True) 没有这个问题。
TEST_ROOT = PROJECT_ROOT / ".test-tmp"

import config  # noqa: E402
import services.cache  # noqa: E402
import services.favorites  # noqa: E402

# 需要在测试期间被重定向的模块级路径常量：(模块, 属性名)
_PATH_TARGETS = (
    (config, "APP_DIR"),
    (config, "FAVORITES_DIR"),
    (config, "CACHE_DIR"),
    (config, "CONFIG_FILE"),
    (services.cache, "CACHE_DIR"),
    (services.favorites, "FAVORITES_DIR"),
)


class IsolatedDataDir:
    """把程序数据目录重定向到临时目录的上下文管理器。"""

    def __init__(self):
        self._tmp = None
        self._patchers = []

    def __enter__(self) -> Path:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self._tmp = TEST_ROOT / f"run_{uuid.uuid4().hex[:12]}"
        base = self._tmp / "TouhouWallpaper"
        favorites = base / "Favorites"
        cache = base / "Cache"
        for path in (base, favorites, cache):
            path.mkdir(parents=True, exist_ok=True)

        values = {
            "APP_DIR": str(base),
            "FAVORITES_DIR": str(favorites),
            "CACHE_DIR": str(cache),
            "CONFIG_FILE": str(base / "config.json"),
        }
        for module, attr in _PATH_TARGETS:
            patcher = mock.patch.object(module, attr, values[attr])
            patcher.start()
            self._patchers.append(patcher)
        return base

    def __exit__(self, *exc_info):
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._patchers.clear()
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None
        return False


class FakeVar:
    """替代 ``tkinter.StringVar``，记录每次 set 的值。"""

    def __init__(self, value=""):
        self._value = value
        self.history = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        self.history.append(value)

    @property
    def last(self):
        return self.history[-1] if self.history else None


class FakeWidget:
    """替代 ``CTkButton`` 等控件，只记录 configure 调用。"""

    def __init__(self):
        self.calls = []

    def configure(self, **kwargs):
        self.calls.append(kwargs)

    def cget(self, key):
        return None


def default_cfg(**overrides):
    """返回一份可安全修改的默认配置副本。"""
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    cfg.update(overrides)
    return cfg


def make_bare_app(cfg=None, mode="online"):
    """构造一个跳过 ``__init__`` 的 WallpaperApp，用于测试纯逻辑方法。

    ``object.__new__`` 拿到的是真正的 WallpaperApp 实例，因此类方法照常绑定；
    只是绕开了下载线程、托盘图标、全局热键与 Tk 窗口这些副作用。
    """
    import gui

    app = object.__new__(gui.WallpaperApp)
    app.cfg = default_cfg() if cfg is None else cfg
    app.mode = mode
    app.is_downloading = False
    app._consecutive_failures = 0
    app._next_refresh_time = 0.0
    app._closing = False
    app.current_applied_wallpaper = ""
    app.countdown_var = FakeVar()
    app.status_var = FakeVar()
    app.next_btn = FakeWidget()
    app.status_log = []
    app.set_status = lambda text, kind="ready": app.status_log.append((text, kind))
    return app


@contextlib.contextmanager
def tk_root():
    """创建并隐藏一个真实的 CTk 根窗口。

    Tk 初始化失败时（无显示环境）抛 SkipTest，让整套测试优雅跳过而不是失败。
    """
    try:
        import customtkinter as ctk
        root = ctk.CTk()
    except Exception as exc:  # pragma: no cover - 只在无显示环境触发
        raise unittest.SkipTest(f"无法创建 Tk 窗口：{exc}")
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def collect_widgets(widget, widget_type):
    """深度收集控件树中指定类型的所有控件。"""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, widget_type):
            found.append(child)
        found.extend(collect_widgets(child, widget_type))
    return found


# ---------- 图片与 HTTP 测试替身 ----------

def png_bytes(size=(8, 8), color="red"):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(size=(8, 8)):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="JPEG")
    return buffer.getvalue()


def webp_bytes(size=(8, 8)):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, "green").save(buffer, format="WEBP")
    return buffer.getvalue()


class FakeResponse:
    """模拟 urlopen 返回的上下文管理器（带 Content-Type 头）。"""

    def __init__(self, data, content_type="image/png"):
        self._data = data
        self.headers = email.message.Message()
        self.headers["Content-Type"] = content_type

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False
