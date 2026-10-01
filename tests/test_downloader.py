"""services.downloader：URL 模板、带重试的 HTTP、JSON 图源解包。"""
import os
import unittest
import unittest.mock as mock

from services import downloader
from tests.helpers import FakeResponse, IsolatedDataDir, png_bytes


class BuildSourceUrlTest(unittest.TestCase):
    def test_substitutes_placeholders(self):
        url = downloader.build_source_url("https://e.com/r?size={size}&site={site}", site="konachan", size="pc")
        self.assertEqual(url, "https://e.com/r?size=pc&site=konachan")

    def test_url_without_placeholders_is_returned_as_is(self):
        self.assertEqual(downloader.build_source_url("https://e.com/r"), "https://e.com/r")

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(downloader.build_source_url("  https://e.com/r  "), "https://e.com/r")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            downloader.build_source_url("   ")

    def test_unknown_placeholder_raises(self):
        with self.assertRaises(ValueError):
            downloader.build_source_url("https://e.com/{nope}")


class FetchWithRetryTest(unittest.TestCase):
    def test_success_on_first_attempt(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(png_bytes())) as opener:
            data, content_type = downloader.fetch_with_retry("https://e.com/r")
        self.assertEqual(data[:4], b"\x89PNG")
        self.assertEqual(content_type, "image/png")
        self.assertEqual(opener.call_count, 1)

    def test_retries_then_succeeds_with_exponential_backoff(self):
        responses = [OSError("boom"), OSError("boom"), FakeResponse(png_bytes())]
        with mock.patch("urllib.request.urlopen", side_effect=responses) as opener, \
                mock.patch("time.sleep") as sleeper:
            data, _ = downloader.fetch_with_retry("https://e.com/r", retries=3)
        self.assertEqual(opener.call_count, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [1, 2])
        self.assertEqual(data[:4], b"\x89PNG")

    def test_exhausted_retries_raises_last_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("网络断了")), \
                mock.patch("time.sleep"):
            with self.assertRaises(OSError) as ctx:
                downloader.fetch_with_retry("https://e.com/r", retries=2)
        self.assertIn("网络断了", str(ctx.exception))

    def test_rejects_non_http_scheme_without_network_call(self):
        with mock.patch("urllib.request.urlopen") as opener:
            with self.assertRaises(ValueError):
                downloader.fetch_with_retry("ftp://e.com/r", retries=1)
        opener.assert_not_called()

    def test_retries_at_least_once(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("x")) as opener:
            with self.assertRaises(OSError):
                downloader.fetch_with_retry("https://e.com/r", retries=0)
        self.assertEqual(opener.call_count, 1)

    def test_no_sleep_after_final_attempt(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("x")), \
                mock.patch("time.sleep") as sleeper:
            with self.assertRaises(OSError):
                downloader.fetch_with_retry("https://e.com/r", retries=2)
        self.assertEqual(sleeper.call_count, 1)


class FetchSourceImageTest(unittest.TestCase):
    def test_direct_image_is_returned(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(png_bytes())):
            data = downloader.fetch_source_image("https://e.com/r")
        self.assertEqual(data[:4], b"\x89PNG")

    def test_json_response_is_followed(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            url = request.full_url if hasattr(request, "full_url") else request
            calls.append(url)
            if len(calls) == 1:
                return FakeResponse(b'{"url": "https://cdn.example/real.png"}', "application/json")
            return FakeResponse(png_bytes())

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            data = downloader.fetch_source_image("https://e.com/r")
        self.assertEqual(calls, ["https://e.com/r", "https://cdn.example/real.png"])
        self.assertEqual(data[:4], b"\x89PNG")

    def test_json_without_usable_url_raises(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b'{"foo": 1}', "application/json")), \
                mock.patch("time.sleep"):
            with self.assertRaises(ValueError):
                downloader.fetch_source_image("https://e.com/r")

    def test_passes_timeout_and_retries_through(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(png_bytes())) as opener:
            downloader.fetch_source_image("https://e.com/r", timeout=7, retries=1)
        self.assertEqual(opener.call_args.kwargs["timeout"], 7)


class DownloadWallpaperTest(unittest.TestCase):
    def _source(self, **overrides):
        source = {
            "id": "s", "name": "测试源",
            "url": "https://e.com/r?size={size}&site={site}",
            "site": "all", "size": "pc", "timeout": 15, "retries": 3,
        }
        source.update(overrides)
        return source

    def test_passes_source_settings_through(self):
        with IsolatedDataDir(), \
                mock.patch.object(downloader, "fetch_source_image", return_value=png_bytes()) as fetch:
            path = downloader.download_wallpaper(self._source(timeout=42, retries=5))
            self.assertTrue(os.path.isfile(path))
        fetch.assert_called_once_with("https://e.com/r?size=pc&site=all", timeout=42, retries=5)

    def test_explicit_overrides_win_over_source(self):
        with IsolatedDataDir(), \
                mock.patch.object(downloader, "fetch_source_image", return_value=png_bytes()) as fetch:
            downloader.download_wallpaper(self._source(), size_override="mobile", timeout=7, retries=1)
        fetch.assert_called_once_with("https://e.com/r?size=mobile&site=all", timeout=7, retries=1)

    def test_defaults_are_used_when_source_omits_them(self):
        source = {"url": "https://e.com/r"}
        with IsolatedDataDir(), \
                mock.patch.object(downloader, "fetch_source_image", return_value=png_bytes()) as fetch:
            downloader.download_wallpaper(source)
        fetch.assert_called_once_with("https://e.com/r", timeout=downloader.DEFAULT_TIMEOUT, retries=downloader.DEFAULT_RETRIES)


if __name__ == "__main__":
    unittest.main()
