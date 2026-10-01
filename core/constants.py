"""跨模块共享的常量。

放在 core/ 下是因为 UI 层与 services 层都要用，而且这里不依赖任何其他模块，
可以作为依赖图的最底层。
"""

# 视为"壁纸图片"的扩展名；比较时统一转小写（见 services.cache / services.favorites）
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

# 壁纸显示方式 -> (WallpaperStyle 注册表值, TileWallpaper 注册表值)
#
# 这份键集合是"合法显示方式"的唯一真相来源：
# settings_view.style_map 的显示标签必须与它一一对应，
# tests/test_ui_smoke.py::test_style_keys_match_service 会守住这一点。
WALLPAPER_STYLES = {
    "fill": (10, 0),
    "fit": (6, 0),
    "center": (0, 0),
    "stretch": (2, 0),
}
