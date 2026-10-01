"""config 模块的读写与容错行为。"""
import json
import os
import unittest

from tests.helpers import IsolatedDataDir, config


class LoadConfigTest(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with IsolatedDataDir():
            cfg = config.load_config()
        self.assertEqual(cfg["interval_minutes"], config.DEFAULT_CONFIG["interval_minutes"])
        self.assertEqual(cfg["wallpaper_style"], "fill")
        self.assertEqual(cfg["sources"], [])

    def test_partial_file_is_merged_over_defaults(self):
        with IsolatedDataDir():
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as handle:
                json.dump({"interval_minutes": 5}, handle)
            cfg = config.load_config()
        self.assertEqual(cfg["interval_minutes"], 5)
        # 未出现在文件里的键仍取默认值
        self.assertEqual(cfg["auto_start"], config.DEFAULT_CONFIG["auto_start"])

    def test_corrupt_json_falls_back_to_defaults(self):
        with IsolatedDataDir():
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as handle:
                handle.write("{ this is not json")
            cfg = config.load_config()
        self.assertEqual(cfg["interval_minutes"], config.DEFAULT_CONFIG["interval_minutes"])

    def test_non_dict_json_falls_back_to_defaults(self):
        with IsolatedDataDir():
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as handle:
                json.dump([1, 2, 3], handle)
            cfg = config.load_config()
        self.assertEqual(cfg["interval_minutes"], config.DEFAULT_CONFIG["interval_minutes"])

    def test_non_list_source_fields_are_coerced(self):
        with IsolatedDataDir():
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as handle:
                json.dump({"sources": "oops", "custom_sources": 42}, handle)
            cfg = config.load_config()
        self.assertEqual(cfg["sources"], [])
        self.assertEqual(cfg["custom_sources"], [])


class SaveConfigTest(unittest.TestCase):
    def test_roundtrip(self):
        with IsolatedDataDir():
            cfg = config.load_config()
            cfg["interval_minutes"] = 120
            cfg["sources"] = [{"id": "custom_x", "name": "测试", "url": "https://e.com/r"}]
            config.save_config(cfg)

            reloaded = config.load_config()
        self.assertEqual(reloaded["interval_minutes"], 120)
        self.assertEqual(len(reloaded["sources"]), 1)
        self.assertEqual(reloaded["sources"][0]["name"], "测试")

    def test_written_as_utf8_without_ascii_escapes(self):
        with IsolatedDataDir():
            cfg = config.load_config()
            cfg["hotkey_favorite"] = "东方"
            config.save_config(cfg)
            with open(config.CONFIG_FILE, "r", encoding="utf-8") as handle:
                raw = handle.read()
        self.assertIn("东方", raw)

    def test_no_temp_file_left_behind(self):
        with IsolatedDataDir():
            config.save_config(config.load_config())
            leftovers = [n for n in os.listdir(config.APP_DIR) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
