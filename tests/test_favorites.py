"""services.favorites：收藏夹读写与文件名清洗。"""
import os
import unittest
from pathlib import Path

from services import favorites
from tests.helpers import IsolatedDataDir, png_bytes


class SafeNameTest(unittest.TestCase):
    def test_illegal_characters_are_replaced(self):
        self.assertEqual(favorites.safe_name('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")

    def test_trailing_dots_are_stripped(self):
        self.assertEqual(favorites.safe_name("name..."), "name")

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(favorites.safe_name("  name  "), "name")

    def test_blank_falls_back_to_timestamped_name(self):
        self.assertTrue(favorites.safe_name("...").startswith("fav_"))

    def test_only_dots_falls_back_to_timestamped_name(self):
        self.assertTrue(favorites.safe_name("   ").startswith("fav_"))


class ListFavoritesTest(unittest.TestCase):
    def test_sorted_case_insensitively(self):
        with IsolatedDataDir() as base:
            directory = Path(base) / "Favorites"
            for name in ("b.PNG", "a.jpg", "notes.txt"):
                (directory / name).write_bytes(b"x")
            self.assertEqual(favorites.list_favorites(), ["a.jpg", "b.PNG"])

    def test_missing_dir_returns_empty(self):
        with IsolatedDataDir() as base:
            os.rmdir(Path(base) / "Favorites")
            self.assertEqual(favorites.list_favorites(), [])


class SaveFavoriteTest(unittest.TestCase):
    def test_copies_file_and_keeps_original(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.png"
            source.write_bytes(png_bytes())
            filename, path = favorites.save_favorite(str(source), "我的壁纸")
            self.assertEqual(filename, "我的壁纸.png")
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(source.exists(), "原文件不应被移动")

    def test_sanitizes_name(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.png"
            source.write_bytes(png_bytes())
            filename, _ = favorites.save_favorite(str(source), "a/b:c")
            self.assertEqual(filename, "a_b_c.png")

    def test_avoids_collision(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.png"
            source.write_bytes(png_bytes())
            first, _ = favorites.save_favorite(str(source), "同名")
            second, _ = favorites.save_favorite(str(source), "同名")
            self.assertNotEqual(first, second)
            self.assertTrue(second.startswith("同名_"))

    def test_missing_source_raises(self):
        with IsolatedDataDir():
            with self.assertRaises(FileNotFoundError):
                favorites.save_favorite("", "x")

    def test_falls_back_to_jpg_for_unknown_extension(self):
        with IsolatedDataDir() as base:
            source = Path(base) / "src.dat"
            source.write_bytes(b"x")
            filename, _ = favorites.save_favorite(str(source), "无名")
            self.assertTrue(filename.endswith(".jpg"))


class DeleteFavoriteTest(unittest.TestCase):
    def test_removes_file(self):
        with IsolatedDataDir() as base:
            target = Path(base) / "Favorites" / "a.png"
            target.write_bytes(b"x")
            self.assertTrue(favorites.delete_favorite("a.png"))
            self.assertFalse(target.exists())

    def test_missing_returns_false(self):
        with IsolatedDataDir():
            self.assertFalse(favorites.delete_favorite("nope.png"))

    def test_empty_or_none_returns_false(self):
        with IsolatedDataDir():
            self.assertFalse(favorites.delete_favorite(""))
            self.assertFalse(favorites.delete_favorite(None))

    def test_rejects_path_traversal(self):
        with IsolatedDataDir() as base:
            outside = Path(base) / "config.json"
            outside.write_text("{}", encoding="utf-8")
            self.assertFalse(favorites.delete_favorite("../config.json"))
            self.assertTrue(outside.exists(), "目录外的文件绝不能被删掉")


if __name__ == "__main__":
    unittest.main()
