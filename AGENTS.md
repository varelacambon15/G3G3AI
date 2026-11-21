# G3G3AI — instrucciones del proyecto

G3G3AI es un cliente de IA personal: modelos locales (llama.cpp) + APIs, con un agente que lee y edita archivos y ejecuta comandos, interfaz web, app Android e instaladores. Interfaz, mensajes de error y documentación en español.

## Filosofía de producto

- **Sencilla de entender y de usar, pero extremadamente completa.** La complejidad va por debajo: la interfaz explica lo esencial, esconde lo avanzado hasta que se necesita y nunca obliga al usuario a entender cómo funciona por dentro.
- Antes de añadir una opción, una pantalla o un ajuste nuevo, preguntar si se puede resolver con menos pasos.
- El resultado debe sentirse «todo incluido» sin abrumar: una sola aplicación, una sola contraseña, todo lo importante a un toque.

## Instalar y probar

- Python 3.10+; dependencias en `requirements.txt`.
- `pip install -r requirements.txt pytest playwright`
- `python -m pytest -q tests` (usa un `llama-server` falso, `tests/fake_llama_server.py`, y un `env` aislado por test).
- `playwright install --with-deps chromium` para `tests/test_ui.py`; se omite si no hay navegador.
- Linux: `./install.sh` compila llama.cpp e instala el servicio de usuario.
- Windows/macOS: PyInstaller con `packaging/g3g3ai.spec`; CI en `.github/workflows/build.yml` (tests en Ubuntu y Windows).

## Estructura

- `g3g3ai/server.py` — FastAPI: endpoints, SSE y orquestación del chat.
- `g3g3ai/tools.py` — herramientas del agente, permisos, aprobaciones y comandos.
- `g3g3ai/files.py` — acceso a archivos: `file_roots`, `write_roots`, `blocked_paths`.
- `g3g3ai/providers.py`, `context.py`, `router.py` — proveedores, historial/resumen y modo Auto.
- `g3g3ai/config.py` — configuración JSON con `DEFAULTS` y migraciones (`CONFIG_VERSION`).
- `g3g3ai/db.py` — SQLite: conversaciones, mensajes y tombstones para la sincronización.
- `g3g3ai/static/` — interfaz web sin build: JS/CSS/HTML puros.
- Resto de `g3g3ai/`: `sandbox.py`, `web.py`, `sync.py`, `undo.py`, `mail.py`, `steam.py`, `mcp.py`, `tasks.py`, `subagent.py`, `documents.py`, `office.py`, `hardware.py`, `llama.py`, `engine.py`, `hub.py`, `images.py`, `memory.py`, `github.py`, `backup.py`, `costs.py`, `profiles.py`, `devtools.py`, `agent_prompt.py`, `compare.py`.
- `android/` — app Android (Java + WebView). `tests/` — pytest.

## Convenciones

- Comentarios, mensajes de error y documentación en español.
- `from __future__ import annotations`; anotaciones de tipo en funciones nuevas.
- Mantener el estilo del archivo; no añadir dependencias ni frameworks sin preguntar.
- La configuración es un dict con `DEFAULTS` en `config.py`; una clave nueva se añade allí y, si cambia el formato, se sube `CONFIG_VERSION` con su migración.
- La interfaz no usa build ni librerías: DOM con el helper `h()`, Markdown propio (`md()`), chat por SSE.
- Los endpoints devuelven JSON; el chat usa SSE (`server.py` → `sse()`).

## Seguridad (no tocar a la ligera)

- Tres listas: `file_roots` (leer), `write_roots` (escribir), `blocked_paths` (protegidas: nadie las ve).
- `Files.resolve()` valida y resuelve symlinks antes de aceptar una ruta.
- Comandos: `sandbox.assess()` (bloqueados/avisos) y aislamiento bubblewrap en Linux.
- Permisos: `ToolContext.mode()` (`off|ask|auto`) y `precheck()` (avisos fuertes/débiles).
- No exponer tokens ni claves API en respuestas, logs ni git.

## Dirección y registro

- Claude es el director del proyecto (decisión del usuario, 2026-11-21): ante dudas de alcance, prioridad o diseño, consultarlo antes de actuar.
- Todo cambio queda reflejado en `docs/HANDOFF.md` (resumen por sesión) y en commits/PRs, para que Claude tenga acceso sin leer la transcripción.
- `CLAUDE.md` en la raíz es un puntero para Claude Code hacia este archivo y el handoff.

## Reglas de trabajo

- No `git commit`, `git push`, `git reset --hard` ni instalar dependencias sin permiso explícito.
- Limitarse a los archivos necesarios; no aceptar cambios ajenos a la tarea.
- Ejecutar `python -m pytest -q tests` antes de dar un cambio por bueno y reportar el resultado.
- Si el cambio afecta al comportamiento visible o a la interfaz, actualizar `README.md`.
