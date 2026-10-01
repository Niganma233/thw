"""wallpaper_service 的下载、缓存与收藏逻辑。

网络部分用假的 urlopen 替身，缓存与收藏重定向到临时目录。
"""
import email.message
import io
import os
import time
import unittest
import unittest.mock as mock
from pathlib import Path

from PIL import Image

from tests.helpers import IsolatedDataDir, wallpaper_service


def png_bytes(size=(8, 8), color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="JPEG")
    return buffer.getvalue()


def webp_bytes(size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "green").save(buffer, format="WEBP")
    return buffer.getvalue()


class FakeResponse:
    """模拟 urlopen 返回的上下文管理器。"""

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


class BuildSourceUrlTest(unittest.TestCase):
    def test_substitutes_placeholders(self):
        url = wallpaper_service.build_source_url("https://e.com/r?size={size}&site={site}", site="konachan", size="pc")
        self.assertEqual(url, "https://e.com/r?size=pc&site=konachan")

    def test_url_without_placeholders_is_returned_as_is(self):
        self.assertEqual(wallpaper_service.build_source_url("https://e.com/r"), "https://e.com/r")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            wallpaper_service.build_source_url("   ")

    def test_unknown_placeholder_raises(self):
        with self.assertRaises(ValueError):
            wallpaper_service.build_source_url("https://e.com/{nope}")


class DetectExtensionTest(unittest.TestCase):
    def test_known_formats(self):
        cases = [
            (png_bytes(), ".png"),
            (jpeg_bytes(), ".jpg"),
            (webp_bytes(), ".webp"),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(wallpaper_service._detect_extension(data), expected)

    def test_garbage_raises(self):
        with self.assertRaises(Exception):
            wallpaper_service._detect_extension(b"definitely not an image")


class ResolveJsonImageUrlTest(unittest.TestCase):
    def test_finds_url_in_known_keys(self):
        for key in ("url", "image", "image_url", "download_url", "src"):
            with self.subTest(key=key):
                payload = ('{"%s": "https://cdn.example/a.png"}' % key).encode()
                self.assertEqual(wallpaper_service._resolve_json_image_url(payload), "https://cdn.example/a.png")

    def test_ignores_non_http_values(self):
        self.assertIsNone(wallpaper_service._resolve_json_image_url(b'{"url": "not-a-url"}'))

    def test_returns_none_for_non_json(self):
        self.assertIsNone(wallpaper_service._resolve_json_image_url(b"\x89PNG\r\n"))

    def test_returns_none_for_json_list(self):
        self.assertIsNone(wallpaper_service._resolve_json_image_url(b'["https://e.com/a.png"]'))


class FetchWithRetryTest(unittest.TestCase):
    def test_success_on_first_attempt(self):
        with mock.patch.object(wallpaper_service.urllib.request, "urlopen", return_value=FakeResponse(png_bytes())) as opener:
            data, content_type = wallpaper_service.fetch_with_retry("https://e.com/r")
        self.assertEqual(data[:4], b"\x89PNG")
        self.assertEqual(content_type, "image/png")
        self.assertEqual(opener.call_count, 1)

    def test_retries_then_succeeds(self):
        responses = [OSError("boom"), OSError("boom"), FakeResponse(png_bytes())]
        with mock.patch.object(wallpaper_service.urllib.request, "urlopen", side_effect=responses) as opener, \
                mock.patch.object(wallpaper_service.time, "sleep") as sleeper:
            data, _ = wallpaper_service.fetch_with_retry("https://e.com/r", retries=3)
        self.assertEqual(opener.call_count, 3)
        # 指数退避：2**0, 2**1
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [1, 2])
        self.assertEqual(data[:4], b"\x89PNG")

    def test_exhausted_retries_raises_last_error(self):
        with mock.patch.object(wallpaper_service.urllib.request, "urlopen", side_effect=OSError("网络断了")), \
                mock.patch.object(wallpaper_service.time, "sleep"):
            with self.assertRaises(OSError) as ctx:
                wallpaper_service.fetch_with_retry("https://e.com/r", retries=2)
        self.assertIn("网络断了", str(ctx.exception))

    def test_rejects_non_http_scheme(self):
        with mock.patch.object(wallpaper_service.urllib.request, "urlopen") as opener:
            with self.assertRaises(ValueError):
                wallpaper_service.fetch_with_retry("ftp://e.com/r", retries=1)
        opener.assert_not_called()

    def test_retries_at_least_once(self):
        with mock.patch.object(wallpaper_service.urllib.request, "urlopen", side_effect=OSError("x")) as opener:
            with self.assertRaises(OSError):
                wallpaper_service.fetch_with_retry("https://e.com/r", retries=0)
        self.assertEqual(opener.call_count, 1)


class FetchSourceImageTest(unittest.TestCase):
    def test_direct_image_is_returned(self):
        with mock.patch.object(wallpaper_service.urllib.request, "urlopen", return_value=FakeResponse(png_bytes())):
            data = wallpaper_service.fetch_source_image("https://e.com/r")
        self.assertEqual(wallpaper_service._detect_extension(data), ".png")

    def test_json_response_is_followed(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            url = request.full_url if hasattr(request, "full_url") else request
            calls.append(url)
            if len(calls) == 1:
                return FakeResponse(b'{"url": "https://cdn.example/real.png"}', "application/json")
            return FakeResponse(png_bytes())

        with mock.patch.object(wallpaper_service.urllib.request, "urlopen", side_effect=fake_urlopen):
            data = wallpaper_service.fetch_source_image("https://e.com/r")
        self.assertEqual(calls, ["https://e.com/r", "https://cdn.example/real.png"])
        self.assertEqual(wallpaper_service._detect_extension(data), ".png")

    def test_json_without_usable_url_raises(self):
        with mock.patch.object(wallpaper_service.urllib.request, "urlopen", return_value=FakeResponse(b'{"foo": 1}', "application/json")), \
                mock.patch.object(wallpaper_service.time, "sleep"):
            with self.assertRaises(ValueError):
                wallpaper_service.fetch_source_image("https://e.com/r")


class WriteWallpaperFileTest(unittest.TestCase):
    def test_png_is_stored_with_png_extension(self):
        with IsolatedDataDir() as base:
            path = wallpaper_service._write_wallpaper_file(png_bytes())
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.startswith(str(base / "Cache")))
            self.assertTrue(path.endswith(".png"))

    def test_webp_is_converted_to_png(self):
        with IsolatedDataDir():
            path = wallpaper_service._write_wallpaper_file(webp_bytes())
            self.assertTrue(path.endswith(".png"))
            with Image.open(path) as img:
                self.assertEqual(img.format, "PNG")

    def test_no_temp_file_left_behind(self):
        with IsolatedDataDir() as base:
            wallpaper_service._write_wallpaper_file(png_bytes())
            leftovers = [n for n in os.listdir(base / "Cache") if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_unique_filenames(self):
        with IsolatedDataDir():
            first = wallpaper_service._write_wallpaper_file(png_bytes())
            second = wallpaper_service._write_wallpaper_file(png_bytes())
        self.assertNotEqual(first, second)


class DownloadWallpaperTest(unittest.TestCase):
    def _source(self, **overrides):
        source = {"id": "s", "name": "测试源", "url": "https://e.com/r?size={size}&site={site}",
                  "site": "all", "size": "pc", "timeout": 15, "retries": 3}
        source.update(overrides)
        return source

    def test_passes_source_settings_through(self):
        with IsolatedDataDir(), \
                mock.patch.object(wallpaper_service, "fetch_source_image", return_value=png_bytes()) as fetch:
            path = wallpaper_service.download_wallpaper(self._source(timeout=42, retries=5))
            self.assertTrue(os.path.isfile(path))
        fetch.assert_called_once_with("https://e.com/r?size=pc&site=all", timeout=42, retries=5)

    def test_explicit_overrides_win_over_source(self):
        with IsolatedDataDir(), \
                mock.patch.object(wallpaper_service, "fetch_source_image", return_value=png_bytes()) as fetch:
            wallpaper_service.download_wallpaper(self._source(), size_override="mobile", timeout=7, retries=1)
        fetch.assert_called_once_with("https://e.com/r?size=mobile&site=all", timeout=7, retries=1)


class CacheCleanupTest(unittest.TestCase):
    def _make_cache(self, base, count):
        cache = Path(base) / "Cache"
        paths = []
        for index in range(count):
            path = cache / f"img_{index}.png"
            path.write_bytes(b"x" * (index + 1))
            # 显式设置 mtime，保证排序可预测：index 越大越新
            stamp = 1_700_000_000 + index
            os.utime(path, (stamp, stamp))
            paths.append(path)
        return paths

    def test_cleanup_keeps_newest_max_files(self):
        with IsolatedDataDir() as base:
            self._make_cache(base, 4)
            wallpaper_service._cleanup_cache(None, max_files=2)
            remaining = sorted(os.listdir(Path(base) / "Cache"))
        self.assertEqual(remaining, ["img_2.png", "img_3.png"])

    def test_cleanup_protects_current_wallpaper_even_if_old(self):
        with IsolatedDataDir() as base:
            paths = self._make_cache(base, 3)
            protected = str(paths[0])  # 最旧的一张，正常会被删
            wallpaper_service._cleanup_cache(protected, max_files=1)
            remaining = sorted(os.listdir(Path(base) / "Cache"))
        self.assertIn("img_0.png", remaining)

    def test_cleanup_on_missing_dir_is_silent(self):
        with IsolatedDataDir() as base:
            os.rmdir(Path(base) / "Cache")
            wallpaper_service._cleanup_cache(None)  # 不应抛异常


class CacheInfoTest(unittest.TestCase):
    def test_empty_cache(self):
        with IsolatedDataDir():
            self.assertEqual(wallpaper_service.get_cache_info(), (0, 0))

    def test_counts_only_image_files(self):
        with IsolatedDataDir() as base:
            cache = Path(base) / "Cache"
            (cache / "a.png").write_bytes(b"12345")
            (cache / "b.JPG").write_bytes(b"123")
            (cache / "notes.txt").write_bytes(b"ignored")
            count, total = wallpaper_service.get_cache_info()
        self.assertEqual(count, 2)
        self.assertEqual(total, 8)

    def test_format_bytes(self):
        cases = [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (1536, "1.5 KB"), (1048576, "1.0 MB")]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(wallpaper_service.format_bytes(value), expected)

    def test_format_bytes_negative_is_clamped(self):
        self.assertEqual(wallpaper_service.format_bytes(-5), "0 B")


class ClearCacheTest(unittest.TestCase):
    def test_removes_images_and_reports_totals(self):
        with IsolatedDataDir() as base:
            cache = Path(base) / "Cache"
            (cache / "a.png").write_bytes(b"12345")
            (cache / "b.png").write_bytes(b"123")
            deleted, freed, failed = wallpaper_service.clear_cache()
        self.assertEqual((deleted, freed, failed), (2, 8, 0))

    def test_protects_current_wallpaper(self):
        with IsolatedDataDir() as base:
            cache = Path(base) / "Cache"
            keep = cache / "keep.png"
            keep.write_bytes(b"12345")
            (cache / "drop.png").write_bytes(b"123")
            deleted, _, _ = wallpaper_service.clear_cache(str(keep))
            remaining = os.listdir(cache)
        self.assertEqual(deleted, 1)
        self.assertEqual(remaining, ["keep.png"])

    def test_ignores_non_image_files(self):
        with IsolatedDataDir() as base:
            cache = Path(base) / "Cache"
            (cache / "notes.txt").write_bytes(b"keep me")
            wallpaper_service.clear_cache()
            self.assertTrue((cache / "notes.txt").exists())

    def test_missing_dir_returns_zeros(self):
        with IsolatedDataDir() as base:
            os.rmdir(Path(base) / "Cache")
            self.assertEqual(wallpaper_service.clear_cache(), (0, 0, 0))


class SafeNameTest(unittest.TestCase):
    def test_illegal_characters_are_replaced(self):
        self.assertEqual(wallpaper_service.safe_name('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")

    def test_trailing_dots_are_stripped(self):
        self.assertEqual(wallpaper_service.safe_name("name..."), "name")

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(wallpaper_service.safe_name("  name  "), "name")

    def test_blank_falls_back_to_timestamped_name(self):
        result = wallpaper_service.safe_name("...")
        self.assertTrue(result.startswith("fav_"))


class FavoritesTest(unittest.TestCase):
    def test_list_is_sorted_case_insensitively(self):
        with IsolatedDataDir() as base:
            favorites = Path(base) / "Favorites"
            for name in ("b.PNG", "a.jpg", "notes.txt"):
                (favorites / name).write_bytes(b"x")
            self.assertEqual(wallpaper_service.list_favorites(), ["a.jpg", "b.PNG"])

    def test_list_on_missing_dir_returns_empty(self):
        with IsolatedDataDir() as base:
            os.rmdir(Path(base) / "Favorites")
            self.assertEqual(wallpaper_service.list_favorites(), [])

    def test_save_copies_file(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.png"
            source.write_bytes(png_bytes())
            filename, path = wallpaper_service.save_favorite(str(source), "我的壁纸")
            self.assertEqual(filename, "我的壁纸.png")
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(source.exists(), "原文件不应被移动")

    def test_save_sanitizes_name(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.png"
            source.write_bytes(png_bytes())
            filename, _ = wallpaper_service.save_favorite(str(source), "a/b:c")
            self.assertEqual(filename, "a_b_c.png")

    def test_save_avoids_collision(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.png"
            source.write_bytes(png_bytes())
            first, _ = wallpaper_service.save_favorite(str(source), "同名")
            second, _ = wallpaper_service.save_favorite(str(source), "同名")
            self.assertNotEqual(first, second)
            self.assertTrue(second.startswith("同名_"))

    def test_save_missing_source_raises(self):
        with IsolatedDataDir():
            with self.assertRaises(FileNotFoundError):
                wallpaper_service.save_favorite("", "x")

    def test_save_falls_back_to_jpg_for_unknown_extension(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.dat"
            source.write_bytes(b"x")
            filename, _ = wallpaper_service.save_favorite(str(source), "无名")
            self.assertTrue(filename.endswith(".jpg"))

    def test_delete_removes_file(self):
        with IsolatedDataDir() as base:
            favorites = Path(base) / "Favorites"
            target = favorites / "a.png"
            target.write_bytes(b"x")
            self.assertTrue(wallpaper_service.delete_favorite("a.png"))
            self.assertFalse(target.exists())

    def test_delete_missing_returns_false(self):
        with IsolatedDataDir():
            self.assertFalse(wallpaper_service.delete_favorite("nope.png"))

    def test_delete_rejects_path_traversal(self):
        with IsolatedDataDir() as base:
            outside = Path(base) / "config.json"
            outside.write_text("{}", encoding="utf-8")
            self.assertFalse(wallpaper_service.delete_favorite("../config.json"))
            self.assertTrue(outside.exists(), "目录外的文件绝不能被删掉")


if __name__ == "__main__":
    unittest.main()
