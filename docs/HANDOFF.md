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

- Instalados Git 2.56.1 y GitHub CLI 2.105.0 (winget).
- `C:\Github\G3G3AI-ccr-0ee08766-rvyi3x` convertido de ZIP a clon real:
  `origin` → `https://github.com/varelacambon15/G3G3AI.git`, rama por defecto
  `ccr-0ee08766-rvyi3x` en seguimiento, HEAD en `60b4d9a`.
- Rama de trabajo nueva: `feat/opencode-integration`.
- Añadidos `AGENTS.md` (instrucciones del proyecto), `CLAUDE.md` (puntero para Claude
  Code) y `opencode.json` (permisos: pedir confirmación en `git push` y `winget install`).
- `Guia_OpenCode.pdf` queda sin trackear a propósito (no forma parte del repo).

**En curso:**

- Parche de seguridad (agente delegado, sin commit todavía):
  1. validación del cabecero `Host` para cerrar el DNS rebinding;
  2. escritura vía API limitada a `write_roots`;
  3. `grep` deja de seguir symlinks hacia rutas protegidas.
  Tests nuevos en `tests/test_app.py`.

**Pendiente:**

- `gh auth login` (usuario) → commits, push y PR.
- Python para ejecutar los tests (no está en el `PATH`; se puede usar `uv` para crear
  un venv sin instalar Python del sistema).
- Decidir licencia del repo (está público y sin LICENSE) y nombre de la rama por defecto.
- Acceso remoto a OpenCode (`opencode pair --remote` o Tailscale).

**Cómo verificar:**

- `python -m pytest -q tests` desde la raíz del repo.
