"""系统托盘图标与右键菜单。

图标是代码画出来的（不依赖外部图片资源），菜单项由调用方给出。
"""
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

ICON_NAME = "TouhouWallpaper"
DEFAULT_TITLE = "Touhou Wallpaper"

# 图标尺寸与配色
ICON_SIZE = 64
CIRCLE_FILL = "#3b82f6"
CIRCLE_OUTLINE = "#2563eb"
CIRCLE_WIDTH = 2
# 两座"山"的顶点，画成东方风格的小图标
MOUNTAIN_SHAPES = (
    ((16, 44), (28, 22), (40, 44)),
    ((34, 44), (44, 30), (52, 44)),
)


def create_tray_image():
    """画一个 64x64 的托盘图标。"""
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = 4
    draw.ellipse(
        [margin, margin, ICON_SIZE - margin, ICON_SIZE - margin],
        fill=CIRCLE_FILL,
        outline=CIRCLE_OUTLINE,
        width=CIRCLE_WIDTH,
    )
    for shape in MOUNTAIN_SHAPES:
        draw.polygon(shape, fill="white")
    return image


class TrayController:
    """管理托盘图标：启动、停止、把菜单回调切回主线程。"""

    def __init__(self, root, title=DEFAULT_TITLE):
        self._root = root
        self._title = title
        self._icon = None

    @property
    def running(self):
        return self._icon is not None

    def start(self, handlers):
        """显示托盘图标。

        ``handlers`` 是 ``[(菜单标签, 回调), ...]``；第一项作为默认项
        （左键单击/双击托盘时触发）。
        """
        menu = tuple(
            item(label, self._marshal(callback), default=(index == 0))
            for index, (label, callback) in enumerate(handlers)
        )
        self._icon = pystray.Icon(ICON_NAME, create_tray_image(), self._title, menu)
        self._icon.run_detached()
        return self._icon

    def stop(self):
        """移除托盘图标；重复调用是安全的。"""
        icon, self._icon = self._icon, None
        if icon is None:
            return
        try:
            icon.stop()
        except Exception:
            pass

    def _marshal(self, callback):
        # 托盘回调跑在 pystray 自己的线程里，必须切回 Tk 主线程
        return lambda: self._root.after(0, callback)
