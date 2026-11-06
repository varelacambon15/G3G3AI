# G3G3AI

Cliente de IA al estilo de LM Studio para tu **Konkr Pocket Fit** (SteamOS ARM) y tu **PC**, al que te conectas también desde el **móvil**. Combina modelos locales (llama.cpp) con modelos por API (DeepSeek, Claude, OpenAI…) y puede trabajar como **agente** sobre tus archivos.

## Qué hace

- 💻 **Modelos locales** con llama.cpp. Puedes buscar y descargar modelos GGUF de Hugging Face (con aviso de si caben en la RAM), cargarlos y descargarlos de memoria.
- ☁ **Modelos por API**: DeepSeek, Anthropic (Claude), OpenAI, Gemini, Groq, OpenRouter, y cualquier servidor compatible con OpenAI (por ejemplo Ollama o LM Studio).
- 🔀 **Modo Auto**: en cada mensaje decide si responde el modelo local (gratis y privado) o uno por API (más potente). Si uno falla antes de responder, prueba con el otro.
- 🛠 **Modo agente**: la IA puede listar, leer, buscar y **editar archivos** y **ejecutar comandos**. Cada acción te pide permiso (también desde el móvil). El modelo de API puede **pasarle subtareas al modelo local** (resumir, traducir…) para ahorrar coste.
- 🔗 **Konkr ↔ PC**: cada equipo puede usar el modelo local del otro (Ajustes → Añadir proveedor → «Otro equipo con G3G3AI»).
- 📱 **Desde el móvil**: interfaz web protegida con contraseña, instalable como app.
- 📁 Explorador de archivos, subida y descarga, adjuntos en el chat.

## Instalación

### Konkr (SteamOS ARM) — con acceso desde Big Picture

No necesita root ni desbloquear el sistema. En el **modo escritorio**, abre Konsole:

```bash
git clone https://github.com/varelacambon15/G3G3AI.git ~/G3G3AI
cd ~/G3G3AI && ./install.sh
```

También puedes hacer doble clic en `konkr/Instalar G3G3AI.desktop`.

El instalador:
1. compila llama.cpp optimizado para el procesador de la Konkr (unos 10–20 minutos);
2. crea un servicio que arranca G3G3AI solo al iniciar sesión;
3. instala Chromium (Flatpak, solo para tu usuario) si no tienes navegador;
4. añade **G3G3AI a Steam**: en el modo juego, ve a **Biblioteca → No de Steam → G3G3AI**. Se abre a pantalla completa, y al salir con el botón Steam el servidor sigue encendido para el móvil.

Si no se puede añadir a Steam automáticamente, el instalador te explica cómo hacerlo a mano (son 3 pasos). Para el teclado en pantalla en modo juego, pulsa **Steam + X**. Para cambiar el tamaño de la interfaz, usa la variable `G3G3AI_SCALE` (por defecto 1.25).

Para actualizar: `cd ~/G3G3AI && git pull && ./install.sh`

### PC con Windows — `G3G3AI.exe`

1. Descarga `G3G3AI.exe` de la sección **Releases** del repositorio, o de la pestaña **Actions** (último build, artefacto `G3G3AI-windows`).
2. Ábrelo. La primera vez, Windows SmartScreen puede avisar porque el ejecutable no está firmado: pulsa *Más información → Ejecutar de todas formas*. Y si el firewall pregunta, permite el acceso en **redes privadas** para poder conectar desde el móvil.
3. En **Modelos**, pulsa **Instalar** en el motor llama.cpp: *Vulkan* si tienes tarjeta gráfica, *CPU* si no.
4. Descarga un modelo y cárgalo.

Para dejarlo encendido sin ventana (y usarlo solo desde el móvil): `G3G3AI.exe --headless`. Para apagarlo: Ajustes → Apagar servidor.

### PC con Linux o macOS

```bash
git clone https://github.com/varelacambon15/G3G3AI.git && cd G3G3AI && ./install.sh
```

En Linux x64 también hay un binario `G3G3AI-linux-x64` en Releases/Actions.

### Android

- **Como cliente** (lo recomendado): abre en el navegador la dirección que aparece en Ajustes → Acceso remoto, y usa «Añadir a pantalla de inicio».
- **Como servidor** (experimental): con [Termux](https://f-droid.org/packages/com.termux/) y `bash android/termux-install.sh`. Funciona con modelos pequeños (1–3B). Android puede cerrar Termux en segundo plano.

## Uso

### Conectar desde el móvil

Abre `http://IP-DEL-EQUIPO:8800/?token=CONTRASEÑA`. La dirección exacta aparece en **Ajustes → Acceso remoto** y al instalar. El móvil tiene que estar en la misma Wi-Fi. Para acceder desde fuera de casa, usa [Tailscale](https://tailscale.com) en los dos dispositivos (no abras el puerto a internet).

### Configurar DeepSeek y el modo Auto

1. Ajustes → Proveedores API → marca **DeepSeek** y pega tu clave API. Guarda.
2. Ajustes → Modo Auto:
   - **modelo rápido** = el local;
   - **modelo potente** = `deepseek-chat` (o `deepseek-reasoner` para razonamiento profundo).
3. En el chat, elige **🔀 Auto** en el selector.

Con la estrategia *Inteligente*:
- las preguntas cortas y la charla van al modelo local;
- el código, los análisis, los documentos largos, los adjuntos y el modo agente van al modelo potente.

Cada respuesta indica qué modelo contestó y por qué.

### Modo agente

Activa **🛠 Agente** junto al selector de modelo. Los permisos se configuran en Ajustes:

| Acción | Opciones |
|---|---|
| Leer, listar y buscar archivos | Siempre permitido, dentro de las carpetas accesibles |
| Escribir o editar archivos | Desactivado / **Preguntar** / Automático |
| Ejecutar comandos | Desactivado / **Preguntar** / Automático |

Con *Preguntar* verás una tarjeta con el comando exacto o el cambio propuesto, con los botones **Permitir** y **Denegar**. Si la pestaña está en segundo plano, recibirás una notificación del navegador. ⚠ Los comandos se ejecutan con tus permisos de usuario y pueden afectar a todo el equipo: usa *Automático* solo si confías en el modelo.

## Modelos recomendados

En la Konkr (8 GB de RAM), mejor modelos de 3–4B en versión Q4_K_M: **Qwen3 4B** (bueno con herramientas y en modo agente), **Gemma 3 4B**, **Llama 3.2 3B**, **Qwen2.5 Coder 3B**. En un PC con 16 GB o más y tarjeta gráfica puedes usar modelos de 7–14B.

## Comandos útiles (Linux / Konkr)

```bash
systemctl --user restart g3g3ai     # reiniciar
journalctl --user -u g3g3ai -f      # registro
g3g3ai --show-token                 # ver contraseña
g3g3ai --new-token                  # cambiar contraseña
```

## Desarrollo

```
g3g3ai/
  server.py     API, autenticación, chat con modo Auto, proxy /v1
  router.py     decisión local ↔ API
  tools.py      herramientas del agente y aprobaciones
  providers.py  streaming OpenAI/Anthropic + bucle de herramientas
  llama.py      proceso llama-server
  engine.py     descarga de llama.cpp precompilado (Windows/macOS/Linux x64)
  hub.py        Hugging Face
  desktop.py    app de escritorio (.exe)
  static/       interfaz web
konkr/          lanzador para Big Picture, integración con Steam
android/        instalación experimental en Termux
packaging/      especificación de PyInstaller e icono
```

Pruebas: `pip install -r requirements.txt pytest && python -m pytest tests`.
Generar el ejecutable: `pip install pyinstaller pywebview && pyinstaller packaging/g3g3ai.spec`. GitHub Actions lo compila en cada push, y crea una Release con `G3G3AI.exe` al subir una etiqueta `v*`.
