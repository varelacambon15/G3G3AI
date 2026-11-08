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


# --- Análisis de nombres y etiquetas de modelos ------------------------------------------------
MOE_RE = re.compile(r"(\d+(?:\.\d+)?)[bB][-_.]?[aA](\d+(?:\.\d+)?)[bB]")          # 30B-A3B
EXPERTS_RE = re.compile(r"(\d+)x(\d+(?:\.\d+)?)[bB](?![a-z])")                       # 8x7B
SIZE_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z])")                  # 4B, 0.6B, 8b
CAPS = {
    "vision": re.compile(r"(\bvl\b|-vl|vision|llava|pixtral|minicpm-v|gemma-?3(?!.*\b1b\b)|gemma-?4|"
                         r"moondream|smolvlm|internvl|image-text)", re.I),
    "code": re.compile(r"(coder|codestral|devstral|starcoder|codegemma|codellama|\bcode\b)", re.I),
    "reasoning": re.compile(r"(\br1\b|-r1|reason|think|qwq|magistral|\bo1\b)", re.I),
    "image": re.compile(r"(stable-?diffusion|sd-?turbo|sdxl|sd3|\bflux\b|sd1\.5|sd-?1)", re.I),
}
Q4_GB_PER_B = 0.6  # Q4_K_M ≈ 4,8 bits por parámetro


def analyze(repo_id: str, tags=(), pipeline: str | None = None) -> dict:
    """Tamaño (en miles de millones de parámetros), MoE y capacidades a partir del nombre y las etiquetas."""
    name = repo_id.split("/")[-1]
    text = " ".join([name, pipeline or "", *[t for t in tags if ":" not in t]])
    params = active = None
    moe = False
    if (m := MOE_RE.search(name)):
        params, active, moe = float(m.group(1)), float(m.group(2)), True
    elif (m := EXPERTS_RE.search(name)):
        params, moe = round(int(m.group(1)) * float(m.group(2)) * 0.8, 1), True
    else:
        sizes = [float(x) for x in SIZE_RE.findall(name) if 0.05 <= float(x) <= 1000]
        params = sizes[0] if sizes else None
    caps = [k for k, rx in CAPS.items() if rx.search(text)]
    if pipeline == "image-text-to-text" and "vision" not in caps:
        caps.append("vision")
    return {"params": params, "active": active, "moe": moe, "caps": caps,
            "est_gb": round(params * Q4_GB_PER_B + 0.3, 1) if params and "image" not in caps else None}


QUANT_INFO = [  # (prefijo, descripción, nivel de calidad 1-6)
    ("F32", "Original sin comprimir (enorme)", 6), ("BF16", "Original (enorme)", 6), ("F16", "Original (enorme)", 6),
    ("Q8", "Casi sin pérdida, grande", 5), ("Q6", "Muy alta calidad", 5), ("Q5", "Alta calidad", 4),
    ("Q4_K_M", "Equilibrio recomendado", 3), ("IQ4", "Buena calidad, algo más pequeño", 3),
    ("Q4", "Buena calidad, algo más pequeño", 3), ("IQ3", "Pequeño, pierde algo de calidad", 2),
    ("Q3", "Pequeño, pierde algo de calidad", 2), ("IQ2", "Mínimo: calidad baja", 1), ("Q2", "Mínimo: calidad baja", 1),
    ("IQ1", "Mínimo: calidad muy baja", 1),
]


def quant_info(quant: str) -> tuple[str, int]:
    q = (quant or "").upper()
    for prefix, label, level in QUANT_INFO:
        if q.startswith(prefix):
            return label, level
    return "", 0


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
    SORTS = {"downloads": "downloads", "likes": "likes", "updated": "lastModified", "trending": "trendingScore"}

    async def _list_models(self, query: str, sort: str, limit: int) -> list[dict]:
        base = [("search", query), ("filter", "gguf"), ("sort", self.SORTS.get(sort, "downloads")),
                ("direction", "-1"), ("limit", str(limit))]
        expand = [("expand[]", f) for f in ("downloads", "likes", "lastModified", "tags", "pipeline_tag", "trendingScore")]
        async with httpx.AsyncClient(timeout=20, headers=_headers(self.cfg["hf_token"])) as c:
            r = await c.get(f"{HF}/api/models", params=base + expand)
            if r.status_code == 400:  # por si la API no acepta «expand»: búsqueda básica
                r = await c.get(f"{HF}/api/models", params=base)
            r.raise_for_status()
        return r.json()

    async def search(self, query: str, sort: str = "downloads", limit: int = 60) -> list[dict]:
        local = {m["repo"] for m in self.local_models()}
        out = []
        for m in await self._list_models(query, sort, limit):
            rid = m.get("id") or m.get("modelId")
            if not rid:
                continue
            info = analyze(rid, m.get("tags") or [], m.get("pipeline_tag"))
            out.append({"id": rid, "author": rid.split("/")[0], "name": rid.split("/")[-1],
                        "downloads": m.get("downloads", 0), "likes": m.get("likes", 0),
                        "updated": m.get("lastModified"), "trending": m.get("trendingScore"),
                        "pipeline": m.get("pipeline_tag"), "downloaded": rid in local,
                        "url": f"{HF}/{rid}", **info})
        return out

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
        dest = self.models_dir / repo.replace("/", "__")
        for g in out:
            g["files"].sort()
            g["mmproj"] = "mmproj" in g["name"].lower()
            g["quality"], g["level"] = quant_info(g["quant"]) if not g["mmproj"] else ("Proyector de visión", 0)
            g["downloaded"] = all((dest / Path(f).name).exists() for f in g["files"])
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
