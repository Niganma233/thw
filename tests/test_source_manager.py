"""source_manager 的迁移、排序、候选回退与参数校验。"""
import unittest

from tests.helpers import default_cfg
from source_manager import BUILTIN_SOURCES, SourceManager, validate_source_url


class ValidateSourceUrlTest(unittest.TestCase):
    def test_accepts_http_and_https(self):
        self.assertEqual(validate_source_url(" https://e.com/r "), "https://e.com/r")
        self.assertEqual(validate_source_url("http://e.com/r"), "http://e.com/r")

    def test_accepts_template_placeholders(self):
        url = "https://e.com/random?size={size}&site={site}"
        self.assertEqual(validate_source_url(url), url)

    def test_rejects_empty(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_source_url(value)

    def test_rejects_non_http_scheme(self):
        for value in ("ftp://e.com/r", "file:///c:/x.png", "e.com/r"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_source_url(value)

    def test_rejects_broken_template(self):
        with self.assertRaises(ValueError):
            validate_source_url("https://e.com/{unknown}")


class NormalizeCustomTest(unittest.TestCase):
    def test_clamps_timeout_and_retries(self):
        low = SourceManager._normalize_custom({"name": "a", "url": "https://e.com/r", "timeout": 0, "retries": 0})
        high = SourceManager._normalize_custom({"name": "b", "url": "https://e.com/r", "timeout": 999, "retries": 99})
        self.assertEqual(low["timeout"], 5)
        self.assertEqual(low["retries"], 1)
        self.assertEqual(high["timeout"], 60)
        self.assertEqual(high["retries"], 5)

    def test_generates_id_and_marks_not_builtin(self):
        data = SourceManager._normalize_custom({"name": "a", "url": "https://e.com/r"})
        self.assertTrue(data["id"].startswith("custom_"))
        self.assertFalse(data["builtin"])
        self.assertTrue(data["enabled"])

    def test_blank_name_gets_fallback(self):
        data = SourceManager._normalize_custom({"name": "   ", "url": "https://e.com/r"})
        self.assertEqual(data["name"], "自定义图源")

    def test_invalid_url_raises(self):
        with self.assertRaises(ValueError):
            SourceManager._normalize_custom({"name": "a", "url": "not-a-url"})


class MigrateLegacyTest(unittest.TestCase):
    def test_converts_custom_sources_to_new_list(self):
        cfg = default_cfg(custom_sources=[
            {"name": "旧图源", "url": "https://old.example/r"},
        ])
        SourceManager(cfg)
        self.assertEqual(len(cfg["sources"]), 1)
        self.assertEqual(cfg["sources"][0]["name"], "旧图源")
        self.assertIn("timeout", cfg["sources"][0])

    def test_rewrites_custom_index_selection_to_new_id(self):
        cfg = default_cfg(custom_sources=[
            {"name": "第一个", "url": "https://a.example/r"},
            {"name": "第二个", "url": "https://b.example/r"},
        ], source_id="custom:1")
        SourceManager(cfg)
        second_id = next(s["id"] for s in cfg["sources"] if s["name"] == "第二个")
        self.assertEqual(cfg["source_id"], second_id)

    def test_out_of_range_custom_selection_falls_back_to_all(self):
        # Phase 1 修复：以前只在 int() 抛异常时回退，N 能解析但旧图源不存在时
        # 会把悬空的 "custom:7" 原样留在配置里。
        cfg = default_cfg(custom_sources=[], source_id="custom:7")
        SourceManager(cfg)
        self.assertEqual(cfg["source_id"], "all")

    def test_selection_pointing_at_deduped_legacy_entry_falls_back(self):
        # 旧索引 1 指向的 URL 已经在 sources 里，迁移时被去重跳过，于是映射表里
        # 没有 1；选择值必须回退而不是悬空。
        cfg = default_cfg(
            sources=[{"name": "已有", "url": "https://dup.example/r"}],
            custom_sources=[
                {"name": "第一个", "url": "https://first.example/r"},
                {"name": "重复", "url": "https://dup.example/r"},
            ],
            source_id="custom:1",
        )
        SourceManager(cfg)
        self.assertEqual(cfg["source_id"], "all")

    def test_valid_legacy_selection_still_migrates(self):
        cfg = default_cfg(
            custom_sources=[
                {"name": "第一个", "url": "https://a.example/r"},
                {"name": "第二个", "url": "https://b.example/r"},
            ],
            source_id="custom:0",
        )
        SourceManager(cfg)
        first_id = next(s["id"] for s in cfg["sources"] if s["name"] == "第一个")
        self.assertEqual(cfg["source_id"], first_id)

    def test_non_numeric_custom_selection_falls_back_to_all(self):
        cfg = default_cfg(custom_sources=[], source_id="custom:abc")
        SourceManager(cfg)
        self.assertEqual(cfg["source_id"], "all")

    def test_duplicate_urls_are_dropped(self):
        cfg = default_cfg(custom_sources=[
            {"name": "A", "url": "https://same.example/r"},
            {"name": "B", "url": "https://same.example/r"},
        ])
        SourceManager(cfg)
        self.assertEqual(len(cfg["sources"]), 1)

    def test_invalid_entries_are_skipped(self):
        cfg = default_cfg(sources=[
            {"name": "好", "url": "https://ok.example/r"},
            {"name": "坏", "url": "nonsense"},
            {"name": "", "url": "https://blank.example/r"},
            "not-a-dict",
        ])
        SourceManager(cfg)
        self.assertEqual([s["name"] for s in cfg["sources"]], ["好"])

    def test_migration_is_idempotent(self):
        cfg = default_cfg(custom_sources=[{"name": "旧", "url": "https://old.example/r"}])
        SourceManager(cfg)
        first = [s["id"] for s in cfg["sources"]]
        SourceManager(cfg)
        self.assertEqual([s["id"] for s in cfg["sources"]], first)

    def test_non_list_sources_field_is_repaired(self):
        cfg = default_cfg(sources="broken")
        SourceManager(cfg)
        self.assertEqual(cfg["sources"], [])


class SourceAccessTest(unittest.TestCase):
    def setUp(self):
        self.cfg = default_cfg()
        self.manager = SourceManager(self.cfg)

    def test_get_finds_builtin_and_custom(self):
        self.assertEqual(self.manager.get("all")["id"], "all")
        data, _ = self.manager.add_or_update(None, "自定义", "https://e.com/r", "all", "pc", 15, 3)
        self.assertEqual(self.manager.get(data["id"])["name"], "自定义")

    def test_get_unknown_returns_none(self):
        self.assertIsNone(self.manager.get("does-not-exist"))

    def test_get_returns_a_copy(self):
        source = self.manager.get("all")
        source["name"] = "被改坏了"
        self.assertNotEqual(self.manager.get("all")["name"], "被改坏了")

    def test_all_sources_lists_builtins_first(self):
        self.manager.add_or_update(None, "自定义", "https://e.com/r", "all", "pc", 15, 3)
        sources = self.manager.all_sources()
        self.assertEqual(len(sources), len(BUILTIN_SOURCES) + 1)
        self.assertTrue(all(s["builtin"] for s in sources[:len(BUILTIN_SOURCES)]))

    def test_add_or_update_appends_then_updates_in_place(self):
        data, index = self.manager.add_or_update(None, "新", "https://e.com/r", "all", "pc", 15, 3)
        self.assertEqual(index, 0)
        updated, index2 = self.manager.add_or_update(data["id"], "改名", "https://e.com/r2", "all", "pc", 20, 4)
        self.assertEqual(index2, 0)
        self.assertEqual(len(self.cfg["sources"]), 1)
        self.assertEqual(updated["name"], "改名")
        self.assertEqual(updated["timeout"], 20)

    def test_delete_removes_by_id(self):
        data, _ = self.manager.add_or_update(None, "待删", "https://e.com/r", "all", "pc", 15, 3)
        self.assertIsNotNone(self.manager.delete(data["id"]))
        self.assertIsNone(self.manager.delete(data["id"]))
        self.assertEqual(self.cfg["sources"], [])

    def test_move_reorders_and_clamps(self):
        first, _ = self.manager.add_or_update(None, "一", "https://a.com/r", "all", "pc", 15, 3)
        second, _ = self.manager.add_or_update(None, "二", "https://b.com/r", "all", "pc", 15, 3)
        self.assertTrue(self.manager.move(second["id"], 0))
        self.assertEqual([s["name"] for s in self.cfg["sources"]], ["二", "一"])
        # 越界索引被夹紧
        self.manager.move(second["id"], 99)
        self.assertEqual([s["name"] for s in self.cfg["sources"]], ["一", "二"])
        self.assertFalse(self.manager.move("nope", 0))

    def test_set_enabled(self):
        data, _ = self.manager.add_or_update(None, "开关", "https://e.com/r", "all", "pc", 15, 3)
        self.assertTrue(self.manager.set_enabled(data["id"], False))
        self.assertFalse(self.cfg["sources"][0]["enabled"])
        self.assertFalse(self.manager.set_enabled("nope", False))


class EnabledCandidatesTest(unittest.TestCase):
    def setUp(self):
        self.cfg = default_cfg()
        self.manager = SourceManager(self.cfg)

    def test_preferred_source_comes_first(self):
        candidates = self.manager.enabled_candidates("yandere")
        self.assertEqual(candidates[0]["id"], "yandere")

    def test_disabled_custom_sources_are_excluded(self):
        data, _ = self.manager.add_or_update(None, "停用", "https://e.com/r", "all", "pc", 15, 3)
        self.manager.set_enabled(data["id"], False)
        ids = [s["id"] for s in self.manager.enabled_candidates()]
        self.assertNotIn(data["id"], ids)

    def test_disabled_preferred_is_not_forced_in(self):
        data, _ = self.manager.add_or_update(None, "停用", "https://e.com/r", "all", "pc", 15, 3)
        self.manager.set_enabled(data["id"], False)
        candidates = self.manager.enabled_candidates(data["id"])
        self.assertNotIn(data["id"], [s["id"] for s in candidates])

    def test_custom_sources_precede_builtins_as_fallback(self):
        data, _ = self.manager.add_or_update(None, "自定义", "https://e.com/r", "all", "pc", 15, 3)
        ordered = [s["id"] for s in self.manager.enabled_candidates()]
        self.assertLess(ordered.index(data["id"]), ordered.index("all"))

    def test_no_duplicate_ids(self):
        ids = [s["id"] for s in self.manager.enabled_candidates("all")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unknown_preferred_is_ignored(self):
        self.assertTrue(self.manager.enabled_candidates("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
