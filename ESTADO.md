# ESTADO — rama `android-remoto-macos` (0.44.0)

> Documento de estado para quien retome este trabajo (humano u otra IA).
> Rama creada desde la rama por defecto del repositorio, `ccr-0ee08766-rvyi3x` (0.43.0, commit `e470a48`).
> En este repositorio **no existe `main`**: la rama por defecto es `ccr-0ee08766-rvyi3x`.
> **No se ha tocado la rama por defecto.**

## Qué hay en esta rama

Objetivo: pulir la app Android y facilitar conectarla con el PC (emparejamiento QR/código,
descubrimiento en la red), más contenido en el chat directo y versión de macOS en CI.

1. **Generador QR propio** (`g3g3ai/qr.py`, sin dependencias) verificado dos veces:
   - Matriz idéntica celda a celda a la biblioteca de referencia de Nayuki (MIT) en las 10 versiones.
   - Decodificación real con OpenCV de las 10 versiones (harness con escala x3/x6).
   - Tests: `tests/test_qr.py` (matriz dorada fija + OpenCV opcional).
2. **Emparejamiento con el móvil** (`g3g3ai/pairing.py` + endpoints en `server.py`):
   - `POST /api/pair/code` (sólo desde el propio PC) → código de 6 dígitos + QR SVG con `{g3g3ai:1, urls, code}`.
   - `GET /api/pair/status`, `POST /api/pair/exchange` (sin autenticar: cambia código por contraseña; 5 intentos, caduca en 10 min).
   - Descubrimiento UDP en el mismo puerto TCP: ping `{"g3g3ai":1,"q":"discover"}` → nombre/IP/puerto/URLs (nunca la contraseña); máx. 1 respuesta/segundo/IP.
   - Página `/m` (`g3g3ai/static/m.html`): escáner QR del móvil; al emparejar guarda en `localStorage` y avisa a la app con `g3g3ai://paired?d=...`.
   - Tarjeta «Conectar la app del móvil» en Ajustes → Acceso (`static/js/settings.js`).
   - **Nota de seguridad:** `/api/pair/exchange` está fuera de la lista de rutas autenticadas del middleware (server.py, `auth_mw`); su protección es el código de 6 dígitos con bloqueo a los 5 intentos y caducidad.
3. **App Android** (`android/`):
   - `Net.java` (nuevo): descubrimiento UDP, `exchange` y `check` en hilos con callbacks a la interfaz.
   - `ServersActivity.java`: buscar en la red, enlazar QR, emparejar por código, estado «En línea» por tarjeta.
   - `WebActivity.java`: modo `pair` (abre `/m` del PC) y retorno `g3g3ai://paired` → Equipos.
   - Chat directo (`assets/direct/`): conversaciones fijadas/favoritas con orden, exportar a Markdown,
     chip de uso del plan (OpenCode Go/OpenRouter/DeepSeek, misma lógica que el escritorio),
     ficha del modelo al tocar el selector, 12 sugerencias de inicio (4 al azar).
   - `versionCode 16`, `versionName "0.44.0"`.
4. **macOS en CI** (`.github/workflows/build.yml`): job `macos` (`macos-latest`) que compila con el spec
   existente, monta `G3G3AI.app` (Info.plist con la versión leída de `__init__.py`, firma ad hoc y comprobación
   de arranque) y publica `G3G3AI-macos.zip` (la .app) y el binario para el updater con el nombre de la
   arquitectura del runner (`G3G3AI-macos-arm64` o `-x64`). Incluido en el job `release`.
   - **Por qué `macos-latest`:** `runs-on: macos-14` resolvió a `macos-14-arm64-us-default` y GitHub lo rechazó
     en 1 s («configuration is not supported») en la cuenta del autor. `macos-latest` sí arranca.
   - Si el runner sale Intel, la .app funciona en Macs Apple Silicon con Rosetta 2 (y se publica como `-x64`).
5. **Actualización automática en macOS** (`g3g3ai/updater.py`): asset según `platform.machine()`
   (`G3G3AI-macos-arm64` / `-x64`), verificación de cabecera Mach-O (MH_MAGIC_64/FAT) y sustitución del binario
   dentro de `G3G3AI.app/Contents/MacOS/`. Tras sustituirlo se **vuelve a firmar la .app**
   (`codesign --force --deep -s -`): si no, la firma ad hoc queda inválida y macOS mata el proceso en el siguiente
   arranque. Si la firma falla, sólo se anota en el log.
6. **README**: secciones nuevas «Conectar la app del móvil con el PC (emparejamiento)» y macOS.
7. Versión: `g3g3ai/__init__.py` → `0.44.0`.

## Verificación hecha

- `tests/test_qr.py`: OK (incluye decodificado OpenCV).
- `tests/test_pairing.py`: OK (ciclo completo, sólo-local, bloqueo por intentos, caducidad, UDP, /m).
- Batería completa: **136 passed, 12 skipped** (245 s, sin `test_ui.py`, que necesita navegador: la hará el CI).
- APK compilada aquí mismo (Gradle 8.11.1 + JDK 17 + SDK android-35): `BUILD SUCCESSFUL`,
  firmada con clave de depuración y verificada con apksigner → `G3G3AI-android-0.44.0.apk`.

## Cómo revertir / continuar

- Todo está en commits de la rama `android-remoto-macos`; la rama por defecto no se ha tocado.
  Revertir = no fusionar la rama.
- Para revertir un paso concreto: `git revert <commit>` en la rama.
- Commits de esta rama (de más antiguo a más nuevo):
  - `25c5169` generador QR verificado
  - `b6632c2` emparejamiento + `/m` + descubrimiento UDP
  - `7f5e137` app Android (chat directo ampliado y conexión con el PC)
  - `f3427a7` macOS en CI + README (0.44.0)
  - `b6a47f4` `.gitignore` de artefactos Gradle
  - `9ec79bb` refirmado de la .app tras actualizar
  - `e4b0c11` macOS en CI con `macos-latest` y arquitectura detectada en el runner
  - `f5856a1` heredoc del Info.plist sin comillas (para que se expanda la versión); **sólo en local, push pendiente**
- **Comprobado en el CI real** (run `46155137321`, commit `e4b0c11`): `tests`, `windows`, `linux`, `macos` y `android`
  en **success** (macOS ya monta y firma la .app; Android produce la APK en el runner). `release` en `skipped`
  porque no había etiqueta.
- Antes de ese run, el job `macos` fallaba en 1 s por la etiqueta del runner (`macos-14` → `macos-14-arm64-us-default`,
  «is not supported» en esta cuenta).
- **Fallo detectado y corregido después**: el heredoc del `Info.plist` usaba delimitador entrecomillado (`<<'PLIST'`),
  así que `$VER` no se expandía y la .app se publicaba con la versión literal `$VER`. Comprobado en Git Bash con las
  dos variantes y ya corregido en `f5856a1`; el run `46155137321` todavía llevaba la versión literal en el plist.
- Estado: **`origin` está en `e4b0c11`**; falta empujar `f5856a1` (el push quedó denegado).
- Pendiente: (1) empujar `f5856a1`; (2) lanzar la release 0.44.0 etiquetando `v0.44.0`, o con Actions →
  «Run workflow» sobre la rama (el job `release` se dispara también con `workflow_dispatch`).
