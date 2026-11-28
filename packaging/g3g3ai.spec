# PyInstaller: genera G3G3AI.exe (Windows) o G3G3AI (Linux/macOS) en un único archivo.
#   pyinstaller packaging/g3g3ai.spec
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

hidden = collect_submodules("uvicorn") + ["multipart", "python_multipart"]
extra_datas, extra_bins = [], []
# Plantillas de Word/PowerPoint y datos de fpdf2/oletools
for pkg in ("docx", "pptx", "fpdf", "oletools", "pdfminer", "pdfplumber"):
    try:
        __import__(pkg)
        extra_datas += collect_data_files(pkg)
        hidden += collect_submodules(pkg)
    except ImportError:
        pass
for pkg in ("rapidocr", "onnxruntime"):  # OCR de PDF escaneados (modelos .onnx y config.yaml)
    try:
        __import__(pkg)
        extra_datas += collect_data_files(pkg)
        extra_bins += collect_dynamic_libs(pkg)
        hidden += collect_submodules(pkg)
    except ImportError:
        pass
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
if sys.platform == "darwin":
    # macOS: una aplicación G3G3AI.app (en modo carpeta: un solo archivo no se admite en una .app)
    import re as _re
    _version = _re.search(r'__version__ = "([^"]+)"', (ROOT / "g3g3ai" / "__init__.py").read_text(encoding="utf-8")).group(1)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="G3G3AI", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="G3G3AI", upx=False)
    app = BUNDLE(coll, name="G3G3AI.app", bundle_identifier="com.g3g3ai.app",
                 info_plist={"CFBundleName": "G3G3AI", "CFBundleDisplayName": "G3G3AI", "CFBundleShortVersionString": _version,
                             "CFBundleVersion": _version, "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True,
                             "NSMicrophoneUsageDescription": "G3G3AI usa el micrófono para dictar mensajes.",
                             "NSCameraUsageDescription": "G3G3AI usa la cámara para adjuntar fotos."})
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="G3G3AI",
        console=False,  # sin ventana negra de consola
        icon=str(ROOT / "packaging" / "icon.ico") if sys.platform == "win32" else None,
        upx=False,
    )
