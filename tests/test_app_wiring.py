"""整机装配冒烟测试：真的构造一次 ``WallpaperApp``。

这是唯一能一次性验证「所有视图的构造参数、回调契约、共享实例都对得上」的测试——
单独构建某个视图是发现不了 ``SourceManagerView(..., manager=...)`` 这类装配错误的。

所有外部副作用都打了桩：壁纸读写、托盘图标、全局热键、定时器循环、写配置、
开机自启注册表，因此不会真的换壁纸、注册热键或碰注册表。
"""
import json
import time
import unittest
import unittest.mock as mock

import wallpaper_service
from tests.helpers import IsolatedDataDir, config, tk_root


class AppWiringTest(unittest.TestCase):
    def _construct(self, root, prefs=None):
        """在打桩环境下构造 WallpaperApp，返回 (app, 打桩记录)。"""
        import gui

        if prefs:
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as handle:
                json.dump(prefs, handle, ensure_ascii=False)

        with mock.patch.object(wallpaper_service, "get_current_windows_wallpaper", return_value=""), \
                mock.patch.object(gui.WallpaperApp, "init_tray_icon") as tray, \
                mock.patch.object(gui.WallpaperApp, "register_hotkeys") as hotkeys, \
                mock.patch.object(gui.WallpaperApp, "timer_loop") as timer, \
                mock.patch.object(gui.WallpaperApp, "fetch_and_set_wallpaper") as fetch, \
                mock.patch.object(gui.WallpaperApp, "_warn_if_data_dir_readonly"), \
                mock.patch.object(config, "save_config"):
            app = gui.WallpaperApp(root)
        return app, {"tray": tray, "hotkeys": hotkeys, "timer": timer, "fetch": fetch}

    def test_all_views_are_constructed(self):
        with IsolatedDataDir(), tk_root() as root:
            app, _ = self._construct(root)
            self.assertIsNotNone(app.settings_view)
            self.assertIsNotNone(app.source_view)
            self.assertIsNotNone(app.favorite_view)

    def test_source_manager_instance_is_shared_with_view(self):
        # Phase 1：图源管理器只建一个实例，由 app 持有并注入视图，
        # 避免在同一份 cfg 上重复跑 migrate_legacy。
        with IsolatedDataDir(), tk_root() as root:
            app, _ = self._construct(root)
            self.assertIs(app.source_view.manager, app.source_manager)

    def test_tray_and_hotkeys_are_initialised(self):
        with IsolatedDataDir(), tk_root() as root:
            _, mocks = self._construct(root)
        mocks["tray"].assert_called_once()
        mocks["hotkeys"].assert_called_once()

    def test_timer_loop_is_started(self):
        with IsolatedDataDir(), tk_root() as root:
            _, mocks = self._construct(root)
        mocks["timer"].assert_called_once()

    def test_startup_fetch_happens_by_default(self):
        with IsolatedDataDir(), tk_root() as root:
            _, mocks = self._construct(root)
        mocks["fetch"].assert_called_once()

    def test_startup_fetch_can_be_disabled(self):
        with IsolatedDataDir(), tk_root() as root:
            _, mocks = self._construct(root, prefs={"refresh_on_startup": False})
        mocks["fetch"].assert_not_called()

    def test_status_starts_ready(self):
        with IsolatedDataDir(), tk_root() as root:
            app, _ = self._construct(root)
            self.assertEqual(app.status.var.get(), "在线轮播就绪")
            self.assertEqual(app.status.text, "在线轮播就绪")

    def test_favorite_view_is_populated_on_startup(self):
        with IsolatedDataDir(), tk_root() as root:
            app, _ = self._construct(root)
            self.assertEqual(app.favorite_view.fav_combo_var.get(), "暂无收藏壁纸")

    def test_source_view_reflects_configured_selection(self):
        with IsolatedDataDir(), tk_root() as root:
            app, _ = self._construct(root, prefs={"source_id": "yandere"})
            self.assertEqual(app.source_view.selected_id, "yandere")

    def test_initial_deadline_follows_interval(self):
        with IsolatedDataDir(), tk_root() as root:
            app, _ = self._construct(root, prefs={"interval_minutes": 45})
            remaining = app.scheduler.next_refresh_time - time.time()
            self.assertGreater(remaining, 44 * 60)
            self.assertLessEqual(remaining, 45 * 60)

    def test_apply_settings_wires_both_views_into_cfg(self):
        # 顺带验证 settings_view.collect() / favorite_view.collect() 返回的键
        # 与 cfg 键位对得上——apply_settings 是把它们直接 update 进 cfg 的。
        with IsolatedDataDir(), tk_root() as root:
            app, _ = self._construct(root)
            known_keys = set(config.DEFAULT_CONFIG)
            self.assertTrue(set(app.settings_view.collect()) <= known_keys)
            self.assertTrue(set(app.favorite_view.collect()) <= known_keys)

            with mock.patch.object(config, "save_config") as save, \
                    mock.patch.object(config, "set_auto_start_registry") as registry, \
                    mock.patch.object(wallpaper_service, "set_wallpaper_style") as style, \
                    mock.patch.object(type(app), "register_hotkeys"), \
                    mock.patch("tkinter.messagebox.showinfo"):
                self.assertTrue(app.apply_settings())

        save.assert_called_once()
        registry.assert_called_once()
        style.assert_called_once()


if __name__ == "__main__":
    unittest.main()
