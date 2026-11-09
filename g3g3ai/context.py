"""Construcción del historial que se envía al modelo.

- Adjuntos: texto/documentos van como texto; imágenes y PDF escaneados como imágenes si el modelo
  ve imágenes, o como descripción hecha por un modelo con visión si no (p.ej. DeepSeek).
- Conversaciones largas: cuando no caben en el contexto, los mensajes antiguos se resumen
  automáticamente y se guarda el resumen (se ve en el chat como «🗜 resumida»).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

from . import documents as D

CHARS_PER_TOKEN = 3.5
IMAGE_TOKENS = 1000
MAX_LIVE_IMAGES = 6       # imágenes enviadas como imagen (las más recientes); el resto, como descripción
KEEP_RECENT = 6           # mensajes recientes que nunca se resumen
DESCRIBE_PROMPT = ("Describe con detalle esta imagen para alguien que no puede verla. Transcribe literalmente "
                   "todo el texto visible (incluidos números, tablas y rótulos). Sé preciso y no inventes.")
SUMMARY_PROMPT = ("Resume la conversación siguiente para poder continuarla sin el texto original. Conserva: "
                  "objetivo del usuario, decisiones tomadas, datos y cifras importantes, archivos, rutas y comandos "
                  "relevantes, y tareas pendientes. Escribe en el idioma de la conversación, en viñetas, "
                  "como máximo unas 400 palabras.")


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            for part in c:
                total += IMAGE_TOKENS if part.get("type") == "image_url" else len(part.get("text", "")) / CHARS_PER_TOKEN
        else:
            total += len(json.dumps(c, ensure_ascii=False)) / CHARS_PER_TOKEN
    return int(total)


def clip_middle(text: str, max_tokens: int) -> str:
    """Recorta un texto largo conservando el principio y el final."""
    limit = int(max_tokens * CHARS_PER_TOKEN)
    if len(text) <= limit:
        return text
    half = max(limit // 2, 50)
    return text[:half] + "\n[... recortado ...]\n" + text[-half:]


def shrink_to_fit(sys_msg: list[dict], history: list[dict], budget: int) -> list[dict]:
    """Si el historial supera el presupuesto, recorta el mensaje de texto más largo hasta que quepa."""
    history = [dict(m) for m in history]
    for _ in range(40):
        if estimate_tokens(sys_msg + history) <= budget:
            break
        texts = [(len(m["content"]), i) for i, m in enumerate(history) if isinstance(m.get("content"), str)]
        if not texts:
            break
        n, i = max(texts)
        if n < 800:  # nada razonable que recortar
            break
        history[i]["content"] = clip_middle(history[i]["content"], int(n / CHARS_PER_TOKEN * 0.6))
    return history


def image_part(media: str, b64: str) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:{media};base64,{b64}"}}


class HistoryBuilder:
    def __init__(self, db, cfg, llama, provider_for, provider_available, complete_messages):
        self.db = db
        self.cfg = cfg
        self.llama = llama
        self.provider_for = provider_for
        self.available = provider_available
        self.complete = complete_messages

    # Visión ----------------------------------------------------------------------
    def supports_vision(self, pid: str) -> bool:
        if pid == "local":
            return bool(self.llama.vision)
        p = self.provider_for(pid)
        if "vision" in p and p["vision"] is not None and p["vision"] != "auto":
            return bool(p["vision"])
        base = (p.get("base_url") or "").lower()
        return not any(x in base for x in ("deepseek", "groq"))

    def describer(self) -> tuple[str, str] | None:
        """Modelo con visión para describir imágenes a modelos que no las ven."""
        spec = self.cfg["vision_fallback"] or ""
        if spec:
            pid, _, model = spec.partition("::")
            if self.available(pid) and self.supports_vision(pid):
                return pid, model or pid
        if self.llama.ready and self.llama.vision:
            return "local", "local"
        return None

    async def describe(self, media: str, b64: str) -> tuple[str, str]:
        d = self.describer()
        if not d:
            raise RuntimeError("El modelo elegido no ve imágenes y no hay ningún modelo con visión disponible. "
                               "Carga un modelo local con visión (p.ej. Gemma 3 4B + mmproj) o elige un modelo "
                               "de visión en Ajustes → Visión.")
        pid, model = d
        text = await self.complete(self.provider_for(pid), model,
                                   [{"role": "user", "content": [{"type": "text", "text": DESCRIBE_PROMPT},
                                                                 image_part(media, b64)]}], 1200)
        shown = self.llama.status()["model"] if pid == "local" else model
        return text, shown

    # Historial -------------------------------------------------------------------------
    async def build(self, conv: dict, pid: str, model: str, system: str, max_tokens: int) -> AsyncIterator[dict]:
        """Genera eventos para la interfaz y termina con {"type": "_history", "messages": [...]}."""
        vision = self.supports_vision(pid)
        msgs = conv["messages"]
        upto = conv.get("summary_upto") or 0
        # Imágenes que van «en vivo»: las de los mensajes más recientes
        live_budget = MAX_LIVE_IMAGES
        live_ids = set()
        for m in reversed(msgs):
            imgs = [a for a in ((m.get("meta") or {}).get("attachments") or []) if a.get("kind") in ("image", "pdf_scan")]
            if imgs and live_budget > 0 and m["id"] > upto:
                live_ids.add(m["id"])
                live_budget -= len(imgs)

        history = []
        for m in msgs:
            if m["id"] <= upto or m["role"] not in ("user", "assistant"):
                continue
            meta = m.get("meta") or {}
            text = meta.get("expanded") or m["content"]
            atts = [a for a in (meta.get("attachments") or []) if a.get("kind") in ("image", "pdf_scan")]
            if m["role"] != "user" or not atts:
                history.append({"role": m["role"], "content": text})
                continue
            parts = [{"type": "text", "text": text or "(imagen adjunta)"}]
            descriptions = meta.setdefault("descriptions", {})
            changed = False
            for a in atts:
                path = Path(a["path"])
                live = vision and m["id"] in live_ids
                try:
                    images = []
                    if live or a["path"] not in descriptions:
                        images = D.pdf_page_images(path) if a["kind"] == "pdf_scan" else [D.image_data_url(path)]
                except (OSError, D.DocumentError) as e:
                    parts.append({"type": "text", "text": f"[No se pudo abrir {a['name']}: {e}]"})
                    continue
                if live:
                    parts += [image_part(mt, b) for mt, b in images]
                    continue
                if a["path"] not in descriptions:
                    yield {"type": "status", "text": f"👁 Describiendo {a['name']}…"}
                    descs = []
                    for i, (mt, b) in enumerate(images, 1):
                        d, by = await self.describe(mt, b)
                        descs.append((f"Página {i}: " if len(images) > 1 else "") + d)
                    descriptions[a["path"]] = {"text": "\n".join(descs), "by": by}
                    changed = True
                d = descriptions[a["path"]]
                parts.append({"type": "text", "text": f"[Contenido de la imagen «{a['name']}» "
                                                      f"(descrito por {d['by']}):\n{d['text']}]"})
            if changed:
                self.db.update_message_meta(m["id"], meta)
            if all(p["type"] == "text" for p in parts):
                history.append({"role": "user", "content": "\n\n".join(p["text"] for p in parts)})
            else:
                history.append({"role": "user", "content": parts})

        # Resumen automático si no cabe
        budget = self.budget(pid, max_tokens)
        sys_msg = [{"role": "system", "content": system}] if system else []
        summary_msg = ([{"role": "user", "content": f"[Resumen de la conversación anterior]\n{conv['summary']}"},
                        {"role": "assistant", "content": "Entendido, continúo a partir de ese resumen."}]
                       if conv.get("summary") else [])
        if estimate_tokens(sys_msg + summary_msg + history) > budget and len(history) > KEEP_RECENT:
            yield {"type": "status", "text": "🗜 Resumiendo la parte antigua de la conversación…"}
            kept = history[-KEEP_RECENT:]
            while len(kept) > 2 and estimate_tokens(sys_msg + kept) > budget * 0.6:
                kept = kept[2:]
            old = history[:len(history) - len(kept)]
            p = self.provider_for(pid)
            pieces = [
                f"{'USUARIO' if h['role'] == 'user' else 'ASISTENTE'}: "
                + (h["content"] if isinstance(h["content"], str)
                   else " ".join(part.get("text", "[imagen]") for part in h["content"]))
                for h in old]
            summary = await self.summarize(p, model, pid, pieces, conv.get("summary"), max_tokens)
            # Último id de mensaje cubierto por el resumen
            visible = [m for m in msgs if m["id"] > upto and m["role"] in ("user", "assistant")]
            new_upto = visible[len(old) - 1]["id"]
            self.db.set_summary(conv["id"], summary, new_upto)
            conv["summary"], conv["summary_upto"] = summary, new_upto
            summary_msg = [{"role": "user", "content": f"[Resumen de la conversación anterior]\n{summary}"},
                           {"role": "assistant", "content": "Entendido, continúo a partir de ese resumen."}]
            history = kept
            yield {"type": "compacted", "messages": len(old)}
        # Último recurso: si aun así no cabe (p.ej. un adjunto enorme en un modelo local de 8K), se recortan los mensajes más largos
        final = shrink_to_fit(sys_msg, summary_msg + history, budget)
        yield {"type": "_history", "messages": final}

    def window(self, pid: str) -> int:
        """Tamaño real de contexto del modelo (tokens)."""
        if pid == "local":
            return int((self.llama.params or {}).get("ctx") or self.cfg["llama_ctx"])
        return int(self.cfg["context_budget"] or 60000)

    async def summarize(self, p, model: str, pid: str, pieces: list[str], previous: str | None,
                        max_tokens: int) -> str:
        """Resume mensajes antiguos por tandas que quepan en el contexto del modelo (resumen acumulativo).
        Antes se enviaba todo de una vez y un modelo local de 8K rechazaba la petición (HTTP 400)."""
        out_tokens = 1500 if self.window(pid) > 16000 else 700
        chunk_tokens = max(500, int(self.window(pid) * 0.75) - out_tokens - 600)
        chunks, cur, size = [], [], 0
        for text in pieces:
            text = clip_middle(text, chunk_tokens)
            t = int(len(text) / CHARS_PER_TOKEN)
            if cur and size + t > chunk_tokens:
                chunks.append("\n\n".join(cur)); cur, size = [], 0
            cur.append(text); size += t
        if cur:
            chunks.append("\n\n".join(cur))
        summary = previous or ""
        for chunk in chunks:
            body = (f"RESUMEN PREVIO:\n{clip_middle(summary, 900)}\n\nMENSAJES NUEVOS:\n{chunk}" if summary else chunk)
            summary = await self.complete(p, model, [{"role": "system", "content": SUMMARY_PROMPT},
                                                     {"role": "user", "content": body}], out_tokens)
        return summary

    def budget(self, pid: str, max_tokens: int) -> int:
        if pid == "local":
            ctx = int((self.llama.params or {}).get("ctx") or self.cfg["llama_ctx"])
            return max(1024, int(ctx * 0.8) - max_tokens)
        return int(self.cfg["context_budget"] or 60000)
