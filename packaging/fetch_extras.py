"""Descarga los programas de la «edición completa» en una carpeta G3G3AI-extras (lo usa la integración continua).

    python packaging/fetch_extras.py windows dist/G3G3AI-extras
    python packaging/fetch_extras.py linux   dist/G3G3AI-extras

Incluye: llama.cpp (CPU y Vulkan), stable-diffusion.cpp, whisper.cpp (Windows), Python portátil (python-build-standalone) y, en Windows,
Git portátil (MinGit). Usa la última versión publicada de cada uno. GITHUB_TOKEN, si existe, evita el límite de la API.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# (carpeta destino, repositorio, patrón del archivo) por plataforma
SOURCES = {
    "windows": [
        ("llama-cpu", "ggml-org/llama.cpp", r"bin-win-cpu-x64\.zip$"),
        ("llama-vulkan", "ggml-org/llama.cpp", r"bin-win-vulkan-x64\.zip$"),
        ("sd", "leejet/stable-diffusion.cpp", r"bin-win-(cpu|avx2)-x64\.zip$"),
        ("whisper", "ggml-org/whisper.cpp", r"^whisper-bin-x64\.zip$"),
        ("python", "astral-sh/python-build-standalone", r"cpython-3\.12\.\d+\+\d+-x86_64-pc-windows-msvc-install_only\.tar\.gz$"),
        ("git", "git-for-windows/git", r"^MinGit-[\d.]+-64-bit\.zip$"),
    ],
    "linux": [
        ("llama-cpu", "ggml-org/llama.cpp", r"bin-ubuntu-x64\.(zip|tar\.gz)$"),
        ("llama-vulkan", "ggml-org/llama.cpp", r"bin-ubuntu-vulkan-x64\.(zip|tar\.gz)$"),
        ("sd", "leejet/stable-diffusion.cpp", r"bin-Linux-[\w.-]*x86_64\.zip$"),
        ("python", "astral-sh/python-build-standalone", r"cpython-3\.12\.\d+\+\d+-x86_64-unknown-linux-gnu-install_only\.tar\.gz$"),
    ],
}


def pick(assets: list[dict], pattern: str) -> dict | None:
    rx = re.compile(pattern, re.I)
    found = [a for a in assets if rx.search(a["name"])]
    return sorted(found, key=lambda a: a["name"])[-1] if found else None


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "G3G3AI-build", "Accept": "application/vnd.github+json"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {tok}")
    for attempt in range(4):                     # GitHub devuelve a veces 502/503/504 pasajeros
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            code = getattr(e, "code", None)
            if attempt == 3 or (code is not None and code < 500 and code != 429):
                raise
            print(f"  reintento {attempt + 1} tras: {e}", flush=True)
            time.sleep(5 * (attempt + 1))


def find_asset(repo: str, pattern: str) -> dict | None:
    """El archivo más reciente que encaje, buscando en las últimas publicaciones: la «latest» de un proyecto
    no siempre trae binarios (llama.cpp los publica en cada compilación; whisper.cpp a veces sólo el código)."""
    releases = json.loads(_get(f"https://api.github.com/repos/{repo}/releases?per_page=30"))
    for rel in releases:
        if rel.get("draft"):
            continue
        a = pick(rel.get("assets", []), pattern)
        if a:
            return a
    names = sorted({a["name"] for r in releases[:3] for a in r.get("assets", [])})
    raise RuntimeError(f"ningún archivo encaja con {pattern}; en las últimas hay: {', '.join(names[:40]) or 'nada'}")


def extract(data: bytes, name: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(dest)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            t.extractall(dest, filter="data")
    # si todo quedó dentro de una sola carpeta, se sube un nivel (dest/python/python.exe en vez de dest/python/python/…)
    kids = list(dest.iterdir())
    if len(kids) == 1 and kids[0].is_dir():
        inner = kids[0]
        for p in inner.iterdir():
            shutil.move(str(p), dest / p.name)
        inner.rmdir()


def main(platform_name: str, out: str) -> int:
    dest = Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    failed = []
    for sub, repo, pattern in SOURCES[platform_name]:
        try:
            a = find_asset(repo, pattern)
            print(f"· {sub}: {a['name']} ({a['size'] // 1_000_000} MB)", flush=True)
            extract(_get(a["browser_download_url"]), a["name"], dest / sub)
        except Exception as e:  # noqa: BLE001  (lo que falle se omite; el resto de la edición sigue valiendo)
            failed.append(f"{sub}: {e}")
            print(f"! {sub}: {e}", flush=True)
    (dest / "LEEME.txt").write_text(
        "Programas incluidos en la edición completa de G3G3AI. La app los usa automáticamente;\n"
        "no hace falta instalarlos. Cada uno conserva su licencia (MIT / PSF / GPL en el caso de Git).\n", encoding="utf-8")
    if failed:
        print("Omitidos:\n  " + "\n  ".join(failed))
    return 0 if len(failed) < len(SOURCES[platform_name]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
