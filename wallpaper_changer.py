import atexit
import ctypes
import sys
from tkinter import messagebox

import customtkinter as ctk
from gui import WallpaperApp

_INSTANCE_LOCK_HANDLE = None


def acquire_single_instance_lock():
    global _INSTANCE_LOCK_HANDLE
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.GetLastError.restype = ctypes.c_ulong
    handle = kernel32.CreateMutexW(None, False, "Global\\TouhouWallpaperAutoChanger")
    if not handle or kernel32.GetLastError() == 183:
        if handle:
            kernel32.CloseHandle(handle)
        return False
    _INSTANCE_LOCK_HANDLE = handle
    return True


def release_single_instance_lock():
    global _INSTANCE_LOCK_HANDLE
    if _INSTANCE_LOCK_HANDLE:
        ctypes.windll.kernel32.CloseHandle(_INSTANCE_LOCK_HANDLE)
        _INSTANCE_LOCK_HANDLE = None


atexit.register(release_single_instance_lock)


def main():
    silent = "--silent" in sys.argv
    if not acquire_single_instance_lock():
        if not silent:
            root = ctk.CTk()
            root.withdraw()
            messagebox.showinfo("Touhou Wallpaper", "程序已经在运行中。")
            root.destroy()
        return
    root = ctk.CTk()
    WallpaperApp(root, silent=silent)
    root.mainloop()


if __name__ == "__main__":
    main()
