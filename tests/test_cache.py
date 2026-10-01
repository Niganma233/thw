"""services.cache：缓存落盘、统计与清理。"""
import os
import unittest
from pathlib import Path

from PIL import Image

from services import cache
from tests.helpers import IsolatedDataDir, png_bytes, webp_bytes


class WriteWallpaperFileTest(unittest.TestCase):
    def test_png_is_stored_with_png_extension(self):
        with IsolatedDataDir() as base:
            path = cache.write_wallpaper_file(png_bytes())
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.startswith(str(base / "Cache")))
            self.assertTrue(path.endswith(".png"))

    def test_webp_is_converted_to_png(self):
        # SystemParametersInfoW 对 WebP 支持不可靠，必须先转码。
        with IsolatedDataDir():
            path = cache.write_wallpaper_file(webp_bytes())
            self.assertTrue(path.endswith(".png"))
            with Image.open(path) as img:
                self.assertEqual(img.format, "PNG")

    def test_garbage_is_rejected(self):
        with IsolatedDataDir() as base:
            with self.assertRaises(Exception):
                cache.write_wallpaper_file(b"not an image")
            leftovers = os.listdir(base / "Cache")
        self.assertEqual(leftovers, [], "无效数据不应留下任何缓存文件")

    def test_no_temp_file_left_behind(self):
        with IsolatedDataDir() as base:
            cache.write_wallpaper_file(png_bytes())
            leftovers = [n for n in os.listdir(base / "Cache") if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_unique_filenames(self):
        with IsolatedDataDir():
            first = cache.write_wallpaper_file(png_bytes())
            second = cache.write_wallpaper_file(png_bytes())
        self.assertNotEqual(first, second)


class CleanupCacheTest(unittest.TestCase):
    def _make_cache(self, base, count):
        cache_dir = Path(base) / "Cache"
        paths = []
        for index in range(count):
            path = cache_dir / f"img_{index}.png"
            path.write_bytes(b"x" * (index + 1))
            # 显式设置 mtime，保证排序可预测：index 越大越新
            stamp = 1_700_000_000 + index
            os.utime(path, (stamp, stamp))
            paths.append(path)
        return paths

    def test_keeps_newest_max_files(self):
        with IsolatedDataDir() as base:
            self._make_cache(base, 4)
            cache.cleanup_cache(None, max_files=2)
            remaining = sorted(os.listdir(Path(base) / "Cache"))
        self.assertEqual(remaining, ["img_2.png", "img_3.png"])

    def test_protects_current_wallpaper_even_if_old(self):
        with IsolatedDataDir() as base:
            paths = self._make_cache(base, 3)
            protected = str(paths[0])  # 最旧的一张，正常会被删
            cache.cleanup_cache(protected, max_files=1)
            remaining = sorted(os.listdir(Path(base) / "Cache"))
        self.assertIn("img_0.png", remaining)

    def test_missing_dir_is_silent(self):
        with IsolatedDataDir() as base:
            os.rmdir(Path(base) / "Cache")
            cache.cleanup_cache(None)  # 不应抛异常

    def test_write_does_not_exceed_cache_limit(self):
        with IsolatedDataDir() as base:
            for _ in range(cache.MAX_CACHED_FILES + 3):
                cache.write_wallpaper_file(png_bytes())
            count, _ = cache.get_cache_info()
        self.assertLessEqual(count, cache.MAX_CACHED_FILES)


class CacheInfoTest(unittest.TestCase):
    def test_empty_cache(self):
        with IsolatedDataDir():
            self.assertEqual(cache.get_cache_info(), (0, 0))

    def test_counts_only_image_files(self):
        with IsolatedDataDir() as base:
            cache_dir = Path(base) / "Cache"
            (cache_dir / "a.png").write_bytes(b"12345")
            (cache_dir / "b.JPG").write_bytes(b"123")
            (cache_dir / "notes.txt").write_bytes(b"ignored")
            count, total = cache.get_cache_info()
        self.assertEqual(count, 2)
        self.assertEqual(total, 8)

    def test_missing_dir_returns_zeros(self):
        with IsolatedDataDir() as base:
            os.rmdir(Path(base) / "Cache")
            self.assertEqual(cache.get_cache_info(), (0, 0))


class FormatBytesTest(unittest.TestCase):
    def test_units(self):
        cases = [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (1536, "1.5 KB"), (1048576, "1.0 MB")]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(cache.format_bytes(value), expected)

    def test_negative_is_clamped(self):
        self.assertEqual(cache.format_bytes(-5), "0 B")

    def test_gigabytes(self):
        self.assertEqual(cache.format_bytes(2 * 1024 ** 3), "2.0 GB")


class ClearCacheTest(unittest.TestCase):
    def test_removes_images_and_reports_totals(self):
        with IsolatedDataDir() as base:
            cache_dir = Path(base) / "Cache"
            (cache_dir / "a.png").write_bytes(b"12345")
            (cache_dir / "b.png").write_bytes(b"123")
            deleted, freed, failed = cache.clear_cache()
        self.assertEqual((deleted, freed, failed), (2, 8, 0))

    def test_protects_current_wallpaper(self):
        with IsolatedDataDir() as base:
            cache_dir = Path(base) / "Cache"
            keep = cache_dir / "keep.png"
            keep.write_bytes(b"12345")
            (cache_dir / "drop.png").write_bytes(b"123")
            deleted, _, _ = cache.clear_cache(str(keep))
            remaining = os.listdir(cache_dir)
        self.assertEqual(deleted, 1)
        self.assertEqual(remaining, ["keep.png"])

    def test_ignores_non_image_files(self):
        with IsolatedDataDir() as base:
            cache_dir = Path(base) / "Cache"
            (cache_dir / "notes.txt").write_bytes(b"keep me")
            cache.clear_cache()
            self.assertTrue((cache_dir / "notes.txt").exists())

    def test_missing_dir_returns_zeros(self):
        with IsolatedDataDir() as base:
            os.rmdir(Path(base) / "Cache")
            self.assertEqual(cache.clear_cache(), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
