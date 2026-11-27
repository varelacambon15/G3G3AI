"""Plugins compatibles con el formato de los plugins de Claude Code.

Un plugin es una carpeta con cualquiera de estas piezas:
    .claude-plugin/plugin.json   nombre, descripción, versión, autor
    skills/<habilidad>/SKILL.md   habilidades: instrucciones que la IA carga cuando la tarea encaja
                                  (cabecera YAML con «name» y «description»; puede traer archivos de apoyo)
    commands/<comando>.md         comandos «/comando» (el texto es la instrucción; $ARGUMENTS = lo que escribas detrás)
    .mcp.json                     conectores MCP que aporta el plugin ({"mcpServers": {...}})

Se instalan desde un repositorio de GitHub («usuario/repo», o un enlace, también a una subcarpeta) o desde una
carpeta del equipo. Si el repositorio es un «marketplace» (.claude-plugin/marketplace.json), se instalan los
plugins que declara. Se guardan en la carpeta de configuración de G3G3AI, en «plugins».
"""
from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

MAX_ZIP = 60 * 1024 * 1024
MAX_SKILL = 60_000


class PluginError(Exception):
    pass


def plugins_dir() -> Path:
    from .config import CONFIG_DIR
    d = CONFIG_DIR / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _frontmatter(text: str) -> tuple[dict, str]:
    """Cabecera YAML sencilla («clave: valor») y cuerpo."""
    m = re.match(r"^﻿?---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if mm:
            v = mm.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            meta[mm.group(1).lower()] = v
    return meta, m.group(2)


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-.")[:60] or "plugin"


def read_plugin(root: Path) -> dict:
    meta = {}
    for f in (root / ".claude-plugin" / "plugin.json", root / "plugin.json"):
        if f.is_file():
            try:
                meta = json.loads(f.read_text("utf-8"))
            except ValueError:
                meta = {}
            break
    author = meta.get("author")
    info = {"id": root.name, "name": str(meta.get("name") or root.name), "description": str(meta.get("description") or ""),
            "version": str(meta.get("version") or ""), "author": author.get("name") if isinstance(author, dict) else (author or ""),
            "path": str(root), "skills": [], "commands": [], "mcp": []}
    for sk in sorted((root / "skills").glob("*/SKILL.md")) if (root / "skills").is_dir() else []:
        fm, body = _frontmatter(sk.read_text("utf-8", errors="replace"))
        info["skills"].append({"name": fm.get("name") or sk.parent.name, "description": fm.get("description", "")[:400],
                               "path": str(sk)})
    cmd_dir = root / "commands"
    for c in sorted(cmd_dir.rglob("*.md")) if cmd_dir.is_dir() else []:
        fm, body = _frontmatter(c.read_text("utf-8", errors="replace"))
        name = ":".join(c.relative_to(cmd_dir).with_suffix("").parts)
        info["commands"].append({"name": name, "description": fm.get("description") or body.strip().split("\n")[0][:120],
                                 "hint": fm.get("argument-hint", ""), "path": str(c)})
    info["mcp"] = [s["name"] for s in mcp_servers_of(root, info["name"])]
    return info


def mcp_servers_of(root: Path, pname: str) -> list[dict]:
    """Servidores de «.mcp.json» con el formato de mcp.parse_servers ({name, argv, env} o {name, url, headers})."""
    f = root / ".mcp.json"
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text("utf-8"))
    except ValueError:
        return []
    servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
    out = []

    def sub(v):
        return str(v).replace("${CLAUDE_PLUGIN_ROOT}", str(root)).replace("${G3G3AI_PLUGIN_ROOT}", str(root))
    for name, s in (servers or {}).items():
        if not isinstance(s, dict):
            continue
        n = f"{_safe_name(pname)}__{_safe_name(name)}"
        if s.get("url"):
            out.append({"name": n, "url": sub(s["url"]), "headers": {k: sub(v) for k, v in (s.get("headers") or {}).items()}})
        elif s.get("command"):
            out.append({"name": n, "argv": [sub(s["command"])] + [sub(a) for a in s.get("args") or []],
                        "env": {k: sub(v) for k, v in (s.get("env") or {}).items()}})
    return out


class Plugins:
    def __init__(self, cfg):
        self.cfg = cfg

    def _disabled(self) -> set:
        return set(self.cfg["plugins_disabled"] or [])

    def list(self) -> list[dict]:
        out = []
        for d in sorted(plugins_dir().iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                p = read_plugin(d)
                p["enabled"] = d.name not in self._disabled()
                out.append(p)
        return out

    def enabled(self) -> list[dict]:
        return [p for p in self.list() if p["enabled"]]

    def skills(self) -> list[dict]:
        return [{**s, "plugin": p["name"]} for p in self.enabled() for s in p["skills"]]

    def commands(self) -> list[dict]:
        return [{**c, "plugin": p["name"]} for p in self.enabled() for c in p["commands"]]

    def mcp(self) -> list[dict]:
        out = []
        for p in self.enabled():
            out += mcp_servers_of(Path(p["path"]), p["name"])
        return out

    def skill_text(self, name: str, file: str | None = None) -> str:
        sk = next((s for s in self.skills() if s["name"].lower() == (name or "").strip().lower()), None)
        if not sk:
            names = ", ".join(s["name"] for s in self.skills()) or "ninguna"
            return f"Error: no hay ninguna habilidad «{name}». Disponibles: {names}."
        base = Path(sk["path"]).parent
        if file:
            target = (base / file).resolve()
            if base.resolve() not in target.parents or not target.is_file():
                return f"Error: «{file}» no es un archivo de la habilidad «{sk['name']}»."
            return target.read_text("utf-8", errors="replace")[:MAX_SKILL]
        _, body = _frontmatter(Path(sk["path"]).read_text("utf-8", errors="replace"))
        extra = [str(f.relative_to(base)) for f in sorted(base.rglob("*")) if f.is_file() and f.name != "SKILL.md"][:60]
        return (f"Habilidad «{sk['name']}» (plugin {sk['plugin']}). Sigue estas instrucciones:\n\n{body.strip()[:MAX_SKILL]}"
                + (f"\n\nArchivos de apoyo (léelos con skill name=«{sk['name']}» file=«ruta» si los necesitas): "
                   + ", ".join(extra) if extra else ""))

    def command_prompt(self, name: str, args: str = "") -> str | None:
        c = next((c for c in self.commands() if c["name"].lower() == name.lower()), None)
        if not c:
            return None
        _, body = _frontmatter(Path(c["path"]).read_text("utf-8", errors="replace"))
        body = body.strip()
        body = body.replace("$ARGUMENTS", args) if "$ARGUMENTS" in body else (body + (f"\n\n{args}" if args else ""))
        for i, a in enumerate(args.split(), 1):
            body = body.replace(f"${i}", a)
        return body

    # --- Instalar / quitar --------------------------------------------------------
    def set_enabled(self, pid: str, on: bool) -> None:
        dis = self._disabled()
        dis.discard(pid) if on else dis.add(pid)
        self.cfg.set("plugins_disabled", sorted(dis))

    def remove(self, pid: str) -> None:
        d = plugins_dir() / _safe_name(pid)
        if d.is_dir() and d.parent == plugins_dir():
            shutil.rmtree(d)
        self.set_enabled(pid, True)

    def install(self, source: str, token: str = "") -> list[str]:
        """Instala desde «usuario/repo», un enlace de GitHub (con /tree/rama/subcarpeta) o una carpeta local."""
        source = (source or "").strip()
        if not source:
            raise PluginError("Indica un repositorio de GitHub (usuario/repo) o una carpeta.")
        local = Path(source).expanduser()
        if local.is_dir():
            return self._install_from(local)
        m = re.match(r"^(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^/]+)(/.*)?)?/?$", source)
        if not m:
            raise PluginError("No reconozco el origen: escribe «usuario/repositorio», un enlace de GitHub o una carpeta.")
        owner, repo, ref, sub = m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip("/")
        import httpx
        h = {"User-Agent": "G3G3AI", **({"Authorization": f"Bearer {token}"} if token else {})}
        url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref or ''}".rstrip("/")
        try:
            r = httpx.get(url, headers=h, follow_redirects=True, timeout=60)
        except httpx.HTTPError as e:
            raise PluginError(f"No se pudo descargar de GitHub: {e}") from e
        if r.status_code == 404:
            raise PluginError(f"No encuentro el repositorio {owner}/{repo} (si es privado, añade tu token de GitHub en Conectores).")
        if r.status_code >= 400:
            raise PluginError(f"GitHub respondió {r.status_code} al descargar {owner}/{repo}.")
        if len(r.content) > MAX_ZIP:
            raise PluginError("El repositorio es demasiado grande para un plugin.")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for info in z.infolist():
                    dest = (t / info.filename).resolve()
                    if t.resolve() not in dest.parents and dest != t.resolve():
                        raise PluginError("El archivo descargado tiene rutas no válidas.")
                z.extractall(t)
            tops = [d for d in t.iterdir() if d.is_dir()]
            root = tops[0] if len(tops) == 1 else t
            if sub:
                root = root / sub
                if not root.is_dir():
                    raise PluginError(f"No existe la carpeta «{sub}» en el repositorio.")
            return self._install_from(root, default_name=repo if not sub else Path(sub).name)

    def _install_from(self, root: Path, default_name: str | None = None) -> list[str]:
        roots = self._find_plugins(root)
        if not roots:
            raise PluginError("Ahí no hay ningún plugin (ni habilidades en skills/, ni comandos en commands/, ni .mcp.json).")
        done = []
        for r in roots:
            meta = read_plugin(r)
            has_meta = (r / ".claude-plugin" / "plugin.json").is_file() or (r / "plugin.json").is_file()
            name = _safe_name(meta["name"] if has_meta else (default_name if r == root and default_name else r.name))
            dest = plugins_dir() / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(r, dest, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"))
            done.append(name)
        return done

    @staticmethod
    def _is_plugin(d: Path) -> bool:
        return ((d / ".claude-plugin" / "plugin.json").is_file() or (d / "skills").is_dir() or (d / "commands").is_dir()
                or (d / ".mcp.json").is_file())

    def _find_plugins(self, root: Path) -> list[Path]:
        mk = root / ".claude-plugin" / "marketplace.json"
        if mk.is_file():
            try:
                data = json.loads(mk.read_text("utf-8"))
            except ValueError:
                data = {}
            out = []
            for p in data.get("plugins") or []:
                src = p.get("source") if isinstance(p, dict) else None
                if isinstance(src, str):
                    d = (root / src).resolve()
                    if d.is_dir() and root.resolve() in [d, *d.parents] and self._is_plugin(d):
                        out.append(d)
            if out:
                return out
        if self._is_plugin(root):
            return [root]
        return [d for d in sorted(root.iterdir()) if d.is_dir() and self._is_plugin(d)][:30]
