# G3G3AI

Cliente de IA al estilo de LM Studio para tus **PC** (Windows, Linux, macOS), al que te conectas también desde el **móvil**. Combina modelos locales (llama.cpp) con modelos por API (DeepSeek, Claude, OpenAI…) y puede trabajar como **agente** sobre tus archivos.

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
- 🔄 **Sincronización entre equipos**: con una clave común se sincronizan conversaciones, memoria y APIs. Además, cada equipo puede usar el modelo local del otro (Ajustes → Añadir proveedor → «Otro equipo con G3G3AI»).
- ✦ **Interfaz cuidada**: barra lateral con búsqueda y conversaciones por fecha, compositor con menú «+» y herramientas, vista previa de HTML/SVG en un panel lateral, modo claro y oscuro.
- 📱 **Desde el móvil**: interfaz web protegida con contraseña, instalable como app.
- 📁 Explorador de archivos, subida y descarga, adjuntos en el chat.

## Instalación

### Linux (x64 y ARM, incluido SteamOS)

No necesita root. En una terminal:

```bash
git clone https://github.com/varelacambon15/G3G3AI.git ~/G3G3AI
cd ~/G3G3AI && ./install.sh
```

El instalador:
1. compila llama.cpp optimizado para tu procesador (unos 10–20 minutos);
2. crea un servicio que arranca G3G3AI solo al iniciar sesión;
3. instala Chromium (Flatpak, solo para tu usuario) si no tienes navegador.

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

- **App (APK):** se conecta a tu PC, y además tiene un **💬 Chat directo con API** para usar DeepSeek, Claude, OpenAI… desde el móvil sin ningún equipo encendido. Las claves se importan de un equipo con un toque. Ver `android/README.md`.
- **Como cliente web** (sin instalar nada): abre en el navegador la dirección que aparece en Ajustes → Acceso remoto, y usa «Añadir a pantalla de inicio».
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
- 🛡 **Aislamiento Linux:** se ejecutan con *bubblewrap*, el mismo aislamiento que usa Flatpak. Ven el sistema en solo lectura, solo pueden escribir en las carpetas modificables (y en un `/tmp` temporal), y las rutas protegidas aparecen vacías. El aislamiento no puede ocultar las rutas protegidas por patrón (como `.env`): solo las indicadas con ruta completa.
- **Sin aislamiento (Windows, macOS):** se pide confirmación siempre, aunque estén en *Automático*. «Permitir siempre aquí» sí lo evita dentro de una conversación.
- **Bloqueados siempre:** `rm -rf /` o `~`, formatear discos, escribir directamente en discos, bombas fork…
- **Siempre preguntan**, incluso en *Automático* o con «permitir siempre»: `sudo`, `curl … | sh`, apagar o reiniciar, borrados recursivos, `git push --force`, servicios del sistema, el registro de Windows…

**Búsqueda web:** `web_search` usa DuckDuckGo sin clave, o Brave Search / Tavily con clave (más fiables; ambos tienen plan gratuito). `fetch_url` lee páginas públicas, pero nunca puede acceder a tu red local (127.0.0.1, 192.168.x.x, `.local`…), para que una página no pueda hacer que la IA toque tus dispositivos. La IA cita las fuentes con enlaces.

### Memoria

- La IA guarda notas breves con la herramienta `memory_save` cuando aprende algo útil y duradero, o cuando le dices «recuerda que…». «Olvida…» las borra. Cada recuerdo guardado aparece en el chat como 💾.
- Al empezar cada conversación recibe tus recuerdos como contexto.
- En **Ajustes → 🧠 Memoria** puedes ver, editar, añadir y borrar recuerdos. En «General» puedes desactivar la memoria, impedir que la IA guarde recuerdos por su cuenta, o no enviar la memoria a las APIs externas (así solo la conoce el modelo local).
- No guarda nada que parezca una contraseña o una clave.
- Cada equipo (PC, portátil) tiene su propia memoria.

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
- **En local** (Modelos → 🎨 Generación de imágenes): instala stable-diffusion.cpp (en Windows con un botón; en Linux con `./install.sh --with-sd`), descarga un modelo de imagen GGUF (por ejemplo, SD Turbo) y pulsa 🎨 en él. En el otro equipo, cuenta con bastante espera por imagen y calidad modesta. En un PC con tarjeta gráfica va mucho mejor.

### Sincronizar tus equipos

1. En uno de los equipos: **Ajustes → 🔄 Sincronización → Generar clave nueva**. Copia la clave (6 grupos de 4 letras y números).
2. En el otro equipo: pega la clave en el mismo sitio y pulsa **Guardar clave**.
3. En cualquiera de los dos, añade la dirección del otro (por ejemplo `192.168.1.50`, la ves en su *Ajustes → Acceso remoto*) y pulsa **Sincronizar ahora**. A partir de ahí se sincronizan solos cada 2 minutos.

**Qué se sincroniza:** conversaciones, memoria, proveedores API **con sus claves** (si configuras DeepSeek en el PC, aparece en el otro equipo), modo Auto, instrucciones, permisos del agente y ajustes de imágenes y búsqueda web.
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

**Comandos:**
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
- En Linux, `build_exe` crea ejecutables de Linux. Los `.exe` de Windows se crean en el PC con Windows.

### ⭐ Favoritos y modelos ocultos

- **☆/★** junto al selector marca el modelo actual como favorito. Los favoritos salen arriba, en el grupo «⭐ Favoritos».
- **⚙ Gestionar modelos…** (al final del selector) abre una ventana con buscador para marcar favoritos y ocultar modelos, uno a uno o todos los de un proveedor (respetando los favoritos). Útil con OpenRouter, que lista cientos.
- El modelo seleccionado se sigue viendo aunque esté oculto. Favoritos y ocultos se sincronizan entre tus equipos.

### 💻 Code
La pestaña **Code** es el chat con el agente activado y un panel de proyecto:
- **Proyecto:** fija la carpeta de trabajo (se recuerda por conversación).
- **Cambios:** archivos creados/editados con su diff; deshaz uno a uno o todos.
- **Terminal:** comandos que ejecutó la IA y su salida. **Plan:** la lista de tareas en curso.
- **Comandos con `/`:** `/plan`, `/clear`, `/undo`, `/init` (crea `G3G3AI.md`), `/review`, `/test`, `/help`.

### 🐙 GitHub
Con un **token de GitHub** (Ajustes → «Token de GitHub», o la variable `GITHUB_TOKEN`) el agente puede:
- **Leer** sin preguntar: issues, pull requests (con sus archivos), estado del CI, archivos del repositorio y búsqueda de código.
- **Escribir** siempre con tu permiso (no se puede marcar «siempre»): crear issues, comentar, cerrar y abrir pull requests.
- **Git** con `run_command`: crea ramas, commits y `git push` (el push siempre pide confirmación; los push forzados avisan como peligrosos). Usa el remoto `origin` de la carpeta del proyecto.
Flujo típico: «arregla el issue #12» → lee el issue, crea una rama, edita, ejecuta los tests, hace commit, te pide permiso para el push, abre el PR y comprueba el CI.

### 🕒 Tareas programadas
En la pestaña **Tareas** el agente trabaja solo a la hora que elijas (cada día a una hora, cada N minutos o una vez), con el modelo que tengas seleccionado, aunque no haya ninguna ventana abierta (G3G3AI debe estar en marcha en ese equipo). Ejemplo: «cada noche a las 03:00 ejecuta los tests y cuéntame qué falla».
- **Sin supervisión:** nadie puede aprobar acciones, así que todo lo que pediría permiso se **deniega** (comandos fuera de «Comandos permitidos», servidores MCP, escribir en GitHub…) y el agente continúa sin ello y lo cuenta en su informe.
- **Por defecto solo lee.** Con «puede editar archivos» aplica ediciones dentro de tus carpetas permitidas (deshacibles desde la conversación).
- El resultado queda en una conversación 🕒; la interfaz avisa al terminar, y puedes ejecutarla ya, pausarla o borrarla. Si G3G3AI estaba apagado, lo vencido hace menos de 6 h se ejecuta al arrancar.

### 🔌 Servidores MCP
Conecta herramientas externas con el estándar **MCP** (archivos, bases de datos, Jira, navegador…). En Ajustes → «Servidores MCP» añade una línea por servidor:

```
archivos = npx -y @modelcontextprotocol/server-filesystem C:\Proyectos
basedatos = DB_URL=postgres://… npx -y @modelcontextprotocol/server-postgres
```
Sus herramientas aparecen al agente como `mcp__servidor__herramienta`. **Cada llamada te pide permiso** (puedes marcar «Permitir siempre aquí»), no se usan en modo Plan y un servidor roto no afecta a los demás. «Probar servidores» muestra su estado y sus herramientas. Los servidores se ejecutan con tus permisos de usuario: instala sólo los que conozcas.

### 🏠 Modelos locales
Los modelos locales reciben un trato propio para que funcionen mejor con el agente:
- **Menos carga por turno:** un modelo pequeño ve solo 8 herramientas con descripciones cortas (~750 tokens en vez de ~2.200) y un prompt más corto; el plan y lo cambiante va al final para reutilizar la caché del prompt.
- **Más fiables:** temperatura baja con herramientas (Ajustes → «temperatura con herramientas», 0.3), JSON de las llamadas reparado si el modelo lo escribe mal (comas finales, comillas simples…) y error claro si no se puede.
- **Más rápidos:** `llama-server` con una sola ranura (todo el contexto es para tu conversación), caché de prompt y sin «pensar» por defecto en Qwen3 y similares (actívalo en Ajustes si prefieres razonamiento a costa de velocidad). La salida pedida nunca supera la mitad del contexto.
- **🧪 Probar con el agente** (Modelos → modelo cargado): comprueba si el modelo llama bien a las herramientas y a qué velocidad va, y te dice qué hacer si no.

### 📧 Buscar en tu correo
Ajustes → **Correo** → «La IA puede buscar en mi correo» (desactivado por defecto). Lee los buzones del perfil de **Thunderbird** detectado (Mail e ImapMail) y, si quieres, carpetas con archivos `.eml` o buzones mbox extra. Si tu correo está también en Outlook, con Thunderbird basta; los archivos `.pst/.ost` de Outlook no se leen.
- **Solo lectura:** el correo original no se toca. Se crea un índice local (con búsqueda de texto rápida, sin distinguir acentos) que se actualiza solo con lo nuevo.
- **Qué puede hacer:** `mail_search` (texto, remitente, destinatario, asunto, fechas AAAA-MM-DD, carpeta; la papelera y el spam se excluyen) y `mail_read` (cabeceras y texto; los adjuntos solo se listan). Ejemplo: «¿Qué mensajes me llegaron esta semana de jmoreno?».
- **Permiso en cada uso** (puedes marcar «permitir siempre aquí»). Si el modelo es de una API en la nube, el aviso lo dice: **los mensajes que lea se envían a ese servicio**. Con un modelo local no sale nada de tu equipo.
- **Contra engaños:** el texto de un correo se trata como datos; se le ordena al modelo no obedecer instrucciones escritas dentro de un mensaje.
- **Límites:** los mensajes IMAP solo están en disco si Thunderbird los guarda sin conexión; si compactas una carpeta en Thunderbird, pulsa «Reconstruir».

### 🎚 Se adapta al modelo
Según el modelo elegido (o lo que fijes en Ajustes → «Exigencia del agente»):
- **Pequeño** (≤8B o desconocido en local): pocas herramientas, reglas cortas, una llamada a la vez y salidas de herramientas más pequeñas, para que acierte más.
- **Mediano** (Haiku, mini/flash, 9–29B): método completo.
- **Grande** (Sonnet/Opus, GPT-5, DeepSeek V3/R1, 30B+): método completo, más Git/GitHub y trabajo en profundidad (leer varios archivos a la vez, revisarse a sí mismo).

### ⚡ Como Claude Code
- **Salida en vivo:** los comandos muestran lo que imprimen mientras corren; al detener la respuesta (■ o Esc) se mata el comando y sus procesos hijos.
- **Ayudantes (`delegate`):** para investigar sin llenar el contexto, el agente lanza un ayudante de sólo lectura con contexto propio que devuelve un informe breve con rutas y datos.
- **Ayudantes que editan, en paralelo:** `delegate_edit` lanza ayudantes que trabajan en una **copia aislada** del proyecto (pueden editar y ejecutar comandos sin tocar tus archivos) y devuelven una propuesta con su diff; varios a la vez para repartir tareas independientes. `apply_patch` la aplica al proyecto real pidiéndote permiso con el diff, y no pisa archivos que hayan cambiado mientras tanto. Los comandos del ayudante necesitan el aislamiento de Linux; sin él sólo edita.
- **Escribe mientras trabaja:** pulsa Intro y el mensaje queda en cola; se envía al terminar.
- **Atajos:** `Esc` detiene · `Mayús+Tab` cambia de modo (Normal → Aceptar ediciones → Plan) · `Ctrl/Cmd+Mayús+O` conversación nueva.
- **Pide acceso en vez de rendirse:** si necesita una carpeta que no está permitida (Documentos, Descargas…), el agente te lo pide con `request_folder_access` (siempre con tu confirmación; nunca la raíz del disco, tu carpeta personal entera ni carpetas del sistema) y queda guardado en Ajustes.
- **Adjuntos del correo:** `mail_save_attachments` guarda los adjuntos de los correos que elijas en una carpeta («guarda en Documentos/Javier Moreno los adjuntos que me ha mandado jmoreno estos 10 días»).
- **Comparar carpetas:** `compare_dirs` compara dos carpetas (solo lectura) y dice qué falta en cada una, qué tiene el mismo nombre pero contenido distinto (compara el contenido, no solo la fecha) y qué se ha movido o renombrado. Ignora `.git`, `node_modules` y similares, más los patrones que le des. Respeta las rutas protegidas. Ejemplo: «compara mis Documentos con la copia del disco externo y dime qué me falta».
- **Conoce tu equipo:** la herramienta `system_info` le da al agente tu procesador, RAM, gráfica, disco y el modelo local que mejor te encaja, sin pedirte que ejecutes comandos. El agente viene **activado por defecto**; si lo desactivas (⚙ junto al cuadro de texto), el modelo lo sabe y te lo dice en vez de «no puedo».
- **Correo protegido:** los perfiles de Thunderbird y Outlook están en las rutas protegidas por defecto (también en Windows y macOS). Si algún día quieres que la IA lea tu correo, quítalos de Ajustes → «Rutas protegidas» y añade la carpeta a las visibles.
- **Copia de seguridad cifrada:** Ajustes → «💾 Copia de seguridad» exporta ajustes (con claves API), memoria y, si quieres, conversaciones a un archivo `.g3bak` cifrado con tu contraseña, para importarlo en otro equipo.
- **Uso y coste:** cada respuesta muestra sus tokens y un coste estimado; Ajustes → «💸 Uso y coste» resume el mes por modelo. Los precios son orientativos y editables; con un límite mensual te avisa al 80% y al 100%.
- **Contexto a la vista:** junto al cuadro de texto ves el % de contexto usado; `/compact` resume la conversación ahora y conserva el último intercambio.
- **Volver atrás (↶):** en cada mensaje tuyo, el botón ↶ devuelve los archivos que la IA tocó desde ahí a su estado anterior y borra esa parte de la conversación para que reformules. Lo que hagan los comandos no se deshace.
- **Permisos a tu medida:** en el aviso de un comando pulsa «Permitir este comando siempre»; se guarda en Ajustes → «Comandos permitidos» (admite `*`, p.ej. `npm test*`). Los peligrosos siguen pidiendo permiso y un comando encadenado (`;`, `&&`, `|`) solo pasa si coincide exacto.
- **Menos permisos, sin abrir lo peligroso («Confiar en mis carpetas»):** en el primer aviso de un comando o edición aparece el botón *Confiar en mis carpetas* (o en Ajustes). Con él dejan de pedir permiso: crear y editar archivos en tus carpetas modificables (deshacible), `python`/`pytest` sobre scripts de esas carpetas, `git status/diff/log…`, `npm test/build`, `dir`/`ls` de carpetas visibles y filtros inofensivos como `2>&1` o `| more`. **Siguen pidiendo permiso:** `pip install`, `git push`, `python -c`, comandos encadenados (`;`, `&&`, tuberías a otros programas), redirecciones a archivos y todo lo que esté fuera de tus carpetas. Un script de Python puede hacer lo mismo que tú: actívalo solo si confías en lo que escribe la IA.
- **Comprueba lo que hace:** si edita archivos de un proyecto con pruebas reconocibles (pytest, npm, cargo, go) y no las ejecuta, se le pide que las pase antes de dar la tarea por terminada.

### 🛠 Cómo trabaja el agente

El modo **🛠 Agente** sigue unas reglas de trabajo pensadas para que se comporte con método, tanto con modelos grandes como con locales pequeños:

- **Investiga antes de cambiar:** `list_dir`, `grep_files` (busca texto o expresiones regulares *dentro* de los archivos) y `read_file`.
- **Edita con cuidado:** `edit_file` admite varios cambios a la vez (`edits`) y `replace_all`; respeta los saltos de línea y el BOM del archivo; si un fragmento no coincide, indica la línea más parecida; si un cambio falla no se aplica ninguno. **Exige haber leído el archivo antes** y detecta si cambió por fuera desde entonces.
- **Ves el cambio exacto:** al pedir permiso aparece el **diff** (rojo/verde). Los cambios que no se pueden aplicar se rechazan antes, sin molestarte.
- **Plan visible:** en tareas largas crea un plan (📋) con `todo_write` y lo va marcando. El plan se conserva entre mensajes.
- **Recuerda lo que hizo:** el historial incluye un registro compacto de las herramientas usadas en las últimas respuestas (qué archivos leyó, qué editó, qué comandos ejecutó), así que en el mensaje siguiente no empieza de cero.
- **↩ Deshacer cambios:** arriba aparece este botón cuando la IA ha modificado o creado archivos en la conversación. Los devuelve a como estaban (no cubre lo que hagan los comandos).
- **Permisos del agente** (⚙︎ junto al cuadro de mensaje): *Normal* (pregunta según Ajustes), *Plan* (sólo lee y propone un plan numérico, sin tocar nada) y *Aceptar ediciones* (edita sin preguntar; los comandos siguen pidiendo permiso).
- **Proyectos:** en «📝 Instrucciones y carpeta del proyecto» puedes dar a cada conversación su carpeta de trabajo. Si dentro hay un archivo `G3G3AI.md`, la IA lo lee como instrucciones del proyecto (lenguaje, cómo ejecutar las pruebas, estilo…), como hace `CLAUDE.md` con Claude Code.
- **Robustez:** si un modelo escribe la llamada a una herramienta como texto (`<tool_call>…`), se ejecuta igualmente; si anuncia un paso y se para, se le pide que lo haga; si repite la misma acción sin avanzar, se le avisa y se corta; si la respuesta se corta por longitud, continúa sola. Los pasos máximos por respuesta se ajustan en Ajustes (por defecto 40).

### ✂ Respuestas largas que se cortan
Cuando una respuesta termina antes de tiempo, G3G3AI ya no falla en silencio: explica el motivo y deja un botón **▶ Continuar**.
- **Límite de longitud**: continúa solo hasta 3 veces; si aun así no basta, avisa y ofrece «Continuar».
- **Tope del proveedor** (créditos de OpenRouter, 8192 en DeepSeek…): lee el máximo admitido y reintenta solo con ese valor.
- **Error o filtro del proveedor / conexión perdida**: se muestra el motivo en el propio mensaje.
- **Contexto local lleno**: el error indica subir «Contexto» en Ajustes o abrir otra conversación.
- Se envían latidos cada 15 s para que proxys y túneles no corten durante razonamientos largos, y el chat deja de repintar a cada frame cuando el texto es enorme.

### 🔎 Buscador de modelos

En **Modelos → Buscar y descargar modelos**:
- **Búsqueda** en Hugging Face (formato GGUF), ordenada por descargas, tendencia, «me gusta» o más recientes.
- **Explorar** sin escribir: Chat general, Código, Visión, Razonamiento, MoE rápidos, Pequeños, Imágenes.
- **Cada resultado muestra:** tamaño (4B, 8B, 30B con 3B activos…), si es MoE, capacidades (visión, código, razonamiento), memoria aproximada, si **cabe en este equipo**, descargas, «me gusta», cuándo se actualizó y si ya lo tienes.
- **Filtros:** tamaño, visión, código, razonamiento, «solo los que caben» y ordenación local.
- **Archivos de cada modelo:** qué significa cada cuantización, ⭐ la **recomendada para tu equipo**, aviso de lo que no cabe o ya está descargado, y descarga automática del proyector de visión si hace falta.

### 🧭 Recomendación según tu equipo

En **Modelos → Recomendado para este equipo**, G3G3AI detecta el procesador (núcleos, AVX2, AVX-512, dotprod/i8mm), la RAM y las gráficas con su memoria (NVIDIA, AMD, Intel integrada, Adreno), y propone:
- el tamaño de modelo que encaja (3–4B, 7–8B, 12–14B, MoE «A3B» o 27–32B) y si conviene cargarlo en la gráfica o en el procesador;
- el motor que debes instalar (CPU o Vulkan);
- contexto, hilos, capas GPU y argumentos extra. **Aplicar ajustes** los guarda con un clic;
- búsquedas en Hugging Face para encontrar esos modelos, y avisos (procesador sin AVX2, gráfica AMD sin ROCm, modelos MoE que van justos de RAM…).

### 🦙 Ollama (motor alternativo, cómodo en el PC)

En **Modelos → Ollama**:
- **Instalar Ollama:** en Windows con `winget`, o con el instalador oficial si no hay winget. En macOS con Homebrew. En Linux se muestra el comando oficial (pide contraseña de administrador). En SteamOS no se recomienda: usa llama.cpp.
- **Iniciar Ollama** si está instalado pero parado.
- **Descargar modelos** por nombre (`qwen3:8b`, `gemma3:4b`…), con progreso y sugerencias según tu hardware, y **borrarlos**.
- **Usar en el chat:** activa el proveedor «Ollama (local)» en el selector. Funciona con el modo Auto, el agente, la memoria y las fotos (con modelos con visión).

## Modelos recomendados

Con 8 GB de RAM, mejor modelos de 3–4B en versión Q4_K_M: **Qwen3 4B** (bueno con herramientas y en modo agente), **Gemma 3 4B**, **Llama 3.2 3B**, **Qwen2.5 Coder 3B**. En un PC con 16 GB o más y tarjeta gráfica puedes usar modelos de 7–14B.

## Comandos útiles (Linux)

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
  hardware.py   detección del hardware y recomendación de modelo y ajustes
  agent_prompt.py  instrucciones de trabajo del agente
  undo.py       copias para deshacer los cambios de una conversación
  ollama.py     integración con Ollama (instalar, modelos, proveedor)
  providers.py  streaming OpenAI/Anthropic + bucle de herramientas
  llama.py      proceso llama-server
  engine.py     descarga de llama.cpp precompilado (Windows/macOS/Linux x64)
  hub.py        Hugging Face
  desktop.py    app de escritorio (.exe)
  static/       interfaz web
android/        instalación experimental en Termux
packaging/      especificación de PyInstaller e icono
```

Pruebas: `pip install -r requirements.txt pytest && python -m pytest tests` (la prueba de interfaz usa Playwright: `pip install playwright && playwright install chromium`; si no está, se omite).
Generar el ejecutable: `pip install pyinstaller pywebview && pyinstaller packaging/g3g3ai.spec`. GitHub Actions lo compila en cada push, y crea una Release con `G3G3AI.exe` al subir una etiqueta `v*`.
