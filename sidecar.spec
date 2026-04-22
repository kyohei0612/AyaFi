# PyInstaller spec for the AyaFi Python sidecar.
#
# Builds a single `dist/sidecar.exe` that the Tauri shell spawns in release
# mode (replacing the dev-time `python scripts/sidecar.py`). Dev mode is
# untouched — this spec is only consumed when we actually ship.
#
# Usage: .venv/Scripts/python -m PyInstaller sidecar.spec  (from repo root)
#
# Hidden imports: anything imported dynamically (pydantic v2 model parsers,
# optional LLM SDKs, atproto's lazy registry) so PyInstaller's static
# analyzer doesn't drop them.

# mypy: ignore-errors
# ruff: noqa
# pyright: ignore
# fmt: off
# type: ignore
# type: ignore
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("aya_afi")
hiddenimports += collect_submodules("pydantic")
hiddenimports += collect_submodules("pydantic_core")
hiddenimports += collect_submodules("pydantic_settings")
hiddenimports += collect_submodules("httpx")
hiddenimports += collect_submodules("atproto")
hiddenimports += collect_submodules("atproto_core")
hiddenimports += collect_submodules("atproto_client")
hiddenimports += collect_submodules("google.genai")
hiddenimports += [
    "pythonjsonlogger.jsonlogger",
    "tenacity",
    "aiolimiter",
    "dotenv",
    "pyperclip",
]

datas = []

a = Analysis(
    ["scripts/sidecar.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.tests", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
