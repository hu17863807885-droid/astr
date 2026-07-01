# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).resolve()


a = Analysis(
    [str(ROOT / "oa_review_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["astropy", "numpy", "pandas", "matplotlib"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OA_Review",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OA_Review",
)
app = BUNDLE(
    coll,
    name="OA_Review.app",
    icon=None,
    bundle_identifier="org.astronaut.oa-review",
    info_plist={
        "CFBundleDisplayName": "OA Review",
        "NSHighResolutionCapable": True,
    },
)
