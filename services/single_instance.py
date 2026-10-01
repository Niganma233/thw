"""单实例锁：用命名互斥体保证同时只跑一个程序。

从 wallpaper_changer.py 里搬出来，让入口只剩下参数解析与装配。
"""
import atexit
import ctypes

MUTEX_NAME = "Global\\TouhouWallpaperAutoChanger"
ERROR_ALREADY_EXISTS = 183

_handle = None


def acquire():
    """尝试取得单实例锁。已在运行则返回 False。"""
    global _handle
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.GetLastError.restype = ctypes.c_ulong

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle or kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        if handle:
            kernel32.CloseHandle(handle)
        return False
    _handle = handle
    return True


def release():
    """释放单实例锁（幂等）。"""
    global _handle
    if _handle:
        ctypes.windll.kernel32.CloseHandle(_handle)
        _handle = None


# 进程退出时兜底释放，避免异常退出把锁留在那里
atexit.register(release)
