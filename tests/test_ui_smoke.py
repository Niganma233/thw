"""真实 Tk 窗口下的界面冒烟测试。

这些用例会真的创建 CustomTkinter 控件树，用来兜住"改动把界面改崩"这类回归。
它们不启动 WallpaperApp（那会拉起下载线程、托盘图标与全局热键），
只单独构建三个视图。

Tk 初始化失败时（无显示环境）自动跳过，不会让整套测试失败。
"""
import unittest
import unittest.mock as mock
from pathlib import Path

from PIL import Image

from core.constants import WALLPAPER_STYLES

from tests.helpers import (
    IsolatedDataDir,
    collect_widgets,
    default_cfg,
    tk_root,
)


def _ctk():
    import customtkinter as ctk
    return ctk


def collect_entries(widget):
    """深度收集控件树里所有 CTkEntry。"""
    return collect_widgets(widget, _ctk().CTkEntry)


def make_png(path, size=(40, 30), color="red"):
    Image.new("RGB", size, color).save(path)
    return str(path)


class SettingsViewSmokeTest(unittest.TestCase):
    def _build(self, root, **overrides):
        from ui.settings_view import SettingsView
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

    def test_style_keys_match_service(self):
        # settings_view 的显示标签与 core.constants 的注册表取值必须覆盖同一组
        # 样式键，否则会出现"界面上能选但这个样式设不进去"，或反过来漏掉一个样式。
        with IsolatedDataDir(), tk_root() as root:
            view = self._build(root)
            self.assertEqual(set(view.style_map), set(WALLPAPER_STYLES))

    def test_interval_keys_are_unique(self):
        # interval_map 是 标签->分钟 的映射，反向查找（collect）依赖取值唯一，
        # 否则会静默取到错的那个间隔。
        with IsolatedDataDir(), tk_root() as root:
            values = list(self._build(root).interval_map.values())
        self.assertEqual(len(values), len(set(values)))


class FixedHeightComboBoxSmokeTest(unittest.TestCase):
    def test_builds_with_values(self):
        from ui.fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a", "b", "c"], max_visible_items=2)
            self.assertFalse(combo.is_dropdown_open())

    def test_open_then_close_dropdown(self):
        from ui.fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a", "b", "c"])
            combo.pack()
            root.update_idletasks()
            combo._open_dropdown_menu()
            self.assertTrue(combo.is_dropdown_open())
            combo.close_dropdown()
            self.assertFalse(combo.is_dropdown_open())

    def test_close_when_not_open_is_safe(self):
        from ui.fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a"])
            combo.close_dropdown()
            self.assertFalse(combo.is_dropdown_open())

    def test_configure_values_closes_open_dropdown(self):
        from ui.fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=["a", "b"])
            combo.pack()
            root.update_idletasks()
            combo._open_dropdown_menu()
            combo.configure(values=["x", "y", "z"])
            self.assertFalse(combo.is_dropdown_open())

    def test_empty_values_do_not_open(self):
        from ui.fixed_combobox import FixedHeightComboBox
        with tk_root() as root:
            combo = FixedHeightComboBox(root, values=[])
            combo._open_dropdown_menu()
            self.assertFalse(combo.is_dropdown_open())

    def test_choosing_index_sets_value_and_fires_command(self):
        from ui.fixed_combobox import FixedHeightComboBox
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
    """FavoriteView 现在只依赖显式钩子，不再持有 WallpaperApp。"""

    def _hooks(self, applied=None, is_current=False):
        from ui.favorite_view import FavoriteViewHooks

        self.statuses = []
        self.behavior_changes = []
        self.refresh_requests = []
        self.applied_paths = []
        applied_result = True if applied is None else applied

        def on_apply(path):
            self.applied_paths.append(path)
            return applied_result

        return FavoriteViewHooks(
            set_status=lambda text, kind="ready": self.statuses.append((text, kind)),
            on_behavior_changed=self.behavior_changes.append,
            on_favorite_current=lambda: None,
            on_apply=on_apply,
            on_is_current=lambda path: is_current,
            on_refresh_requested=lambda: self.refresh_requests.append(True),
        )

    def _view(self, root, initial_behavior="pause", **hook_kwargs):
        from ui.favorite_view import FavoriteView
        tab = _ctk().CTkFrame(root)
        # FavoriteView.__init__ 只建控件；填充列表是 app.WallpaperApp 之后调用的
        view = FavoriteView(tab, self._hooks(**hook_kwargs), initial_behavior=initial_behavior)
        view.refresh()
        return view

    def test_builds_with_no_favorites(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._view(root)
            self.assertEqual(view.fav_combo_var.get(), "暂无收藏壁纸")
            self.assertEqual(view.current_selection(), "")
            self.assertEqual(view.collect()["favorite_behavior"], "pause")

    def test_refresh_lists_favorites_and_previews_first(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "saved.png")
            with tk_root() as root:
                view = self._view(root)
                self.assertEqual(view.fav_combo_var.get(), "saved.png")
                self.assertEqual(view.current_selection(), "saved.png")
                self.assertIsNotNone(view._preview_img, "预览图应当被加载")

    def test_preview_follows_selection(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "a.png", color="red")
            make_png(Path(base) / "Favorites" / "b.png", color="blue")
            with tk_root() as root:
                view = self._view(root)
                view.select("b.png")
                self.assertEqual(view.current_selection(), "b.png")
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
        from core.scheduler import resolve_favorite_behavior
        cfg = default_cfg(favorite_behavior=None, favorite_carousel=True)
        with IsolatedDataDir(), tk_root() as root:
            view = self._view(root, initial_behavior=resolve_favorite_behavior(cfg))
            self.assertEqual(view.favorite_behavior_var.get(), "carousel")

    def test_apply_asks_the_hook_and_reports_success(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "a.png")
            with tk_root() as root:
                view = self._view(root)
                self.assertTrue(view.apply_selected())
        self.assertEqual(len(self.applied_paths), 1)
        self.assertTrue(self.applied_paths[0].endswith("a.png"))

    def test_apply_failure_shows_an_error(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "a.png")
            with tk_root() as root:
                view = self._view(root, applied=False)
                with mock.patch("tkinter.messagebox.showerror") as error:
                    self.assertFalse(view.apply_selected())
                self.assertTrue(error.called)

    def test_apply_with_nothing_selected_warns(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._view(root)
            with mock.patch("tkinter.messagebox.showwarning") as warning:
                self.assertFalse(view.apply_selected())
            self.assertTrue(warning.called)
            self.assertEqual(self.applied_paths, [])

    def test_select_next_wraps_around(self):
        with IsolatedDataDir() as base:
            for name in ("a.png", "b.png"):
                make_png(Path(base) / "Favorites" / name)
            with tk_root() as root:
                view = self._view(root)
                self.assertEqual(view.current_selection(), "a.png")
                self.assertTrue(view.select_next())
                self.assertEqual(view.current_selection(), "b.png")
                self.assertTrue(view.select_next())
                self.assertEqual(view.current_selection(), "a.png")
        self.assertEqual(len(self.applied_paths), 2, "每次轮播都应请求应用")

    def test_select_next_without_favorites_returns_false(self):
        with IsolatedDataDir(), tk_root() as root:
            view = self._view(root)
            self.assertFalse(view.select_next())
        self.assertEqual(self.applied_paths, [])

    def test_behavior_change_is_reported_but_cfg_is_left_alone(self):
        # 视图不再自己写 cfg：写配置由 App 的 on_favorite_behavior_changed 负责
        with IsolatedDataDir(), tk_root() as root:
            view = self._view(root)
            view.favorite_behavior_var.set("carousel")
            view._mark_dirty()
        self.assertEqual(self.behavior_changes, ["carousel"])

    def test_delete_of_current_wallpaper_requests_a_refresh(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "a.png")
            with tk_root() as root:
                view = self._view(root, is_current=True)
                with mock.patch("tkinter.messagebox.askyesno", return_value=True):
                    self.assertTrue(view.delete_selected())
        self.assertEqual(self.refresh_requests, [True])
        self.assertEqual(self.statuses, [])

    def test_delete_of_other_wallpaper_reports_status(self):
        with IsolatedDataDir() as base:
            make_png(Path(base) / "Favorites" / "a.png")
            with tk_root() as root:
                view = self._view(root, is_current=False)
                with mock.patch("tkinter.messagebox.askyesno", return_value=True):
                    self.assertTrue(view.delete_selected())
        self.assertEqual(self.refresh_requests, [])
        self.assertEqual(self.statuses[-1], ("已删除收藏", "ready"))


class SourceManagerViewSmokeTest(unittest.TestCase):
    def _view(self, root, cfg=None, manager=None):
        from ui.source_manager_view import SourceManagerView
        cfg = default_cfg() if cfg is None else cfg
        changes = []
        statuses = []
        tab = _ctk().CTkFrame(root)
        # 回调契约：app.WallpaperApp._source_changed(save=False)，所以必须接受
        # save 关键字参数。
        view = SourceManagerView(
            tab, cfg, manager=manager,
            on_changed=lambda save=False: changes.append(save),
            on_status=lambda text, kind="ready": statuses.append((text, kind)),
        )
        return view, cfg, changes, statuses

    def test_injected_manager_is_reused(self):
        # WallpaperApp 把自己已经持有的 SourceManager 注入进来，避免在同一份 cfg
        # 上重复跑迁移，也避免两个实例各持一份状态。
        from services.sources import SourceManager
        cfg = default_cfg()
        manager = SourceManager(cfg)
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root, cfg, manager=manager)
            self.assertIs(view.manager, manager)

    def test_standalone_view_builds_its_own_manager(self):
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root)
            self.assertIsNotNone(view.manager)

    def test_lists_builtins_and_custom_sources(self):
        from services.sources import BUILTIN_SOURCES
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

    def test_editor_tracks_exactly_six_controls(self):
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root)
            self.assertEqual(len(view._editor_controls), 6)

    def test_builtin_disables_combos_too(self):
        # 旧实现只遍历 CTkEntry，site / size 两个下拉框在内置图源下仍可改，
        # 与"内置图源只读"的意图不符。
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root)
            view.select("all")
            combo_states = {
                view._site_combo.cget("state"),
                view._size_combo.cget("state"),
            }
            entry_states = {
                view._name_entry.cget("state"),
                view._url_entry.cget("state"),
                view._timeout_entry.cget("state"),
                view._retries_entry.cget("state"),
            }
        self.assertEqual(combo_states, {"disabled"})
        self.assertEqual(entry_states, {"disabled"})

    def test_custom_source_keeps_combos_readonly_not_free_text(self):
        # 可编辑时下拉框必须是 readonly：normal 会允许自由输入，
        # 用户就能把 {site}/{size} 填成列表以外的值。
        cfg = default_cfg()
        cfg["sources"] = [{"id": "custom_1", "name": "我的源", "url": "https://e.com/r",
                           "site": "all", "size": "pc", "timeout": 15, "retries": 3,
                           "enabled": True, "builtin": False}]
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root, cfg)
            view.select("custom_1")
            self.assertEqual(view._site_combo.cget("state"), "readonly")
            self.assertEqual(view._size_combo.cget("state"), "readonly")
            self.assertEqual(view._name_entry.cget("state"), "normal")

    def test_editor_state_does_not_leak_outside_the_editor(self):
        # 这是本次修复的核心：原来递归遍历整棵 self.parent 子树去禁用所有
        # CTkEntry，图源列表卡片里只要出现输入框就会被一起禁用。
        ctk = _ctk()
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, _ = self._view(root)
            # 该容器已经用 grid 布局，这里也必须用 grid
            outsider = ctk.CTkEntry(view.parent)
            outsider.grid(row=9, column=0)
            view.select("all")
            self.assertEqual(outsider.cget("state"), "normal", "编辑器以外的输入框不应被改动")
            self.assertEqual(view._name_entry.cget("state"), "disabled")

    def test_new_source_clears_editor(self):
        with IsolatedDataDir(), tk_root() as root:
            view, _, _, statuses = self._view(root)
            view.select("all")
            view.new_source()
            self.assertEqual(view.edit_name.get(), "")
            self.assertEqual(view.edit_url.get(), "")
            self.assertEqual(view.edit_timeout.get(), "15")
            self.assertEqual(view._name_entry.cget("state"), "normal")
            self.assertEqual(view._site_combo.cget("state"), "readonly")
        self.assertEqual(statuses[-1][1], "ready")

    def test_saving_while_a_builtin_is_selected_is_refused(self):
        # 不加闸的话会以该内置源的 id 往 cfg["sources"] 里塞一条自定义图源，
        # 而 SourceManager.get() 先查内置表，于是它永远取不到，只会制造重复 id。
        with IsolatedDataDir(), tk_root() as root:
            view, cfg, changes, _ = self._view(root)
            view.select("all")
            notifications_before = len(changes)
            with mock.patch("tkinter.messagebox.showinfo") as info:
                view.save()
            self.assertEqual(cfg["sources"], [], "内置图源下保存不应产生任何自定义图源")
            self.assertTrue(info.called, "应当提示用户内置图源不能修改")
            self.assertEqual(len(changes), notifications_before, "被拒绝时不应触发 on_changed")

    def test_saving_a_custom_source_still_works(self):
        with IsolatedDataDir(), tk_root() as root:
            view, cfg, _, _ = self._view(root)
            view.new_source()
            view.edit_name.set("新源")
            view.edit_url.set("https://new.example/r")
            view.save()
            names = [s["name"] for s in cfg["sources"]]
        self.assertEqual(names, ["新源"])

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
