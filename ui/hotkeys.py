"""全局快捷键的注册与注销。

把对 ``keyboard`` 库的依赖收在一个地方：该库只支持 Windows 且需要管理员权限才能
可靠工作，未安装时 ``keyboard is None``，此时一切注册/注销都静默跳过。
"""
try:
    import keyboard
except ImportError:  # pragma: no cover - 取决于运行环境
    keyboard = None


class HotkeyManager:
    """按 (快捷键文本, 回调, 名称) 注册全局快捷键。

    回调跑在 keyboard 自己的监听线程里，所以统一用 ``root.after(0, ...)``
    切回 Tk 主线程——Tk 控件只能从主线程操作。
    """

    def __init__(self, root, on_error=None):
        self._root = root
        self._on_error = on_error or (lambda text: None)

    @property
    def available(self):
        return keyboard is not None

    def register(self, bindings):
        """注册快捷键，返回真正注册成功的文本列表。

        注册前会先注销旧的，因此可以反复调用（保存设置时就是这么做的）。
        """
        if keyboard is None:
            return []
        self.unregister()
        registered = []
        for hotkey_text, callback, label in bindings:
            hotkey_text = (hotkey_text or "").strip()
            if not hotkey_text:
                continue
            try:
                keyboard.add_hotkey(hotkey_text, self._marshal(callback))
                registered.append(hotkey_text)
            except Exception as exc:
                self._on_error(f"{label}快捷键无效：{exc}")
        return registered

    def unregister(self):
        """注销全部快捷键；退出时调用。"""
        if keyboard is None:
            return
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

    def _marshal(self, callback):
        def run_in_main_thread():
            self._root.after(0, callback)

        return run_in_main_thread
