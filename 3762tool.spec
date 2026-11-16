# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：376.2 协议解析工具（onedir）
a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=['qgdw3762', 'app_svc', 'gui'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='376.2协议解析工具',
    debug=False,
    upx=False,
    console=False,
    icon='resources/icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='376.2协议解析工具',
)
