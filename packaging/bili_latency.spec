# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one windowed executable, no console window.

Build with:  pyinstaller packaging/bili_latency.spec --noconfirm
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ICON_ICO = ROOT / "assets" / "icon.ico"
ICON_PNG = ROOT / "assets" / "icon.png"

# Qt modules the app never touches; excluding them keeps the download small.
EXCLUDES = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtOpenGLWidgets", "PySide6.QtSerialPort",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "tkinter", "unittest", "pydoc_data", "test",
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=["bili_latency", "bili_latency.app", "bili_latency.cli"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BiliLatencyMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # no console window: this is a desktop app
    disable_windowed_traceback=False,
    icon=str(ICON_ICO if sys.platform.startswith("win") else ICON_PNG),
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="BiliLatencyMonitor.app",
        icon=str(ICON_PNG),
        bundle_identifier="com.bili-latency-monitor",
        info_plist={
            "LSUIElement": True,          # menu-bar app, no dock icon
            "NSHighResolutionCapable": True,
        },
    )
