# THW — 东方壁纸自动更换器

一个运行在 Windows 托盘的小工具：定时从多图源随机获取东方（Touhou）壁纸并自动更换桌面壁纸，支持星标收藏喜欢的壁纸、为收藏夹提供轮播与预览、自定义图源以及全局快捷键。

## 功能特性

- 🖼️ **多图源支持**：内置多个东方 Project 随机图源，支持用户**自定义添加**图源，并可独立配置超时与重试参数
- 🎯 **智能回退**：当前图源失败时自动切换到其他启用的图源，保证换壁纸不中断
- 🖼️ **壁纸显示方式**：支持填充 / 适应 / 居中 / 拉伸四种桌面显示方式（通过注册表设置）
- ⭐ **星标收藏**：收藏当前壁纸，可在收藏时**重命名**，并可在 UI 中**预览**已收藏的壁纸
- 🔁 **星标轮播**：开启后按设定的间隔在收藏夹内自动循环切换壁纸（此时不再拉取在线壁纸）
- ⌨️ **全局快捷键**：为「收藏当前壁纸」「切换在线壁纸」自定义全局快捷键（默认不设置，需自行填写）
- 🗔 **最小化到托盘**：关闭窗口不退出，常驻托盘随时可唤出
- 🔒 **单实例**：使用全局互斥锁确保程序只运行一个实例，重复启动时提示并退出
- ♻️ **退出还原**：退出时自动还原系统最初的原壁纸
- 🧹 **缓存管理**：自动清理旧缓存并保护当前壁纸，可手动清理缓存释放空间
- 📦 **图源管理**：可视化管理自定义图源，支持拖拽排序优先级、启用/禁用、在线测试

## 安装与运行

需要 Python 3.8+，仅支持 Windows。

```bash
pip install -r requirements.txt
python wallpaper_changer.py
```

以静默方式启动（直接最小化到托盘）：

```bash
python wallpaper_changer.py --silent
```

## 项目结构

分层规则：**core → services → ui → app**，箭头永不反向。
`tests/test_layering.py` 会自动检查这条规则、以及"core 与 services 不得依赖界面工具包"。

```
wallpaper_changer.py   入口：参数解析、单实例检查、全局外观、启动主窗口

app.py                 编排层：生命周期、下载调度、托盘与视图之间的协调
                       （本身不含任何 tkinter 依赖——弹窗走 ui.dialogs，控件在 ui.main_window）

core/                  纯逻辑与本地配置，不依赖界面工具包
  paths.py               数据目录（APP_DIR / Favorites / Cache / config.json）
  config_store.py        配置文件的读写
  constants.py           共享常量（图片扩展名、壁纸显示方式）
  scheduler.py           定时策略：间隔、收藏暂停、失败退避、倒计时文案

services/              与外部世界打交道的能力
  wallpaper_win.py       桌面壁纸读写（Win32 + 注册表显示方式）
  images.py              把图源返回的字节解释成图片
  downloader.py          网络抓取与多图源回退
  wallpaper_worker.py    后台下载线程（结果走队列，不碰界面）
  cache.py               下载缓存的落盘、统计与清理
  favorites.py           收藏夹读写
  sources.py             图源的增删改、排序、启用状态与配置迁移
  autostart.py           开机自启（注册表）
  single_instance.py     单实例锁（命名互斥体）

ui/                    所有 CustomTkinter 控件
  theme.py               全局外观与共享字体/配色
  widgets.py             共享小控件（卡片、打开目录）
  status_bar.py          状态栏与未捕获回调异常的呈现
  main_window.py         主窗口外壳：顶栏、动作按钮、标签页、底栏
  settings_view.py       设置面板：自动轮播、壁纸显示、缓存管理、全局快捷键
  source_manager_view.py 图源管理器：列表、拖拽排序、启用/禁用、编辑、测试
  favorite_view.py       收藏面板：收藏管理、预览、收藏轮播
  fixed_combobox.py      收藏选择框：固定高度（最多 8 项）的可滚动下拉列表
  tray.py                系统托盘图标与菜单
  hotkeys.py             全局快捷键注册
  dialogs.py             弹窗与收藏命名对话框

tests/                 单元测试（标准库 unittest，无需额外安装）
```

## 开发

跑测试：

```bash
python -m unittest discover -s tests -t .
```

测试不需要额外安装任何东西（用标准库 `unittest` 写成，`pytest` 也能直接收集）。
测试把数据目录重定向到项目下的 `.test-tmp/`，**不会**碰到 `%APPDATA%` 里的真实
配置、收藏与缓存；托盘图标、全局热键、弹窗、下载线程也都用替身顶掉了。

依赖说明：`customtkinter` 在 `requirements.txt` 里是**精确锁定**的版本。
`ui/fixed_combobox.py` 依赖 `CTkComboBox` 的一批私有属性、`ui/dialogs.py` 依赖
`CTkInputDialog._entry`，升级 CustomTkinter 前请先跑一遍测试——
`tests/test_ui_smoke.py` 里的 `FixedHeightComboBoxSmokeTest` 会真的展开一次下拉列表。

## 使用方法

### 界面操作

- **自动轮播设置**：设置启动时是否立即刷新一次、是否开机自启，以及定时刷新间隔（支持 5 分钟 ~ 4 小时，可选"不自动定时"）。
- **图源管理**：
  - 内置图源可直接点击「使用」切换当前源；
  - 自定义图源可添加/编辑/删除，支持拖拽排序调整优先级；
  - 每个图源可独立配置超时（5-60 秒）和重试次数（1-5 次）；
  - 关闭启用开关后，该图源不会作为自动回退图源；
  - 图源支持：直接返回图片、302 跳转图片，或返回 `{"url": "图片地址"}` 的 JSON 响应。
- **壁纸显示**：支持填充 / 适应 / 居中 / 拉伸四种方式，切换后立即生效。
- **星标收藏夹管理**：
  - 「⭐ 收藏当前壁纸」：收藏桌面当前壁纸，弹出对话框可为壁纸命名；
  - 「定时轮播星标壁纸」：勾选后按设置间隔自动在收藏夹内切换；
  - 下拉框选择收藏项后，下方会显示该壁纸的**预览图**；收藏再多，下拉列表也只显示固定高度（最多 8 项），其余项目滚动查看，列表宽度与上方控件对齐；
  - 「应用选中的星标壁纸」：锁定使用该壁纸（在线轮播暂停，除非开启星标轮播）；
  - 「🗑️ 取消星标」：取消星标并从本地删除图片文件。
- **缓存管理**：显示缓存图片数量/占用空间，可手动清理缓存，并保护当前正在使用的壁纸。
- **全局快捷键**：在输入框中填写快捷键（例如 `ctrl+shift+s` / `ctrl+shift+f`），点击「保存设置」后生效。留空表示不注册。

### 托盘菜单

右键托盘图标可：打开设置界面、换一张在线壁纸、收藏当前壁纸、退出并还原壁纸。

## 配置说明

程序数据保存在 `%APPDATA%\TouhouWallpaper` 下：

| 文件/目录 | 说明 |
| --- | --- |
| `config.json` | 程序配置（自动轮播间隔、图源、快捷键、星标轮播开关、自定义图源列表等） |
| `Favorites/` | 星标收藏的壁纸图片 |
| `Cache/` | 下载的壁纸缓存（自动限制数量，保护当前使用壁纸） |

## 打包为 exe（推荐）

```bash
pip install pyinstaller
pyinstaller thw.spec
```

生成的 `dist/thw.exe` 可独立运行（无控制台窗口）。
`thw.spec` 已纳入版本管理，改动入口或新增依赖时请一并更新它。

## 注意事项

- 依赖 `keyboard` 库实现全局快捷键，若安装后快捷键无效，请尝试**以管理员身份运行**。
- 图源 URL 模板支持 `{size}` 和 `{site}` 两个占位符，例如 `https://example.com/random?size={size}&site={site}`。
- 本项目基于个人兴趣制作，不对使用效果与接口稳定性负责。
- 本项目使用 vibe coding。

## 致谢
本项目中的东方 Project 相关图片素材，通过 东方 Project 随机图片 [API](https://img.paulzzh.com) 获取。**感谢该 API 的维护者**。
