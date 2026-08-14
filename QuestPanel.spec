# PyInstaller spec for QuestPanel.
#
#   pyinstaller QuestPanel.spec --noconfirm
#
# Produces dist/QuestPanel/QuestPanel.exe (onedir -- starts noticeably faster
# than onefile, which re-extracts to a temp dir on every launch).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
ROOT = Path(SPECPATH)

# assets/ ships alongside the executable; app/core/paths.py resolves it via
# sys._MEIPASS when frozen. Empty asset folders are kept so users can drop in
# their own audio/icons next to the exe.
datas = [
    (str(ROOT / "assets"), "assets"),
]

# Qt Multimedia backends are loaded dynamically and are easy to miss.
hiddenimports = [
    "PySide6.QtMultimedia",
]

excludes = [
    "tkinter", "unittest", "pydoc", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtDesigner",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtHelp", "PySide6.QtSerialPort", "PySide6.QtOpenGL",
]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QuestPanel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # no console window -- this is a desktop widget
    disable_windowed_traceback=False,
    icon=str(ROOT / "build" / "questpanel.ico")
    if (ROOT / "build" / "questpanel.ico").is_file()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="QuestPanel",
)
