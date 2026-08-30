import sys
import ctypes
import atexit
import tkinter as tk
from tkinter import messagebox

import config
from gui import WallpaperApp

# 单实例锁
_INSTANCE_LOCK_HANDLE = None


def acquire_single_instance_lock():
    """创建全局互斥锁保证程序单实例运行；已有实例返回 False"""
    global _INSTANCE_LOCK_HANDLE
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    mutex_name = "Global\\TouhouWallpaperAutoChanger"
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    error = kernel32.GetLastError()
    if error == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return False
    _INSTANCE_LOCK_HANDLE = handle
    return True


def _release_single_instance_lock():
    """释放单实例互斥锁"""
    global _INSTANCE_LOCK_HANDLE
    if _INSTANCE_LOCK_HANDLE:
        ctypes.windll.kernel32.CloseHandle(_INSTANCE_LOCK_HANDLE)
        _INSTANCE_LOCK_HANDLE = None


atexit.register(_release_single_instance_lock)


def main():
    is_silent = "--silent" in sys.argv

    # 单实例锁：已有实例在运行时直接退出
    if not acquire_single_instance_lock():
        if not is_silent:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("提示", "程序已在运行中！")
            root.destroy()
        sys.exit(0)

    root = tk.Tk()
    app = WallpaperApp(root, silent=is_silent)
    root.mainloop()


if __name__ == "__main__":
    main()
