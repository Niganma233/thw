"""core.paths：数据目录与目录创建。

目录创建从"import 副作用"改成了显式调用，所以值得单独测一遍——
尤其是建不出来的时候不能抛异常。
"""
import os
import unittest
from pathlib import Path

from core import paths
from tests.helpers import IsolatedDataDir


class EnsureDirsTest(unittest.TestCase):
    def test_creates_favorites_and_cache(self):
        with IsolatedDataDir() as base:
            for name in ("Favorites", "Cache"):
                os.rmdir(Path(base) / name)
            paths.ensure_dirs()
            self.assertTrue(os.path.isdir(paths.FAVORITES_DIR))
            self.assertTrue(os.path.isdir(paths.CACHE_DIR))

    def test_is_idempotent(self):
        with IsolatedDataDir():
            paths.ensure_dirs()
            paths.ensure_dirs()

    def test_does_not_raise_when_creation_is_impossible(self):
        # 数据目录不可写时不能直接崩：界面启动后会明确提示"数据目录不可写"
        with IsolatedDataDir() as base:
            blocker = Path(base) / "Cache"
            os.rmdir(blocker)
            blocker.write_text("I am a file, not a directory", encoding="utf-8")
            paths.ensure_dirs()  # 不应抛出

    def test_directories_are_under_app_dir(self):
        with IsolatedDataDir():
            for path in (paths.FAVORITES_DIR, paths.CACHE_DIR):
                self.assertTrue(path.startswith(paths.APP_DIR))
            self.assertTrue(paths.CONFIG_FILE.startswith(paths.APP_DIR))

    def test_importing_paths_has_no_side_effects(self):
        # 与旧 config.py 的关键差别：import 不再创建目录。
        # 这里通过"删除目录后重新导入仍然不存在"来确认。
        import importlib

        with IsolatedDataDir() as base:
            target = Path(base) / "Favorites"
            os.rmdir(target)
            importlib.reload(paths)
            # reload 会重新读取环境变量，但不会主动建目录
            self.assertFalse(target.exists(), "import core.paths 不应创建目录")


if __name__ == "__main__":
    unittest.main()
