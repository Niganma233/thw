"""真实 Tk 窗口下的界面冒烟测试。

这些用例会真的创建 CustomTkinter 控件树，用来兜住"改动把界面改崩"这类回归。
它们不启动 WallpaperApp（那会拉起下载线程、托盘图标与全局热键），
只单独构建三个视图。

Tk 初始化失败时（无显示环境）自动跳过，不会让整套测试失败。
"""
import contextlib
import copy
import os
import unittest
from pathlib import Path

from PIL import Image

from tests.helpers import IsolatedDataDir, config, default_cfg, make_bare_app, wallpaper_service


def _ctk():
    import customtkinter as ctk
    return ctk


@contextlib.contextmanager
def tk_root():
    try:
        ctk = _ctk()
        root = ctk.CTk()
    except Exception as exc:  # pragma: no cover - 只在无显示环境触发
        raise unittest.SkipTest(f"无法创建 Tk 窗口：{exc}")
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def collect_entries(widget):
    """深度收集控件树里所有 CTkEntry。"""
    ctk = _ctk()
    found = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkEntry):
            found.append(child)
        found.extend(collect_entries(child))
    return found


def make_png(path, size=(40, 30), color="red"):
    Image.new("RGB", size, color).save(path)
    return str(path)


class SettingsViewSmokeTest(unittest.TestCase):
    def _build(self, root, **overrides):
        from settings_view import SettingsView
        tab = _ctk().CTkFrame(root)
        return SettingsView(tab, default_cfg(**overrides))

    def test_builds_and_collects_all_keys(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._build(root, interval_minutes=30)
            collected = view.collect()
        self.assertEqual(set(collected), {
            "refresh_on_startup", "auto_start", "interval_minutes",
            "wallpaper_style", "hotkey_favorite", "hotkey_switch",
        })

    def test_interval_roundtrip(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._build(root, interval_minutes=120)
            self.assertEqual(view.collect()["interval_minutes"], 120)

    def test_interval_zero_roundtrip(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._build(root, interval_minutes=0)
            self.assertEqual(view.interval_var.get(), "不自动更换")
            self.assertEqual(view.collect()["interval_minutes"], 0)

    def test_style_roundtrip(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._build(root, wallpaper_style="center")
            self.assertEqual(view.collect()["wallpaper_style"], "center")

    def test_unknown_style_falls_back_to_fill(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._build(root, wallpaper_style="bogus")
            self.assertEqual(view.collect()["wallpaper_style"], "fill")

    def test_hotkeys_are_stripped(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._build(root, hotkey_switch="  ctrl+shift+f  ")
            self.assertEqual(view.collect()["hotkey_switch"], "ctrl+shift+f")

    def test_cache_info_reads_isolated_dir(self):
        with IsolatedDataDir() as base:
            (Path(base) / "Cache" / "a.png").write_bytes(b"12345")
            with tk_root() as root:
                view = self._build(root)
        self.assertIn("1 张图片", view.cache_info_var.get())


class FixedHeightComboBoxSmokeTest(unittest.TestCase):
    def test_builds_with_values(self):
        from fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a", "b", "c"], max_visible_items=2)
            self.assertFalse(combo.is_dropdown_open())

    def test_open_then_close_dropdown(self):
        from fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a", "b", "c"])
            combo.pack()
            root.update_idletasks()
            combo._open_dropdown_menu()
            self.assertTrue(combo.is_dropdown_open())
            combo.close_dropdown()
            self.assertFalse(combo.is_dropdown_open())

    def test_close_when_not_open_is_safe(self):
        from fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a"])
            combo.close_dropdown()
            self.assertFalse(combo.is_dropdown_open())

    def test_configure_values_closes_open_dropdown(self):
        from fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a", "b"])
            combo.pack()
            root.update_idletasks()
            combo._open_dropdown_menu()
            combo.configure(values=["x", "y", "z"])
            self.assertFalse(combo.is_dropdown_open())

    def test_empty_values_do_not_open(self):
        from fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=[])
            combo._open_dropdown_menu()
            self.assertFalse(combo.is_dropdown_open())

    def test_choosing_index_sets_value_and_fires_command(self):
        from fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            picked = []
            combo = FixedHeightComboBox(root, values=["a", "b", "c"], command=picked.append)
            combo.pack()
            root.update_idletasks()
            combo._open_dropdown_menu()
            combo._choose_index(1)
            self.assertEqual(combo.get(), "b")
            self.assertEqual(picked, ["b"])


class FavoriteViewSmokeTest(unittest.TestCase):
    def _view(self, root):
        from favorite_view import FavoriteView
        app = make_bare_app()
        app.favorite_current_wallpaper = lambda: None
        app.on_favorite_behavior_changed = lambda behavior: None
        app.reset_refresh_timer = lambda: None
        app.fetch_and_set_wallpaper = lambda: None
        tab = _ctk().CTkFrame(root)
        # FavoriteView.__init__ 只建控件；填充列表是 gui.WallpaperApp 之后调用的
        view = FavoriteView(tab, app)
        view.refresh()
        return view

    def test_builds_with_no_favorites(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._view(root)
            self.assertEqual(view.fav_combo_var.get(), "暂无收藏壁纸")
            self.assertEqual(view.collect()["favorite_behavior"], "pause")

    def test_refresh_lists_favorites_and_previews_first(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "saved.png")
            with tk_root() as root:
                view = self._view(root)
                self.assertEqual(view.fav_combo_var.get(), "saved.png")
                self.assertIsNotNone(view._preview_img, "预览图应当被加载")

    def test_preview_follows_selection(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "a.png", color="red")
            make_png(Path(base) / "Favorites" / "b.png", color="blue")
            with tk_root() as root:
                view = self._view(root)
                view.fav_combo_var.set("b.png")
                view.update_preview()
                self.assertIsNotNone(view._preview_img)

    def test_unreadable_preview_degrades_gracefully(self):
        with IsolatedDataDir() as base:
            (Path(base) / "Favorites" / "broken.png").write_bytes(b"not an image")
            with tk_root() as root:
                view = self._view(root)
                self.assertIsNone(view._preview_img)
                self.assertEqual(view.preview_label.cget("text"), "无法预览")

    def test_collect_reports_carousel_flag(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._view(root)
            view.favorite_behavior_var.set("carousel")
            collected = view.collect()
        self.assertEqual(collected["favorite_behavior"], "carousel")
        self.assertTrue(collected["favorite_carousel"])

    def test_legacy_config_maps_to_carousel(self):
        with IsolatedDataDir(), tk_root() as root:
            from favorite_view import FavoriteView
            app = make_bare_app(default_cfg(favorite_behavior=None, favorite_carousel=True))
            app.favorite_current_wallpaper = lambda: None
            tab = _ctk().CTkFrame(root)
            view = FavoriteView(tab, app)
            self.assertEqual(view.favorite_behavior_var.get(), "carousel")


class SourceManagerViewSmokeTest(unittest.TestCase):
    def _view(self, root, cfg=None):
        from source_manager_view import SourceManagerView
        cfg = default_cfg() if cfg is None else cfg
        changes = []
        statuses = []
        tab = _ctk().CTkFrame(root)
        # 回调契约：gui.WallpaperApp._source_changed(save=False)，所以必须接受
        # save 关键字参数。
        view = SourceManagerView(
            tab, cfg,
            on_changed=lambda save=False: changes.append(save),
            on_status=lambda text, kind="ready": statuses.append((text, kind)),
        )
        return view, cfg, changes, statuses

    def test_lists_builtins_and_custom_sources(self):
        from source_manager import BUILTIN_SOURCES
        cfg = default_cfg()
        cfg["sources"] = [{"id": "custom_1", "name": "我的源", "url": "https://e.com/r",
                           "site": "all", "size": "pc", "timeout": 15, "retries": 3,
                           "enabled": True, "builtin": False}]
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root, cfg)
            row_count = len(view._row_widgets)
        self.assertEqual(row_count, len(BUILTIN_SOURCES) + 1)

    def test_select_updates_cfg_and_notifies(self):
        with IsolatedDataDir(), tk_root() as root:
            view, cfg, changes, _ = self._view(root)
            view.select("konachan")
            self.assertEqual(cfg["source_id"], "konachan")
            self.assertEqual(view.selected_id, "konachan")
        self.assertEqual(len(changes), 1)

    def test_builtin_source_disables_editor_entries(self):
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root)
            view.select("all")
            states = {entry.cget("state") for entry in collect_entries(view.parent)}
        self.assertEqual(states, {"disabled"}, "内置图源不可编辑")

    def test_custom_source_enables_editor_entries(self):
        cfg = default_cfg()
        cfg["sources"] = [{"id": "custom_1", "name": "我的源", "url": "https://e.com/r",
                           "site": "all", "size": "pc", "timeout": 15, "retries": 3,
                           "enabled": True, "builtin": False}]
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root, cfg)
            view.select("custom_1")
            states = {entry.cget("state") for entry in collect_entries(view.parent)}
        self.assertEqual(states, {"normal"}, "自定义图源应当可编辑")

    def test_new_source_clears_editor(self):
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, statuses = self._view(root)
            view.select("all")
            view.new_source()
            self.assertEqual(view.edit_name.get(), "")
            self.assertEqual(view.edit_url.get(), "")
            self.assertEqual(view.edit_timeout.get(), "15")
        self.assertEqual(statuses[-1][1], "ready")

    def test_toggle_disables_custom_source(self):
        cfg = default_cfg()
        cfg["sources"] = [{"id": "custom_1", "name": "我的源", "url": "https://e.com/r",
                           "site": "all", "size": "pc", "timeout": 15, "retries": 3,
                           "enabled": True, "builtin": False}]
        with IsolatedDataDir(), tk_root() as root:
            view, cfg, changes, _ = self._view(root, cfg)
            view.toggle("custom_1", False)
            self.assertFalse(cfg["sources"][0]["enabled"])
        self.assertTrue(changes)


if __name__ == "__main__":
    unittest.main()
