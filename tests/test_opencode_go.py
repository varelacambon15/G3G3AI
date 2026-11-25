"""Proveedor «OpenCode Go»: migración de config, filtro de modelos y error de cuota.

Todo se prueba con dobles falsos: ningún test llama a internet.
"""
import asyncio
import json

import pytest


GO_BASE = "https://opencode.ai/inference/go/openai/v1"
GO_MODELS_URL = "https://opencode.ai/inference/go/v1/models"

# Respuesta pública de https://opencode.ai/inference/go/v1/models (recortada).
GO_PAYLOAD = {"object": "list", "data": [
    {"id": "deepseek-v4.1-flash", "api": {"chat-completions": {"base_url": GO_BASE}},
     "recommended_api": "chat-completions"},
    {"id": "mimo-v2.6-pro", "api": {"chat-completions": {"base_url": GO_BASE}},
     "recommended_api": "chat-completions"},
    {"id": "beam-free", "api": {"chat-completions": {"base_url": GO_BASE}},
     "recommended_api": "chat-completions"},
    {"id": "grok-4.7", "api": {"responses": {"base_url": GO_BASE}}, "recommended_api": "responses"},
    {"id": "claude-haiku-5-5", "api": {"messages": {"base_url": GO_BASE}},
     "recommended_api": "messages"},
    {"id": "jev-1.14", "api": {"systemone": {}}, "recommended_api": "systemone"},
    {"id": "text-embedding-3-small", "api": {"embeddings": {}}, "recommended_api": "embeddings"},
    {"id": "iceman-contributor-free", "api": {"chat-completions": {}},
     "recommended_api": "chat-completions"},
    {"id": "muse-spark-1.3-contributor", "api": {"responses": {}}, "recommended_api": "responses"},
]}


def _install_models_double(monkeypatch, payload):
    """Sustituye GET /models por una respuesta fija y devuelve las URLs pedidas."""
    import httpx

    seen = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return payload

    async def fake_get(self, url, params=None, headers=None):
        seen.append(str(url))
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    return seen


def test_migration_adds_opencode_go_without_touching_existing_keys(tmp_path):
    from g3g3ai.config import Config

    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "config_version": 7,
        "token": "mi-token",
        "providers": [{"id": "deepseek", "name": "DeepSeek", "type": "openai",
                       "base_url": "https://api.deepseek.com", "api_key": "sk-vieja", "enabled": True}],
    }), "utf-8")

    cfg = Config(path)

    assert cfg["config_version"] == 8
    assert cfg["token"] == "mi-token"
    deepseek = cfg.provider("deepseek")
    assert deepseek["api_key"] == "sk-vieja" and deepseek["enabled"] is True
    go = cfg.provider("opencode-go")
    assert go is not None
    assert go["name"] == "OpenCode Go" and go["type"] == "openai"
    assert go["base_url"] == GO_BASE
    assert go["models_url"] == GO_MODELS_URL
    assert go["api_key"] == "" and go["enabled"] is False


def test_opencode_go_list_models_keeps_only_chat_completions(monkeypatch):
    from g3g3ai.providers import list_models

    seen = _install_models_double(monkeypatch, GO_PAYLOAD)
    go = {"id": "opencode-go", "type": "openai", "base_url": GO_BASE,
          "models_url": GO_MODELS_URL, "api_key": "clave-falsa"}

    models = asyncio.run(list_models(go))

    assert seen == [GO_MODELS_URL]  # usa models_url, no base_url + /models
    assert models == ["beam-free", "deepseek-v4.1-flash", "mimo-v2.6-pro"]
    assert not any(m.startswith(("iceman", "muse-spark")) for m in models)
    assert "grok-4.7" not in models and "claude-haiku-5-5" not in models  # otras APIs quedan fuera


def test_list_models_hides_blocked_ids_for_any_provider(monkeypatch):
    from g3g3ai.providers import list_models

    seen = _install_models_double(monkeypatch, GO_PAYLOAD)
    deepseek = {"id": "deepseek", "type": "openai", "base_url": "https://api.deepseek.com",
                "api_key": "clave-falsa"}

    models = asyncio.run(list_models(deepseek))

    assert seen == ["https://api.deepseek.com/models"]  # sin models_url, comportamiento de siempre
    assert "grok-4.7" in models  # el filtro por api sólo se aplica a OpenCode Go
    assert not any(m.startswith(("iceman", "muse-spark")) for m in models)


def test_opencode_go_429_explains_quota_and_suggests_free_models(monkeypatch):
    import httpx
    from g3g3ai.providers import ProviderError, chat_stream

    class FakeResponse:
        status_code = 429
        text = '{"error": {"message": "quota exceeded"}}'

        async def aread(self):
            return self.text.encode()

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(httpx.AsyncClient, "stream",
                        lambda self, method, url, json=None, headers=None: FakeStream())

    async def collect(p):
        return [ev async for ev in chat_stream(p, "deepseek-v4.1-flash",
                                                [{"role": "user", "content": "hola"}], {"max_tokens": 256})]

    go = {"id": "opencode-go", "type": "openai", "base_url": GO_BASE, "api_key": "clave-falsa"}
    with pytest.raises(ProviderError) as err:
        asyncio.run(collect(go))
    msg = str(err.value)
    assert "HTTP 429" in msg
    assert "cuota" in msg and "plan OpenCode Go" in msg
    assert "hy4-flash-free" in msg and "beam-free" in msg

    # En otros proveedores el mensaje de cuota no cambia.
    deepseek = {"id": "deepseek", "type": "openai", "base_url": "https://api.deepseek.com",
                "api_key": "clave-falsa"}
    with pytest.raises(ProviderError) as err:
        asyncio.run(collect(deepseek))
    assert "HTTP 429" in str(err.value)
    assert "OpenCode Go" not in str(err.value)
