# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

    pip install pyinstaller
    pyinstaller thw.spec

入口是 wallpaper_changer.py；core / services / ui 三个包会被自动分析到。
生成的 dist/thw.exe 可独立运行（无控制台窗口）。
"""

a = Analysis(
    ['wallpaper_changer.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # pystray 的后端是运行时按平台选择的，显式声明更稳妥
    hiddenimports=['pystray._win32'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='thw',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # 窗口化程序：不能有控制台窗口，否则 --silent 开机自启会闪黑框
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
