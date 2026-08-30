import os
import shutil
import time
import ctypes
import urllib.request
import winreg

from config import FAVORITES_DIR, TEMP_WALLPAPER_PATH

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png')

# 壁纸显示方式: 键 -> (WallpaperStyle, TileWallpaper)
WALLPAPER_STYLES = {
    "fill": (10, 0),     # 填充：裁剪填满整个屏幕（默认）
    "fit": (6, 0),       # 适应：完整显示整张图，留黑边
    "center": (0, 0),    # 居中
    "stretch": (2, 0),   # 拉伸
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


def set_wallpaper_style(style_key):
    """通过注册表 HKCU\\Control Panel\\Desktop 设置壁纸显示方式"""
    wallpaper_style, tile_wallpaper = WALLPAPER_STYLES.get(style_key, WALLPAPER_STYLES["fill"])
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, str(wallpaper_style))
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, str(tile_wallpaper))
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"设置壁纸显示方式失败: {e}")
        return False


def fetch_with_retry(url, timeout=15, retries=3, backoff_base=2):
    """带重试机制的 urlopen 封装：最多尝试 retries 次，失败后按指数退避等待"""
    last_exc = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(backoff_base ** attempt)
    raise last_exc


def download_wallpaper(site, size, timeout=15, retries=3):
    """下载在线壁纸到临时文件并返回路径（内部自带重试机制）"""
    api_url = f"https://img.paulzzh.com/touhou/random?size={size}&site={site}"
    img_data = fetch_with_retry(api_url, timeout=timeout, retries=retries)
    with open(TEMP_WALLPAPER_PATH, "wb") as f:
        f.write(img_data)
    return TEMP_WALLPAPER_PATH


# ---------------- 星标收藏 ----------------
def list_favorites():
    """返回收藏夹中的壁纸文件名列表"""
    return [f for f in os.listdir(FAVORITES_DIR) if f.lower().endswith(IMAGE_EXTENSIONS)]


def save_favorite(src_path, name):
    """把图片拷贝到收藏夹并命名为 name，返回 (文件名, 完整路径)。

    若同名已存在则自动追加时间戳以避免覆盖。
    """
    fav_filename = f"{name}.jpg"
    fav_path = os.path.join(FAVORITES_DIR, fav_filename)
    if os.path.exists(fav_path):
        base, ext = os.path.splitext(fav_filename)
        fav_filename = f"{base}_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
        fav_path = os.path.join(FAVORITES_DIR, fav_filename)
    shutil.copy2(src_path, fav_path)
    return fav_filename, fav_path


def delete_favorite(filename):
    """从收藏夹物理删除图片，返回是否删除成功"""
    fav_path = os.path.join(FAVORITES_DIR, filename)
    if os.path.exists(fav_path):
        os.remove(fav_path)
        return True
    return False
