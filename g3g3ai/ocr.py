"""OCR en el propio equipo (sin Internet) para PDF escaneados e imágenes con texto.

Usa RapidOCR 3 (modelos PP-OCRv6 en ONNX, incluidos en el paquete: lee bien tildes, eñes y cifras sueltas). Reconstruye las filas de las tablas
agrupando las cajas de texto por altura, con « | » entre columnas, para que la IA pueda leer partes de
horas, nóminas o facturas escaneadas.
"""
from __future__ import annotations

import threading
from pathlib import Path

MAX_PAGES = 30
_engine = None
_lock = threading.Lock()
_cache: dict[tuple[str, float, int], str] = {}


def available() -> bool:
    try:
        import rapidocr  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR
        _engine = RapidOCR(params={"Global.log_level": "error"})
    return _engine


def lines_from_boxes(result) -> list[str]:
    """[(caja, texto, confianza)] → líneas de texto en orden de lectura; columnas separadas por « | »."""
    items = []
    for box, text, _score in result or []:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append({"y": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys), "x": min(xs), "x2": max(xs), "t": text.strip()})
    items = [i for i in items if i["t"]]
    items.sort(key=lambda i: i["y"])
    rows: list[list[dict]] = []
    for it in items:
        if rows:
            row = rows[-1]
            ref_y = sum(i["y"] for i in row) / len(row)
            ref_h = max(i["h"] for i in row)
            if abs(it["y"] - ref_y) < max(ref_h, it["h"]) * 0.6:
                row.append(it)
                continue
        rows.append([it])
    out = []
    for row in rows:
        row.sort(key=lambda i: i["x"])
        parts, last = [], None
        for i in row:
            if last is not None and i["x"] - last["x2"] < max(i["h"], last["h"]) * 0.8:
                parts[-1] += " " + i["t"]          # misma celda (palabras cercanas)
            else:
                parts.append(i["t"])
            last = i
        out.append(" | ".join(parts))
    return out


def image_text(img) -> str:
    """Texto de una imagen (ruta, bytes o PIL.Image)."""
    import numpy as np
    from PIL import Image
    if isinstance(img, (str, Path)):
        img = Image.open(img)
    elif isinstance(img, bytes):
        import io
        img = Image.open(io.BytesIO(img))
    arr = np.array(img.convert("RGB"))
    with _lock:                                      # el motor no es seguro entre hilos
        r = _get_engine()(arr)
    if r.boxes is None:
        return ""
    return "\n".join(lines_from_boxes(zip(r.boxes.tolist(), r.txts, r.scores)))


def pdf_text(path: Path, max_pages: int = MAX_PAGES) -> str:
    """Texto por OCR de las páginas de un PDF escaneado ('' si no hay OCR disponible)."""
    if not available():
        return ""
    path = Path(path)
    key = (str(path.resolve()), path.stat().st_mtime, max_pages)
    if key in _cache:
        return _cache[key]
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    parts = []
    try:
        n = len(pdf)
        for i in range(min(n, max_pages)):
            page = pdf[i]
            w = page.get_width() or 612                   # puntos (1/72 pulgada)
            scale = max(1.0, min(3.0, 1600 / w))           # ~1600 px de ancho: A4 a unos 190 ppp
            img = page.render(scale=scale).to_pil()
            t = image_text(img).strip()
            if t:
                parts.append(f"--- Página {i + 1} ---\n{t}")
        if n > max_pages:
            parts.append(f"[… {n - max_pages} páginas más sin leer]")
    finally:
        pdf.close()
    text = "\n\n".join(parts)
    if len(_cache) > 32:
        _cache.clear()
    _cache[key] = text
    return text
