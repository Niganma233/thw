"""wallpaper_service 兼容层的契约。

四个视图目前仍然 ``import wallpaper_service``，所以这个壳必须把原来的公开名字
原样转出来。Phase 7 会把调用方直接指向 services.*，届时本文件与外壳一起删除。
"""
import unittest

import wallpaper_service
from services import cache, downloader, favorites, wallpaper_win

# 四个视图 + gui 实际用到的全部名字（由 grep 得出）
NAMES_USED_BY_VIEWS = (
    "WALLPAPER_STYLES",
    "build_source_url",
    "clear_cache",
    "delete_favorite",
    "download_wallpaper",
    "fetch_source_image",
    "format_bytes",
    "get_cache_info",
    "get_current_windows_wallpaper",
    "list_favorites",
    "save_favorite",
    "set_wallpaper_style",
    "set_wallpaper_windows",
)


class ShimContractTest(unittest.TestCase):
    def test_reexports_every_name_the_views_use(self):
        for name in NAMES_USED_BY_VIEWS:
            with self.subTest(name=name):
                self.assertTrue(hasattr(wallpaper_service, name), f"兼容层缺少 {name}")

    def test_names_are_the_split_module_objects(self):
        # 必须是同一对象，否则会出现两套实现各自演化的诡异问题
        self.assertIs(wallpaper_service.download_wallpaper, downloader.download_wallpaper)
        self.assertIs(wallpaper_service.fetch_source_image, downloader.fetch_source_image)
        self.assertIs(wallpaper_service.build_source_url, downloader.build_source_url)
        self.assertIs(wallpaper_service.clear_cache, cache.clear_cache)
        self.assertIs(wallpaper_service.get_cache_info, cache.get_cache_info)
        self.assertIs(wallpaper_service.format_bytes, cache.format_bytes)
        self.assertIs(wallpaper_service.save_favorite, favorites.save_favorite)
        self.assertIs(wallpaper_service.list_favorites, favorites.list_favorites)
        self.assertIs(wallpaper_service.delete_favorite, favorites.delete_favorite)
        self.assertIs(wallpaper_service.set_wallpaper_windows, wallpaper_win.set_wallpaper_windows)

    def test_all_declares_only_real_attributes(self):
        for name in wallpaper_service.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(wallpaper_service, name))

    def test_every_used_name_is_declared_in_all(self):
        missing = [name for name in NAMES_USED_BY_VIEWS if name not in wallpaper_service.__all__]
        self.assertEqual(missing, [], "视图用到的名字应当都在 __all__ 里声明")

    def test_private_helpers_are_not_part_of_the_contract(self):
        # 旧的私有名（_detect_extension 等）已随拆分成为各模块的公开函数，
        # 兼容层刻意不再转出它们，避免新代码继续依赖私有接口。
        for legacy in ("_detect_extension", "_resolve_json_image_url", "_cleanup_cache", "_write_wallpaper_file"):
            with self.subTest(name=legacy):
                self.assertFalse(hasattr(wallpaper_service, legacy))


if __name__ == "__main__":
    unittest.main()
