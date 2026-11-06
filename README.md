# G3G3AI

Cliente de IA al estilo de LM Studio para tu **Konkr Pocket Fit** (SteamOS ARM) y tu **PC**, al que te conectas también desde el **móvil**. Combina modelos locales (llama.cpp) con modelos por API (DeepSeek, Claude, OpenAI…) y puede trabajar como **agente** sobre tus archivos.

## Qué hace

- 💻 **Modelos locales** con llama.cpp. Puedes buscar y descargar modelos GGUF de Hugging Face (con aviso de si caben en la RAM), cargarlos y descargarlos de memoria.
- ☁ **Modelos por API**: DeepSeek, Anthropic (Claude), OpenAI, Gemini, Groq, OpenRouter, y cualquier servidor compatible con OpenAI (por ejemplo Ollama o LM Studio).
- 🎯 **Tú eliges el modelo**: en el selector del chat escoges un modelo local o uno de API para cada conversación.
- 🔀 **Casilla Auto (opcional, desactivada por defecto)**: si la marcas, en cada mensaje se decide si responde el modelo local (gratis y privado) o uno por API (más potente). Si uno falla antes de responder, prueba con el otro.
- 🛠 **Modo agente**: la IA puede leer, buscar y **editar archivos** y **ejecutar comandos**, con permisos, carpetas separadas para leer y modificar, rutas protegidas y comandos aislados. El modelo de API puede **pasarle subtareas al modelo local** para ahorrar coste.
- 🌐 **Búsqueda web**: busca en internet y lee páginas, citando las fuentes.
- 📷 **Fotos y documentos**: adjunta fotos (o hazlas con la cámara del móvil), PDF, Word, Excel, PowerPoint u OpenDocument, y pregunta sobre ellos. Si el modelo elegido no ve imágenes (como DeepSeek), otro modelo con visión las describe automáticamente.
- 🗜 **Conversaciones largas**: cuando no caben en el contexto, lo antiguo se resume solo, y en las tareas largas del agente se recortan las salidas viejas de las herramientas.
- 🧠 **Memoria entre conversaciones**: recuerda datos duraderos sobre ti (preferencias, proyectos…). Cada recuerdo nuevo se ve en el chat y puedes editarlos o borrarlos en Ajustes → Memoria.
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

### Configurar DeepSeek y la casilla Auto

1. Ajustes → Proveedores API → marca **DeepSeek** y pega tu clave API. Guarda.
2. Ajustes → Modo Auto:
   - **modelo rápido** = el local;
   - **modelo potente** = `deepseek-chat` (o `deepseek-reasoner` para razonamiento profundo).
3. En el chat, elige **DeepSeek** en el selector para usarlo directamente, o marca la casilla **🔀 Auto** para que se alterne solo (mientras Auto está marcada, el selector queda en pausa).

Con la estrategia *Inteligente*:
- las preguntas cortas y la charla van al modelo local;
- el código, los análisis, los documentos largos, los adjuntos y el modo agente van al modelo potente.

Cada respuesta indica qué modelo contestó y por qué.

### Modo agente (🛠) y búsqueda web (🌐)

Junto al selector de modelo hay tres casillas: **🔀 Auto**, **🌐 Web** (buscar en internet y leer páginas) y **🛠 Agente** (trabajar con tus archivos y comandos). Se pueden combinar.

**Carpetas: útil pero seguro**

| Lista (Ajustes) | Para qué | Por defecto |
|---|---|---|
| Carpetas visibles | La interfaz y la IA pueden **leer** | Tu carpeta personal |
| Carpetas que la IA puede modificar | La IA puede **crear y editar** archivos y sus comandos pueden escribir | `~/G3G3AI-trabajo` (añade tus proyectos) |
| Rutas protegidas | **Nadie** las ve desde G3G3AI, ni la IA ni la interfaz remota | Claves SSH/GPG, perfiles de navegador, llaveros, configuración de Steam y de G3G3AI, `.env`, `*.pem`, `id_rsa*`… |

**Permisos** (Ajustes): escribir/editar y ejecutar comandos pueden estar en *Desactivado*, *Preguntar* (por defecto) o *Automático*. Con *Preguntar* verás el cambio exacto o el comando, con **Permitir**, **Permitir siempre aquí** (no vuelve a preguntar por esa herramienta en esa conversación) y **Denegar**. Si la pestaña está en segundo plano, recibirás una notificación.

**Comandos:**
- 🛡 **Aislamiento (Linux y Konkr):** se ejecutan con *bubblewrap*, el mismo aislamiento que usa Flatpak. Ven el sistema en solo lectura, solo pueden escribir en las carpetas modificables (y en un `/tmp` temporal), y las rutas protegidas aparecen vacías. El aislamiento no puede ocultar las rutas protegidas por patrón (como `.env`): solo las indicadas con ruta completa.
- **Sin aislamiento (Windows, macOS):** se pide confirmación siempre, aunque estén en *Automático*. «Permitir siempre aquí» sí lo evita dentro de una conversación.
- **Bloqueados siempre:** `rm -rf /` o `~`, formatear discos, escribir directamente en discos, bombas fork…
- **Siempre preguntan**, incluso en *Automático* o con «permitir siempre»: `sudo`, `curl … | sh`, apagar o reiniciar, borrados recursivos, `git push --force`, servicios del sistema, el registro de Windows…

**Búsqueda web:** `web_search` usa DuckDuckGo sin clave, o Brave Search / Tavily con clave (más fiables; ambos tienen plan gratuito). `fetch_url` lee páginas públicas, pero nunca puede acceder a tu red local (127.0.0.1, 192.168.x.x, `.local`…), para que una página no pueda hacer que la IA toque tus dispositivos. La IA cita las fuentes con enlaces.

### Memoria

- La IA guarda notas breves con la herramienta `memory_save` cuando aprende algo útil y duradero, o cuando le dices «recuerda que…». «Olvida…» las borra. Cada recuerdo guardado aparece en el chat como 💾.
- Al empezar cada conversación recibe tus recuerdos como contexto.
- En **Ajustes → 🧠 Memoria** puedes ver, editar, añadir y borrar recuerdos. En «General» puedes desactivar la memoria, impedir que la IA guarde recuerdos por su cuenta, o no enviar la memoria a las APIs externas (así solo la conoce el modelo local).
- No guarda nada que parezca una contraseña o una clave.
- Cada equipo (Konkr, PC) tiene su propia memoria.

### Fotos y documentos

- **📎** adjunta archivos del equipo o del dispositivo; **📷** hace o elige una foto. En el ordenador también puedes arrastrar archivos o pegar imágenes con Ctrl+V.
- **Documentos** (PDF, `.docx`, `.xlsx`, `.pptx`, `.odt`…): se convierten a texto en tu equipo, así que funcionan con cualquier modelo.
- **Fotos y PDF escaneados:**
  - Si el modelo ve imágenes (Claude, GPT, Gemini, o un modelo local con visión), las recibe tal cual.
  - Si no (por ejemplo DeepSeek), un modelo con visión las describe y transcribe su texto. Esa descripción se guarda para no repetirla en cada mensaje.
- **Visión en local:** descarga un modelo con visión (Gemma 3 4B o Qwen2.5-VL 3B). El proyector de visión (`mmproj`) se descarga y se carga automáticamente con el modelo. En Ajustes puedes elegir qué modelo describe las imágenes, e indicar para cada proveedor si ve imágenes.

### Conversaciones largas

Cuando una conversación no cabe en el contexto (el del modelo local, o «Contexto máximo para APIs» en Ajustes), los mensajes antiguos se resumen automáticamente: verás «🗜 Se resumieron N mensajes». En las tareas largas del modo agente, las salidas antiguas de las herramientas se recortan para que DeepSeek y otros modelos aguanten más pasos.

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
  sandbox.py    evaluación y aislamiento (bubblewrap) de comandos
  web.py        búsqueda web y lectura de páginas
  memory.py     memoria entre conversaciones
  documents.py  lectura de PDF, Office e imágenes
  context.py    historial: imágenes/visión y resumen de conversaciones largas
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
