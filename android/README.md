# G3G3AI para Android (versión de prueba)

Dos formas de uso:

1. **Conectar a un equipo** (otro equipo con G3G3AI): todas las funciones, incluidos modelos locales,
   agente, búsqueda web y archivos.
2. **Chat directo con API**: sin equipo encendido. La app habla directamente con el proveedor que elijas, del mismo
   catálogo que el escritorio: **OpenCode Go**, OpenRouter, Claude, OpenAI, DeepSeek, Gemini, Groq, Cerebras, Mistral,
   xAI, Kimi, GLM, Qwen y más, o cualquier API compatible con OpenAI. Eliges el proveedor, pegas la clave (con enlace a
   dónde conseguirla) y pulsas **Probar**. Respuestas en streaming con formato, razonamiento, copiar, **volver a generar**
   y **editar** mensajes, conversaciones guardadas en el móvil con **búsqueda**, instrucciones del sistema y fotos para
   modelos con visión. Las claves se guardan en el almacenamiento privado de la app; con **Importar** se copian de un equipo
   guardado. Sin agente, búsqueda web ni modelos locales (para eso, conecta a tu PC).
   El catálogo se genera desde el del escritorio con `python scripts/gen_android_catalog.py`.

- Lista de equipos (nombre, dirección y contraseña). Abre el último usado al iniciar.
- Cámara y selector de archivos para adjuntar fotos y documentos.
- Descargas con la sesión iniciada (se guardan en Descargas).
- Los enlaces externos (fuentes de la búsqueda web) se abren en el navegador.

## Instalar
1. Descarga `G3G3AI-android.apk` de la Release del repositorio.
2. Ábrelo en el móvil y permite «instalar apps de origen desconocido» para tu navegador o gestor de archivos.
   Está firmada con una clave de prueba: Android puede avisar (Play Protect); es normal en una app que no viene de la tienda.

## Compilar
`gradle -p android assembleRelease` (Gradle 8.11 y Android SDK 35). GitHub Actions lo hace en cada push.

`termux-install.sh` es otra cosa: ejecuta el servidor G3G3AI completo dentro de Termux (experimental).
