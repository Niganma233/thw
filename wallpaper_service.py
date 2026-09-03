import ctypes
import io
import json
import os
import shutil
import time
import urllib.request
import uuid
import winreg
from urllib.parse import urlparse

from PIL import Image

from config import CACHE_DIR, FAVORITES_DIR

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

WALLPAPER_STYLES = {
    "fill": (10, 0),
    "fit": (6, 0),
    "center": (0, 0),
    "stretch": (2, 0),
}

BUILTIN_SOURCES = {
    "all": {
        "name": "东方随机图（全部）",
        "url": "https://img.paulzzh.com/touhou/random?size={size}&site=all",
    },
    "konachan": {
        "name": "东方随机图（Konachan）",
        "url": "https://img.paulzzh.com/touhou/random?size={size}&site=konachan",
    },
    "yandere": {
        "name": "东方随机图（Yande.re）",
        "url": "https://img.paulzzh.com/touhou/random?size={size}&site=yandere",
    },
}


def get_current_windows_wallpaper():
    buffer = ctypes.create_unicode_buffer(1024)
    ok = ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buffer), buffer, 0)
    return buffer.value if ok else ""


def set_wallpaper_windows(img_path):
    if not img_path or not os.path.isfile(img_path):
        return False
    abs_path = os.path.abspath(img_path)
    result = ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)
    return bool(result)


def set_wallpaper_style(style_key):
    wallpaper_style, tile_wallpaper = WALLPAPER_STYLES.get(style_key, WALLPAPER_STYLES["fill"])
    key = None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, str(wallpaper_style))
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, str(tile_wallpaper))
        return True
    except OSError as exc:
        print(f"设置壁纸显示方式失败: {exc}")
        return False
    finally:
        if key is not None:
            winreg.CloseKey(key)


def fetch_with_retry(url, timeout=15, retries=3, backoff_base=2):
    last_exc = None
    for attempt in range(retries):
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("只支持 http:// 或 https:// 图源地址")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read(), response.headers.get_content_type()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff_base ** attempt)
    raise last_exc


def _detect_extension(img_data):
    with Image.open(io.BytesIO(img_data)) as img:
        img.verify()
        fmt = (img.format or "JPEG").upper()
    return {
        "JPEG": ".jpg", "JPG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp"
    }.get(fmt, ".jpg")


def _resolve_json_image_url(data):
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception:
        return None
    if isinstance(obj, dict):
        for key in ("url", "image", "image_url", "download_url", "src"):
            value = obj.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return None


def fetch_source_image(url, timeout=15, retries=3):
    data, content_type = fetch_with_retry(url, timeout=timeout, retries=retries)
    try:
        _detect_extension(data)
        return data
    except Exception:
        # 兼容最常见的 JSON 图源：{"url": "https://.../image.jpg"}
        image_url = _resolve_json_image_url(data)
        if not image_url:
            raise ValueError("图源没有直接返回图片，也没有找到可用的图片 URL")
        data, _ = fetch_with_retry(image_url, timeout=timeout, retries=retries)
        _detect_extension(data)
        return data


def build_source_url(source_url, site="all", size="pc"):
    url = (source_url or "").strip()
    if not url:
        raise ValueError("图源地址不能为空")
    try:
        return url.format(size=size, site=site)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"图源 URL 模板格式错误：{exc}") from exc


def _cleanup_cache(keep_path, max_files=12):
    try:
        files = [
            os.path.join(CACHE_DIR, name)
            for name in os.listdir(CACHE_DIR)
            if name.lower().endswith(IMAGE_EXTENSIONS)
        ]
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


def _write_wallpaper_file(img_data):
    ext = _detect_extension(img_data)
    # Windows 桌面壁纸更稳妥地使用 JPG/PNG；WebP/BMP 转为 PNG。
    if ext in (".webp", ".bmp"):
        with Image.open(io.BytesIO(img_data)) as img:
            out = io.BytesIO()
            img.convert("RGB").save(out, format="PNG")
            img_data = out.getvalue()
            ext = ".png"
    filename = f"wallpaper_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(CACHE_DIR, filename)
    temp = path + ".tmp"
    with open(temp, "wb") as f:
        f.write(img_data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    _cleanup_cache(path)
    return path


def download_wallpaper(site, size, source_url=None, timeout=15, retries=3):
    if source_url is None:
        source_url = BUILTIN_SOURCES.get(site, BUILTIN_SOURCES["all"])["url"]
    url = build_source_url(source_url, site=site, size=size)
    img_data = fetch_source_image(url, timeout=timeout, retries=retries)
    return _write_wallpaper_file(img_data)


def list_favorites():
    try:
        files = [f for f in os.listdir(FAVORITES_DIR) if f.lower().endswith(IMAGE_EXTENSIONS)]
    except OSError:
        return []
    return sorted(files, key=str.casefold)


def _safe_name(name):
    cleaned = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip().rstrip(".")
    return cleaned or f"fav_{time.strftime('%Y%m%d_%H%M%S')}"


def save_favorite(src_path, name):
    if not src_path or not os.path.isfile(src_path):
        raise FileNotFoundError("当前壁纸文件不存在")
    base = _safe_name(name)
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        ext = ".jpg"
    fav_filename = f"{base}{ext}"
    fav_path = os.path.join(FAVORITES_DIR, fav_filename)
    if os.path.exists(fav_path):
        fav_filename = f"{base}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}{ext}"
        fav_path = os.path.join(FAVORITES_DIR, fav_filename)
    shutil.copy2(src_path, fav_path)
    return fav_filename, fav_path


def delete_favorite(filename):
    if not filename:
        return False
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        return False
    fav_path = os.path.join(FAVORITES_DIR, safe_name)
    if os.path.isfile(fav_path):
        os.remove(fav_path)
        return True
    return False
