# PyInstaller build for Fastype.app. Run scripts/bundle.sh rather than this directly.
# -*- mode: python -*-

a = Analysis(
    ["scripts/launcher.py"],
    pathex=["src"],
    datas=[("src/fastype/assets/icon.png", "fastype/assets"),
           ("src/fastype/data/*.txt", "fastype/data")],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtPdf", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Fastype", console=False,
          argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Fastype")
app = BUNDLE(
    coll,
    name="Fastype.app",
    icon="assets/Fastype.icns",
    bundle_identifier="com.bogdanmitrea.fastype",
    version="0.2.0",
    info_plist={
        "CFBundleDisplayName": "Fastype",
        "CFBundleShortVersionString": "0.2.0",
        "LSApplicationCategoryType": "public.app-category.education",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
