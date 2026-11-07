"""Diagnóstico de juegos de Steam (SteamOS / Linux con Proton, y Windows).

Lee la estructura de Steam para que la IA pueda averiguar por qué un juego no funciona:
bibliotecas, juegos instalados, versión de Proton, opciones de lanzamiento, prefijo de Wine
(compatdata), registros de Proton y de Steam, y archivos de configuración del juego.
De config.vdf (que contiene datos de la sesión de Steam) sólo se extrae la sección CompatToolMapping.
"""
from __future__ import annotations

import os
import platform
import re
import sys
import time
from pathlib import Path

HOME = Path.home()
CONFIG_EXT = {".ini", ".cfg", ".conf", ".json", ".xml", ".yaml", ".yml", ".toml", ".txt", ".log", ".lua", ".properties"}
SKIP_DIRS = {"__pycache__", "shadercache", "Shaders", "ShaderCache", "Movies", "Videos", "Audio", "Sound", "Music"}


# --- VDF (KeyValues de Valve) ----------------------------------------------------------------
TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text: str) -> dict:
    """Parser mínimo de VDF de texto: {"clave": "valor" | {...}}. Claves en minúsculas para comparar."""
    stack = [{}]
    key = None
    for m in TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            d = {}
            if key is not None:
                stack[-1][key.lower()] = d
            stack.append(d)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = s.replace('\\\\', '\\')
        else:
            stack[-1][key.lower()] = s.replace('\\\\', '\\')
            key = None
    return stack[0]


def _read_vdf(path: Path) -> dict:
    try:
        return parse_vdf(path.read_text("utf-8", errors="replace"))
    except OSError:
        return {}


def _get(d: dict, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k.lower())
        if d is None:
            return default
    return d


# --- Localizar Steam ----------------------------------------------------------------------
def steam_roots(cfg=None) -> list[Path]:
    cands = []
    if cfg is not None and cfg["steam_dir"]:
        cands.append(Path(cfg["steam_dir"]).expanduser())
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
        cands += [Path(pf) / "Steam", Path(r"C:\Program Files\Steam")]
    else:
        cands += [HOME / ".local/share/Steam", HOME / ".steam/steam", HOME / ".steam/root",
                  HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    out = []
    for c in cands:
        try:
            r = c.resolve()
        except OSError:
            continue
        if (r / "steamapps").is_dir() and r not in out:
            out.append(r)
    return out


def libraries(root: Path) -> list[Path]:
    libs = [root]
    data = _read_vdf(root / "steamapps" / "libraryfolders.vdf")
    for v in (data.get("libraryfolders") or {}).values():
        p = v.get("path") if isinstance(v, dict) else None
        if p and Path(p).is_dir() and Path(p).resolve() not in [l.resolve() for l in libs]:
            libs.append(Path(p))
    return libs


def compat_mapping(root: Path) -> dict[str, str]:
    """appid -> herramienta de compatibilidad (p.ej. proton_9, GE-Proton9-20). «0» = predeterminada."""
    data = _read_vdf(root / "config" / "config.vdf")
    m = _get(data, "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping") or {}
    return {k: v.get("name", "") for k, v in m.items() if isinstance(v, dict) and v.get("name")}


def launch_options(root: Path) -> dict[str, str]:
    out = {}
    for lc in (root / "userdata").glob("*/config/localconfig.vdf"):
        data = _read_vdf(lc)
        apps = _get(data, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps") or {}
        for appid, v in apps.items():
            if isinstance(v, dict) and v.get("launchoptions"):
                out[appid] = v["launchoptions"]
    return out


def compat_tools(root: Path) -> list[str]:
    names = []
    for lib in libraries(root):
        names += [p.name for p in (lib / "steamapps" / "common").glob("Proton*") if p.is_dir()]
    for d in (root / "compatibilitytools.d", HOME / ".steam/root/compatibilitytools.d"):
        if d.is_dir():
            names += [p.name for p in d.iterdir() if p.is_dir()]
    return sorted(set(names))


# --- Juegos -------------------------------------------------------------------------------
def list_games(cfg=None) -> list[dict]:
    games = []
    for root in steam_roots(cfg):
        mapping = compat_mapping(root)
        for lib in libraries(root):
            for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
                st = _read_vdf(acf).get("appstate") or {}
                appid = st.get("appid") or acf.stem.split("_")[-1]
                name = st.get("name", "")
                if not name or re.match(r"(Proton|Steam Linux Runtime|Steamworks Common)", name):
                    continue
                inst = lib / "steamapps" / "common" / st.get("installdir", "")
                games.append({
                    "appid": appid, "name": name, "install_dir": str(inst), "installed": inst.is_dir(),
                    "library": str(lib), "size_gb": round(int(st.get("sizeondisk") or 0) / 1e9, 2),
                    "state_flags": st.get("stateflags"), "compat_tool": mapping.get(appid, ""),
                    "compatdata": str(lib / "steamapps" / "compatdata" / appid), "steam_root": str(root),
                })
    games.sort(key=lambda g: g["name"].lower())
    return games


def find_game(cfg, query: str) -> dict | None:
    q = str(query).strip().lower()
    games = list_games(cfg)
    for g in games:
        if g["appid"] == q:
            return g
    exact = [g for g in games if g["name"].lower() == q]
    if exact:
        return exact[0]
    partial = [g for g in games if q in g["name"].lower()]
    return partial[0] if partial else None


def game_write_roots(cfg) -> list[Path]:
    """Carpetas de juegos que la IA puede modificar (siempre con confirmación) si está activado."""
    if not cfg["ai_game_write"]:
        return []
    out = []
    for root in steam_roots(cfg):
        for lib in libraries(root):
            out += [lib / "steamapps" / "common", lib / "steamapps" / "compatdata"]
    return out


def _tail(path: Path, lines: int = 60, grep: str | None = None) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    rows = text.splitlines()
    if grep:
        rows = [r for r in rows if grep in r]
    return "\n".join(rows[-lines:])


def _interesting_files(base: Path, limit: int = 40, max_depth: int = 5) -> list[tuple[float, str, int]]:
    found = []
    if not base.is_dir():
        return found
    base_depth = len(base.parts)
    for dirpath, dirnames, filenames in os.walk(base):
        depth = len(Path(dirpath).parts) - base_depth
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and depth < max_depth]
        for fn in filenames:
            p = Path(dirpath) / fn
            low = fn.lower()
            if p.suffix.lower() in CONFIG_EXT or "crash" in low or low.endswith(".dmp"):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size < 5_000_000:
                    found.append((st.st_mtime, str(p), st.st_size))
    found.sort(reverse=True)
    return found[:limit]


def diagnose(cfg, query: str) -> str:
    roots = steam_roots(cfg)
    if not roots:
        return "No se ha encontrado Steam en este equipo."
    g = find_game(cfg, query)
    if not g:
        return f"No se encontró ningún juego instalado que coincida con «{query}». Usa steam_games para ver la lista."
    root = Path(g["steam_root"])
    lines = [f"# {g['name']} (appid {g['appid']})",
             f"Sistema: {platform.system()} {platform.machine()}" + (f" · {_os_name()}" if _os_name() else ""),
             f"Instalado en: {g['install_dir']}" + ("" if g["installed"] else "  [¡LA CARPETA NO EXISTE!]"),
             f"Tamaño: {g['size_gb']} GB · StateFlags: {g['state_flags']} (4 = instalado y actualizado)"]
    if sys.platform != "win32":
        tool = g["compat_tool"] or "(la predeterminada de Steam o ninguna: juego nativo de Linux o sin forzar Proton)"
        lines.append(f"Herramienta de compatibilidad: {tool}")
        lines.append(f"Versiones de Proton disponibles: {', '.join(compat_tools(root)) or 'ninguna encontrada'}")
        cd = Path(g["compatdata"])
        if cd.is_dir():
            pfx = cd / "pfx"
            lines.append(f"Prefijo de Wine: {cd} ({'con pfx' if pfx.is_dir() else 'SIN pfx: el juego quizá nunca llegó a arrancar'})")
            ver = cd / "version"
            if ver.is_file():
                lines.append(f"Proton que creó el prefijo: {ver.read_text(errors='replace').strip()}")
        else:
            lines.append("Prefijo de Wine: no existe (normal si es nativo de Linux o si nunca se ha ejecutado con Proton)")
    lo = launch_options(root).get(g["appid"])
    lines.append(f"Opciones de lanzamiento: {lo or '(ninguna)'}")

    if sys.platform != "win32":
        plog = HOME / f"steam-{g['appid']}.log"
        if plog.is_file():
            age = (time.time() - plog.stat().st_mtime) / 3600
            lines.append(f"\n## Registro de Proton ({plog}, hace {age:.1f} h) — últimas líneas relevantes")
            text = _tail(plog, 400)
            relevant = [l for l in text.splitlines() if re.search(r"err:|fixme:d3d|warn:seh|exception|crash|"
                                                                    r"failed|cannot|not found|vkd3d|dxvk", l, re.I)]
            lines.append("\n".join(relevant[-50:]) or _tail(plog, 40))
        else:
            lines.append("\nNo hay registro de Proton. Para generarlo: en Steam → Propiedades del juego → Opciones de "
                         "lanzamiento pon `PROTON_LOG=1 %command%`, ejecuta el juego una vez y vuelve a diagnosticar.")
    logs = root / "logs"
    for name in ("compat_log.txt", "console_log.txt", "content_log.txt", "stderr.txt"):
        t = _tail(logs / name, 15, grep=g["appid"])
        if t:
            lines.append(f"\n## {name} (líneas con el appid)\n{t}")

    files = _interesting_files(Path(g["install_dir"]), 25)
    pfx_users = Path(g["compatdata"]) / "pfx" / "drive_c" / "users" / "steamuser"
    for sub in ("AppData/Local", "AppData/Roaming", "AppData/LocalLow", "Documents", "Saved Games"):
        files += _interesting_files(pfx_users / sub, 15, 4)
    if files:
        files.sort(reverse=True)
        lines.append("\n## Archivos de configuración / registros / volcados (más recientes primero)")
        for mtime, p, size in files[:45]:
            lines.append(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))}  {size:>8} B  {p}")
    lines.append("\nPuedes leer estos archivos con read_file. Antes de modificar algo, explica el cambio; "
                 "se guarda una copia de seguridad automática del archivo original.")
    return "\n".join(lines)


def games_summary(cfg, query: str = "") -> str:
    games = list_games(cfg)
    if not steam_roots(cfg):
        return "No se ha encontrado Steam en este equipo."
    q = (query or "").lower()
    if q:
        games = [g for g in games if q in g["name"].lower() or q == g["appid"]]
    if not games:
        return "No hay juegos instalados que coincidan."
    rows = [f"{g['name']} — appid {g['appid']} — {g['size_gb']} GB"
            + (f" — {g['compat_tool']}" if g["compat_tool"] else "") + ("" if g["installed"] else " — (carpeta no encontrada)")
            for g in games[:200]]
    return f"{len(games)} juegos instalados:\n" + "\n".join(rows)


def _os_name() -> str:
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    return ""


def system_hint() -> str:
    """Contexto para la IA sobre el sistema (SteamOS, ARM...)."""
    parts = []
    osn = _os_name()
    if "steamos" in osn.lower() or Path("/usr/bin/steamos-readonly").exists():
        parts.append(f"El equipo usa {osn or 'SteamOS'}: la raíz del sistema es de sólo lectura; instala programas con "
                     "`flatpak install --user` o en la carpeta personal (pip --user, ~/.local/bin) en vez de pacman, "
                     "salvo que el usuario pida expresamente desbloquear el sistema (steamos-readonly disable).")
    if platform.machine().lower() in ("aarch64", "arm64") and sys.platform.startswith("linux"):
        parts.append("La CPU es ARM64: los juegos x86 se ejecutan mediante una capa de traducción (FEX-Emu/box64) "
                     "además de Proton; tenlo en cuenta al diagnosticar fallos de rendimiento o de arranque.")
    if steam_roots():
        parts.append("Para problemas con juegos usa steam_games y game_diagnostics antes de proponer cambios. "
                     "Opciones de lanzamiento útiles: PROTON_LOG=1 %command% para registrar; "
                     "PROTON_USE_WINED3D=1 si falla DXVK; cambiar la versión de Proton en Propiedades → Compatibilidad.")
    return " ".join(parts)
