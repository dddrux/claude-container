# -*- mode: python ; coding: utf-8 -*-
# PyInstaller (onedir) para Linux x64 e Windows x64. Uso: pyinstaller --noconfirm --clean claude-containers.spec
import sys

win = sys.platform == "win32"
a = Analysis(
    ["main.py"],
    datas=[("assets/icon.png", "assets")],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="claude-containers",
    console=False,
    icon="assets/icon.ico" if win else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="claude-containers")
