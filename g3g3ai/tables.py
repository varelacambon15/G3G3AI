"""Consultas sobre hojas de cálculo grandes (xlsx, xlsm, xls, csv) sin pasarlas enteras al modelo.

Un modelo pequeño (y su contexto de 8K) no puede leer una hoja de 500 filas × 150 columnas, pero sí puede pedir
«los operarios cuya columna X esté vacía» o «los de A que no estén en B». El filtrado, el recuento y el cruce de dos
archivos los hace este módulo; al modelo sólo le llega el resultado (y puede guardarlo directamente en un Excel).
"""
from __future__ import annotations

import csv
import unicodedata
from pathlib import Path

MAX_SHOWN = 60          # filas que se devuelven al modelo
MAX_EXPORT = 20000


class TableError(Exception):
    pass


def norm(v) -> str:
    """Normaliza para comparar: sin acentos, minúsculas, espacios y guiones sobrantes."""
    s = "" if v is None else str(v)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return " ".join(s.replace("-", " ").replace(".", " ").split())


def _clean(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _read_rows(path: Path, sheet: str | None) -> tuple[list[list], list[str], str]:
    ext = path.suffix.lower()
    if ext == ".csv" or ext == ".tsv" or ext == ".txt":
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        delim = max([",", ";", "\t", "|"], key=sample.count)
        return [list(r) for r in csv.reader(text.splitlines(), delimiter=delim)], ["(csv)"], "(csv)"
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            names = wb.sheetnames
            name = _pick_sheet(names, sheet)
            return [[_clean(c) for c in r] for r in wb[name].iter_rows(values_only=True)], names, name
        finally:
            wb.close()
    if ext == ".xls":
        import xlrd
        book = xlrd.open_workbook(str(path))
        names = book.sheet_names()
        name = _pick_sheet(names, sheet)
        ws = book.sheet_by_name(name)
        return [[_clean(c) for c in ws.row_values(i)] for i in range(ws.nrows)], names, name
    raise TableError(f"Formato no soportado: {ext}. Usa .xlsx, .xlsm, .xls o .csv.")


def _pick_sheet(names: list[str], sheet: str | None) -> str:
    if not names:
        raise TableError("El archivo no tiene hojas.")
    if not sheet:
        return names[0]
    for n in names:
        if norm(n) == norm(sheet):
            return n
    raise TableError(f"No existe la hoja «{sheet}». Hojas: {', '.join(names)}")


def _detect_header(rows: list[list]) -> int:
    """Fila (0-based) de los encabezados: la que más celdas de texto tiene entre las primeras 15."""
    best, best_n = 0, -1
    for i, r in enumerate(rows[:15]):
        n = sum(1 for c in r if isinstance(c, str) and c.strip())
        if n > best_n:
            best, best_n = i, n
    return best


def load(path: Path, sheet: str | None = None, header_row: int | None = None) -> dict:
    rows, sheets, used = _read_rows(path, sheet)
    if not rows:
        raise TableError("La hoja está vacía.")
    h = (int(header_row) - 1) if header_row else _detect_header(rows)
    if h < 0 or h >= len(rows):
        raise TableError(f"header_row fuera de rango (la hoja tiene {len(rows)} filas).")
    width = max(len(r) for r in rows[h:h + 1] + rows[h + 1:h + 50]) if rows[h + 1:] else len(rows[h])
    headers, seen = [], {}
    for i in range(width):
        base = str(rows[h][i]).strip() if i < len(rows[h]) and rows[h][i] not in (None, "") else f"col{i + 1}"
        k = norm(base)
        seen[k] = seen.get(k, 0) + 1
        headers.append(base if seen[k] == 1 else f"{base}_{seen[k]}")
    data = []
    for r in rows[h + 1:]:
        if all(c in (None, "") for c in r):
            continue
        r = list(r) + [None] * (width - len(r))
        data.append(r[:width])
    return {"headers": headers, "rows": data, "sheets": sheets, "sheet": used, "header_row": h + 1}


def col_index(headers: list[str], name: str) -> int:
    n = norm(name)
    exact = [i for i, h in enumerate(headers) if norm(h) == n]
    if exact:
        return exact[0]
    part = [i for i, h in enumerate(headers) if n and n in norm(h)]
    if len(part) == 1:
        return part[0]
    if len(part) > 1:
        raise TableError(f"«{name}» es ambiguo: coincide con {', '.join(headers[i] for i in part[:6])}. Usa el nombre exacto.")
    raise TableError(f"No existe la columna «{name}». Columnas: {', '.join(h for h in headers[:60])}")


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(str(v))
    except ValueError:
        return None


def _match(cell, op: str, value) -> bool:
    empty = cell is None or str(cell).strip() == ""
    if op in ("empty", "vacio", "vacío"):
        return empty
    if op in ("not_empty", "no_vacio", "no vacío"):
        return not empty
    if op in ("=", "==", "igual"):
        return norm(cell) == norm(value)
    if op in ("!=", "distinto"):
        return norm(cell) != norm(value)
    if op in ("contains", "contiene"):
        return norm(value) in norm(cell)
    if op in ("not_contains", "no_contiene"):
        return norm(value) not in norm(cell)
    if op in (">", "<", ">=", "<="):
        a, b = _num(cell), _num(value)
        if a is None or b is None:
            return False
        return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[op]
    raise TableError(f"Operador no válido: {op}. Usa =, !=, contains, not_contains, empty, not_empty, >, <, >=, <=")


def query(path: Path, *, sheet=None, header_row=None, columns=None, where=None, distinct=False,
          other_path: Path | None = None, other_sheet=None, other_header_row=None,
          column=None, other_column=None, mode="missing") -> dict:
    """Devuelve {"headers", "rows", "total", "info"}.

    where: [{"column": "...", "op": "empty", "value": "..."}] (todas deben cumplirse).
    Cruce: con other_path, column y other_column se queda con las filas cuyo valor de `column` NO está
    (mode="missing") o SÍ está (mode="common") en `other_column` del otro archivo.
    """
    t = load(path, sheet, header_row)
    headers, rows = t["headers"], t["rows"]
    conds = []
    for w in where or []:
        if not isinstance(w, dict) or "column" not in w:
            raise TableError('Cada condición de where es {"column": "...", "op": "...", "value": "..."}')
        conds.append((col_index(headers, w["column"]), str(w.get("op", "=")).lower(), w.get("value")))
    out = [r for r in rows if all(_match(r[i], op, v) for i, op, v in conds)]
    info = [f"{path.name} (hoja «{t['sheet']}», encabezados en la fila {t['header_row']}): {len(rows)} filas"]
    if conds:
        info.append(f"tras filtrar: {len(out)}")
    if other_path is not None:
        if not column or not other_column:
            raise TableError("Para cruzar dos archivos indica column (en este) y other_column (en el otro).")
        o = load(other_path, other_sheet, other_header_row)
        ci, oi = col_index(headers, column), col_index(o["headers"], other_column)
        keys = {norm(r[oi]) for r in o["rows"] if r[oi] not in (None, "")}
        want_in = str(mode).lower() in ("common", "comun", "común", "in")
        out = [r for r in out if r[ci] not in (None, "") and ((norm(r[ci]) in keys) == want_in)]
        info.append(f"cruce con {other_path.name} (hoja «{o['sheet']}», {len(o['rows'])} filas): "
                    f"{'están en' if want_in else 'NO están en'} «{o['headers'][oi]}» → {len(out)}")
    if columns:
        idx = [col_index(headers, c) for c in columns]
        headers_out = [headers[i] for i in idx]
        out = [[r[i] for i in idx] for r in out]
    else:
        headers_out = headers
    if distinct:
        seen, uniq = set(), []
        for r in out:
            k = tuple(norm(c) for c in r)
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        out = uniq
        info.append(f"sin duplicados: {len(out)}")
    return {"headers": headers_out, "rows": out, "total": len(out), "info": info}


def describe(path: Path, sheet=None, header_row=None) -> str:
    t = load(path, sheet, header_row)
    lines = [f"Archivo: {path.name}", f"Hojas: {', '.join(t['sheets'])} (se usa «{t['sheet']}»)",
             f"Filas de datos: {len(t['rows'])} · encabezados en la fila {t['header_row']} · {len(t['headers'])} columnas",
             "Columnas: " + " | ".join(t["headers"][:80]) + (" …" if len(t["headers"]) > 80 else "")]
    for r in t["rows"][:3]:
        lines.append("Ejemplo: " + " | ".join("" if c is None else str(c) for c in r[:12]))
    return "\n".join(lines)


def format_result(res: dict, limit: int = MAX_SHOWN) -> str:
    rows = res["rows"]
    lines = [" · ".join(res["info"]), f"Resultado: {res['total']} filas."]
    if rows:
        lines.append("\t".join(map(str, res["headers"])))
        for r in rows[:limit]:
            lines.append("\t".join("" if c is None else str(c) for c in r))
        if len(rows) > limit:
            lines.append(f"[... {len(rows) - limit} filas más: usa table_export para guardarlas todas en un Excel ...]")
    return "\n".join(lines)


def export(res: dict, dest: Path, title: str = "Resultado") -> int:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    rows = res["rows"][:MAX_EXPORT]
    if dest.suffix.lower() == ".csv":
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(res["headers"])
            w.writerows([["" if c is None else c for c in r] for r in rows])
        return len(rows)
    if dest.suffix.lower() != ".xlsx":
        raise TableError("save_as debe terminar en .xlsx o .csv")
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(list(res["headers"]))
    for r in rows:
        ws.append(["" if c is None else c for c in r])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="C2603F")
        c.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for ci in range(1, ws.max_column + 1):
        L = get_column_letter(ci)
        longest = max((len(str(c.value)) for c in ws[L] if c.value is not None), default=8)
        ws.column_dimensions[L].width = min(max(10, longest + 2), 50)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(dest))
    return len(rows)
