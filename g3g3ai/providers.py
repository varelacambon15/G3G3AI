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
from typing import AsyncIterator

import httpx

from . import tools as T

MAX_TOOL_STEPS = 25


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
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=600), trust_env=not local) as c:
        for _ in range(MAX_TOOL_STEPS):
            body = {"model": model, "messages": msgs, "stream": True,
                    "temperature": opts.get("temperature"), "max_tokens": opts.get("max_tokens"),
                    "stream_options": {"include_usage": True}}
            body = {k: v for k, v in body.items() if v is not None}
            if ctx:
                body["tools"] = ctx.openai_specs()
            content, calls = "", {}
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
                    delta = j["choices"][0].get("delta") or {}
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
            if not calls:
                return
            ordered = [calls[i] for i in sorted(calls)]
            msgs.append({"role": "assistant", "content": content or None, "tool_calls": [
                {"id": k["id"] or f"call_{i}", "type": "function",
                 "function": {"name": k["name"], "arguments": k["args"] or "{}"}}
                for i, k in enumerate(ordered)]})
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
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=600)) as c:
        for _ in range(MAX_TOOL_STEPS):
            body = {"model": model, "messages": msgs, "stream": True,
                    "max_tokens": opts.get("max_tokens") or 4096}
            if opts.get("temperature") is not None:
                body["temperature"] = opts["temperature"]
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
            if stop_reason != "tool_use" or not uses:
                return
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


async def complete(p: dict, model: str, prompt: str, max_tokens: int = 1024) -> str:
    """Respuesta completa sin streaming (para delegar subtareas al modelo local)."""
    text = ""
    async for ev in chat_stream(p, model, [{"role": "user", "content": prompt}],
                                {"max_tokens": max_tokens, "temperature": 0.3}):
        if ev["type"] == "content":
            text += ev["text"]
    return text.strip() or "(sin respuesta)"
