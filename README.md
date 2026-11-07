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
- 🎨 **Generación de imágenes**: por API (OpenAI, Gemini, OpenRouter…) o en local con stable-diffusion.cpp. Escribe `/imagen descripción` o pídeselo a la IA.
- 🧠 **Memoria entre conversaciones**: recuerda datos duraderos sobre ti (preferencias, proyectos…). Cada recuerdo nuevo se ve en el chat y puedes editarlos o borrarlos en Ajustes → Memoria.
- 🔄 **Sincronización Konkr ↔ PC**: con una clave común se sincronizan conversaciones, memoria y APIs. Además, cada equipo puede usar el modelo local del otro (Ajustes → Añadir proveedor → «Otro equipo con G3G3AI»).
- ✦ **Interfaz cuidada**: barra lateral con búsqueda y conversaciones por fecha, compositor con menú «+» y herramientas, vista previa de HTML/SVG en un panel lateral, modo claro y oscuro.
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

### Generación de imágenes

- **Uso:** escribe `/imagen un gato astronauta` (o pulsa 🎨), o pide en el chat «dibújame…» y la IA usará la herramienta `generate_image`. Las imágenes aparecen en el chat y se guardan en `~/G3G3AI-imagenes`.
- **Por API** (Ajustes → 🎨 Imágenes): elige el proveedor y el modelo. Por ejemplo, OpenAI con `gpt-image-1`, Gemini con `imagen-3.0-generate-002` u OpenRouter con `google/gemini-2.5-flash-image`.
- **En local** (Modelos → 🎨 Generación de imágenes): instala stable-diffusion.cpp (en el PC, con un botón; en la Konkr, con `./install.sh --with-sd`), descarga un modelo de imagen GGUF (por ejemplo, SD Turbo) y pulsa 🎨 en él. En la Konkr, cuenta con bastante espera por imagen y calidad modesta. En un PC con tarjeta gráfica va mucho mejor.

### Sincronizar la Konkr y el PC

1. En uno de los equipos: **Ajustes → 🔄 Sincronización → Generar clave nueva**. Copia la clave (6 grupos de 4 letras y números).
2. En el otro equipo: pega la clave en el mismo sitio y pulsa **Guardar clave**.
3. En cualquiera de los dos, añade la dirección del otro (por ejemplo `192.168.1.50`, la ves en su *Ajustes → Acceso remoto*) y pulsa **Sincronizar ahora**. A partir de ahí se sincronizan solos cada 2 minutos.

**Qué se sincroniza:** conversaciones, memoria, proveedores API **con sus claves** (si configuras DeepSeek en el PC, aparece en la Konkr), modo Auto, instrucciones, permisos del agente y ajustes de imágenes y búsqueda web.
**Qué no:** las carpetas, los modelos locales, el puerto y la contraseña de cada equipo. Los archivos adjuntos y las imágenes tampoco se copian: en el otro equipo se verá el texto de la conversación.
**Seguridad:** todo viaja cifrado y autenticado con la clave (AES + HMAC). Un equipo sin la clave no puede leer ni enviar nada. Si el mismo dato cambia en los dos equipos, gana el cambio más reciente.

### Juegos de Steam: diagnosticar y arreglar

En el modo 🛠 Agente, la IA tiene dos herramientas:
- **`steam_games`:** lista los juegos instalados, con su appid, tamaño y versión de Proton.
- **`game_diagnostics`:** reúne lo necesario para saber por qué un juego no funciona:
  - carpeta del juego y versión de Proton (forzada, y la que creó el prefijo);
  - opciones de lanzamiento y prefijo de Wine (`compatdata`);
  - errores del registro de Proton (`~/steam-<appid>.log`) y líneas de los registros de Steam;
  - archivos de configuración, registros y volcados recientes del juego y de su prefijo.

**Cómo usarlo:** «El juego X no arranca, mira qué le pasa». Si no hay registro de Proton, te pedirá que añadas `PROTON_LOG=1 %command%` a las opciones de lanzamiento y lo abras una vez.

**Al arreglarlo:**
- La IA puede modificar archivos del juego y de su prefijo, pero **siempre te pide permiso**, aunque los permisos estén en «Automático».
- Antes del primer cambio guarda una copia del original (`archivo.g3g3ai-original`).
- Se desactiva en Ajustes → «La IA puede trabajar con los juegos de Steam».
- De `config.vdf` (que contiene datos de tu sesión de Steam) solo se lee la sección de Proton.

**Comandos para Konsole:**
- Los comandos van aislados.
- Si uno necesita escribir fuera de las carpetas permitidas (por ejemplo `flatpak install --user`), la IA puede pedir ejecutarlo **fuera del aislamiento**. Esos comandos siempre piden permiso, con aviso.
- La IA sabe que SteamOS tiene el sistema de solo lectura (usa Flatpak o la carpeta personal en vez de pacman) y que en ARM los juegos x86 pasan por una capa de traducción.

### Excel y documentos de Office

- **Leer:**
  - Excel `.xlsx`, `.xlsm` (con macros), plantillas `.xltx` y `.xltm`, y el antiguo `.xls`, con todas las hojas y las **fórmulas** (`D2: =B2*C2`);
  - el código de las **macros VBA**, que solo se lee y nunca se ejecuta;
  - Word (`.docx`, `.docm`), PowerPoint (`.pptx`, `.pptm`) y PDF.
- **Crear** (herramienta `create_document`):
  - **Word** y **PDF** a partir de Markdown, con títulos, listas, tablas y negritas;
  - **Excel** con varias hojas, **fórmulas que funcionan**, encabezado con formato, columnas ajustadas y formatos de número;
  - **PowerPoint** con diapositivas, viñetas y notas.

  Aparecen en el chat como una tarjeta para descargarlos (también desde el móvil). Se guardan en las carpetas modificables y respetan el permiso de escritura.

### Crear programas (`.exe`) en el PC

1. En **Ajustes → 🧰 Herramientas de programación** verás qué hay instalado: Python, Git, Node.js, .NET, compiladores de C/C++ y Rust.
2. Pulsa **Preparar** en «Entorno para crear ejecutables». Crea un entorno de Python propio de G3G3AI con PyInstaller, sin tocar el Python del sistema. En Windows, si no tienes Python, lo instala con `winget`, solo para tu usuario. Git, Node.js y .NET también se instalan con un botón.
3. En el chat, con 🛠 Agente: «Hazme un programa que…». La IA escribe el script y lo compila con la herramienta `build_exe`. El `.exe` aparece en el chat para descargarlo y queda en `G3G3AI-trabajo/dist`.

**Permisos:**
- Compilar ejecuta código, así que pide permiso igual que los comandos.
- Si el programa necesita librerías de internet (`pip`), **siempre** te lo pregunta.
- En Linux y la Konkr, `build_exe` crea ejecutables de Linux. Los `.exe` de Windows se crean en el PC con Windows.

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
  images.py     generación de imágenes (API y stable-diffusion.cpp)
  sync.py       sincronización cifrada entre equipos
  office.py     creación de Word, Excel, PowerPoint y PDF
  steam.py      diagnóstico de juegos de Steam/Proton
  devtools.py   herramientas de programación y compilación de ejecutables
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
