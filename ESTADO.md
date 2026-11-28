# ESTADO — rama `android-remoto-macos` (0.44.0)

> Documento de estado para quien retome este trabajo (humano u otra IA).
> Rama creada desde `main` (0.43.0, commit 145dcea). **No se ha tocado `main`.**

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
4. **macOS en CI** (`.github/workflows/build.yml`): job `macos` (macos-14, Apple Silicon) que compila con el spec
   existente, monta `G3G3AI.app` (Info.plist + firma ad hoc + comprobación de arranque) y publica
   `G3G3AI-macos.zip` (la .app) y `G3G3AI-macos-arm64` (binario para el updater). Incluido en el job `release`.
5. **Actualización automática en macOS** (`g3g3ai/updater.py`): asset `G3G3AI-macos-arm64`, verificación de
   cabecera Mach-O (MH_MAGIC_64/FAT) y sustitución del binario dentro de `G3G3AI.app/Contents/MacOS/`.
6. **README**: secciones nuevas «Conectar la app del móvil con el PC (emparejamiento)» y macOS.
7. Versión: `g3g3ai/__init__.py` → `0.44.0`.

## Verificación hecha

- `tests/test_qr.py`: OK (incluye decodificado OpenCV).
- `tests/test_pairing.py`: OK (ciclo completo, sólo-local, bloqueo por intentos, caducidad, UDP, /m).
- Batería completa: **136 passed, 11 skipped** (247 s, sin `test_ui.py`, que necesita navegador: la hará el CI).
- APK compilada aquí mismo (Gradle 8.11.1 + JDK 17 + SDK android-35): `BUILD SUCCESSFUL`,
  firmada con clave de depuración y verificada con apksigner → `G3G3AI-android-0.44.0.apk`.

## Cómo revertir / continuar

- Todo está en commits de la rama `android-remoto-macos`; `main` no se ha tocado. Revertir = no fusionar la rama.
- Para revertir un paso concreto: `git revert <commit>` en la rama.
- Pendiente al continuar: push de la rama (pide permiso), release 0.44.0 (etiqueta `v0.44.0` o workflow_dispatch),
  y comprobar el job de macOS en un runner real.
