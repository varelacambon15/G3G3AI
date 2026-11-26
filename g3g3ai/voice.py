"""Dictado por voz: audio WAV (16 kHz, mono) → texto.

Motores, por orden en modo «auto»:
  1. Local con whisper.cpp (privado, sin Internet): binario whisper-cli (edición completa o instalado) y un
     modelo ggml descargado de Hugging Face la primera vez.
  2. En la nube, con un proveedor ya configurado que ofrezca transcripción (Groq, OpenAI).
Si ninguno está disponible, la interfaz usa el reconocimiento del navegador cuando existe.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

WHISPER_REPO = "ggerganov/whisper.cpp"
DEFAULT_MODEL = "ggml-small-q5_1.bin"       # ~190 MB, buen español en CPU
MODELS = {
    "ggml-base-q5_1.bin": "Básico · 60 MB · el más rápido",
    "ggml-small-q5_1.bin": "Recomendado · 190 MB",
    "ggml-large-v3-turbo-q5_0.bin": "Máxima calidad · 570 MB · necesita un buen procesador",
}
# (proveedor, modelo de transcripción) por orden de preferencia
CLOUD = [("groq", "whisper-large-v3-turbo"), ("openai", "gpt-4o-mini-transcribe")]
BIN_NAMES = ("whisper-cli", "whisper-cpp", "whisper")


class VoiceError(Exception):
    pass


def find_binary(cfg) -> Path | None:
    from . import extras
    from .config import DATA_DIR
    exe = ".exe" if os.name == "nt" else ""
    if cfg["voice_binary"]:
        p = Path(cfg["voice_binary"]).expanduser()
        if p.is_file():
            return p
    b = extras.whisper_binary()
    if b:
        return b
    for base in (DATA_DIR / "whisper", DATA_DIR / "engine"):
        if base.is_dir():
            for n in BIN_NAMES:
                for p in sorted(base.rglob(n + exe)):
                    if p.is_file():
                        return p
    for n in BIN_NAMES:
        w = shutil.which(n)
        if w and (n != "whisper" or _is_cpp(w)):        # «whisper» puede ser el de Python (openai-whisper)
            return Path(w)
    return None


def _is_cpp(path: str) -> bool:
    try:
        out = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=5)
        return "--model" in (out.stdout + out.stderr) and "-otxt" in (out.stdout + out.stderr)
    except Exception:  # noqa: BLE001
        return False


def model_dir(cfg) -> Path:
    return Path(cfg["models_dir"]).expanduser() / WHISPER_REPO.replace("/", "__")


def model_path(cfg) -> Path | None:
    name = cfg["voice_model"] or DEFAULT_MODEL
    p = model_dir(cfg) / name
    if p.is_file() and p.stat().st_size > 1_000_000:
        return p
    others = sorted(model_dir(cfg).glob("ggml-*.bin")) if model_dir(cfg).is_dir() else []
    return others[0] if others else None                 # cualquier otro modelo ya descargado sirve


def cloud_provider(cfg) -> tuple[dict, str] | None:
    for pid, model in CLOUD:
        p = cfg.provider(pid)
        if p and p.get("api_key") and p.get("enabled"):
            return p, model
    return None


def status(cfg) -> dict:
    binary, model, cloud = find_binary(cfg), model_path(cfg), cloud_provider(cfg)
    engine = cfg["voice_engine"] or "auto"
    ready_local = bool(binary and model)
    use = ("local" if ready_local else "cloud" if cloud else None) if engine == "auto" else \
          ("local" if engine == "local" and ready_local else "cloud" if engine == "cloud" and cloud else
           "browser" if engine == "browser" else None)
    return {"engine": engine, "use": use, "binary": str(binary) if binary else None,
            "model": model.name if model else None, "model_wanted": cfg["voice_model"] or DEFAULT_MODEL,
            "models": MODELS, "cloud": cloud[0]["id"] if cloud else None, "language": cfg["voice_language"] or "auto"}


async def transcribe(cfg, wav: bytes) -> dict:
    if len(wav) < 1000:
        raise VoiceError("No se ha grabado audio.")
    st = status(cfg)
    if st["use"] == "local":
        return {"text": await asyncio.to_thread(_local, cfg, wav), "engine": "local"}
    if st["use"] == "cloud":
        return {"text": await _cloud(cfg, wav), "engine": st["cloud"]}
    if not st["binary"]:
        raise VoiceError("El dictado necesita whisper.cpp (incluido en la edición completa) o un proveedor con "
                         "transcripción (Groq u OpenAI) en Ajustes → Proveedores.")
    raise VoiceError("Falta el modelo de voz: descárgalo en Ajustes → Modelos locales → Dictado por voz.")


def _local(cfg, wav: bytes) -> str:
    binary, model = find_binary(cfg), model_path(cfg)
    lang = cfg["voice_language"] or "auto"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "audio.wav"
        f.write_bytes(wav)
        cmd = [str(binary), "-m", str(model), "-f", str(f), "-l", lang, "-nt", "-np",
               "-t", str(max(1, min(8, (os.cpu_count() or 4) - 1)))]
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}     # sin ventana de consola en Windows
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, **kw)
        if r.returncode != 0:
            raise VoiceError("whisper.cpp falló: " + (r.stderr or r.stdout).strip()[-300:])
    return _clean(r.stdout)


async def _cloud(cfg, wav: bytes) -> str:
    p, model = cloud_provider(cfg)
    lang = cfg["voice_language"] or "auto"
    data = {"model": model, **({"language": lang} if lang != "auto" else {})}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(p["base_url"].rstrip("/") + "/audio/transcriptions", data=data,
                         files={"file": ("audio.wav", wav, "audio/wav")},
                         headers={"Authorization": f"Bearer {p['api_key']}"})
    if r.status_code >= 400:
        raise VoiceError(f"{p.get('name') or p['id']} no pudo transcribir ({r.status_code}): {r.text[:200]}")
    return _clean(r.json().get("text", ""))


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    out = " ".join(ln for ln in lines if ln and not (ln.startswith("[") and ln.endswith("]")))   # [música], [BLANK_AUDIO]
    return out.strip()
