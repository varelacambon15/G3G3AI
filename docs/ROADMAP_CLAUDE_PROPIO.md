# Hoja de ruta: G3G3AI como «Claude propio»

Fecha: 24/11/2026. Estado: **borrador para decidir**, sin código. Fuentes de la comparación con Claude al final.

## 1. Objetivo (según tu encargo)

- App de **Windows** y app de **Android**. Sin Konkr (descartado por ahora).
- Un asistente tipo Claude que use **modelos locales** del PC y **modelos externos** que tú aportes: OpenRouter (incluidos los gratuitos), **OpenCode Go** (MiMo, DeepSeek…), y las APIs que ya existen (DeepSeek, OpenAI, Gemini, Groq, Anthropic…).
- Sencilla por fuera, completa por dentro (AGENTS.md).
- Pensada como respaldo para cuando Claude no esté disponible.
- Desde Android, solo modelos en la nube; con control remoto, usar también los modelos locales del PC.

## 2. Lo que ya tiene G3G3AI (según README y AGENTS.md)

| Función | Estado |
|---|---|
| Chat con modelos locales (llama.cpp) y APIs | Hecho |
| Selector por conversación, favoritos y ocultos | Hecho |
| Modo Auto (local/API según el mensaje) | Hecho |
| Agente: leer, buscar, editar archivos y ejecutar comandos, con permisos | Hecho |
| Búsqueda web con citas | Hecho |
| Adjuntos: PDF, Word, Excel, PowerPoint, imágenes | Hecho |
| Memoria entre conversaciones | Hecho |
| Generación de imágenes (API y local) | Hecho |
| Resumen automático de conversaciones largas | Hecho |
| Sincronización entre equipos | Hecho |
| Code con OpenCode (sesiones, permisos) | Hecho (sin probar contra OpenCode real) |
| Acceso desde móvil y navegador (Tailscale, contraseña) | Hecho |
| App Android (WebView + chat directo con API) | Hecho |
| Copia de seguridad cifrada | Hecho |
| Servidores MCP | Hecho (configuración en texto) |
| Vista previa de HTML/SVG | Hecho |
| Ajustes agrupados | En curso (encargo a OpenCode) |

## 3. Lo que le falta frente a Claude

**Crítico para tu objetivo**
1. **Selector unificado de modelos**: local + OpenRouter (con sus gratuitos) + OpenCode Go, con etiqueta «gratis», «cuota», «coste» y aviso de cuota agotada. Depende del plan A (proveedor OpenCode Go) ya propuesto.
2. **Control del ordenador** (computer use): capturas de pantalla, ratón y teclado, con permiso por acción y parada de emergencia. Es el punto más sensible de seguridad.
3. **Control remoto y «Dispatch»**: encargar tareas desde el móvil a agentes del PC y ver el progreso. Hoy existe el acceso por navegador; falta una experiencia de encargo y seguimiento pensada para móvil.

**Importante**
4. **Proyectos**: espacio persistente con sus archivos, instrucciones y memoria propia. Hoy la memoria es global.
5. **Skills**: paquetes de instrucciones reutilizables que se activan cuando hacen falta.
6. **Navegador interactivo**: hoy solo lee páginas; Claude puede navegar, rellenar formularios y actuar.
7. **Compartir**: exportar o compartir una conversación o un artefacto con enlace.
8. **Voz**: dictar y escuchar respuestas (sobre todo en Android).
9. **Razonamiento**: un control claro para activar el modo de pensar por modelo (hoy solo existe para modelos locales).
10. **Ramas y edición**: editar un mensaje anterior y reintentar desde él, si no está ya. **Hay que verificarlo en la app.**

**Pulido**
11. Artefactos y documentos exportables (Word, PDF, presentación) desde el chat.
12. Tareas programadas más visibles (hoy están en «Tareas»).

## 4. Riesgos que hay que decidir antes de construir

- **Control del ordenador** puede borrar, enviar o comprar cosas sin querer. Necesita: aprobación por acción en Windows, lista de aplicaciones permitidas, parada de emergencia desde el móvil, y registro de lo que hizo. Propongo empezar solo con **capturas + solo lectura** y pasar a escribir (ratón/teclado) en una fase posterior.
- **Control remoto desde el móvil** amplía la superficie de ataque. Mantener Tailscale + contraseña y no abrir puertos a internet. Cualquier función nueva que muestre claves debe respetar lo que ya dice AGENTS.md.
- **Dependencias nuevas** (por ejemplo, una librería para capturar pantalla o simular ratón) requieren tu permiso.

## 5. Fases propuestas

| Fase | Contenido | Depende de |
|---|---|---|
| 0 | Ajustes agrupados | Encargo en curso |
| 1 | Selector unificado (local + OpenRouter + OpenCode Go), gratis/cuota/coste, aviso de cuota agotada | Plan A |
| 2 | Proyectos y Skills | Fase 1 |
| 3 | Control del ordenador, solo lectura (capturas) | Decisión de seguridad |
| 4 | Control del ordenador, escritura con aprobación | Fase 3 |
| 5 | Encargos desde Android con seguimiento (Dispatch) | Acceso remoto |
| 6 | Voz y compartir | Fase 2 |
| 7 | Navegador interactivo | Fase 3 |

## 6. Decisiones que necesito de ti

1. **Prioridades**: ¿Fase 1 (modelos) primero, o control del ordenador?
2. **Control del ordenador**: ¿solo capturas al principio, o también ratón y teclado desde el primer día?
3. **Dependencias**: ¿permites una librería para capturar pantalla y simular ratón en Windows?
4. **Modelos gratuitos de OpenRouter**: el límite del plan gratuito es de unas 50 peticiones al día y 20 por minuto, y se amplía con compras de crédito (ver fuentes). ¿Quieres que la app avise cuando llegues al límite?

**Nota sobre el encargo:** esta es una ampliación grande que cambia la arquitectura (controles de seguridad, proyectos, cliente Android). Según tu propio CLAUDE.md, una decisión así la debe tomar Sonnet con esfuerzo medio, y Opus solo para lo irreversible. Recomiendo cambiar a Sonnet para la arquitectura de las fases 2–4 y dejar a OpenCode el código mecánico.

## 7. Fuentes

- Funciones de Claude (computer use, remote control, projects, skills, memoria): notas de versión de Anthropic y artículos de 2026 que las resumen; verifica las fechas en [support.claude.com/en/articles/12138966-release-notes](https://support.claude.com/en/articles/12138966-release-notes).
- Límites gratuitos de OpenRouter: [openrouter.ai/collections/free-models](https://openrouter.ai/collections/free-models) (página oficial, cambia a menudo) y [openrouter.ai/blog/tutorials/free-llm-apis-compared](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) (comparativa). Las cifras de terceros no coinciden entre sí: confirma en la página oficial antes de fijarlas en la app.
