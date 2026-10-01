"""服务层：与外部世界打交道的能力（Windows、网络、文件系统）。

与界面层的约定：本包**不得**导入 tkinter / customtkinter，
tests/test_layering.py 会守住这条规则。

* ``wallpaper_win``    桌面壁纸读写（Win32 + 注册表显示方式）
* ``images``           把图源返回的字节解释成图片
* ``downloader``       网络抓取与多图源回退
* ``wallpaper_worker`` 后台下载线程（结果走队列，不碰界面）
* ``cache``            下载缓存的落盘、统计与清理
* ``favorites``        收藏夹读写
* ``sources``          图源的增删改、排序、启用状态与配置迁移
* ``autostart``        开机自启（注册表）
* ``single_instance``  单实例锁（命名互斥体）
"""
