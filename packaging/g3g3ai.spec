# PyInstaller: genera G3G3AI.exe (Windows) o G3G3AI (Linux/macOS) en un único archivo.
#   pyinstaller packaging/g3g3ai.spec
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

hidden = collect_submodules("uvicorn") + ["multipart", "python_multipart"]
extra_datas, extra_bins = [], []
for pkg in ("pypdfium2", "pypdfium2_raw"):  # PDF escaneados → imágenes (incluye la librería nativa pdfium)
    try:
        __import__(pkg)
        extra_datas += collect_data_files(pkg)
        extra_bins += collect_dynamic_libs(pkg)
        hidden += collect_submodules(pkg)
    except ImportError:
        pass
try:
    import webview  # noqa: F401
    hidden += collect_submodules("webview")
except ImportError:
    pass

a = Analysis(
    [str(ROOT / "run_desktop.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "g3g3ai" / "static"), "g3g3ai/static")] + extra_datas,
    binaries=extra_bins,
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
