# G3G3AI para Android (versión de prueba)

App cliente: se conecta a G3G3AI en tu Konkr o tu PC (la IA se ejecuta allí).

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
