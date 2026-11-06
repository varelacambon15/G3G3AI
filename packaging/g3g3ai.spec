# PyInstaller: genera G3G3AI.exe (Windows) o G3G3AI (Linux/macOS) en un único archivo.
#   pyinstaller packaging/g3g3ai.spec
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
hidden = collect_submodules("uvicorn") + ["multipart", "python_multipart"]
try:
    import webview  # noqa: F401
    hidden += collect_submodules("webview")
except ImportError:
    pass

a = Analysis(
    [str(ROOT / "run_desktop.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "g3g3ai" / "static"), "g3g3ai/static")],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="G3G3AI",
    console=False,  # sin ventana negra de consola
    icon=str(ROOT / "packaging" / "icon.ico") if sys.platform == "win32" else None,
    upx=False,
)
