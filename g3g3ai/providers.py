"""Proveedores de IA: llama.cpp local, APIs compatibles con OpenAI y Anthropic.

`chat_stream` produce eventos dict:
  {"type": "content", "text": ...}
  {"type": "reasoning", "text": ...}
  {"type": "tool_call", "name": ..., "args": ...}
  {"type": "tool_result", "name": ..., "result": ...}
  {"type": "stats", ...}
"""
from __future__ import annotations

import json
import re
from typing import AsyncIterator

import httpx

from . import tools as T

MAX_TOOL_STEPS = 25
ANTHROPIC_MIN_TOKENS = 16000
OPENAI_MIN_TOKENS = 8192      # los modelos que razonan gastan parte del límite antes de responder
MAX_CONTINUATIONS = 3         # reanudaciones automáticas si la respuesta se corta por longitud
MAX_NUDGES = 2                # avisos si el modelo anuncia una acción y termina sin hacerla
CONTINUE_MSG = "Continúa exactamente donde lo dejaste (tu respuesta se cortó por el límite de longitud)."
NUDGE_MSG = ("Continúa: haz ahora la acción que acabas de anunciar llamando a la herramienta correspondiente. "
             "No describas el siguiente paso: ejecútalo. Termina sólo cuando la tarea esté hecha "
             "o necesites que el usuario decida algo.")
_ANNOUNCE = re.compile(
    r"\b(ahora|a continuaci[oó]n|voy a|vamos a|paso a|procedo a|leo|reviso|compruebo|busco|miro|edito|abro|"
    r"ejecuto|cambio|aplico|let me|now i|next,? i|i'll|i will)\b", re.I)


def announces_action(text: str) -> bool:
    """¿La respuesta termina anunciando un paso («Ahora leo X…») en vez de preguntar o concluir?"""
    tail = (text or "").strip()[-240:]
    if not tail or tail.endswith("?"):
        return False
    last = re.split(r"(?<=[.!])\s+", tail)[-1] or tail
    return bool(_ANNOUNCE.search(last))


def _merge_reasoning_details(acc: list, items: list) -> None:
    """OpenRouter envía reasoning_details por trozos; se reconstruyen para devolverlos en el bucle de herramientas."""
    for it in items or []:
        if not isinstance(it, dict):
            continue
        idx = it.get("index", len(acc))
        while len(acc) <= idx:
            acc.append({})
        cur = acc[idx]
        for k, v in it.items():
            if k == "index":
                continue
            if isinstance(v, str) and k in ("text", "summary", "data") and isinstance(cur.get(k), str):
                cur[k] += v
            else:
                cur[k] = v
KEEP_TOOL_OUTPUTS = 4          # resultados de herramientas recientes que se envían completos
TOOL_BUDGET_CHARS = 120_000    # por encima, se recortan los resultados antiguos
OMITTED = "[Salida anterior omitida para ahorrar contexto; vuelve a ejecutar la herramienta si la necesitas.]"


def _trim_openai(msgs: list[dict]) -> None:
    tool_idx = [i for i, m in enumerate(msgs) if m.get("role") == "tool"]
    if sum(len(str(m.get("content") or "")) for m in msgs) <= TOOL_BUDGET_CHARS:
        return
    for i in tool_idx[:-KEEP_TOOL_OUTPUTS]:
        msgs[i]["content"] = OMITTED


def _trim_anthropic(msgs: list[dict]) -> None:
    if sum(len(json.dumps(m.get("content"), ensure_ascii=False)) for m in msgs) <= TOOL_BUDGET_CHARS:
        return
    results = [b for m in msgs if isinstance(m.get("content"), list)
               for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    for b in results[:-KEEP_TOOL_OUTPUTS]:
        b["content"] = OMITTED


def _anthropic_content(content):
    """Convierte partes estilo OpenAI (texto + image_url data:) al formato de Anthropic."""
    if not isinstance(content, list):
        return content
    out = []
    for part in content:
        if part.get("type") == "image_url":
            url = part["image_url"]["url"]
            media, _, data = url.partition(";base64,")
            out.append({"type": "image", "source": {"type": "base64", "media_type": media.removeprefix("data:"),
                                                     "data": data}})
        elif part.get("type") == "text":
            out.append({"type": "text", "text": part["text"]})
    return out


class ProviderError(Exception):
    pass


async def _raise_for(r: httpx.Response):
    if r.status_code >= 400:
        body = (await r.aread()).decode("utf-8", errors="replace")
        try:
            j = json.loads(body)
            msg = j.get("error", {}).get("message") if isinstance(j.get("error"), dict) else j.get("error")
            body = msg or body
        except json.JSONDecodeError:
            pass
        raise ProviderError(f"HTTP {r.status_code}: {body[:800]}")


async def _sse(r: httpx.Response) -> AsyncIterator[dict]:
    async for line in r.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


# --- Listado de modelos ---------------------------------------------------------
async def list_models(p: dict) -> list[str]:
    async with httpx.AsyncClient(timeout=15) as c:
        if p["type"] == "anthropic":
            r = await c.get(p["base_url"].rstrip("/") + "/v1/models", params={"limit": 100},
                            headers={"x-api-key": p.get("api_key", ""), "anthropic-version": "2023-06-01"})
        else:
            headers = {"Authorization": f"Bearer {p['api_key']}"} if p.get("api_key") else {}
            r = await c.get(p["base_url"].rstrip("/") + "/models", headers=headers)
        if r.status_code >= 400:
            raise ProviderError(f"HTTP {r.status_code}: {r.text[:300]}")
        return sorted(m["id"] for m in r.json().get("data", []))


# --- OpenAI compatible (incluye llama-server local) -----------------------------------
async def _openai_chat(p: dict, model: str, messages: list[dict], opts: dict,
                       ctx: T.ToolContext | None) -> AsyncIterator[dict]:
    url = p["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {p['api_key']}"} if p.get("api_key") else {}
    msgs = list(messages)
    local = p["base_url"].startswith(("http://127.0.0.1", "http://localhost"))
    max_tokens = max(int(opts.get("max_tokens") or 0), OPENAI_MIN_TOKENS)
    continuations = nudges = 0
    used_tools = False
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=600), trust_env=not local) as c:
        for _ in range(MAX_TOOL_STEPS):
            _trim_openai(msgs)
            body = {"model": model, "messages": msgs, "stream": True,
                    "temperature": opts.get("temperature"), "max_tokens": max_tokens,
                    "stream_options": {"include_usage": True}}
            body = {k: v for k, v in body.items() if v is not None}
            if ctx:
                body["tools"] = ctx.openai_specs()
            content, calls, finish, details = "", {}, None, []
            async with c.stream("POST", url, json=body, headers=headers) as r:
                await _raise_for(r)
                async for j in _sse(r):
                    if j.get("timings"):
                        t = j["timings"]
                        yield {"type": "stats", "tokens_per_second": t.get("predicted_per_second"),
                               "tokens": t.get("predicted_n"), "prompt_tokens": t.get("prompt_n")}
                    elif j.get("usage"):
                        u = j["usage"]
                        yield {"type": "stats", "tokens": u.get("completion_tokens"),
                               "prompt_tokens": u.get("prompt_tokens")}
                    if not j.get("choices"):
                        continue
                    finish = j["choices"][0].get("finish_reason") or finish
                    delta = j["choices"][0].get("delta") or {}
                    if delta.get("reasoning_details"):
                        _merge_reasoning_details(details, delta["reasoning_details"])
                    if delta.get("reasoning_content") or delta.get("reasoning"):
                        yield {"type": "reasoning", "text": delta.get("reasoning_content") or delta.get("reasoning")}
                    if delta.get("content"):
                        content += delta["content"]
                        yield {"type": "content", "text": delta["content"]}
                    for tc in delta.get("tool_calls") or []:
                        slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                        slot["id"] = tc.get("id") or slot["id"]
                        fn = tc.get("function") or {}
                        slot["name"] += fn.get("name") or ""
                        slot["args"] += fn.get("arguments") or ""
            if finish == "length" and continuations < MAX_CONTINUATIONS:
                # Cortada por longitud: las llamadas a medias no sirven; se pide que siga
                continuations += 1
                yield {"type": "status", "text": "↪ La respuesta se cortó por longitud; continúa automáticamente…"}
                if content:
                    msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content": CONTINUE_MSG})
                continue
            if not calls:
                if ctx and used_tools and nudges < MAX_NUDGES and announces_action(content):
                    nudges += 1
                    yield {"type": "status", "text": "↪ El modelo anunció un paso sin hacerlo; se le pide que continúe…"}
                    msgs.append({"role": "assistant", "content": content})
                    msgs.append({"role": "user", "content": NUDGE_MSG})
                    continue
                if finish == "length":
                    yield {"type": "content", "text": "\n\n[Respuesta cortada por el límite de longitud. "
                                                      "Escribe «continúa» o sube «Máx. tokens» en Ajustes.]"}
                return
            used_tools = True
            ordered = [calls[i] for i in sorted(calls)]
            assistant = {"role": "assistant", "content": content or None, "tool_calls": [
                {"id": k["id"] or f"call_{i}", "type": "function",
                 "function": {"name": k["name"], "arguments": k["args"] or "{}"}}
                for i, k in enumerate(ordered)]}
            if details:  # OpenRouter: devolver el razonamiento para que el modelo siga su hilo
                assistant["reasoning_details"] = details
            msgs.append(assistant)
            for i, k in enumerate(ordered):
                sink: list[str] = []
                async for ev in T.tool_events(ctx, k["name"], k["args"], sink):
                    yield ev
                msgs.append({"role": "tool", "tool_call_id": k["id"] or f"call_{i}", "content": sink[0]})
        yield {"type": "content", "text": "\n\n[Se alcanzó el límite de pasos con herramientas]"}


# --- Anthropic ---------------------------------------------------------------------
async def _anthropic_chat(p: dict, model: str, messages: list[dict], opts: dict,
                          ctx: T.ToolContext | None) -> AsyncIterator[dict]:
    url = p["base_url"].rstrip("/") + "/v1/messages"
    headers = {"x-api-key": p.get("api_key", ""), "anthropic-version": "2023-06-01"}
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    msgs = [{"role": m["role"], "content": _anthropic_content(m["content"])}
            for m in messages if m["role"] in ("user", "assistant")]
    continuations = nudges = 0
    used_tools = False
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=600)) as c:
        for _ in range(MAX_TOOL_STEPS):
            _trim_anthropic(msgs)
            # Los modelos actuales de Claude piensan antes de responder y ese razonamiento cuenta en
            # max_tokens: se deja margen suficiente. Tampoco admiten temperature (devuelven 400).
            body = {"model": model, "messages": msgs, "stream": True,
                    "max_tokens": max(int(opts.get("max_tokens") or 0), ANTHROPIC_MIN_TOKENS)}
            if system:
                body["system"] = system
            if ctx:
                body["tools"] = ctx.anthropic_specs()
            blocks: dict[int, dict] = {}
            stop_reason = None
            async with c.stream("POST", url, json=body, headers=headers) as r:
                await _raise_for(r)
                async for j in _sse(r):
                    t = j.get("type")
                    if t == "content_block_start":
                        b = dict(j["content_block"])
                        if b.get("type") == "tool_use":
                            b["_json"] = ""
                        blocks[j["index"]] = b
                    elif t == "content_block_delta":
                        d, b = j["delta"], blocks.get(j["index"])
                        if d["type"] == "text_delta":
                            b["text"] = b.get("text", "") + d["text"]
                            yield {"type": "content", "text": d["text"]}
                        elif d["type"] == "thinking_delta":
                            yield {"type": "reasoning", "text": d["thinking"]}
                        elif d["type"] == "input_json_delta":
                            b["_json"] += d["partial_json"]
                    elif t == "message_delta":
                        stop_reason = j.get("delta", {}).get("stop_reason")
                        if j.get("usage"):
                            yield {"type": "stats", "tokens": j["usage"].get("output_tokens")}
                    elif t == "error":
                        raise ProviderError(j.get("error", {}).get("message", "error"))
            uses = [b for _, b in sorted(blocks.items()) if b.get("type") == "tool_use"]
            text = "".join(b.get("text", "") for _, b in sorted(blocks.items()) if b.get("type") == "text")
            if stop_reason == "max_tokens" and continuations < MAX_CONTINUATIONS:
                continuations += 1
                yield {"type": "status", "text": "↪ La respuesta se cortó por longitud; continúa automáticamente…"}
                if text:
                    msgs.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
                msgs.append({"role": "user", "content": CONTINUE_MSG})
                continue
            if stop_reason != "tool_use" or not uses:
                if ctx and used_tools and nudges < MAX_NUDGES and announces_action(text):
                    nudges += 1
                    yield {"type": "status", "text": "↪ El modelo anunció un paso sin hacerlo; se le pide que continúe…"}
                    msgs.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
                    msgs.append({"role": "user", "content": NUDGE_MSG})
                    continue
                return
            used_tools = True
            assistant_content = []
            for _, b in sorted(blocks.items()):
                if b.get("type") == "text" and b.get("text"):
                    assistant_content.append({"type": "text", "text": b["text"]})
                elif b.get("type") == "tool_use":
                    try:
                        b["input"] = json.loads(b["_json"] or "{}")
                    except json.JSONDecodeError:
                        b["input"] = {}
                    assistant_content.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": b["input"]})
            msgs.append({"role": "assistant", "content": assistant_content})
            results = []
            for b in uses:
                sink: list[str] = []
                async for ev in T.tool_events(ctx, b["name"], b["input"], sink):
                    yield ev
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": sink[0]})
            msgs.append({"role": "user", "content": results})
        yield {"type": "content", "text": "\n\n[Se alcanzó el límite de pasos con herramientas]"}


def chat_stream(p: dict, model: str, messages: list[dict], opts: dict,
                ctx: T.ToolContext | None = None) -> AsyncIterator[dict]:
    fn = _anthropic_chat if p["type"] == "anthropic" else _openai_chat
    return fn(p, model, messages, opts, ctx)


async def complete_messages(p: dict, model: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """Respuesta completa (sin herramientas) a partir de una lista de mensajes."""
    text = ""
    async for ev in chat_stream(p, model, messages, {"max_tokens": max_tokens, "temperature": 0.3}):
        if ev["type"] == "content":
            text += ev["text"]
    text = re.sub(r"^\s*<think>.*?</think>", "", text, flags=re.S)  # modelos que piensan en el contenido
    return text.strip() or "(sin respuesta)"


async def complete(p: dict, model: str, prompt: str, max_tokens: int = 1024) -> str:
    """Respuesta completa a un único mensaje (para delegar subtareas al modelo local)."""
    return await complete_messages(p, model, [{"role": "user", "content": prompt}], max_tokens)
