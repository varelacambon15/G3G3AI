"""Lectura de documentos e imágenes adjuntos.

- Texto plano y código: tal cual.
- PDF (pypdf), Word (.docx), Excel (.xlsx), PowerPoint (.pptx), OpenDocument (.odt/.ods/.odp): a texto.
- PDF escaneado (sin texto): se convierten las primeras páginas en imágenes (pypdfium2) para un modelo con visión.
- Imágenes: se reducen (Pillow) y se codifican en base64 para los modelos con visión.
"""
from __future__ import annotations

import base64
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DOC_EXT = {".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
MAX_IMAGE_SIDE = 1568      # px; suficiente para leer texto y barato en tokens
MAX_PDF_IMAGE_PAGES = 4
TEXT_LIMIT = 60_000


class DocumentError(Exception):
    pass


def kind_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in DOC_EXT:
        return "document"
    return "text"


# --- Imágenes -----------------------------------------------------------------------------
def image_data_url(path: Path) -> tuple[str, str]:
    """Devuelve (media_type, base64) de la imagen reducida a un tamaño razonable."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        data = path.read_bytes()
        if len(data) > 5_000_000:
            raise DocumentError("Imagen demasiado grande (instala Pillow para reducirla).")
        ext = path.suffix.lower().lstrip(".").replace("jpg", "jpeg")
        return f"image/{ext}", base64.b64encode(data).decode()
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)  # fotos del móvil giradas
            im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
    except OSError as e:
        raise DocumentError(f"No se pudo abrir la imagen {path.name}: {e}") from e
    return "image/jpeg", base64.b64encode(buf.getvalue()).decode()


# --- Documentos ---------------------------------------------------------------------------
def _xml_text(data: bytes, para_tags=("p", "tr", "br")) -> str:
    out = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return ""

    def walk(el):
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("t", "v") and el.text:  # w:t, a:t, x:v
            out.append(el.text)
        elif tag == "tab":
            out.append("\t")
        elif tag == "span" and el.text:   # OpenDocument
            out.append(el.text)
        elif tag in ("p", "h") and el.text and not len(el):
            out.append(el.text)
        for c in el:
            walk(c)
            if c.tail and tag in ("p", "h", "span"):
                out.append(c.tail)
        if tag in para_tags or tag in ("h",):
            out.append("\n")

    walk(root)
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


def _docx(z: zipfile.ZipFile) -> str:
    return _xml_text(z.read("word/document.xml"))


def _pptx(z: zipfile.ZipFile) -> str:
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.findall(r"\d+", n)[-1]))
    return "\n\n".join(f"--- Diapositiva {i} ---\n{_xml_text(z.read(n))}" for i, n in enumerate(slides, 1))


def _xlsx(z: zipfile.ZipFile) -> str:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{ns}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{ns}t")))
    names = []
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        names = [s.get("name") for s in wb.iter(f"{ns}sheet")]
    except KeyError:
        pass
    sheets = sorted((n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                    key=lambda n: int(re.findall(r"\d+", n)[-1]))
    out = []
    for i, n in enumerate(sheets):
        out.append(f"--- Hoja {names[i] if i < len(names) else i + 1} ---")
        for row in ET.fromstring(z.read(n)).iter(f"{ns}row"):
            cells = []
            for c in row.iter(f"{ns}c"):
                v = c.find(f"{ns}v")
                if c.get("t") == "s" and v is not None:
                    cells.append(shared[int(v.text)] if v.text and int(v.text) < len(shared) else "")
                elif c.get("t") == "inlineStr":
                    cells.append("".join(t.text or "" for t in c.iter(f"{ns}t")))
                else:
                    cells.append(v.text if v is not None and v.text else "")
            if any(cells):
                out.append(" | ".join(cells))
    return "\n".join(out)


def _odf(z: zipfile.ZipFile) -> str:
    return _xml_text(z.read("content.xml"), para_tags=("p", "h", "table-row"))


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise DocumentError("Falta pypdf para leer PDF (pip install pypdf).") from e
    try:
        reader = PdfReader(str(path))
        parts = []
        for i, page in enumerate(reader.pages, 1):
            t = (page.extract_text() or "").strip()
            if t:
                parts.append(f"--- Página {i} ---\n{t}")
            if sum(len(p) for p in parts) > TEXT_LIMIT:
                break
        return "\n\n".join(parts)
    except Exception as e:  # noqa: BLE001 — PDFs dañados o cifrados
        raise DocumentError(f"No se pudo leer el PDF {path.name}: {e}") from e


def pdf_page_images(path: Path, pages: int = MAX_PDF_IMAGE_PAGES) -> list[tuple[str, str]]:
    """Renderiza las primeras páginas de un PDF escaneado como imágenes JPEG (base64)."""
    try:
        import pypdfium2 as pdfium
        from PIL import Image  # noqa: F401
    except ImportError:
        return []
    out = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        for i in range(min(len(pdf), pages)):
            img = pdf[i].render(scale=1.6).to_pil()
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=80)
            out.append(("image/jpeg", base64.b64encode(buf.getvalue()).decode()))
    finally:
        pdf.close()
    return out


def extract_text(path: Path) -> str:
    """Texto de un documento de oficina o PDF. Cadena vacía si no tiene texto (escaneado)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_text(path)[:TEXT_LIMIT]
    try:
        with zipfile.ZipFile(path) as z:
            fn = {".docx": _docx, ".pptx": _pptx, ".xlsx": _xlsx}.get(ext, _odf)
            return fn(z)[:TEXT_LIMIT]
    except (zipfile.BadZipFile, KeyError) as e:
        raise DocumentError(f"No se pudo leer {path.name}: formato no válido") from e
