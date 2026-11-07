"""Generación de imágenes.

Proveedores:
  - API compatible con OpenAI (/images/generations): OpenAI (gpt-image-1), Gemini (imagen-*),
    Together, etc.
  - OpenRouter y similares (/chat/completions con modalities=["image","text"]): p.ej.
    google/gemini-2.5-flash-image.
  - Local: stable-diffusion.cpp (ejecutable «sd» / «sd-cli») con un modelo GGUF o safetensors.
Las imágenes se guardan en la carpeta configurada (por defecto ~/G3G3AI-imagenes).
"""
from __future__ import annotations

import asyncio
import base64
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SD_NAMES = ["sd-cli", "sd"]


class ImageError(Exception):
    pass


def output_dir(cfg) -> Path:
    p = Path(cfg["image_dir"] or (Path.home() / "G3G3AI-imagenes")).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _target(cfg, prompt: str, ext: str = "png") -> Path:
    slug = re.sub(r"[^a-zA-Z0-9áéíóúñü]+", "-", prompt.lower()).strip("-")[:40] or "imagen"
    return output_dir(cfg) / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}.{ext}"


def _save_data_url(cfg, prompt: str, url: str) -> Path:
    head, _, data = url.partition(",")
    ext = "jpg" if "jpeg" in head else ("webp" if "webp" in head else "png")
    out = _target(cfg, prompt, ext)
    out.write_bytes(base64.b64decode(data))
    return out


def find_sd(cfg) -> str | None:
    from .config import DATA_DIR
    exe = ".exe" if sys.platform == "win32" else ""
    cands = [cfg["sd_path"] or ""]
    for base in (DATA_DIR / "sd-engine", DATA_DIR / "stable-diffusion.cpp" / "build" / "bin"):
        if base.is_dir():
            for n in SD_NAMES:
                cands += [str(p) for p in base.rglob(n + exe)]
    cands += [shutil.which(n) or "" for n in SD_NAMES]
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


async def generate(cfg, provider_for, prompt: str, size: str | None = None) -> Path:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageError("Falta la descripción de la imagen.")
    pid = cfg["image_provider"] or ""
    if not pid:
        raise ImageError("La generación de imágenes está desactivada (Ajustes → Imágenes).")
    size = size or cfg["image_size"] or "1024x1024"
    if pid == "local":
        return await asyncio.to_thread(_generate_local, cfg, prompt, size)
    p = provider_for(pid)
    model = cfg["image_model"] or ""
    if not model:
        raise ImageError("Indica el modelo de imágenes en Ajustes → Imágenes.")
    base = p["base_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {p['api_key']}"} if p.get("api_key") else {}
    mode = cfg["image_mode"] or "auto"
    if mode == "auto":
        mode = "chat" if "openrouter" in base else "images"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=300), follow_redirects=True) as c:
        if mode == "chat":
            r = await c.post(f"{base}/chat/completions", headers=headers, json={
                "model": model, "modalities": ["image", "text"],
                "messages": [{"role": "user", "content": prompt}]})
            if r.status_code >= 400:
                raise ImageError(f"HTTP {r.status_code}: {r.text[:400]}")
            msg = (r.json().get("choices") or [{}])[0].get("message") or {}
            imgs = msg.get("images") or []
            if not imgs:
                raise ImageError("El modelo no devolvió ninguna imagen. ¿Es un modelo de generación de imágenes?")
            return _save_data_url(cfg, prompt, imgs[0]["image_url"]["url"])
        r = await c.post(f"{base}/images/generations", headers=headers,
                         json={"model": model, "prompt": prompt, "n": 1, "size": size})
        if r.status_code >= 400:
            raise ImageError(f"HTTP {r.status_code}: {r.text[:400]}")
        item = (r.json().get("data") or [{}])[0]
        if item.get("b64_json"):
            out = _target(cfg, prompt)
            out.write_bytes(base64.b64decode(item["b64_json"]))
            return out
        if item.get("url"):
            img = await c.get(item["url"])
            img.raise_for_status()
            out = _target(cfg, prompt)
            out.write_bytes(img.content)
            return out
    raise ImageError("Respuesta sin imagen.")


def _generate_local(cfg, prompt: str, size: str) -> Path:
    exe = find_sd(cfg)
    if not exe:
        raise ImageError("No está instalado stable-diffusion.cpp. Instálalo en Modelos → Imágenes "
                         "(o con ./install.sh --with-sd en Linux/Konkr).")
    model = cfg["sd_model"] or ""
    if not model or not Path(model).is_file():
        raise ImageError("Elige un modelo de imagen local en Modelos (botón «🎨 Usar para imágenes»).")
    w, _, h = (size or "512x512").partition("x")
    w, h = int(w or 512), int(h or w or 512)
    if cfg["sd_max_side"]:
        m = int(cfg["sd_max_side"])
        if max(w, h) > m:  # en la Konkr, imágenes grandes tardan muchísimo
            w, h = (m, int(h * m / w)) if w >= h else (int(w * m / h), m)
    w, h = w - w % 64 or 64, h - h % 64 or 64
    out = _target(cfg, prompt)
    cmd = [exe, "-m", model, "-p", prompt, "-o", str(out), "-W", str(w), "-H", str(h),
           "--steps", str(int(cfg["sd_steps"] or 4)), "--cfg-scale", str(cfg["sd_cfg"] or 1.0), "-s", "-1"]
    threads = int(cfg["llama_threads"] or 0)
    if threads:
        cmd += ["-t", str(threads)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=1800,
                           creationflags=NO_WINDOW, cwd=str(Path(exe).parent))
    except subprocess.TimeoutExpired as e:
        raise ImageError("La generación local tardó demasiado (más de 30 min).") from e
    if r.returncode != 0 or not out.exists():
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
        raise ImageError(f"stable-diffusion.cpp falló (código {r.returncode}):\n{tail}")
    return out
