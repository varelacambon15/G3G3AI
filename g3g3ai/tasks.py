"""Tareas programadas: el agente trabaja sin ventana abierta, solo y sin supervisión.

Cada tarea guarda un encargo (prompt), cuándo se ejecuta y con qué modelo. Al llegar la hora, el servidor lanza una
conversación nueva («🕒 nombre») con el agente en modo SIN SUPERVISIÓN: nadie puede aprobar acciones, así que todo
lo que pediría permiso se deniega (comandos que no estén en «Comandos permitidos», MCP, escritura en GitHub…).
Por defecto sólo lee; con «puede editar archivos» las ediciones dentro de las carpetas permitidas se aplican solas.
El resultado queda en la conversación y la interfaz avisa al terminar.

Programaciones: {"kind": "interval", "minutes": N} · {"kind": "daily", "time": "HH:MM"} · {"kind": "once", "at": epoch}
(la hora es la del equipo que ejecuta G3G3AI).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid

CHECK_EVERY = 20      # segundos entre comprobaciones del planificador
MIN_INTERVAL = 5      # minutos
CATCH_UP = 6 * 3600   # una tarea vencida hace menos de esto se ejecuta al arrancar; más antigua, se salta a la siguiente

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, prompt TEXT NOT NULL, schedule TEXT NOT NULL,
  provider TEXT, model TEXT, workdir TEXT, mode TEXT DEFAULT 'plan', enabled INTEGER DEFAULT 1,
  next_run REAL, last_run REAL, last_status TEXT, last_conv TEXT, created REAL
);
"""


class TaskError(Exception):
    pass


def validate_schedule(s) -> dict:
    if not isinstance(s, dict):
        raise TaskError("Programación no válida")
    kind = s.get("kind")
    if kind == "interval":
        try:
            n = int(s.get("minutes"))
        except (TypeError, ValueError):
            raise TaskError("Indica cada cuántos minutos")
        if n < MIN_INTERVAL:
            raise TaskError(f"El intervalo mínimo es {MIN_INTERVAL} minutos")
        return {"kind": "interval", "minutes": n}
    if kind == "daily":
        m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(s.get("time", "")))
        if not m:
            raise TaskError("La hora debe ser HH:MM")
        out = {"kind": "daily", "time": f"{int(m.group(1)):02d}:{m.group(2)}"}
        days = s.get("days")
        if days:                                   # días de la semana: 0 = lunes … 6 = domingo
            try:
                d = sorted({int(x) for x in days})
            except (TypeError, ValueError):
                raise TaskError("Días de la semana no válidos")
            if not d or any(x < 0 or x > 6 for x in d):
                raise TaskError("Días de la semana no válidos")
            if len(d) < 7:
                out["days"] = d
        return out
    if kind == "once":
        try:
            at = float(s.get("at"))
        except (TypeError, ValueError):
            raise TaskError("Indica la fecha y hora")
        return {"kind": "once", "at": at}
    raise TaskError("Tipo de programación desconocido")


def next_run(s: dict, after: float) -> float | None:
    """Próxima ejecución estrictamente posterior a `after`, o None si ya no hay (tarea de una sola vez)."""
    if s["kind"] == "interval":
        return after + s["minutes"] * 60
    if s["kind"] == "once":
        return s["at"] if s["at"] > after else None
    hh, mm = (int(x) for x in s["time"].split(":"))
    t = time.localtime(after)
    days = set(s.get("days") or range(7))
    for add in range(0, 8):
        cand = time.mktime((t.tm_year, t.tm_mon, t.tm_mday + add, hh, mm, 0, 0, 0, -1))
        if cand > after and time.localtime(cand).tm_wday in days:
            return cand
    return None


def describe(s: dict) -> str:
    if s["kind"] == "interval":
        return f"cada {s['minutes']} min"
    if s["kind"] == "daily":
        d = s.get("days")
        if not d:
            return f"cada día a las {s['time']}"
        names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        which = "de lunes a viernes" if d == [0, 1, 2, 3, 4] else "los fines de semana" if d == [5, 6] else \
            "los " + ", ".join(names[x] for x in d)
        return f"{which} a las {s['time']}"
    return "una vez, " + time.strftime("%d/%m/%Y %H:%M", time.localtime(s["at"]))


class TaskStore:
    def __init__(self, db):
        self.db = db
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                db._q(stmt)

    def _row(self, r) -> dict:
        d = dict(r)
        d["schedule"] = json.loads(d["schedule"])
        d["enabled"] = bool(d["enabled"])
        d["when"] = describe(d["schedule"])
        return d

    def list(self) -> list[dict]:
        return [self._row(r) for r in self.db._q("SELECT * FROM tasks ORDER BY created").fetchall()]

    def get(self, tid: str) -> dict | None:
        r = self.db._q("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        return self._row(r) if r else None

    def create(self, name: str, prompt: str, schedule, provider: str | None, model: str | None,
               workdir: str | None, mode: str) -> dict:
        if not name.strip() or not prompt.strip():
            raise TaskError("Falta el nombre o el encargo")
        sch = validate_schedule(schedule)
        nxt = next_run(sch, time.time())
        if nxt is None:
            raise TaskError("Esa fecha ya pasó")
        tid = uuid.uuid4().hex[:10]
        self.db._q("INSERT INTO tasks (id,name,prompt,schedule,provider,model,workdir,mode,enabled,next_run,created) "
                   "VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                   (tid, name.strip()[:80], prompt.strip(), json.dumps(sch), provider, model, workdir or None,
                    mode if mode in ("plan", "edits") else "plan", nxt, time.time()))
        return self.get(tid)

    def update(self, tid: str, **f) -> dict | None:
        cur = self.get(tid)
        if not cur:
            return None
        sets, args = [], []
        for k in ("name", "prompt", "provider", "model", "workdir", "mode"):
            if k in f:
                sets.append(f"{k}=?")
                args.append(f[k])
        if "schedule" in f:
            sch = validate_schedule(f["schedule"])
            sets += ["schedule=?", "next_run=?"]
            args += [json.dumps(sch), next_run(sch, time.time())]
        if "enabled" in f:
            sets.append("enabled=?")
            args.append(1 if f["enabled"] else 0)
            if f["enabled"] and "schedule" not in f:
                sets.append("next_run=?")
                args.append(next_run(cur["schedule"], time.time()))
        if sets:
            self.db._q(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", (*args, tid))
        return self.get(tid)

    def delete(self, tid: str) -> None:
        self.db._q("DELETE FROM tasks WHERE id=?", (tid,))

    def due(self, now: float) -> list[dict]:
        return [self._row(r) for r in self.db._q(
            "SELECT * FROM tasks WHERE enabled=1 AND next_run IS NOT NULL AND next_run<=?", (now,)).fetchall()]

    def finish(self, task: dict, status: str, conv: str | None, ran_at: float) -> None:
        nxt = next_run(task["schedule"], ran_at)
        self.db._q("UPDATE tasks SET last_run=?, last_status=?, last_conv=?, next_run=?, enabled=? WHERE id=?",
                   (ran_at, status[:300], conv, nxt, 1 if nxt is not None else 0, task["id"]))


class Scheduler:
    """Bucle que ejecuta las tareas vencidas, de una en una. `runner(task) -> (status, conversation_id)`."""

    def __init__(self, store: TaskStore, runner):
        self.store, self.runner = store, runner
        self.running: set[str] = set()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        # al arrancar: lo que venció hace mucho se salta (se reprograma), lo reciente se ejecuta
        now = time.time()
        for t in self.store.due(now):
            if now - t["next_run"] > CATCH_UP:
                nxt = next_run(t["schedule"], now)
                self.store.db._q("UPDATE tasks SET next_run=?, enabled=? WHERE id=?",
                                 (nxt, 1 if nxt is not None else 0, t["id"]))
        while True:
            try:
                for t in self.store.due(time.time()):
                    await self.run_now(t)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001  (una tarea que falla no debe parar el planificador)
                pass
            await asyncio.sleep(CHECK_EVERY)

    async def run_now(self, task: dict) -> None:
        if task["id"] in self.running:
            return
        self.running.add(task["id"])
        started = time.time()
        try:
            async with self._lock:
                try:
                    status, conv = await self.runner(task)
                except Exception as e:  # noqa: BLE001
                    status, conv = f"Falló: {e}", None
            self.store.finish(task, status, conv, started)
        finally:
            self.running.discard(task["id"])
