"""Búsqueda y descarga de modelos GGUF desde Hugging Face."""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path

import httpx

HF = "https://huggingface.co"
SPLIT_RE = re.compile(r"^(.*)-(\d{5})-of-(\d{5})\.gguf$")


def _headers(token: str | None) -> dict:
    h = {"User-Agent": "g3g3ai/0.1"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def quant_of(filename: str) -> str:
    m = re.search(r"(IQ\d_\w+|Q\d_K_[SML]|Q\d_K|Q\d_\d|Q\d|F16|BF16|F32)", filename, re.I)
    return m.group(1).upper() if m else ""


class Hub:
    def __init__(self, cfg):
        self.cfg = cfg
        self.downloads: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def models_dir(self) -> Path:
        p = Path(self.cfg["models_dir"]).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Búsqueda -----------------------------------------------------------------
    async def search(self, query: str, limit: int = 30) -> list[dict]:
        params = {"search": query, "filter": "gguf", "sort": "downloads", "direction": "-1", "limit": limit}
        async with httpx.AsyncClient(timeout=20, headers=_headers(self.cfg["hf_token"])) as c:
            r = await c.get(f"{HF}/api/models", params=params)
            r.raise_for_status()
        return [
            {"id": m["id"], "downloads": m.get("downloads", 0), "likes": m.get("likes", 0),
             "updated": m.get("lastModified"), "pipeline": m.get("pipeline_tag")}
            for m in r.json()
        ]

    async def files(self, repo: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=20, headers=_headers(self.cfg["hf_token"])) as c:
            r = await c.get(f"{HF}/api/models/{repo}/tree/main", params={"recursive": "true"})
            r.raise_for_status()
        groups: dict[str, dict] = {}
        for f in r.json():
            path = f.get("path", "")
            if f.get("type") != "file" or not path.lower().endswith(".gguf"):
                continue
            size = (f.get("lfs") or {}).get("size") or f.get("size") or 0
            m = SPLIT_RE.match(path)
            key = m.group(1) + ".gguf" if m else path
            g = groups.setdefault(key, {"name": key, "files": [], "size": 0, "quant": quant_of(key)})
            g["files"].append(path)
            g["size"] += size
        out = sorted(groups.values(), key=lambda g: g["size"])
        for g in out:
            g["files"].sort()
            g["mmproj"] = "mmproj" in g["name"].lower()
        return out

    # Descargas ----------------------------------------------------------------
    def start(self, repo: str, files: list[str]) -> dict:
        did = uuid.uuid4().hex[:10]
        dest_dir = self.models_dir / repo.replace("/", "__")
        d = {
            "id": did, "repo": repo, "files": files, "dest": str(dest_dir / Path(files[0]).name),
            "total": 0, "done": 0, "speed": 0.0, "status": "pending", "error": None, "started": time.time(),
        }
        self.downloads[did] = d
        self._tasks[did] = asyncio.create_task(self._run(d, dest_dir))
        return d

    async def _run(self, d: dict, dest_dir: Path):
        dest_dir.mkdir(parents=True, exist_ok=True)
        d["status"] = "downloading"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=True,
                                         headers=_headers(self.cfg["hf_token"])) as c:
                # Tamaño total
                for f in d["files"]:
                    r = await c.head(f"{HF}/{d['repo']}/resolve/main/{f}")
                    d["total"] += int(r.headers.get("content-length") or r.headers.get("x-linked-size") or 0)
                for f in d["files"]:
                    await self._download_one(c, d, f, dest_dir / Path(f).name)
            d["status"] = "done"
        except asyncio.CancelledError:
            d["status"] = "cancelled"
        except Exception as e:  # noqa: BLE001
            d["status"], d["error"] = "error", str(e)

    async def _download_one(self, c: httpx.AsyncClient, d: dict, f: str, target: Path):
        if target.exists():
            d["done"] += target.stat().st_size
            return
        part = target.with_name(target.name + ".part")
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        url = f"{HF}/{d['repo']}/resolve/main/{f}"
        async with c.stream("GET", url, headers=headers) as r:
            if r.status_code == 416:  # ya completo
                part.rename(target)
                d["done"] += have
                return
            r.raise_for_status()
            if have and r.status_code != 206:
                have = 0  # el servidor no admite reanudar
            d["done"] += have
            t0, b0 = time.time(), d["done"]
            with open(part, "ab" if have else "wb") as out:
                async for chunk in r.aiter_bytes(1 << 20):
                    out.write(chunk)
                    d["done"] += len(chunk)
                    dt = time.time() - t0
                    if dt > 1:
                        d["speed"] = (d["done"] - b0) / dt
                        t0, b0 = time.time(), d["done"]
        part.rename(target)

    def cancel(self, did: str) -> None:
        t = self._tasks.get(did)
        if t and not t.done():
            t.cancel()
        elif did in self.downloads:
            del self.downloads[did]

    # Modelos locales -------------------------------------------------------------
    def local_models(self) -> list[dict]:
        out = []
        for p in sorted(self.models_dir.rglob("*.gguf")):
            m = SPLIT_RE.match(p.name)
            if m and m.group(2) != "00001":
                continue  # sólo mostramos la primera parte de modelos divididos
            size = p.stat().st_size
            if m:
                size = sum(x.stat().st_size for x in p.parent.glob(f"{m.group(1)}-*-of-{m.group(3)}.gguf"))
            rel = p.relative_to(self.models_dir)
            is_mmproj = "mmproj" in p.name.lower()
            out.append({
                "name": p.name, "path": str(p), "size": size,
                "repo": rel.parts[0].replace("__", "/") if len(rel.parts) > 1 else "",
                "quant": quant_of(p.name), "mmproj": is_mmproj,
                "vision": not is_mmproj and any(p.parent.glob("*mmproj*.gguf")),
            })
        return out

    def delete_local(self, path: str) -> None:
        p = Path(path).resolve()
        if not p.is_relative_to(self.models_dir.resolve()) or p.suffix != ".gguf":
            raise ValueError("Ruta no válida")
        m = SPLIT_RE.match(p.name)
        targets = list(p.parent.glob(f"{m.group(1)}-*-of-{m.group(3)}.gguf")) if m else [p]
        for t in targets:
            t.unlink(missing_ok=True)
        try:
            p.parent.rmdir()  # borra la carpeta si quedó vacía
        except OSError:
            pass
