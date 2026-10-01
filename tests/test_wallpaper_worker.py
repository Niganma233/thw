"""services.wallpaper_worker：多图源回退的下载 worker。

下载与应用都注入假实现，因此不碰网络、也不碰真实桌面。
"""
import queue
import unittest

from services.wallpaper_worker import (
    EVENT_ERROR,
    EVENT_SUCCESS,
    MAX_REPORTED_ERRORS,
    NO_CANDIDATES_MESSAGE,
    THREAD_NAME,
    WallpaperDownloadWorker,
)


def source(source_id, name=None):
    return {"id": source_id, "name": name or f"源 {source_id}", "url": f"https://e.com/{source_id}"}


class RunTest(unittest.TestCase):
    """直接同步跑 _run，避免线程带来的不确定性。"""

    def _worker(self, download, apply=None):
        events = queue.Queue()
        worker = WallpaperDownloadWorker(events, download=download, apply=apply or (lambda path: True))
        return worker, events

    def test_first_candidate_wins_and_stops(self):
        tried = []

        def download(src):
            tried.append(src["id"])
            return f"/cache/{src['id']}.png"

        worker, events = self._worker(download)
        worker._run([source("a"), source("b")])
        self.assertEqual(tried, ["a"], "第一个图源成功后不应继续尝试")
        self.assertEqual(events.get_nowait(), (EVENT_SUCCESS, "/cache/a.png", "a", "源 a"))

    def test_falls_through_to_next_candidate(self):
        tried = []

        def download(src):
            tried.append(src["id"])
            if src["id"] == "a":
                raise OSError("网络断了")
            return "/cache/b.png"

        worker, events = self._worker(download)
        worker._run([source("a"), source("b")])
        self.assertEqual(tried, ["a", "b"])
        self.assertEqual(events.get_nowait(), (EVENT_SUCCESS, "/cache/b.png", "b", "源 b"))

    def test_all_failures_are_reported(self):
        def download(src):
            raise OSError(f"{src['id']} 失败")

        worker, events = self._worker(download)
        worker._run([source("a"), source("b")])
        event = events.get_nowait()
        self.assertEqual(event[0], EVENT_ERROR)
        self.assertIn("源 a", event[1])
        self.assertIn("源 b", event[1])
        self.assertIn("a 失败", event[1])

    def test_error_message_is_capped(self):
        def download(src):
            raise OSError("失败")

        worker, events = self._worker(download)
        worker._run([source(str(index)) for index in range(6)])
        message = events.get_nowait()[1]
        self.assertEqual(len(message.splitlines()), MAX_REPORTED_ERRORS)

    def test_apply_returning_false_is_treated_as_failure(self):
        # SystemParametersInfoW 返回 0 时不会抛异常，只是返回 False；
        # 这种"没报错但也没成功"必须当成失败继续回退。
        def apply(path):
            return path != "/cache/a.png"

        worker, events = self._worker(lambda src: f"/cache/{src['id']}.png", apply=apply)
        worker._run([source("a"), source("b")])
        self.assertEqual(events.get_nowait(), (EVENT_SUCCESS, "/cache/b.png", "b", "源 b"))

    def test_apply_exception_is_treated_as_failure(self):
        def apply(path):
            raise RuntimeError("注册表被拒")

        worker, events = self._worker(lambda src: f"/cache/{src['id']}.png", apply=apply)
        worker._run([source("a")])
        event = events.get_nowait()
        self.assertEqual(event[0], EVENT_ERROR)
        self.assertIn("注册表被拒", event[1])

    def test_empty_candidate_list_reports_a_readable_error(self):
        worker, events = self._worker(lambda src: "/cache/x.png")
        worker._run([])
        self.assertEqual(events.get_nowait(), (EVENT_ERROR, NO_CANDIDATES_MESSAGE))


class StartTest(unittest.TestCase):
    def test_start_runs_in_a_named_daemon_thread(self):
        events = queue.Queue()
        worker = WallpaperDownloadWorker(
            events, download=lambda src: "/cache/a.png", apply=lambda path: True
        )
        thread = worker.start([source("a")])
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(thread.daemon, "下载线程必须是 daemon，否则退出时会被卡住")
        self.assertEqual(thread.name, THREAD_NAME)
        self.assertEqual(events.get_nowait()[0], EVENT_SUCCESS)

    def test_candidates_are_snapshotted(self):
        # 传入的列表在后台线程启动后不应再被外部改动影响
        events = queue.Queue()
        seen = []
        worker = WallpaperDownloadWorker(
            events, download=lambda src: seen.append(src["id"]) or "/cache/a.png", apply=lambda path: True
        )
        candidates = [source("a")]
        thread = worker.start(candidates)
        candidates.append(source("b"))
        thread.join(timeout=5)
        self.assertEqual(seen, ["a"])


if __name__ == "__main__":
    unittest.main()
