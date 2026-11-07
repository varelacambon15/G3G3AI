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
WORD_EXT = {".docx", ".docm", ".dotx", ".dotm"}
EXCEL_EXT = {".xlsx", ".xlsm", ".xltx", ".xltm"}
PPT_EXT = {".pptx", ".pptm", ".potx", ".ppsx"}
DOC_EXT = {".pdf", ".xls", ".odt", ".ods", ".odp"} | WORD_EXT | EXCEL_EXT | PPT_EXT
MACRO_EXT = {".xlsm", ".xltm", ".xls", ".docm", ".dotm", ".pptm"}
VBA_LIMIT = 40_000
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
                f = c.find(f"{ns}f")
                if c.get("t") == "s" and v is not None:
                    val = shared[int(v.text)] if v.text and int(v.text) < len(shared) else ""
                elif c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{ns}t"))
                else:
                    val = v.text if v is not None and v.text else ""
                if f is not None and f.text:  # fórmula: se muestra junto a su último valor calculado
                    val = f"{c.get('r', '')}: ={f.text} → {val}" if val else f"{c.get('r', '')}: ={f.text}"
                cells.append(val)
            if any(cells):
                out.append(" | ".join(cells))
    return "\n".join(out)


def _xls(path: Path) -> str:
    """Excel antiguo (.xls, formato binario de Excel 97-2003)."""
    try:
        import xlrd
    except ImportError as e:
        raise DocumentError("Falta xlrd para leer .xls (pip install xlrd).") from e
    try:
        book = xlrd.open_workbook(str(path))
    except Exception as e:  # noqa: BLE001
        raise DocumentError(f"No se pudo leer {path.name}: {e}") from e
    out = []
    for sh in book.sheets():
        out.append(f"--- Hoja {sh.name} ---")
        for r in range(sh.nrows):
            cells = []
            for c in sh.row(r):
                v = c.value
                if c.ctype == xlrd.XL_CELL_NUMBER and float(v).is_integer():
                    v = int(v)
                elif c.ctype == xlrd.XL_CELL_DATE:
                    try:
                        v = xlrd.xldate.xldate_as_datetime(v, book.datemode).isoformat(sep=" ")
                    except Exception:  # noqa: BLE001
                        pass
                cells.append(str(v) if v not in ("", None) else "")
            if any(cells):
                out.append(" | ".join(cells))
            if sum(len(x) for x in out) > TEXT_LIMIT:
                break
    return "\n".join(out)


def vba_macros(path: Path) -> str:
    """Código de las macros VBA (Excel/Word/PowerPoint con macros). Sólo se lee, nunca se ejecuta."""
    try:
        from oletools.olevba import VBA_Parser
    except ImportError:
        return ""
    try:
        parser = VBA_Parser(str(path))
        if not parser.detect_vba_macros():
            return ""
        parts = []
        for _, _, name, code in parser.extract_macros():
            code = (code or "").strip()
            if code and not re.fullmatch(r"(Attribute [^\n]*\n?)*", code + "\n"):
                parts.append(f"' ===== Módulo: {name} =====\n{code}")
        parser.close()
        text = "\n\n".join(parts)
        return text[:VBA_LIMIT] + ("\n[... macros recortadas ...]" if len(text) > VBA_LIMIT else "")
    except Exception as e:  # noqa: BLE001 — archivos dañados o protegidos
        return f"(No se pudieron leer las macros: {e})"


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
    if ext == ".xls":
        text = _xls(path)[:TEXT_LIMIT]
    else:
        try:
            with zipfile.ZipFile(path) as z:
                if ext in WORD_EXT:
                    text = _docx(z)
                elif ext in PPT_EXT:
                    text = _pptx(z)
                elif ext in EXCEL_EXT:
                    text = _xlsx(z)
                else:
                    text = _odf(z)
                text = text[:TEXT_LIMIT]
        except (zipfile.BadZipFile, KeyError) as e:
            raise DocumentError(f"No se pudo leer {path.name}: formato no válido") from e
    if ext in MACRO_EXT:
        macros = vba_macros(path)
        if macros:
            text += f"\n\n--- Macros VBA (sólo lectura, no se ejecutan) ---\n{macros}"
    return text
