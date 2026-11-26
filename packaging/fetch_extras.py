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
import urllib.request
import zipfile
from pathlib import Path

# (carpeta destino, repositorio, patrón del archivo) por plataforma
SOURCES = {
    "windows": [
        ("llama-cpu", "ggml-org/llama.cpp", r"bin-win-cpu-x64\.zip$"),
        ("llama-vulkan", "ggml-org/llama.cpp", r"bin-win-vulkan-x64\.zip$"),
        ("sd", "leejet/stable-diffusion.cpp", r"bin-win-avx2-x64\.zip$"),
        ("whisper", "ggml-org/whisper.cpp", r"^whisper-bin-x64\.zip$"),
        ("python", "astral-sh/python-build-standalone", r"cpython-3\.12\.\d+\+\d+-x86_64-pc-windows-msvc-install_only\.tar\.gz$"),
        ("git", "git-for-windows/git", r"^MinGit-[\d.]+-64-bit\.zip$"),
    ],
    "linux": [
        ("llama-cpu", "ggml-org/llama.cpp", r"bin-ubuntu-x64\.(zip|tar\.gz)$"),
        ("llama-vulkan", "ggml-org/llama.cpp", r"bin-ubuntu-vulkan-x64\.(zip|tar\.gz)$"),
        ("sd", "leejet/stable-diffusion.cpp", r"bin-Linux.*x86_64.*\.zip$"),
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
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def latest_assets(repo: str) -> list[dict]:
    return json.loads(_get(f"https://api.github.com/repos/{repo}/releases/latest")).get("assets", [])


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
            a = pick(latest_assets(repo), pattern)
            if not a:
                raise RuntimeError(f"no hay ningún archivo que encaje con {pattern}")
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
