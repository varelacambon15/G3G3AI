"""Búsqueda en tu correo (solo lectura): buzones de Thunderbird (mbox) y carpetas con archivos .eml.

- Se construye un índice local (SQLite, con FTS5 si está disponible) en la carpeta de datos de G3G3AI; el correo
  original nunca se modifica. El índice se actualiza solo con lo nuevo.
- La IA no recibe rutas ni abre archivos: solo puede llamar a `mail_search` y `mail_read`, que consultan este índice.
- Fuentes: el perfil de Thunderbird detectado (Mail e ImapMail) y las rutas extra de Ajustes → «Correo».
  Los mensajes IMAP solo están en disco si Thunderbird los guarda sin conexión (opción por defecto de la mayoría de cuentas).
"""
from __future__ import annotations

import configparser
import email
import email.policy
import email.utils
import html
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

from .config import DATA_DIR

MAX_BODY_INDEX = 30_000     # caracteres de cuerpo que se guardan en el índice por mensaje
MAX_BODY_READ = 20_000      # caracteres que devuelve mail_read
MAX_RAW = 40_000_000        # un mensaje más grande que esto (adjuntos enormes) se indexa sólo por su cabecera
COMMIT_EVERY = 400
FLAG_FOLDERS = re.compile(r"(^|[/\\])(Trash|Papelera|Junk|Spam|Correo no deseado|Drafts|Borradores)(\.sbd)?($|[/\\])", re.I)


# --- Detección de Thunderbird ---------------------------------------------------------------
def _thunderbird_roots() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        return [base / "Thunderbird"]
    if sys.platform == "darwin":
        return [home / "Library" / "Thunderbird"]
    return [home / ".thunderbird", home / ".var" / "app" / "org.mozilla.Thunderbird" / ".thunderbird",
            home / "snap" / "thunderbird" / "common" / ".thunderbird"]


def thunderbird_profiles() -> list[Path]:
    """Carpetas de perfil de Thunderbird (el predeterminado primero)."""
    out: list[Path] = []
    for root in _thunderbird_roots():
        ini = root / "profiles.ini"
        if not ini.is_file():
            continue
        cp = configparser.RawConfigParser()
        try:
            cp.read(ini, encoding="utf-8")
        except (configparser.Error, OSError):
            continue
        found: list[tuple[int, Path]] = []
        for sec in cp.sections():
            if not (sec.startswith("Profile") and cp.has_option(sec, "Path")):
                continue
            p = cp.get(sec, "Path")
            rel = cp.get(sec, "IsRelative", fallback="1") == "1"
            path = (root / p) if rel else Path(p)
            dflt = 0 if cp.get(sec, "Default", fallback="0") == "1" else 1
            if path.is_dir():
                found.append((dflt, path))
        for sec in cp.sections():  # [InstallXXXX] Default=Profiles/xxx.default-release
            if sec.startswith("Install") and cp.has_option(sec, "Default"):
                d = root / cp.get(sec, "Default")
                if d.is_dir():
                    found.insert(0, (-1, d))
        out += [p for _, p in sorted(found, key=lambda t: t[0])]
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def mail_sources(cfg) -> list[Path]:
    srcs: list[Path] = []
    if cfg["mail_auto"]:
        prof = thunderbird_profiles()
        for p in prof[:1]:
            srcs += [d for d in (p / "Mail", p / "ImapMail") if d.is_dir()]
    for raw in cfg["mail_paths"] or []:
        p = Path(str(raw).strip()).expanduser()
        if str(raw).strip() and p.exists():
            srcs.append(p)
    return srcs


def _is_mbox(p: Path) -> bool:
    if p.suffix or not p.is_file() or p.stat().st_size == 0:
        return False
    try:
        with p.open("rb") as f:
            return f.read(5) == b"From "
    except OSError:
        return False


def discover(sources: list[Path]) -> list[tuple[Path, str]]:
    """[(archivo, tipo)] con tipo «mbox» o «eml», recorriendo carpetas (incluidas las .sbd de subcarpetas)."""
    found: list[tuple[Path, str]] = []
    for s in sources:
        if s.is_file():
            found.append((s, "eml" if s.suffix.lower() == ".eml" else "mbox"))
            continue
        for dirpath, dirnames, filenames in os.walk(s):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix.lower() == ".eml":
                    found.append((p, "eml"))
                elif _is_mbox(p):
                    found.append((p, "mbox"))
    return found


def folder_name(path: Path, sources: list[Path]) -> str:
    for s in sources:
        try:
            rel = path.relative_to(s if s.is_dir() else s.parent)
        except ValueError:
            continue
        parts = [x[:-4] if x.endswith(".sbd") else x for x in rel.parts]
        label = s.name if s.is_dir() else ""
        return " / ".join(([label] if label and label not in ("Mail", "ImapMail") else []) + parts)
    return path.name


# --- Lectura de mensajes -----------------------------------------------------------------------
def html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"[ \t\xa0]+", " ", html.unescape(s))


def parse_message(raw: bytes, with_body: bool = True) -> dict:
    """Cabeceras y cuerpo de texto de un mensaje (sin adjuntos). Tolerante: nunca lanza."""
    out = {"sender": "", "to": "", "cc": "", "subject": "", "ts": 0.0, "msgid": "", "body": "", "attachments": []}
    try:
        msg = email.message_from_bytes(raw if len(raw) <= MAX_RAW else raw[:200_000], policy=email.policy.default)
        out["sender"] = str(msg.get("From", "") or "")
        out["to"] = str(msg.get("To", "") or "")
        out["cc"] = str(msg.get("Cc", "") or "")
        out["subject"] = " ".join(str(msg.get("Subject", "") or "").split())
        out["msgid"] = str(msg.get("Message-ID", "") or "")
        try:
            out["ts"] = email.utils.parsedate_to_datetime(str(msg.get("Date", ""))).timestamp()
        except (TypeError, ValueError, AttributeError, IndexError, OverflowError):
            out["ts"] = 0.0
        if with_body:
            body = msg.get_body(preferencelist=("plain", "html"))
            if body is not None:
                text = body.get_content()
                if body.get_content_type() == "text/html":
                    text = html_to_text(text)
                out["body"] = re.sub(r"\n{3,}", "\n\n", text.replace("\r", "")).strip()
            out["attachments"] = [a.get_filename() or "(sin nombre)" for a in msg.iter_attachments()]
    except Exception:  # noqa: BLE001  (correo corrupto: se indexa lo que haya)
        pass
    return out


def iter_mbox(path: Path, start: int = 0):
    """(offset, longitud, bytes) de cada mensaje de un mbox a partir de `start` (límite de mensaje)."""
    with path.open("rb") as f:
        f.seek(start)
        off, cur, prev_blank, pos = start, [], True, start
        for line in f:
            if line.startswith(b"From ") and prev_blank and cur:
                data = b"".join(cur)
                yield off, len(data), data
                off, cur = pos, []
            cur.append(line)
            prev_blank = line in (b"\n", b"\r\n")
            pos += len(line)
        if cur:
            data = b"".join(cur)
            yield off, len(data), data


# --- Índice ---------------------------------------------------------------------------------------
def _fts_ok() -> bool:
    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
        return True
    except sqlite3.Error:
        return False


class MailIndex:
    def __init__(self, cfg, path: Path | None = None):
        self.cfg = cfg
        self.path = path or (DATA_DIR / "mail_index.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.fts = _fts_ok()
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, kind TEXT, size INTEGER, mtime REAL, head TEXT, upto INTEGER);
            CREATE TABLE IF NOT EXISTS msgs (id INTEGER PRIMARY KEY, file TEXT, folder TEXT, off INTEGER, len INTEGER,
              ts REAL, sender TEXT, recipients TEXT, subject TEXT, body TEXT, att INTEGER);
            CREATE INDEX IF NOT EXISTS msgs_ts ON msgs(ts);
            CREATE INDEX IF NOT EXISTS msgs_file ON msgs(file);
            """)
            if self.fts:
                self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(sender, recipients, subject, body, "
                                "tokenize='unicode61 remove_diacritics 2')")
        self.state = {"running": False, "files_done": 0, "files_total": 0, "started": 0.0, "finished": 0.0, "error": None}
        self._thread: threading.Thread | None = None
        self._stop = False

    # ---- construcción
    def start(self, rebuild: bool = False) -> bool:
        if self.state["running"]:
            return False
        self.state.update({"running": True, "files_done": 0, "files_total": 0, "started": time.time(), "error": None})
        self._thread = threading.Thread(target=self._run, args=(rebuild,), daemon=True)
        self._thread.start()
        return True

    def wait(self, timeout: float = 60) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _run(self, rebuild: bool) -> None:
        try:
            self.index_all(rebuild)
        except Exception as e:  # noqa: BLE001
            self.state["error"] = str(e)
        finally:
            self.state.update({"running": False, "finished": time.time()})

    def index_all(self, rebuild: bool = False) -> None:
        sources = mail_sources(self.cfg)
        files = discover(sources)
        self.state["files_total"] = len(files)
        with self.lock:
            if rebuild:
                self.db.executescript("DELETE FROM msgs; DELETE FROM files;")
                if self.fts:
                    self.db.execute("DELETE FROM fts")
            known = {r["path"] for r in self.db.execute("SELECT path FROM files")}
        current = {str(p) for p, _ in files}
        for gone in known - current:           # archivos que ya no existen
            self._drop_file(gone)
        for p, kind in files:
            if self._stop:
                break
            try:
                self._index_file(p, kind, folder_name(p, sources))
            except OSError:
                pass
            self.state["files_done"] += 1

    def _drop_file(self, path: str) -> None:
        with self.lock:
            if self.fts:
                self.db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM msgs WHERE file=?)", (path,))
            self.db.execute("DELETE FROM msgs WHERE file=?", (path,))
            self.db.execute("DELETE FROM files WHERE path=?", (path,))
            self.db.commit()

    def _head(self, p: Path) -> str:
        with p.open("rb") as f:
            return f.read(512).hex()

    def _add(self, file: str, folder: str, off: int, length: int, m: dict) -> None:
        body = m["body"][:MAX_BODY_INDEX]
        recips = (m["to"] + " " + m["cc"]).strip()
        cur = self.db.execute("INSERT INTO msgs (file, folder, off, len, ts, sender, recipients, subject, body, att) "
                              "VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (file, folder, off, length, m["ts"], m["sender"], recips, m["subject"], body, len(m["attachments"])))
        if self.fts:
            self.db.execute("INSERT INTO fts (rowid, sender, recipients, subject, body) VALUES (?,?,?,?,?)",
                            (cur.lastrowid, m["sender"], recips, m["subject"], body))

    def _index_file(self, p: Path, kind: str, folder: str) -> None:
        st = p.stat()
        path = str(p)
        with self.lock:
            row = self.db.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()
        head = self._head(p)
        if row and row["size"] == st.st_size and abs(row["mtime"] - st.st_mtime) < 1 and row["head"] == head:
            return                                     # sin cambios
        if kind == "eml":
            self._drop_file(path)
            raw = p.read_bytes()
            with self.lock:
                self._add(path, folder, 0, len(raw), parse_message(raw))
                self.db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)", (path, kind, st.st_size, st.st_mtime, head, st.st_size))
                self.db.commit()
            return
        start = 0
        if row and row["head"] == head and st.st_size >= row["upto"]:
            start = row["upto"]                        # sólo se añadió al final: se indexa lo nuevo
        else:
            self._drop_file(path)
        n = 0
        upto = start
        for off, length, raw in iter_mbox(p, start):
            if self._stop:
                break
            with self.lock:
                self._add(path, folder, off, length, parse_message(raw))
                n += 1
                upto = off + length
                if n % COMMIT_EVERY == 0:
                    self.db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)", (path, kind, st.st_size, st.st_mtime, head, upto))
                    self.db.commit()
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)", (path, kind, st.st_size, st.st_mtime, head, upto))
            self.db.commit()

    # ---- consulta
    def stats(self) -> dict:
        with self.lock:
            n = self.db.execute("SELECT COUNT(*) FROM msgs").fetchone()[0]
            f = self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            lo, hi = self.db.execute("SELECT MIN(ts), MAX(ts) FROM msgs WHERE ts>0").fetchone()
        return {"messages": n, "files": f, "oldest": lo, "newest": hi, "fts": self.fts, **self.state}

    @staticmethod
    def _day(s: str | None, end: bool = False) -> float | None:
        if not s:
            return None
        m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", str(s))
        if not m:
            raise ValueError(f"Fecha no válida «{s}»: usa AAAA-MM-DD")
        y, mo, d, hh, mm = (int(x) if x else None for x in m.groups())
        if hh is None:
            hh, mm = (23, 59) if end else (0, 0)
        return time.mktime((y, mo, d, hh, mm, 59 if end else 0, 0, 0, -1))

    def search(self, query: str = "", sender: str = "", to: str = "", subject: str = "", since: str | None = None,
               until: str | None = None, folder: str = "", limit: int = 20, include_junk: bool = False,
               person: str = "") -> list[dict]:
        limit = max(1, min(int(limit or 20), 50))
        where, args = [], []
        t0, t1 = self._day(since), self._day(until, end=True)
        if t0 is not None:
            where.append("m.ts >= ?"); args.append(t0)
        if t1 is not None:
            where.append("m.ts <= ?"); args.append(t1)
        for col, val in (("m.sender", sender), ("m.recipients", to), ("m.subject", subject), ("m.folder", folder)):
            if val and val.strip():
                where.append(f"{col} LIKE ? ESCAPE '\\'")
                args.append("%" + val.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        if person and person.strip():  # remitente O destinatario: para cuando el modelo no sabe en qué sentido va
            like = "%" + person.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append("(m.sender LIKE ? ESCAPE '\\' OR m.recipients LIKE ? ESCAPE '\\')")
            args += [like, like]
        if not include_junk:
            where.append("m.folder NOT LIKE '%Trash%' AND m.folder NOT LIKE '%Papelera%' AND m.folder NOT LIKE '%Junk%' "
                         "AND m.folder NOT LIKE '%Spam%' AND m.folder NOT LIKE '%no deseado%'")
        terms = re.findall(r"[\w@.\-]+", (query or "").lower())
        sql = "SELECT m.id, m.folder, m.ts, m.sender, m.recipients, m.subject, m.body, m.att FROM msgs m"
        if terms and self.fts:
            match = " ".join('"' + t.replace('"', "") + '"*' for t in terms[:8])
            sql += " JOIN fts ON fts.rowid = m.id"
            where.insert(0, "fts MATCH ?"); args.insert(0, match)
        elif terms:  # sin FTS5: todas las palabras deben aparecer
            for t in terms[:8]:
                where.append("(m.subject || ' ' || m.sender || ' ' || m.body) LIKE ?"); args.append(f"%{t}%")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY m.ts DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def raw(self, mid: int) -> tuple[dict, bytes] | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM msgs WHERE id=?", (mid,)).fetchone()
        if not r:
            return None
        with Path(r["file"]).open("rb") as f:
            f.seek(r["off"])
            return dict(r), f.read(min(r["len"], MAX_RAW))

    def read(self, mid: int) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM msgs WHERE id=?", (mid,)).fetchone()
        if not r:
            return None
        p = Path(r["file"])
        try:
            with p.open("rb") as f:
                f.seek(r["off"])
                raw = f.read(min(r["len"], MAX_RAW))
        except OSError:
            return {**dict(r), "error": "No se pudo abrir el archivo original (¿se movió o Thunderbird compactó la carpeta? Reindexa)."}
        m = parse_message(raw)
        m.update({"id": r["id"], "folder": r["folder"]})
        return m


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (name or "adjunto").strip()).strip(". ") or "adjunto"
    return name[:150]


def attachments_of(raw: bytes) -> list[tuple[str, bytes]]:
    """[(nombre, contenido)] de los adjuntos de un mensaje."""
    out = []
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        for i, a in enumerate(msg.iter_attachments(), 1):
            data = a.get_payload(decode=True)
            if data is None:
                continue
            out.append((safe_filename(a.get_filename() or f"adjunto_{i}"), data))
    except Exception:  # noqa: BLE001
        pass
    return out


def fmt_date(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "sin fecha"


def format_results(rows: list[dict], total_indexed: int, building: bool) -> str:
    if not rows:
        return ("No hay mensajes que coincidan." + (" (El índice aún se está construyendo: vuelve a intentarlo en un rato.)" if building else "")
                + f" Mensajes indexados: {total_indexed}.")
    lines = []
    for r in rows:
        snippet = " ".join((r["body"] or "").split())[:180]
        lines.append(f"[#{r['id']}] {fmt_date(r['ts'])} · De: {r['sender'] or '?'} · Para: {(r['recipients'] or '')[:80]} · "
                     f"Asunto: {r['subject'] or '(sin asunto)'} · Carpeta: {r['folder']}" + (" · 📎" if r["att"] else "")
                     + (f"\n    {snippet}" if snippet else ""))
    note = "\n(Índice aún en construcción: puede haber más resultados.)" if building else ""
    return (f"{len(rows)} mensaje(s), del más reciente al más antiguo. Los extractos están INCOMPLETOS: para mostrar o "
            "citar un correo, léelo antes con mail_read. Para guardar sus adjuntos usa mail_save_attachments.\n"
            + "\n".join(lines) + note)


def format_message(m: dict) -> str:
    if m.get("error"):
        return "Error: " + m["error"]
    body = m["body"]
    cut = "\n[… recortado …]" if len(body) > MAX_BODY_READ else ""
    return (f"De: {m['sender']}\nPara: {m['to']}" + (f"\nCc: {m['cc']}" if m["cc"] else "") + f"\nFecha: {fmt_date(m['ts'])}\n"
            f"Asunto: {m['subject']}\nCarpeta: {m['folder']}"
            + (f"\nAdjuntos (no se leen): {', '.join(m['attachments'])}" if m["attachments"] else "")
            + f"\n\n{body[:MAX_BODY_READ]}{cut}")
