"""services.images：把图源返回的字节解释成图片。"""
import unittest

from services.images import detect_extension, resolve_json_image_url
from tests.helpers import jpeg_bytes, png_bytes, webp_bytes


class DetectExtensionTest(unittest.TestCase):
    def test_known_formats(self):
        cases = [
            (png_bytes(), ".png"),
            (jpeg_bytes(), ".jpg"),
            (webp_bytes(), ".webp"),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(detect_extension(data), expected)

    def test_garbage_raises(self):
        with self.assertRaises(Exception):
            detect_extension(b"definitely not an image")

    def test_empty_bytes_raise(self):
        with self.assertRaises(Exception):
            detect_extension(b"")


class ResolveJsonImageUrlTest(unittest.TestCase):
    def test_finds_url_in_known_keys(self):
        for key in ("url", "image", "image_url", "download_url", "src"):
            with self.subTest(key=key):
                payload = ('{"%s": "https://cdn.example/a.png"}' % key).encode()
                self.assertEqual(resolve_json_image_url(payload), "https://cdn.example/a.png")

    def test_ignores_non_http_values(self):
        self.assertIsNone(resolve_json_image_url(b'{"url": "not-a-url"}'))

    def test_returns_none_for_non_json(self):
        self.assertIsNone(resolve_json_image_url(b"\x89PNG\r\n"))

    def test_returns_none_for_json_list(self):
        self.assertIsNone(resolve_json_image_url(b'["https://e.com/a.png"]'))

    def test_key_precedence_follows_url_keys_order(self):
        # _URL_KEYS 的顺序决定优先级："url" 排在 "src" 前面，所以它胜出。
        payload = b'{"src": "https://a.example/1.png", "url": "https://b.example/2.png"}'
        self.assertEqual(resolve_json_image_url(payload), "https://b.example/2.png")


if __name__ == "__main__":
    unittest.main()
