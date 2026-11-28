# G3G3AI — guía para programarse a sí misma

> Este archivo lo carga G3G3AI como instrucciones del proyecto cuando trabaja en esta carpeta, y sirve también como
> primer mensaje de relevo para un chat nuevo ("lee G3G3AI.md y sigue"). Está escrito para una IA: sé literal.
> Si algo de aquí no coincide con el código, **manda el código**: corrige este archivo en el mismo commit.

## Qué es
G3G3AI: chat de IA local + por API. Servidor FastAPI (`g3g3ai/`) con interfaz web (`g3g3ai/static/`), app de escritorio
(PyInstaller + pywebview: Windows `.exe`, Linux, macOS `.app`) y app de Android (`android/`, cliente WebView + «Chat directo»).
El usuario habla español: responde y comenta en español; el código y los commits, también en español (como el resto del repo).

## Mapa rápido
| Qué | Dónde |
|---|---|
| Servidor, rutas `/api/*`, bucle del chat | `g3g3ai/server.py` |
| Herramientas del agente y permisos | `g3g3ai/tools.py` (`ALL_SPECS`, `ToolContext`, `mode()`, `names()`) |
| Proveedores/streaming, límites de uso | `g3g3ai/providers.py` · catálogo `catalog.py` |
| Prompts del agente | `g3g3ai/agent_prompt.py` · `APP_FEATURES` en `server.py` |
| GitHub (issues, PR, CI, release) | `g3g3ai/github.py` |
| Equipos de IAs, proyectos, plugins, conectores MCP | `team.py`, `projects.py`, `plugins.py`, `connectors.py`, `mcp.py` |
| Emparejar el móvil (código, QR, UDP) | `pairing.py`, `qr.py` |
| Actualización automática desde Releases | `updater.py` |
| Interfaz web (8 scripts, mismo ámbito global) | `g3g3ai/static/js/*.js`, `static/index.html`, `static/style.css` |
| App Android | `android/app/src/main/java/com/g3g3ai/client/*.java` y `assets/direct/` (chat directo) |
| CI y publicación | `.github/workflows/build.yml` · notas: `packaging/release_notes.py` |
| Pruebas | `tests/` (`test_app.py`, `test_ui.py` con Playwright, `test_android_direct.py`) |

## El ciclo para cambiar la app (hazlo siempre así)
1. **Lee antes de tocar.** `git status`, `git log --oneline -10`, esta guía y los archivos afectados. No supongas.
2. **Rama propia:** `git switch -c auto/<tema-corto>` desde la rama por defecto. **No existe `main`**: la rama por defecto
   es `ccr-0ee08766-rvyi3x`. No empujes a ella sin que el usuario lo diga.
3. **Cambios pequeños y verificables.** Un tema por rama.
4. **Pruebas:** `python -m pytest -q tests --timeout=300` (≈2 min). Si falla algo que no tocaste, dilo; no lo ocultes.
   `test_ui.py` necesita Playwright/Chromium; si no está, se omite (entonces dilo y deja que lo haga el CI).
5. **Versión:** si el cambio se publica, sube `__version__` en `g3g3ai/__init__.py` y `versionName`/`versionCode` en
   `android/app/build.gradle` (versionCode +1).
6. **Commit** con mensaje claro en español: la primera línea será el titular en las notas de la versión
   (`packaging/release_notes.py` las construye con los commits). Añade `[skip ci]` solo si vas a lanzar el flujo a mano.
7. **Push de tu rama** y **mira el CI con la herramienta `github`:** `runs` (ref = tu rama) → `run` (run_id) → si falla,
   `job_log` (job_id) para leer el error real. Arréglalo y vuelve a empujar. No des nada por bueno sin CI en verde.
8. **Release:** acción `dispatch` (pide permiso al usuario) sobre la rama indicada: compila Windows, Linux, macOS y Android
   y publica la Release `v<versión>`. Después comprueba con `release`.
9. **La app se actualiza sola:** al haber Release nueva, la app muestra «Actualizar a …» (abajo a la izquierda). Ése es el
   cierre del ciclo: editar → probar → empujar → CI → release → actualizar. El APK de Android se instala a mano.

## Reglas que ya nos costaron tiempo
- **Windows y `python -c "..."`:** las comillas anidadas fallan. Escribe un `.py` con `write_file` y ejecútalo; no repitas el
  mismo comando fallido: cambia de método.
- **Configuración:** nunca leas `config.json` (contiene claves; la IA no debe verlas). Usa `app_settings` (get/set) y
  `suggest_team` para proponer equipos. Para saber qué modelos hay, mira los proveedores con `app_settings`.
- **No inventes** nombres de modelos, rutas, ajustes ni resultados: comprueba y cita lo que viste.
- **No dupliques trabajo:** antes de empezar una función grande, `git branch -r` y `git log origin/<rama>` para ver si ya
  existe. (Ya pasó: `android-remoto-macos` repitió el emparejamiento por QR/código, la app de Android y macOS que ya estaban
  en la rama por defecto como 0.44.0. Si quieres algo de esa rama, trae solo lo que falte con `git cherry-pick`/`git diff`.)
- **GitHub Actions:** el runner de Ubuntu a veces falla en `playwright install` por el repositorio de Microsoft (ya está
  parcheado en `build.yml`). En macOS usa `runs-on: macos-latest` (las etiquetas `macos-14` fueron rechazadas en 1 s). En
  scripts de shell del CI, un heredoc con delimitador entrecomillado (`<<'EOF'`) **no** expande variables.
- **El job `release` publica aunque falle `macos`** (solo exige Windows, Linux y Android). Mira el resultado de macOS aparte.
- **Interfaz web:** los 8 scripts de `static/js/` comparten ámbito global y se cargan en orden (core, models-ui, panels, chat,
  projects, local-models, settings, main). Tras editar JS, comprueba la sintaxis (`node --check`) y usa las pruebas de UI.
- **Android:** sin SDK local no se compila: confía en el job `android` del CI. En Java, cuidado con las variables que se usan
  dentro de lambdas (deben ser `final`).
- **Respuesta lenta del chat:** cada paso del agente es una ida y vuelta al modelo. Menos pasos = más rápido: usa
  `grep_files`/`read_file` en vez de muchos comandos, no hagas sondeos innecesarios y no repitas lo que ya falló.

## Permisos y seguridad (no se negocian)
- La IA nunca ve claves de API. Los comandos y escrituras siguen el selector Manual / Semi-auto / Auto del chat.
- Las acciones de GitHub que escriben (`create_pr`, `dispatch`, …) piden permiso siempre.
- El correo es solo lectura. No subas secretos, `config.json` ni archivos de `G3G3AI-extras` al repositorio.
- No uses `--force`, no reescribas historia ajena ni borres ramas que no creaste tú.

## Estado actual (actualízalo al terminar cada ciclo)
- Rama por defecto: `ccr-0ee08766-rvyi3x`. Última versión publicada: ver `github` → `release`.
- Hecho: equipos guardados por proyecto, fijadas/favoritas, cola de mensajes, uso del plan de OpenCode Go, conectores y
  plugins, actualización automática, emparejar el móvil (QR/código/UDP), macOS (Apple Silicon), CI de GitHub desde la herramienta.
- Ideas pendientes (pide confirmación antes de empezar cualquiera):
  1. Escáner de QR dentro de la app de Android (hoy se escanea con la cámara del móvil).
  2. Notarizar la app de macOS (hoy: firma ad hoc; primera vez, clic derecho → Abrir).
  3. Reiniciar la app desde dentro tras compilar una versión local (`build_exe`) para probarla sin publicar.
  4. Acelerar el agente: menos pasos por tarea, paralelizar lecturas, avisos de «modelo lento» con cambio de modelo sugerido.

## Primer mensaje para un chat nuevo (cópialo tal cual)
> Lee `G3G3AI.md` y `git log --oneline -10`. Vas a trabajar en el propio repositorio de G3G3AI: rama `auto/<tema>`, cambios
> pequeños, pruebas, push, CI con la herramienta `github` (`runs` → `run` → `job_log`) y nada de publicar sin que yo lo
> confirme. Dime en tres líneas qué has entendido y qué vas a hacer primero.
