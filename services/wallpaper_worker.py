"""后台下载壁纸：按候选图源顺序尝试，失败就换下一个。

只负责"把结果放进队列"，不碰界面——调用方在自己的线程里排空队列并更新 UI。
下载与应用壁纸都可以注入，因此不需要网络或真实桌面就能测试整条回退链路。
"""
import threading

from services import downloader, wallpaper_win

# 队列事件类型
EVENT_SUCCESS = "success"
EVENT_ERROR = "error"

# 全部图源都失败时最多回报几条错误，避免状态栏被刷屏
MAX_REPORTED_ERRORS = 3

THREAD_NAME = "wallpaper-download"
APPLY_FAILED_MESSAGE = "Windows 没有成功应用壁纸"
NO_CANDIDATES_MESSAGE = "没有可用的图源"


class WallpaperDownloadWorker:
    def __init__(self, event_queue, download=None, apply=None):
        self._queue = event_queue
        self._download = download or downloader.download_wallpaper
        self._apply = apply or wallpaper_win.set_wallpaper_windows

    def start(self, candidates):
        """起一个后台线程依次尝试 ``candidates``，结果以队列事件回传。

        事件格式：
            ("success", 落盘路径, 图源 id, 图源名)
            ("error", 错误摘要)
        """
        thread = threading.Thread(
            target=self._run, args=(list(candidates),), name=THREAD_NAME, daemon=True
        )
        thread.start()
        return thread

    def _run(self, candidates):
        if not candidates:
            # 正常路径下调用方已经挡掉了空候选，这里只是别让状态栏出现空错误
            self._queue.put((EVENT_ERROR, NO_CANDIDATES_MESSAGE))
            return
        errors = []
        for source in candidates:
            try:
                path = self._download(source)
                if not self._apply(path):
                    raise RuntimeError(APPLY_FAILED_MESSAGE)
                self._queue.put((EVENT_SUCCESS, path, source["id"], source["name"]))
                return
            except Exception as exc:
                errors.append(f"{source['name']}: {exc}")
        self._queue.put((EVENT_ERROR, "\n".join(errors[:MAX_REPORTED_ERRORS])))
