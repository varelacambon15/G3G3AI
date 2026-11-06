# G3G3AI

Cliente de IA tipo LM Studio pensado para la **Konkr Pocket Fit** (SteamOS ARM, aarch64), que también funciona en cualquier Linux.

- 💻 **Modelos locales** con [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`), compilado de forma nativa para tu CPU ARM (dotprod/i8mm).
- ⬇ **Descarga de modelos GGUF** desde Hugging Face con buscador, tamaños, aviso de si caben en la RAM, progreso y reanudación.
- ☁ **Modelos por API**: OpenAI, Anthropic (Claude), OpenRouter y cualquier servidor compatible con OpenAI (Groq, Ollama o LM Studio en otro PC…).
- 📱 **Acceso desde el móvil o el portátil**: interfaz web adaptada al móvil, protegida con contraseña, instalable como app (PWA).
- 📁 **Acceso a archivos**: explorador, vista previa, subida desde el móvil y descarga, adjuntos en el chat y herramientas para que **la IA lea (y opcionalmente escriba) tus archivos**.
- 💬 Chat con streaming, razonamiento visible (modelos *thinking*), historial, editar/regenerar, instrucciones de sistema por conversación y velocidad en tok/s.
- 🔌 **API compatible con OpenAI** en `http://IP:8800/v1`, para usar el modelo local del Konkr desde otras apps.

## Instalación en la Konkr

No hace falta root ni desbloquear el sistema de solo lectura: todo se instala en `/home`.

```bash
cd ~
git clone https://github.com/varelacambon15/G3G3AI.git
cd G3G3AI
./install.sh
```

El instalador:
1. crea un entorno Python en `~/.local/share/g3g3ai/venv`;
2. descarga y compila `llama-server` en `~/.local/share/g3g3ai/llama.cpp` (unos 10-20 min);
3. crea el comando `g3g3ai` y un servicio de usuario que arranca solo al iniciar sesión;
4. muestra la dirección y la contraseña para el móvil.

Opciones: `--vulkan` (GPU Adreno, experimental), `--skip-llama`, `--no-service`, `--update-llama`.

## Uso

- **En la Konkr:** abre `http://127.0.0.1:8800`.
- **Desde el móvil o el portátil** (misma Wi-Fi): abre la dirección `http://IP-DE-LA-KONKR:8800/?token=…` que aparece en **Ajustes → Acceso remoto** o al instalar. En el móvil, «Añadir a pantalla de inicio» la deja como app.
- **Fuera de casa:** instala [Tailscale](https://tailscale.com) en la Konkr y en el móvil, y usa la IP de Tailscale.

Comandos útiles:

```bash
systemctl --user status g3g3ai      # estado
systemctl --user restart g3g3ai     # reiniciar tras cambiar el puerto
journalctl --user -u g3g3ai -f      # registro
g3g3ai --show-token                 # ver la contraseña
g3g3ai --new-token                  # generar una contraseña nueva
```

## Modelos recomendados (8 GB de RAM)

| Modelo | Cuantización | Tamaño aprox. |
|---|---|---|
| Qwen3 4B | Q4_K_M | 2,5 GB |
| Gemma 3 4B it | Q4_K_M | 2,5 GB |
| Llama 3.2 3B Instruct | Q4_K_M | 2 GB |
| Qwen2.5 Coder 3B | Q4_K_M | 2 GB |
| Phi-4 mini | Q4_K_M | 2,5 GB |

Los modelos de 7-8B en Q4 (unos 4,5-5 GB) funcionan, pero van justos de memoria con SteamOS abierto. Para la herramienta de archivos conviene usar modelos que admitan *tool calling* (Qwen3, Llama 3.2, …).

## Archivos y seguridad

- La interfaz y la IA solo ven las carpetas de **Ajustes → Carpetas accesibles** (por defecto, tu carpeta personal).
- La escritura de archivos por parte de la IA está **desactivada** por defecto.
- Los archivos subidos desde el móvil al adjuntarlos se guardan en `~/G3G3AI-subidas`.
- Configuración (incluidas las claves API) en `~/.config/g3g3ai/config.json` (permisos 600); historial en `~/.local/share/g3g3ai/g3g3ai.db`.
- La conexión es HTTP en tu red local. No abras el puerto 8800 a internet: para acceder desde fuera usa Tailscale o una VPN.

## Estructura

```
g3g3ai/
  server.py     API FastAPI + interfaz + autenticación + proxy /v1
  llama.py      gestión del proceso llama-server
  hub.py        búsqueda/descarga en Hugging Face y modelos locales
  providers.py  streaming OpenAI/Anthropic + bucle de herramientas
  tools.py      herramientas de archivos para la IA
  files.py      acceso a archivos limitado a las carpetas permitidas
  db.py         historial en SQLite
  static/       interfaz web (HTML/CSS/JS sin dependencias)
install.sh      instalador
tests/          pruebas (con un llama-server simulado)
```

Pruebas: `pip install pytest && python -m pytest tests`.
