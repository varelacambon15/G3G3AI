"""Creación de documentos: Word (.docx), Excel (.xlsx), PowerPoint (.pptx) y PDF.

- .docx y .pdf: a partir de Markdown (títulos, listas, tablas, negrita, cursiva, código).
- .xlsx: a partir de JSON {"sheets": [{"name", "rows": [[...]], "column_widths"?: {...}}]}.
  Las celdas que empiezan por "=" son fórmulas de Excel. La primera fila se trata como encabezado.
- .pptx: a partir de JSON {"title", "subtitle"?, "slides": [{"title", "bullets": [...], "notes"?}]}.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FORMATS = {".docx", ".xlsx", ".pptx", ".pdf"}


class OfficeError(Exception):
    pass


# --- Markdown sencillo → bloques --------------------------------------------------------------
def parse_markdown(md: str) -> list[tuple]:
    """Devuelve bloques: ("h", nivel, texto) · ("p", texto) · ("ul"/"ol", [items]) · ("table", filas) · ("code", texto)."""
    lines = md.replace("\r", "").split("\n")
    out, i, para = [], 0, []

    def flush():
        if para:
            out.append(("p", " ".join(x.strip() for x in para)))
            para.clear()

    while i < len(lines):
        l = lines[i]
        if l.strip().startswith("```"):
            flush()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            out.append(("code", "\n".join(buf)))
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", l)
        if m:
            flush()
            out.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue
        if re.match(r"^\s*\|.*\|\s*$", l) and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            flush()
            row = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]  # noqa: E731
            rows = [row(l)]
            i += 2
            while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
                rows.append(row(lines[i]))
                i += 1
            out.append(("table", rows))
            continue
        m = re.match(r"^\s*([-*+]|\d+[.)])\s+(.*)", l)
        if m:
            flush()
            kind = "ol" if m.group(1)[0].isdigit() else "ul"
            items = []
            while i < len(lines):
                mm = re.match(r"^\s*([-*+]|\d+[.)])\s+(.*)", lines[i])
                if not mm:
                    break
                items.append(mm.group(2).strip())
                i += 1
            out.append((kind, items))
            continue
        if not l.strip():
            flush()
        elif re.match(r"^\s*(-{3,}|\*{3,})\s*$", l):
            flush()
        else:
            para.append(l)
        i += 1
    flush()
    return out


def inline_runs(text: str) -> list[tuple[str, str]]:
    """Divide «**negrita** *cursiva* `código`» en [(estilo, texto)]."""
    runs = []
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            runs.append(("b", part[2:-2]))
        elif part.startswith("`") and part.endswith("`"):
            runs.append(("code", part[1:-1]))
        elif (part.startswith("*") and part.endswith("*")) or (part.startswith("_") and part.endswith("_")):
            runs.append(("i", part[1:-1]))
        else:
            runs.append(("", part))
    return runs


# --- Word ---------------------------------------------------------------------------------
def create_docx(path: Path, markdown: str) -> None:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    def add_runs(par, text):
        for style, t in inline_runs(text):
            r = par.add_run(t)
            r.bold = style == "b"
            r.italic = style == "i"
            if style == "code":
                r.font.name = "Consolas"

    for block in parse_markdown(markdown):
        kind = block[0]
        if kind == "h":
            doc.add_heading(block[2], level=min(block[1], 4) if block[1] > 1 else 1 if len(doc.paragraphs) else 0)
        elif kind == "p":
            add_runs(doc.add_paragraph(), block[1])
        elif kind in ("ul", "ol"):
            for item in block[1]:
                add_runs(doc.add_paragraph(style="List Bullet" if kind == "ul" else "List Number"), item)
        elif kind == "code":
            p = doc.add_paragraph()
            r = p.add_run(block[1])
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
        elif kind == "table":
            rows = block[1]
            ncols = max(len(r) for r in rows)
            t = doc.add_table(rows=len(rows), cols=ncols)
            t.style = "Table Grid"
            for ri, row in enumerate(rows):
                for ci in range(ncols):
                    cell = t.cell(ri, ci)
                    cell.text = ""
                    add_runs(cell.paragraphs[0], row[ci] if ci < len(row) else "")
                    if ri == 0:
                        for r in cell.paragraphs[0].runs:
                            r.bold = True
    doc.save(str(path))


# --- Excel --------------------------------------------------------------------------------
def _cell_value(v):
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"-?\d+[.,]\d+", s) and s.count(",") <= 1:
            return float(s.replace(",", "."))
    return v


def create_xlsx(path: Path, spec) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except json.JSONDecodeError:
            # También vale CSV / tabla de texto: una hoja con separador ; , o tabulador
            sep = "\t" if "\t" in spec else (";" if ";" in spec else ",")
            spec = {"sheets": [{"name": "Hoja1", "rows": [line.split(sep) for line in spec.strip().splitlines()]}]}
    if isinstance(spec, list):
        spec = {"sheets": [{"name": "Hoja1", "rows": spec}]}
    sheets = spec.get("sheets") or []
    if not sheets:
        raise OfficeError('Formato esperado: {"sheets": [{"name": "Hoja1", "rows": [["A", "B"], [1, 2]]}]}')
    wb = Workbook()
    wb.remove(wb.active)
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="C2603F")
    for sh in sheets:
        ws = wb.create_sheet(str(sh.get("name") or f"Hoja{len(wb.sheetnames) + 1}")[:31])
        rows = sh.get("rows") or []
        for row in rows:
            ws.append([_cell_value(v) for v in row])
        header = sh.get("header", True)
        if header and rows:
            for c in ws[1]:
                c.font, c.fill = head_font, head_fill
                c.alignment = Alignment(vertical="center")
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
        widths = sh.get("column_widths") or {}
        for ci in range(1, ws.max_column + 1):
            letter = get_column_letter(ci)
            if letter in widths:
                ws.column_dimensions[letter].width = widths[letter]
                continue
            longest = max((len(str(c.value)) for c in ws[letter] if c.value is not None
                           and not str(c.value).startswith("=")), default=8)
            ws.column_dimensions[letter].width = min(max(10, longest + 2), 60)
        for fmt_col, fmt in (sh.get("number_formats") or {}).items():
            for c in ws[fmt_col][1 if header else 0:]:
                c.number_format = fmt
    wb.save(str(path))


# --- PowerPoint -----------------------------------------------------------------------------
def create_pptx(path: Path, spec) -> None:
    from pptx import Presentation
    from pptx.util import Pt

    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except json.JSONDecodeError as e:
            raise OfficeError('Formato esperado: {"title": "...", "slides": [{"title": "...", "bullets": ["..."]}]}') from e
    prs = Presentation()
    prs.slide_width, prs.slide_height = 12192000, 6858000  # 16:9
    if spec.get("title"):
        s = prs.slides.add_slide(prs.slide_layouts[0])
        s.shapes.title.text = spec["title"]
        if spec.get("subtitle") and len(s.placeholders) > 1:
            s.placeholders[1].text = spec["subtitle"]
    for sl in spec.get("slides") or []:
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = str(sl.get("title", ""))
        body = s.placeholders[1].text_frame
        body.clear()
        for k, b in enumerate(sl.get("bullets") or []):
            level = 0
            if isinstance(b, dict):
                level, b = int(b.get("level", 0)), b.get("text", "")
            p = body.paragraphs[0] if k == 0 else body.add_paragraph()
            p.text, p.level = str(b), min(level, 4)
            for r in p.runs:
                r.font.size = Pt(22 if level == 0 else 18)
        if sl.get("notes"):
            s.notes_slide.notes_text_frame.text = str(sl["notes"])
    if not len(prs.slides):
        raise OfficeError("La presentación no tiene diapositivas.")
    prs.save(str(path))


# --- PDF ------------------------------------------------------------------------------------
def _unicode_font() -> str | None:
    cands = ["/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/noto/NotoSans-Regular.ttf",
             "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
    if sys.platform == "win32":
        cands = [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"] + cands
    return next((c for c in cands if Path(c).is_file()), None)


def create_pdf(path: Path, markdown: str) -> None:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    font = _unicode_font()
    if font:
        pdf.add_font("U", "", font)
        bold = font.replace("Sans.ttf", "Sans-Bold.ttf").replace("Regular", "Bold").replace("arial.ttf", "arialbd.ttf")
        pdf.add_font("U", "B", bold if Path(bold).is_file() else font)
        fam = "U"
        clean = lambda t: t  # noqa: E731
    else:
        fam = "Helvetica"
        clean = lambda t: t.encode("latin-1", "replace").decode("latin-1")  # noqa: E731
    plain = lambda t: clean("".join(x for _, x in inline_runs(t)))  # noqa: E731
    width = pdf.w - pdf.l_margin - pdf.r_margin
    for block in parse_markdown(markdown):
        kind = block[0]
        if kind == "h":
            pdf.set_font(fam, "B", {1: 20, 2: 16, 3: 13}.get(block[1], 12))
            pdf.ln(3)
            pdf.multi_cell(width, 8, plain(block[2]))
            pdf.ln(1)
        elif kind == "p":
            pdf.set_font(fam, "", 11)
            pdf.multi_cell(width, 6, plain(block[1]))
            pdf.ln(2)
        elif kind in ("ul", "ol"):
            pdf.set_font(fam, "", 11)
            for n, item in enumerate(block[1], 1):
                mark = f"{n}." if kind == "ol" else "-"
                pdf.multi_cell(width, 6, plain(f"  {mark} {item}"))
            pdf.ln(2)
        elif kind == "code":
            pdf.set_font("Courier", "", 9)
            pdf.set_fill_color(244, 242, 236)
            pdf.multi_cell(width, 5, block[1].encode("latin-1", "replace").decode("latin-1"), fill=True)
            pdf.ln(2)
        elif kind == "table":
            pdf.set_font(fam, "", 10)
            with pdf.table() as table:
                for ri, row in enumerate(block[1]):
                    r = table.row()
                    for cell in row:
                        r.cell(plain(cell))
            pdf.ln(3)
    pdf.output(str(path))


def create(path: Path, content) -> Path:
    ext = path.suffix.lower()
    if ext not in FORMATS:
        raise OfficeError(f"Formato no soportado: {ext}. Usa .docx, .xlsx, .pptx o .pdf.")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if ext == ".docx":
            create_docx(path, content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
        elif ext == ".xlsx":
            create_xlsx(path, content)
        elif ext == ".pptx":
            create_pptx(path, content)
        else:
            create_pdf(path, content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
    except ImportError as e:
        raise OfficeError(f"Falta una librería para crear {ext}: {e.name}. Reinstala G3G3AI.") from e
    return path
