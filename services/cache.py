"""下载缓存的落盘、统计与清理。

缓存目录目前是导入时从 config 取到的模块级常量（``from config import CACHE_DIR``，
按值绑定）。这意味着重定向路径必须同时改本模块的 CACHE_DIR —— 测试就是这么做的
（见 tests/helpers.py），Phase 7 会把路径改成可注入的 core/paths.py，届时这个坑消失。
"""
import io
import os
import time
import uuid

from PIL import Image

from config import CACHE_DIR
from core.constants import IMAGE_EXTENSIONS
from services.images import detect_extension

# 缓存里最多保留多少张图片（当前正在使用的那张始终受保护）
MAX_CACHED_FILES = 16


def cleanup_cache(keep_path, max_files=MAX_CACHED_FILES):
    """按修改时间保留最新的 ``max_files`` 张，其余删掉；``keep_path`` 永不删除。"""
    try:
        files = [os.path.join(CACHE_DIR, name) for name in os.listdir(CACHE_DIR) if name.lower().endswith(IMAGE_EXTENSIONS)]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        protected = os.path.abspath(keep_path) if keep_path else ""
        for path in files[max_files:]:
            if os.path.abspath(path) == protected:
                continue
            try:
                os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def write_wallpaper_file(image_data):
    """把下载到的图片写进缓存，返回落盘路径。

    WebP / BMP 会先转成 PNG —— SystemParametersInfoW 对这两种格式支持不可靠。
    先写 ``.tmp`` 再 ``os.replace``，避免中途失败留下半张图被当成正常缓存。
    """
    ext = detect_extension(image_data)
    if ext in (".webp", ".bmp"):
        with Image.open(io.BytesIO(image_data)) as img:
            out = io.BytesIO()
            img.convert("RGB").save(out, format="PNG")
            image_data = out.getvalue()
            ext = ".png"

    filename = f"wallpaper_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(CACHE_DIR, filename)
    temp = path + ".tmp"
    with open(temp, "wb") as handle:
        handle.write(image_data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    cleanup_cache(path)
    return path


def get_cache_info():
    """返回缓存图片的 (数量, 总字节数)。"""
    total = 0
    count = 0
    try:
        for name in os.listdir(CACHE_DIR):
            if not name.lower().endswith(IMAGE_EXTENSIONS):
                continue
            path = os.path.join(CACHE_DIR, name)
            if os.path.isfile(path):
                count += 1
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
    except OSError:
        pass
    return count, total


def format_bytes(size):
    """把字节数格式化成适合界面显示的文本。"""
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def clear_cache(keep_path=None):
    """清理缓存图片；``keep_path`` 用于保护当前正在使用的壁纸。

    返回 ``(删除文件数, 释放字节数, 失败文件数)``。
    """
    protected = os.path.abspath(keep_path) if keep_path and os.path.isfile(keep_path) else ""
    deleted = 0
    freed = 0
    failed = 0
    try:
        names = os.listdir(CACHE_DIR)
    except OSError:
        return 0, 0, 0

    for name in names:
        if not name.lower().endswith(IMAGE_EXTENSIONS):
            continue
        path = os.path.join(CACHE_DIR, name)
        if os.path.abspath(path) == protected:
            continue
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
            os.remove(path)
            deleted += 1
            freed += size
        except OSError:
            failed += 1
    return deleted, freed, failed
