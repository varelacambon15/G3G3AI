# Handoff — registro de sesiones

Fuente compartida entre OpenCode y Claude. Cada sesión de trabajo deja aquí un resumen:
qué se cambió, por qué, qué queda pendiente y cómo verificarlo. El detalle fino está en
los commits y los PRs; esto es el mapa para que cualquiera de los dos agentes retome
el hilo sin leer la transcripción.

## Convención

- Al terminar cada sesión: añadir una entrada nueva arriba con fecha, quién y resumen.
- Enlazar commits/PRs cuando existan.
- No pegar secretos ni transcripciones completas. Si hace falta el detalle crudo,
  exportar la sesión con `opencode session export <id> --sanitize`.

---

## 2026-11-21 · OpenCode — sesión inicial

**Objetivo:** integrar el trabajo de OpenCode en G3G3AI de la misma forma que Claude,
con todo centralizado en OpenCode y con Claude como director del proyecto.

**Hecho:**

- Instalados Git 2.56.1, GitHub CLI 2.105.0 y Tailscale 1.104.7 (winget).
- `C:\Github\G3G3AI-ccr-0ee08766-rvyi3x` convertido de ZIP a clon real:
  `origin` → `https://github.com/varelacambon15/G3G3AI.git`, rama por defecto
  `ccr-0ee08766-rvyi3x` en seguimiento, HEAD en `60b4d9a`.
- Rama de trabajo nueva: `feat/opencode-integration`.
- Añadidos `AGENTS.md` (instrucciones del proyecto), `CLAUDE.md` (puntero para Claude
  Code) y `opencode.json` (permisos: pedir confirmación en `git push` y `winget install`).
- `Guia_OpenCode.pdf` queda sin trackear a propósito (no forma parte del repo).
- PC unido a Tailscale como `pc-a` → `100.79.12.46` (G3G3AI quedará accesible en
  `http://100.79.12.46:8800` desde cualquier dispositivo de la misma cuenta).

**Fase 0 completada — PR #1 (seguridad):** https://github.com/varelacambon15/G3G3AI/pull/1

- `server.py`: el bypass de «localhost sin contraseña» exige además Host local (cierra
  el DNS rebinding); `/api/status` no filtra el token y `/api/shutdown` se limita al
  equipo con Host local.
- `server.py`: `/api/files/write` escribe solo en `write_roots`.
- `files.py`: `grep` resuelve el symlink antes de comprobar `blocked_paths`.
- 3 tests nuevos; verificado con `python -m pytest -q tests` → 77 pasan, 5 omitidos,
  2 fallan. Los 2 fallos son **preexistentes** (fallan igual en `60b4d9a`; Python 3.14
  frente al 3.12 de la CI).
- Filosofía de producto añadida a `AGENTS.md`: sencilla de entender y de usar, pero
  extremadamente completa.

**En curso — Fase 1: panel de OpenCode dentro de G3G3AI.**

- Diseño cerrado: pestaña «OpenCode» con lista de sesiones, chat con streaming,
  permisos respondibles y botón de «web completa» (proxy de la interfaz de OpenCode),
  todo con la contraseña de G3G3AI.
- API de OpenCode ya mapeada: `session.list`, `session.create`, `session.prompt`,
  `session.message.list`, `event.subscribe` (SSE), `permission.request`,
  `session.interrupt`.

**Pendiente:**

- Fase 1 (panel) y, si convence, Fase 2 (OpenCode como herramienta del agente).
- Acceso remoto: instalar Tailscale en móvil y portátiles con la misma cuenta.
- Decidir licencia del repo (está público y sin LICENSE) y nombre de la rama por defecto.

**Cómo verificar:**

- `python -m pytest -q tests` desde la raíz del repo (venv en `.venv/`, creado con `uv`).
- Arrancar G3G3AI y abrir `http://100.79.12.46:8800` desde otro dispositivo con Tailscale.
