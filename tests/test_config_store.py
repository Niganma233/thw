"""config 模块的读写与容错行为。"""
import json
import os
import unittest

from core import config_store, paths
from tests.helpers import IsolatedDataDir


class LoadConfigTest(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with IsolatedDataDir():
            cfg = config_store.load_config()
        self.assertEqual(cfg["interval_minutes"], config_store.DEFAULT_CONFIG["interval_minutes"])
        self.assertEqual(cfg["wallpaper_style"], "fill")
        self.assertEqual(cfg["sources"], [])

    def test_partial_file_is_merged_over_defaults(self):
        with IsolatedDataDir():
            with open(paths.CONFIG_FILE, "w", encoding="utf-8") as handle:
                json.dump({"interval_minutes": 5}, handle)
            cfg = config_store.load_config()
        self.assertEqual(cfg["interval_minutes"], 5)
        # 未出现在文件里的键仍取默认值
        self.assertEqual(cfg["auto_start"], config_store.DEFAULT_CONFIG["auto_start"])

    def test_corrupt_json_falls_back_to_defaults(self):
        with IsolatedDataDir():
            with open(paths.CONFIG_FILE, "w", encoding="utf-8") as handle:
                handle.write("{ this is not json")
            cfg = config_store.load_config()
        self.assertEqual(cfg["interval_minutes"], config_store.DEFAULT_CONFIG["interval_minutes"])

    def test_non_dict_json_falls_back_to_defaults(self):
        with IsolatedDataDir():
            with open(paths.CONFIG_FILE, "w", encoding="utf-8") as handle:
                json.dump([1, 2, 3], handle)
            cfg = config_store.load_config()
        self.assertEqual(cfg["interval_minutes"], config_store.DEFAULT_CONFIG["interval_minutes"])

    def test_non_list_source_fields_are_coerced(self):
        with IsolatedDataDir():
            with open(paths.CONFIG_FILE, "w", encoding="utf-8") as handle:
                json.dump({"sources": "oops", "custom_sources": 42}, handle)
            cfg = config_store.load_config()
        self.assertEqual(cfg["sources"], [])
        self.assertEqual(cfg["custom_sources"], [])

    def test_defaults_are_not_mutated_by_a_loaded_config(self):
        # Phase 1 修复：以前是 DEFAULT_CONFIG.copy()（浅拷贝），cfg["sources"] 与
        # DEFAULT_CONFIG["sources"] 是同一个列表对象，追加图源会污染默认值，
        # 之后每次启动都会带着上一次运行残留的图源。
        with IsolatedDataDir():
            cfg = config_store.load_config()
            cfg["sources"].append({"id": "x", "name": "污染", "url": "https://e.com/r"})
            cfg["custom_sources"].append({"name": "污染"})
            fresh = config_store.load_config()
        self.assertEqual(config_store.DEFAULT_CONFIG["sources"], [])
        self.assertEqual(config_store.DEFAULT_CONFIG["custom_sources"], [])
        self.assertEqual(fresh["sources"], [])
        self.assertEqual(fresh["custom_sources"], [])


class SaveConfigTest(unittest.TestCase):
    def test_roundtrip(self):
        with IsolatedDataDir():
            cfg = config_store.load_config()
            cfg["interval_minutes"] = 120
            cfg["sources"] = [{"id": "custom_x", "name": "测试", "url": "https://e.com/r"}]
            config_store.save_config(cfg)

            reloaded = config_store.load_config()
        self.assertEqual(reloaded["interval_minutes"], 120)
        self.assertEqual(len(reloaded["sources"]), 1)
        self.assertEqual(reloaded["sources"][0]["name"], "测试")

    def test_written_as_utf8_without_ascii_escapes(self):
        with IsolatedDataDir():
            cfg = config_store.load_config()
            cfg["hotkey_favorite"] = "东方"
            config_store.save_config(cfg)
            with open(paths.CONFIG_FILE, "r", encoding="utf-8") as handle:
                raw = handle.read()
        self.assertIn("东方", raw)

    def test_no_temp_file_left_behind(self):
        with IsolatedDataDir():
            config_store.save_config(config_store.load_config())
            leftovers = [n for n in os.listdir(paths.APP_DIR) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
