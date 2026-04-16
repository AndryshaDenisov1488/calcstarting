# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

# Каталог, где лежит этот .spec (корень проекта при запуске из него)
_spec_dir = os.path.dirname(os.path.abspath(SPEC))

datas = [
    (os.path.join(_spec_dir, "assets", "app_logo.jpg"), "assets"),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all("PySide6")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# reportlab / pypdf / dbfread подтягиваются как зависимости; при «No module» добавить в hiddenimports
hiddenimports += [
    "dbfread",
    "dbfread.field_parser",
    "reportlab",
    "pypdf",
]

a = Analysis(
    [os.path.join(_spec_dir, "calcfs_pdf_export", "__main__.py")],
    pathex=[_spec_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="CalcFSPdfExport",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(_spec_dir, "assets", "app_icon.ico"),
)
