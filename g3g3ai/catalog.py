"""Catálogo de proveedores de IA listos para añadir (clave → listo).

Todos son compatibles con la API de OpenAI salvo Anthropic. Las URL son las públicas de cada proveedor; si alguno
cambia la suya, se puede editar en Ajustes → Proveedores. «Probar conexión» pide la lista de modelos para comprobarlo.
"""
from __future__ import annotations

# (id, nombre, tipo, url base, dónde conseguir la clave, descripción, etiquetas)
PROVIDERS: list[tuple[str, str, str, str, str, str, list[str]]] = [
    ("opencode-go", "OpenCode Go", "openai", "https://opencode.ai/zen/go/v1", "https://opencode.ai/docs/go/",
     "Suscripción barata con modelos abiertos punteros (GLM, Kimi, DeepSeek, Qwen…).", ["suscripción"]),
    ("opencode-zen", "OpenCode Zen", "openai", "https://opencode.ai/zen/v1", "https://opencode.ai/docs/zen/",
     "Pago por uso con modelos seleccionados para programar.", ["pago por uso"]),
    ("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "https://openrouter.ai/keys",
     "Cientos de modelos (Claude, GPT, Gemini, DeepSeek…) con una sola clave; algunos gratis.", ["muchos modelos", "gratis"]),
    ("anthropic", "Anthropic (Claude)", "anthropic", "https://api.anthropic.com", "https://console.anthropic.com/settings/keys",
     "Claude directamente: el mejor para trabajar con herramientas.", []),
    ("openai", "OpenAI", "openai", "https://api.openai.com/v1", "https://platform.openai.com/api-keys",
     "Modelos GPT de OpenAI.", []),
    ("deepseek", "DeepSeek", "openai", "https://api.deepseek.com", "https://platform.deepseek.com/api_keys",
     "Muy barato y bueno en código y razonamiento.", ["barato"]),
    ("gemini", "Google Gemini", "openai", "https://generativelanguage.googleapis.com/v1beta/openai", "https://aistudio.google.com/apikey",
     "Modelos Gemini; plan gratuito con límites.", ["gratis"]),
    ("groq", "Groq", "openai", "https://api.groq.com/openai/v1", "https://console.groq.com/keys",
     "Respuestas muy rápidas con modelos abiertos; plan gratuito.", ["rápido", "gratis"]),
    ("cerebras", "Cerebras", "openai", "https://api.cerebras.ai/v1", "https://cloud.cerebras.ai",
     "Velocidad extrema con modelos abiertos; plan gratuito.", ["rápido", "gratis"]),
    ("mistral", "Mistral", "openai", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys",
     "Modelos europeos de Mistral.", []),
    ("xai", "xAI (Grok)", "openai", "https://api.x.ai/v1", "https://console.x.ai",
     "Modelos Grok.", []),
    ("moonshot", "Moonshot (Kimi)", "openai", "https://api.moonshot.ai/v1", "https://platform.moonshot.ai/console/api-keys",
     "Modelos Kimi, buenos como agentes.", []),
    ("zai", "Z.ai (GLM)", "openai", "https://api.z.ai/api/paas/v4", "https://z.ai/manage-apikey/apikey-list",
     "Modelos GLM.", []),
    ("qwen", "Alibaba Qwen (DashScope)", "openai", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
     "https://modelstudio.console.alibabacloud.com/", "Modelos Qwen oficiales.", []),
    ("together", "Together AI", "openai", "https://api.together.xyz/v1", "https://api.together.ai/settings/api-keys",
     "Muchos modelos abiertos.", ["muchos modelos"]),
    ("fireworks", "Fireworks AI", "openai", "https://api.fireworks.ai/inference/v1", "https://fireworks.ai/account/api-keys",
     "Modelos abiertos rápidos.", []),
    ("huggingface", "Hugging Face", "openai", "https://router.huggingface.co/v1", "https://huggingface.co/settings/tokens",
     "Inferencia de modelos abiertos con tu token de Hugging Face.", ["muchos modelos"]),
    ("nvidia", "NVIDIA NIM", "openai", "https://integrate.api.nvidia.com/v1", "https://build.nvidia.com",
     "Modelos abiertos alojados por NVIDIA; créditos de prueba.", ["gratis"]),
    ("perplexity", "Perplexity", "openai", "https://api.perplexity.ai", "https://www.perplexity.ai/settings/api",
     "Modelos con búsqueda web integrada.", ["web"]),
    ("ollama", "Ollama (este equipo)", "openai", "http://127.0.0.1:11434/v1", "https://ollama.com/download",
     "Modelos locales gestionados por Ollama. No necesita clave.", ["local"]),
    ("lmstudio", "LM Studio (este equipo)", "openai", "http://127.0.0.1:1234/v1", "https://lmstudio.ai",
     "Servidor local de LM Studio. No necesita clave.", ["local"]),
]


def as_list() -> list[dict]:
    return [{"id": i, "name": n, "type": t, "base_url": u, "key_url": k, "description": d, "tags": tags,
             "needs_key": "local" not in tags}
            for i, n, t, u, k, d, tags in PROVIDERS]


def preset(pid: str) -> dict | None:
    return next((p for p in as_list() if p["id"] == pid), None)
