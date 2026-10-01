"""兼容层：原先这个模块里的实现已按职责拆到 services/ 与 core/ 下。

拆分对照：
    Windows 壁纸读写      -> services.wallpaper_win
    图片字节解释          -> services.images
    网络抓取与多图源回退  -> services.downloader
    缓存落盘/统计/清理    -> services.cache
    收藏夹读写            -> services.favorites
    共享常量              -> core.constants

这里只把原来的公开名字重新导出，让尚未迁移的调用方（四个视图）零改动。
Phase 7 会把调用方直接指向新模块，然后删掉本文件——新代码请直接 import services.*。
"""
from core.constants import IMAGE_EXTENSIONS, WALLPAPER_STYLES  # noqa: F401
from services.cache import clear_cache, format_bytes, get_cache_info  # noqa: F401
from services.downloader import (  # noqa: F401
    build_source_url,
    download_wallpaper,
    fetch_source_image,
    fetch_with_retry,
)
from services.favorites import (  # noqa: F401
    delete_favorite,
    list_favorites,
    safe_name,
    save_favorite,
)
from services.wallpaper_win import (  # noqa: F401
    get_current_windows_wallpaper,
    set_wallpaper_style,
    set_wallpaper_windows,
)

__all__ = [
    # 常量
    "IMAGE_EXTENSIONS",
    "WALLPAPER_STYLES",
    # Windows
    "get_current_windows_wallpaper",
    "set_wallpaper_style",
    "set_wallpaper_windows",
    # 下载
    "build_source_url",
    "download_wallpaper",
    "fetch_source_image",
    "fetch_with_retry",
    # 缓存
    "clear_cache",
    "format_bytes",
    "get_cache_info",
    # 收藏
    "delete_favorite",
    "list_favorites",
    "safe_name",
    "save_favorite",
]
