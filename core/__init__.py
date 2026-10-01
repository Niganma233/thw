"""核心层：纯逻辑与本地配置。

这一层不依赖 tkinter / customtkinter，也不做网络请求、不碰注册表。

* ``paths``        数据目录在哪
* ``config_store`` 配置文件的读写
* ``constants``    跨模块共享的常量
* ``scheduler``    换壁纸的定时策略（纯逻辑，时间由调用方传入）
"""
