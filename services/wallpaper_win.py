"""Windows 桌面壁纸的读写。

只碰 Win32 与注册表，不涉及网络、下载或文件布局。
"""
import ctypes
import os
import winreg

from core.constants import WALLPAPER_STYLES

# SystemParametersInfoW 的两个 action / flag 组合
_SPI_GETDESKWALLPAPER = 0x0073
_SPI_SETDESKWALLPAPER = 20
_SPIF_UPDATEINIFILE = 3


def get_current_windows_wallpaper():
    """返回当前桌面壁纸路径；取不到时返回空串。"""
    buffer = ctypes.create_unicode_buffer(1024)
    ok = ctypes.windll.user32.SystemParametersInfoW(_SPI_GETDESKWALLPAPER, len(buffer), buffer, 0)
    return buffer.value if ok else ""


def set_wallpaper_windows(img_path):
    """把指定文件设为桌面壁纸；文件不存在或系统调用失败时返回 False。"""
    if not img_path or not os.path.isfile(img_path):
        return False
    return bool(ctypes.windll.user32.SystemParametersInfoW(_SPI_SETDESKWALLPAPER, 0, os.path.abspath(img_path), _SPIF_UPDATEINIFILE))


def set_wallpaper_style(style_key):
    """设置桌面壁纸的缩放方式（填充/适应/居中/拉伸）。

    写的是 HKCU\\Control Panel\\Desktop 下的 WallpaperStyle 与 TileWallpaper；
    这两项通常要在重新应用一次壁纸之后才会立刻生效。
    """
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
