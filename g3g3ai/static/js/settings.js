// G3G3AI · Ajustes, sincronización, proveedores y nube.
// Parte 7/8 de la interfaz: se cargan en orden y comparten el ámbito global.
// --- Ajustes ---------------------------------------------------------------------------
const FIELDS = [
  ["memory_enabled", "🧠 Usar la memoria entre conversaciones", "checkbox"],
  ["memory_auto", "🧠 La IA puede guardar recuerdos por su cuenta", "checkbox", "Cada recuerdo nuevo aparece en el chat. También puedes decirle «recuerda que…» u «olvida…»."],
  ["memory_api", "🧠 Enviar la memoria también a modelos por API", "checkbox", "Si lo desactivas, sólo el modelo local conoce tus recuerdos."],
  ["vision_fallback", "👁 Modelo para describir imágenes", "model", "Cuando el modelo elegido no ve imágenes (p.ej. DeepSeek), éste las describe. Vacío = el local si tiene visión."],
  ["context_budget", "Contexto máximo para APIs (tokens)", "number", "Por encima, lo más antiguo de la conversación se resume automáticamente."],
  ["image_provider", "🎨 Imágenes: proveedor", "imgprov", "Escribe «/imagen descripción» en el chat o pide a la IA que dibuje algo."],
  ["image_model", "🎨 Imágenes: modelo (API)", "text", "OpenAI: gpt-image-1 · Gemini: imagen-3.0-generate-002 · OpenRouter: google/gemini-2.5-flash-image"],
  ["image_mode", "🎨 Imágenes: tipo de API", "imgmode"],
  ["image_size", "🎨 Imágenes: tamaño", "imgsize"],
  ["image_dir", "🎨 Carpeta de imágenes", "text", "Vacío = ~/G3G3AI-imagenes"],
  ["sd_steps", "🎨 Local: pasos", "number", "1–4 para modelos «turbo»; 20–30 para modelos normales."],
  ["sd_cfg", "🎨 Local: CFG", "number", "1.0 para «turbo»; ~7 para modelos normales."],
  ["sd_max_side", "🎨 Local: tamaño máximo (px)", "number", "En equipos modestos, 512 es razonable; más grande tarda mucho más."],
  ["router_mode", "Modo Auto: estrategia", "router"],
  ["router_fast", "Modo Auto: modelo rápido", "model", "Normalmente el local (gratis, privado)."],
  ["router_strong", "Modo Auto: modelo potente", "model", "Normalmente una API (DeepSeek, Claude…). Se usa para código, análisis, documentos largos y el modo agente."],
  ["default_system_prompt", "Instrucciones del sistema", "textarea"],
  ["temperature", "Temperatura", "number", "0 = preciso · 1 = creativo"],
  ["max_tokens", "Máx. tokens por respuesta", "number"],
  ["models_dir", "Carpeta de modelos", "text"],
  ["llama_server_path", "Ruta de llama-server", "text", "Vacío = autodetectar (~/.local/share/g3g3ai/llama.cpp)"],
  ["llama_ctx", "Contexto por defecto", "number", "0 = automático: se calcula con la memoria libre y el tamaño del modelo. Más contexto = más RAM."],
  ["llama_threads", "Hilos (0 = auto)", "number"],
  ["llama_gpu_layers", "Capas en GPU", "number", "Sólo si compilaste llama.cpp con Vulkan (Adreno)."],
  ["llama_extra_args", "Argumentos extra de llama-server", "text", "p.ej. --flash-attn on --cache-type-k q8_0"],
  ["autoload_last_model", "Cargar el último modelo al arrancar", "checkbox"],
  ["file_roots", "Carpetas visibles (una por línea)", "lines", "La interfaz y la IA sólo pueden ver (leer) estas carpetas."],
  ["ai_write", "Agente: escribir/editar archivos", "perm"],
  ["ai_commands", "Agente: ejecutar comandos", "perm", "«Preguntar» muestra cada acción para que la apruebes (también desde el móvil). Con aislamiento activo, los comandos sólo pueden escribir en las carpetas modificables; sin él, siempre se pide confirmación. Los comandos peligrosos se bloquean."],
  ["agent_max_steps", "Pasos máximos del agente por respuesta", "number", "Cada llamada a una herramienta es un paso. Si se agota, escribe «continúa»."],
  ["agent_workdir", "Carpeta de trabajo del agente", "text", "Debe estar dentro de las carpetas que la IA puede modificar."],
  ["ai_game_write", "🎮 La IA puede trabajar con los juegos de Steam", "checkbox", "Lee y, pidiendo permiso cada vez, modifica las carpetas de los juegos y sus prefijos de Proton. Antes de cambiar un archivo guarda una copia «.g3g3ai-original»."],
  ["monthly_budget_usd", "Límite de gasto mensual estimado ($)", "number", "Te avisa al llegar al 80% y al 100%. 0 = sin aviso."],
  ["model_prices", "Precios por modelo ($ por millón de tokens, uno por línea)", "lines", "Formato: «modelo = entrada, salida», p.ej. «deepseek-chat = 0.27, 1.10». Sobrescribe los precios orientativos."],
  ["mcp_servers", "Servidores MCP (uno por línea)", "lines", "Formato: nombre = [VAR=valor] comando args. Se guardan solos al salir del cuadro; luego usa «Probar servidores»."],
  ["mcp_default_model", "Modelo para Claude (MCP)", "model", "El que usa Claude Code al delegar en G3G3AI sin indicar uno. Vacío = el modelo local cargado."],
  ["mail_paths", "Correo: rutas extra (una por línea)", "lines", "Carpetas con buzones mbox o archivos .eml, además del perfil de Thunderbird detectado."],
  ["commands_trusted", "Confiar en mis carpetas (menos permisos)", "checkbox", "Sin preguntar: crear y editar archivos en tus carpetas modificables (deshacible), python/pytest sobre scripts de esas carpetas, git de solo lectura (status, diff, log…), npm test/build, dir/ls de carpetas visibles y filtros como «| more» o «2>&1». Nunca: pip install, git push, python -c, comandos encadenados (; & |) ni nada fuera de tus carpetas. Un script de Python puede hacer cualquier cosa que tú puedas, así que actívalo solo si confías en lo que escribe la IA."],
  ["command_allow", "Comandos permitidos sin preguntar (uno por línea)", "lines", "Se ejecutan sin pedir confirmación (salvo los peligrosos). Puedes usar * como comodín, p.ej. «npm test*» o «git status». Un comando encadenado (con ; & | >) sólo se admite si coincide exactamente."],
  ["write_roots", "Carpetas que la IA puede modificar (una por línea)", "lines", "Añade aquí tus proyectos. Fuera de estas carpetas la IA sólo puede leer."],
  ["blocked_paths", "Rutas protegidas (una por línea)", "lines", "Nadie puede verlas desde G3G3AI, ni la IA ni la interfaz. Sin barra = patrón de nombre (p.ej. .env, *.pem)."],
  ["command_sandbox", "Aislamiento de comandos", "sandbox"],
  ["web_provider", "Búsqueda web: proveedor", "webprov", "DuckDuckGo no necesita clave pero a veces bloquea. Brave y Tavily tienen plan gratuito y son más fiables."],
  ["web_api_key", "Búsqueda web: clave API", "password", "Sólo para Brave o Tavily."],
  ["hf_token", "Token de Hugging Face (opcional)", "password", "Sólo para modelos restringidos."],
  ["voice_engine", "Dictado por voz", "voiceeng", "Automático: whisper.cpp en este equipo si tienes el modelo de voz; si no, Groq u OpenAI si los has añadido; si no, el del navegador. Pulsa el micrófono para configurarlo."],
  ["voice_language", "Idioma del dictado", "text", "auto = detectarlo. O un código: es, en, ca, gl, eu, fr…"],
  ["voice_binary", "Ruta de whisper-cli", "text", "Vacío = autodetectar (edición completa, ~/.local/share/g3g3ai/whisper o el PATH)."],
  ["github_token", "Token de GitHub (opcional)", "password", "Permite a la IA leer issues, PR y CI, y —pidiendo permiso— crear issues y pull requests. Crea uno en github.com/settings/tokens con acceso a los repos que quieras."],
  ["agent_temperature", "Modelos locales: temperatura con herramientas", "number", "Más baja = llamadas a herramientas más fiables. 0.2–0.4 suele ir bien."],
  ["local_thinking", "Modelos locales: dejarles «pensar»", "checkbox", "Qwen3 y similares razonan antes de responder: mejor en problemas difíciles pero mucho más lento. Desactivado = respuestas directas."],
  ["agent_profile", "Exigencia del agente según el modelo", "profile", "Automático ajusta herramientas y reglas a la potencia del modelo (pequeño, mediano, grande). Fuérzalo si un modelo local rinde mejor o peor de lo esperado."],
  ["localhost_without_token", "Este mismo equipo entra sin contraseña", "checkbox"],
  ["port", "Puerto", "number", "Requiere reiniciar el servicio."],
];
$("#bk-export").addEventListener("click", async () => {
  const password = $("#bk-pass").value;
  try {
    const r = await fetch("/api/backup/export", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password, conversations: $("#bk-convs").checked }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const a = h("a", { href: URL.createObjectURL(await r.blob()), download: `g3g3ai-${new Date().toISOString().slice(0, 10)}.g3bak` });
    document.body.append(a); a.click(); a.remove();
    toast("Copia exportada. Guarda la contraseña: sin ella no se puede abrir.", 6000);
  } catch (e) { toast(e.message, 6000); }
});
$("#bk-import").addEventListener("click", () => { if ($("#bk-pass").value) $("#bk-file").click(); else toast("Escribe primero la contraseña de la copia"); });
$("#bk-file").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  if (!confirm("Se importarán los ajustes (incluidas las claves API) y la memoria de la copia, y sustituirán a los actuales. ¿Continuar?")) return;
  try {
    const buf = new Uint8Array(await f.arrayBuffer());
    let bin = ""; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    const r = await api("/api/backup/import", { method: "POST", body: { data: btoa(bin), password: $("#bk-pass").value } });
    toast(`Importado: ${r.memories} recuerdos, ${r.conversations} conversaciones${r.settings ? " y los ajustes" : ""}.`, 6000);
    $("#bk-pass").value = ""; loadSettings();
  } catch (er) { toast(er.message, 6000); }
});
function renderClaude() {
  const box = $("#claude-box"); if (!box) return; box.innerHTML = "";
  const st = S.status || {};
  const port = S.settings?.port || 8800;
  const url = `http://127.0.0.1:${port}/mcp`;
  const needsToken = !S.settings?.localhost_without_token;
  const cmd = `claude mcp add --transport http g3g3ai ${url}` + (needsToken && st.token ? ` --header "Authorization: Bearer ${st.token}"` : "");
  box.append(h("p", { class: "muted" }, "Claude Code puede delegar en G3G3AI consultas para tu modelo local (privado y gratis) u otro proveedor, o tareas sobre tus archivos y tu correo. Ejecuta esto una vez en una terminal:"),
    h("div", { class: "row" }, h("code", { class: "access-url grow" }, cmd), h("button", { class: "ghost small", onclick: () => copyText(cmd, "Orden copiada") }, ico("copy"), "Copiar")),
    h("p", { class: "muted" }, "Después, en Claude Code, pide por ejemplo: «pregúntale a g3g3ai con el modelo local…». Las tareas con herramientas se hacen sin supervisión: lo que pediría permiso se deniega. Cada consulta queda como conversación en G3G3AI."));
}
async function renderMail() {
  const box = $("#mail-box"); box.innerHTML = "";
  box.append(h("p", { class: "muted" }, "Deja que la IA busque en tu correo (solo lectura): «mensajes de esta semana de Pérez», «qué me pidió Ana sobre la nómina»… Usa los buzones de Thunderbird (si el mismo correo está también en Outlook, Thunderbird basta) o carpetas con archivos .eml. El correo original no se modifica; se crea un índice local. ",
    h("b", {}, "Privacidad:"), " cada búsqueda te pide permiso, y si usas un modelo en la nube (OpenRouter, DeepSeek…) los mensajes que lea se envían a ese servicio. Con un modelo local no sale nada de tu equipo."));
  try {
    const st = await api("/api/mail/status");
    box.append(h("label", { class: "check" }, h("input", { type: "checkbox", checked: st.enabled, onchange: async (e) => {
      await api("/api/settings", { method: "PUT", body: { ...(await api("/api/settings")), mail_enabled: e.target.checked } }).catch((er) => toast(er.message));
      if (e.target.checked) await api("/api/mail/index", { method: "POST", body: {} }).catch(() => {});
      renderMail();
    } }), " La IA puede buscar en mi correo"));
    box.append(h("p", { class: "muted" }, st.profiles.length ? "Perfil de Thunderbird detectado: " + st.profiles[0] : "No se encontró Thunderbird. Añade la carpeta de tu correo en «Correo: rutas extra» más abajo."));
    if (st.enabled) {
      const fmt = (t) => t ? new Date(t * 1000).toLocaleDateString() : "—";
      box.append(h("p", {}, st.running ? `⏳ Indexando… ${st.files_done}/${st.files_total} buzones · ${st.messages} mensajes` :
        `${st.messages} mensajes indexados de ${st.files} buzones/archivos (${fmt(st.oldest)} → ${fmt(st.newest)})` + (st.error ? " · ⚠ " + st.error : "") + (st.fts ? "" : " · sin búsqueda de texto rápida (FTS5 no disponible)")));
      box.append(h("div", { class: "row" },
        h("button", { class: "ghost small", disabled: st.running, onclick: async () => { await api("/api/mail/index", { method: "POST", body: {} }); setTimeout(renderMail, 500); } }, "Actualizar índice"),
        h("button", { class: "ghost small", disabled: st.running, onclick: async () => { if (confirm("¿Reconstruir el índice desde cero? Puede tardar.")) { await api("/api/mail/index", { method: "POST", body: { rebuild: true } }); setTimeout(renderMail, 500); } } }, "Reconstruir"),
        h("button", { class: "ghost small", onclick: () => renderMail() }, "Refrescar")));
      if (st.running) setTimeout(renderMail, 3000);
    }
  } catch (e) { box.append(h("p", { class: "muted" }, e.message)); }
}
async function renderMcp(refresh = false) {
  const box = $("#mcp-box"); box.innerHTML = "";
  box.append(h("p", { class: "muted" }, "Conecta herramientas externas (archivos, bases de datos, Jira, navegador…) con el estándar MCP. Añade una línea por servidor en «Servidores MCP» más abajo, p. ej. ",
    h("code", {}, "archivos = npx -y @modelcontextprotocol/server-filesystem C:\\Proyectos"), ". Cada llamada te pide permiso."));
  try {
    const { servers } = await api("/api/mcp?refresh=" + refresh);
    if (!servers.length) box.append(h("p", { class: "muted" }, "No hay servidores configurados."));
    for (const s of servers) box.append(h("div", { class: "mcp-server" },
      h("b", {}, (s.ok ? "🟢 " : "🔴 ") + s.name), " ", h("code", {}, s.command),
      s.error ? h("div", { class: "muted" }, "⚠ " + s.error) : null,
      s.tools.length ? h("ul", { class: "mcp-tools" }, s.tools.map((t) => h("li", { title: t.description }, t.name))) : null));
  } catch (e) { box.append(h("p", { class: "muted" }, e.message)); }
  box.append(h("button", { class: "ghost small", onclick: async (ev) => { ev.target.disabled = true; ev.target.textContent = "Comprobando…"; await renderMcp(true); } }, "Probar servidores"));
}
async function renderUsage() {
  const box = $("#usage-box"); box.innerHTML = "";
  try {
    const u = await api("/api/usage");
    const money = (v) => "$" + v.toFixed(v < 1 ? 3 : 2);
    const k = (n) => n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : n >= 1000 ? (n / 1000).toFixed(1) + "k" : n;
    box.append(h("p", {}, `Este mes: `, h("b", {}, money(u.total.cost)), ` estimados · ${k(u.total.input)} tokens de entrada · ${k(u.total.output)} de salida`
      + (u.budget ? ` · límite ${money(u.budget)} (${u.budget_pct}%)` : "")));
    const rows = Object.entries(u.models).sort((a, b) => b[1].cost - a[1].cost);
    if (!rows.length) box.append(h("p", { class: "muted" }, "Todavía no hay uso registrado este mes."));
    else box.append(h("table", { class: "usage-table" }, h("tr", {}, ["Modelo", "Respuestas", "Entrada", "Salida", "Coste"].map((t) => h("th", {}, t))),
      rows.map(([name, m]) => h("tr", {}, h("td", {}, name), h("td", {}, m.calls), h("td", {}, k(m.input)), h("td", {}, k(m.output)),
        h("td", {}, m.unpriced ? "sin precio" : money(m.cost))))));
    box.append(h("p", { class: "muted" }, "Los precios son orientativos; ajústalos en «Precios por modelo». Los modelos locales cuestan 0."));
  } catch (e) { box.append(h("p", { class: "muted" }, "No se pudo cargar el uso: " + e.message)); }
}
async function loadSettings() {
  S.settings = await api("/api/settings");
  await refreshStatus();
  const st = S.status, acc = $("#access-info"); acc.innerHTML = "";
  acc.append(h("p", {}, "Conecta el móvil o portátil a la misma red Wi-Fi y abre:"));
  for (const u of st.urls) acc.append(h("code", { class: "access-url" }, st.token ? `${u}/?token=${st.token}` : u));
  if (!st.urls.length) acc.append(h("p", { class: "muted" }, "No se detectó ninguna IP de red local."));
  acc.append(h("p", {}, "Contraseña: ", st.token ? h("code", {}, st.token) : h("span", { class: "muted" }, "(sólo visible desde el propio equipo)")));
  acc.append(h("p", { class: "muted" }, "Consejo: en el móvil usa «Añadir a pantalla de inicio» para tenerla como app. Para acceder fuera de casa, instala Tailscale en ambos dispositivos. ",
    "Otras apps compatibles con OpenAI pueden usar ", h("code", {}, `${st.urls[0] || "http://IP:" + S.settings.port}/v1`), " con la contraseña como API key."));

  acc.append(h("p", { class: "muted" }, `Equipo: ${st.hostname} · ${st.platform} · G3G3AI ${st.version}`));
  if (st.is_local) acc.append(h("button", { class: "danger small", onclick: async () => {
    if (!confirm("¿Apagar el servidor de G3G3AI? Dejarás de poder conectarte desde otros dispositivos.")) return;
    await api("/api/shutdown", { method: "POST" }).then(() => toast("Apagando…")).catch((e) => toast(e.message));
  } }, "⏻ Apagar servidor"));

  const pe = $("#providers-edit"); pe.innerHTML = "";
  S.settings.providers.forEach((p, idx) => pe.append(providerBox(p, idx)));
  loadMemory();
  renderSync();
  renderDevtools();
  renderUsage(); renderCloud();
  renderMcp();
  renderMail();
  renderClaude();

  const f = $("#settings-form"); f.innerHTML = "";
  for (let [key, label, type, hint] of FIELDS) {
    const v = S.settings[key];
    let inp;
    if (type === "textarea") inp = h("textarea", { name: key, rows: 3 }, v || "");
    else if (type === "lines") inp = h("textarea", { name: key, rows: 2 }, (v || []).join("\n"));
    else if (type === "checkbox") inp = h("input", { type: "checkbox", name: key, checked: !!v });
    else if (type === "perm") inp = selectEl(key, v, [["off", "Desactivado"], ["ask", "Preguntar cada vez"], ["auto", "Automático (sin preguntar)"]]);
    else if (type === "sandbox") {
      const sb = S.status?.sandbox || {};
      inp = selectEl(key, v, [["auto", "Usar si está disponible (recomendado)"], ["off", "Desactivado"]]);
      hint = !sb.supported ? "No disponible en este sistema: los comandos piden siempre confirmación."
        : sb.available ? (sb.active ? "🛡 Activo: los comandos sólo pueden escribir en las carpetas modificables." : "Disponible pero desactivado.")
        : "Falta bubblewrap (bwrap). En SteamOS viene con Flatpak; en otras distros instala el paquete «bubblewrap».";
    }
    else if (type === "imgprov") {
      const opts = [["", "Desactivado"], ["local", "Local (stable-diffusion.cpp)"]];
      for (const p of S.settings.providers.filter((p) => p.enabled && p.type !== "anthropic")) opts.push([p.id, p.name]);
      inp = selectEl(key, v || "", opts);
    }
    else if (type === "imgmode") inp = selectEl(key, v, [["auto", "Automático"], ["images", "/images/generations (OpenAI, Gemini…)"], ["chat", "Chat con imágenes (OpenRouter)"]]);
    else if (type === "imgsize") inp = selectEl(key, v, [["1024x1024", "Cuadrada 1024×1024"], ["1024x1536", "Vertical 1024×1536"], ["1536x1024", "Horizontal 1536×1024"], ["512x512", "Pequeña 512×512"]]);
    else if (type === "profile") inp = selectEl(key, v || "auto", [["auto", "Automático (según el modelo)"], ["small", "Modelo pequeño: pocas herramientas, un paso a la vez"], ["standard", "Mediano: método completo"], ["full", "Grande: método completo + trabajo en profundidad"]]);
    else if (type === "voiceeng") inp = selectEl(key, v, [["auto", "Automático"], ["local", "Sólo en este equipo (whisper.cpp)"], ["cloud", "Sólo en la nube (Groq / OpenAI)"], ["browser", "El del navegador"]]);
    else if (type === "webprov") inp = selectEl(key, v, [["duckduckgo", "DuckDuckGo (sin clave)"], ["brave", "Brave Search (clave)"], ["tavily", "Tavily (clave)"]]);
    else if (type === "router") inp = selectEl(key, v, [["smart", "Inteligente (según la tarea)"], ["local_first", "Local primero"], ["api_first", "API primero"]]);
    else if (type === "model") {
      const opts = MS.catalog.map((m) => [m.value, `${m.label} · ${m.group}`]);  // todos, también los ocultos
      if (key === "vision_fallback") opts.unshift(["", "Automático (el modelo local si tiene visión)"]);
      if (key === "mcp_default_model") opts.unshift(["", "El modelo local cargado"]);
      if (v && !opts.some((o) => o[0] === v)) opts.push([v, v + " (no disponible ahora)"]);
      inp = selectEl(key, v, opts);
    }
    else inp = h("input", { type, name: key, value: v ?? "", step: type === "number" ? "any" : null });
    const sec = SETTINGS_SECTION[key] || "general";
    const adv = ADVANCED_KEYS.has(key) ? "1" : "";
    const lab = h("label", {}, String(label).replace(/^[^\p{L}\p{N}]+\s*/u, "")); lab.dataset.stab = sec; inp.dataset.stab = sec;
    lab.dataset.adv = inp.dataset.adv = adv;
    lab.dataset.key = inp.dataset.key = key;
    lab.dataset.find = `${label} ${hint || ""} ${key.replace(/_/g, " ")}`.toLowerCase();
    f.append(lab, inp);
    if (hint) { const hd = h("div", { class: "hint" }, hint); hd.dataset.stab = sec; hd.dataset.adv = adv; hd.dataset.key = key; f.append(hd); }
  }
  showSettingsTab(store.get("settings_tab", "general"));
  if ($("#settings-search").value.trim()) searchSettings();
}
// Lo esencial a la vista; lo técnico, plegado (la IA también puede cambiarlo si se lo pides)
const ADVANCED_KEYS = new Set(("context_budget router_mode router_fast router_strong vision_fallback memory_api image_mode image_dir " +
  "sd_steps sd_cfg sd_max_side llama_server_path llama_extra_args llama_gpu_layers llama_threads models_dir agent_max_steps " +
  "agent_workdir ai_game_write blocked_paths command_sandbox agent_profile command_allow model_prices localhost_without_token " +
  "port hf_token agent_temperature image_model web_api_key voice_binary").split(" "));
const SETTINGS_SECTION = {};
for (const [sec, keys] of Object.entries({
  local: "image_provider image_model image_mode image_size image_dir sd_steps sd_cfg sd_max_side models_dir llama_server_path llama_ctx llama_threads llama_gpu_layers llama_extra_args autoload_last_model hf_token agent_temperature local_thinking voice_engine voice_language voice_binary",
  agent: "file_roots ai_write ai_commands agent_max_steps agent_workdir ai_game_write commands_trusted command_allow write_roots blocked_paths command_sandbox agent_profile github_token",
  mail: "mcp_servers mail_paths mcp_default_model", data: "monthly_budget_usd model_prices", access: "localhost_without_token port",
})) for (const k of keys.split(" ")) SETTINGS_SECTION[k] = sec;
const SETTINGS_TITLES = { general: "General", providers: "", agent: "Agente y permisos", local: "Modelos locales e imágenes", mail: "Correo e integraciones", data: "Datos y uso", access: "Acceso" };
// Buscar entre todas las opciones (de cualquier pestaña, también las avanzadas)
const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
function searchSettings() {
  const q = norm($("#settings-search").value.trim());
  if (!q) { $("#settings-noresults").classList.add("hidden"); showSettingsTab(store.get("settings_tab", "general")); return; }
  const words = q.split(/\s+/);
  const hit = (text) => { const t = norm(text); return words.every((w) => t.includes(w)); };
  $$("#settings-tabs [data-stab]").forEach((b) => b.classList.remove("active"));
  let found = 0;
  const keys = new Set();
  $$("#settings-form label[data-key]").forEach((l) => { if (hit(l.dataset.find)) keys.add(l.dataset.key); });
  $$("#settings-form [data-key]").forEach((el) => el.classList.toggle("hidden", !keys.has(el.dataset.key)));
  found += keys.size;
  const formCard = $("#settings-form").closest(".card");
  formCard.classList.toggle("hidden", !keys.size);
  $("#settings-form-title").textContent = "Opciones";
  $("#adv-toggle")?.classList.add("hidden");
  $$("#view-settings .card[data-stab]").forEach((c) => {
    if (c === formCard) return;
    const ok = hit(c.textContent + " " + [...c.querySelectorAll("input,textarea")].map((i) => i.placeholder || "").join(" "));
    c.classList.toggle("hidden", !ok);
    if (ok) found++;
  });
  $("#settings-noresults").classList.toggle("hidden", found > 0);
}
$("#settings-search").addEventListener("input", searchSettings);
$("#settings-search").addEventListener("keydown", (e) => { if (e.key === "Escape") { e.target.value = ""; searchSettings(); } });
function showSettingsTab(tab) {
  store.set("settings_tab", tab);
  $$("#settings-tabs [data-stab]").forEach((b) => b.classList.toggle("active", b.dataset.stab === tab));
  $$("#view-settings .card[data-stab]").forEach((c) => { if (c.dataset.stab !== "all") c.classList.toggle("hidden", c.dataset.stab !== tab); });
  let any = false, advCount = 0;
  const showAdv = !!S.showAdvanced;
  $$("#settings-form [data-stab]").forEach((el) => {
    const inTab = el.dataset.stab === tab, adv = el.dataset.adv === "1";
    if (inTab && adv && el.tagName === "LABEL") advCount++;
    const on = inTab && (!adv || showAdv);
    el.classList.toggle("hidden", !on); any = any || on;
  });
  let btn = $("#adv-toggle");
  if (!btn) { btn = h("button", { id: "adv-toggle", type: "button", class: "ghost small", onclick: () => { S.showAdvanced = !S.showAdvanced; showSettingsTab(store.get("settings_tab", "general")); } }); $("#settings-form").after(btn); }
  btn.textContent = showAdv ? "Ocultar opciones avanzadas" : `Mostrar opciones avanzadas (${advCount})`;
  btn.classList.toggle("hidden", !advCount);
  any = any || advCount > 0;
  const formCard = $("#settings-form").closest(".card");
  formCard.classList.toggle("hidden", !any);
  $("#settings-form-title").textContent = SETTINGS_TITLES[tab] || "Opciones";
}
$$("#settings-tabs [data-stab]").forEach((b) => b.addEventListener("click", () => {
  $("#settings-search").value = ""; $("#settings-noresults").classList.add("hidden");
  showSettingsTab(b.dataset.stab);
}));
// --- Herramientas de programación --------------------------------------------------------------
let devTimer = null;
async function renderDevtools(refresh = false) {
  const box = $("#devtools-box"); if (!box) return;
  const d = await api("/api/devtools" + (refresh ? "?refresh=true" : ""));
  box.innerHTML = "";
  const win = d.tools.platform === "win32";
  box.append(h("p", { class: "muted" }, "Con el modo 🛠 Agente, la IA puede escribir programas y compilarlos. "
    + (win ? "Para crear .exe necesita el entorno de compilación (Python + PyInstaller, aparte del sistema)."
           : "En este equipo crea ejecutables de Linux; los .exe de Windows se crean en el PC con Windows.")));
  const names = [["pyinstaller", "Entorno para crear ejecutables (PyInstaller)"], ["python", "Python"], ["git", "Git"],
    ["node", "Node.js"], ["dotnet", ".NET SDK"], ["gcc", "GCC (C/C++)"], ["cl", "MSVC (C/C++)"], ["cargo", "Rust"]];
  const ul = h("ul", { class: "list" });
  for (const [k, label] of names) {
    if (k === "cl" && !win) continue;
    const v = d.tools[k];
    const canInstall = !v && (k === "pyinstaller" || d.installable.includes(k));
    ul.append(h("li", {},
      h("span", { class: "name" }, label),
      h("span", { class: "badge " + (v ? "ok" : "") }, v ? "✔ " + v : "no instalado"),
      canInstall ? h("button", { class: k === "pyinstaller" ? "primary small" : "ghost small", disabled: d.state.status === "running",
        onclick: async () => { await api("/api/devtools/install", { method: "POST", body: { what: k } }); renderDevtools(); } },
        k === "pyinstaller" ? "Preparar" : "Instalar") : null));
  }
  box.append(ul);
  const st = d.state;
  if (st.status !== "idle") {
    box.append(h("p", {}, st.status === "running" ? `⏳ Instalando ${st.what}…` : st.status === "done" ? `✔ ${st.what} instalado` : `✕ Error: ${st.error}`));
    box.append(h("details", { open: st.status !== "done" }, h("summary", {}, "Registro"), h("pre", { class: "logs" }, (st.log || []).join("\n"))));
  }
  box.append(h("div", { class: "row end" }, h("button", { class: "ghost small", onclick: () => renderDevtools(true) }, "Volver a comprobar")));
  clearTimeout(devTimer);
  if (st.status === "running" && S.view === "settings") devTimer = setTimeout(() => renderDevtools(true), 2500);
}

// --- Sincronización entre equipos -------------------------------------------------------------
async function renderSync() {
  const box = $("#sync-box"); box.innerHTML = "";
  const st = await api("/api/sync/status");
  box.append(h("p", { class: "muted" }, "Pon la misma clave en todos tus equipos con G3G3AI (PC, portátil…) y añade la dirección del otro. "
    + "Se sincronizan conversaciones, memoria y proveedores API (con sus claves). Cada equipo conserva sus carpetas, modelos locales y contraseña. "
    + `Todo viaja cifrado con la clave. Se sincroniza cada ${Math.round(st.interval / 60)} min.`));
  const keyRow = h("div", { class: "row" });
  if (st.has_key) {
    const shown = h("span", { class: "sync-key" }, "••••-••••-••••-••••-••••-••••");
    keyRow.append(h("b", {}, "Clave:"), shown,
      h("button", { class: "ghost small", onclick: async (e) => {
        const { key } = await api("/api/sync/key"); shown.textContent = key; e.target.remove();
      } }, "Mostrar"),
      h("button", { class: "ghost small", onclick: () => { keyRow.replaceWith(keyEditor()); } }, "Cambiar"));
    box.append(keyRow);
  } else box.append(keyEditor());

  box.append(h("h3", { style: "font-size:15px;margin:16px 0 6px" }, "Equipos"));
  const ul = h("ul", { class: "list" });
  const peers = st.peers || [];
  if (!peers.length) ul.append(h("li", { class: "muted" }, "Ninguno todavía. Añade la dirección del otro equipo (la ves en su Ajustes → Acceso remoto)."));
  for (const p of peers) {
    const s2 = st.status[p.url];
    ul.append(h("li", {},
      h("div", { class: "name" }, p.name || "Equipo (aún sin sincronizar)", h("div", { class: "sub" }, p.url)),
      s2 ? h("span", { class: "badge " + (s2.ok ? "ok" : "bad"), title: s2.message || "" },
        s2.ok ? `✔ ${new Date(s2.when * 1000).toLocaleTimeString()} · ↓${s2.received} ↑${s2.sent}` : "✕ " + s2.message)
        : h("span", { class: "badge" }, "pendiente"),
      h("button", { class: "ghost small", onclick: async () => {
        await api("/api/settings", { method: "PUT", body: { sync_peers: peers.filter((x) => x.url !== p.url) } }); renderSync();
      } }, "Quitar")));
  }
  box.append(ul);
  const add = h("input", { class: "grow", placeholder: "http://192.168.1.50:8800" });
  box.append(h("form", { class: "row", onsubmit: async (e) => {
    e.preventDefault();
    let url = add.value.trim(); if (!url) return;
    if (!/^https?:\/\//.test(url)) url = "http://" + url;
    if (!/:\d+(\/|$)/.test(url.replace(/^https?:\/\//, ""))) url = url.replace(/\/$/, "") + ":8800";
    await api("/api/settings", { method: "PUT", body: { sync_peers: [...peers, { url: url.replace(/\/$/, "") }] } });
    renderSync();
  } }, add, h("button", { class: "ghost small" }, "Añadir equipo")));
  for (const [label, s2] of Object.entries(st.status).filter(([k]) => k.startsWith("recibido de")))
    box.append(h("p", { class: "muted", style: "font-size:13px" }, `↔ ${label}: ${new Date(s2.when * 1000).toLocaleString()}`));
  box.append(h("div", { class: "row end" }, h("button", { class: "primary small", disabled: !st.has_key || !peers.length, onclick: async (e) => {
    e.target.disabled = true; e.target.textContent = "Sincronizando…";
    try { await api("/api/sync/now", { method: "POST" }); toast("Sincronización terminada"); S.models = {}; await loadProviders(); loadConversations(); }
    catch (err) { toast(err.message); }
    renderSync();
  } }, "🔄 Sincronizar ahora")));
}
function keyEditor() {
  const inp = h("input", { class: "grow sync-key", placeholder: "Pega aquí la clave del otro equipo" });
  return h("div", {},
    h("div", { class: "row" },
      h("button", { class: "primary small", onclick: async () => {
        if (!confirm("¿Generar una clave nueva? Tendrás que ponerla también en tus otros equipos.")) return;
        const { key } = await api("/api/sync/new-key", { method: "POST" });
        prompt("Clave nueva. Cópiala y pégala en Ajustes → Sincronización de tus otros equipos:", key);
        renderSync();
      } }, "Generar clave nueva"),
      h("span", { class: "muted" }, "o")),
    h("form", { class: "row", style: "margin-top:8px", onsubmit: async (e) => {
      e.preventDefault(); if (!inp.value.trim()) return;
      await api("/api/settings", { method: "PUT", body: { sync_key: inp.value.trim().toUpperCase() } });
      toast("Clave guardada"); renderSync();
    } }, inp, h("button", { class: "ghost small" }, "Guardar clave")));
}

async function loadMemory() {
  const box = $("#memory-list"); box.innerHTML = "";
  const items = await api("/api/memory");
  if (!items.length) box.append(h("li", { class: "muted" }, "Todavía no hay recuerdos."));
  for (const m of items) {
    box.append(h("li", {},
      h("span", { class: "name" }, m.content, h("div", { class: "sub" }, (m.source === "manual" ? "añadido a mano · " : "guardado por la IA · ") + new Date(m.updated * 1000).toLocaleString())),
      h("button", { class: "ghost small", onclick: async () => {
        const t = prompt("Editar recuerdo", m.content); if (t == null) return;
        await api(`/api/memory/${m.id}`, { method: "PUT", body: { content: t } }).catch((e) => toast(e.message)); loadMemory();
      } }, "✎"),
      h("button", { class: "ghost small", onclick: async () => { await api(`/api/memory/${m.id}`, { method: "DELETE" }); loadMemory(); } }, "🗑")));
  }
}
$("#memory-add").addEventListener("submit", async (e) => {
  e.preventDefault(); const inp = $("#memory-new"); if (!inp.value.trim()) return;
  try { await api("/api/memory", { method: "POST", body: { content: inp.value } }); inp.value = ""; loadMemory(); }
  catch (err) { toast(err.message); }
});
$("#memory-clear").addEventListener("click", async () => {
  if (!confirm("¿Borrar todos los recuerdos?")) return;
  await api("/api/memory", { method: "DELETE" }); loadMemory();
});
function selectEl(name, value, options) {
  const s = h("select", { name });
  for (const [v, label] of options) s.append(h("option", { value: v, selected: v === value }, label));
  return s;
}
function providerBox(p, idx) {
  const set = (k) => (e) => { S.settings.providers[idx][k] = e.target.type === "checkbox" ? e.target.checked : e.target.value; };
  return h("div", { class: "provider-box" },
    h("div", { class: "row" },
      h("label", { class: "toggle grow" }, h("input", { type: "checkbox", checked: !!p.enabled, onchange: set("enabled") }), h("b", {}, p.name), h("span", { class: "badge" }, p.type)),
      h("button", { class: "ghost small", onclick: () => { S.settings.providers.splice(idx, 1); loadSettingsProvidersOnly(); autosaveSettings(); } }, "Quitar")),
    h("details", { open: !!p.enabled }, h("summary", { class: "muted" }, p.api_key ? "Configurado ✔" : "Configurar"),
      h("div", { class: "form-grid" },
        h("label", {}, "Nombre"), h("input", { value: p.name, oninput: set("name") }),
        h("label", {}, "URL base"), h("input", { value: p.base_url, oninput: set("base_url") }),
        h("label", {}, "Clave API"), h("input", { type: "password", value: p.api_key || "", placeholder: "sk-…", oninput: set("api_key") }),
        h("label", {}, "¿Ve imágenes?"), (() => {
          const sel = selectEl("", p.vision === true ? "yes" : p.vision === false ? "no" : "auto",
            [["auto", "Automático"], ["yes", "Sí"], ["no", "No (describirlas con otro modelo)"]]);
          sel.onchange = (e) => { S.settings.providers[idx].vision = { yes: true, no: false, auto: null }[e.target.value]; };
          return sel;
        })())));
}
function loadSettingsProvidersOnly() {
  const pe = $("#providers-edit"); pe.innerHTML = "";
  S.settings.providers.forEach((p, idx) => pe.append(providerBox(p, idx)));
}
// --- Añadir proveedor: catálogo con búsqueda, clave y prueba de conexión ------------------------
async function providerDialog(focusId) {
  let dlg = $("#provider-dialog");
  if (!dlg) { dlg = h("dialog", { id: "provider-dialog" }); document.body.append(dlg); }
  dlg.innerHTML = "";
  const list = await api("/api/providers/catalog");
  const search = h("input", { type: "search", placeholder: "Buscar proveedor…", class: "grow" });
  const grid = h("div", { class: "prov-grid" });
  const detail = h("div", { class: "prov-detail hidden" });
  dlg.append(h("div", { class: "dialog-head" }, h("b", {}, "Añadir un proveedor de IA"),
    h("button", { class: "icon-btn", onclick: () => dlg.close(), "aria-label": "Cerrar" }, ico("x"))),
    h("div", { class: "row" }, search), grid, detail);
  const draw = () => {
    const q = search.value.trim().toLowerCase();
    grid.innerHTML = "";
    for (const c of list.filter((c) => !q || (c.name + " " + c.description + " " + c.tags.join(" ")).toLowerCase().includes(q)))
      grid.append(h("button", { class: "prov-card" + (c.configured ? " added" : ""), onclick: () => open(c) },
        h("b", {}, c.name), h("span", { class: "muted" }, c.description),
        h("span", { class: "prov-tags" }, c.configured ? h("span", { class: "tag ok" }, "Configurado") : null, c.tags.map((t) => h("span", { class: "tag" }, t)))));
    grid.append(h("button", { class: "prov-card", onclick: () => open({ id: "", name: "", type: "openai", base_url: "", key_url: "", description: "", tags: [], needs_key: false, custom: true }) },
      h("b", {}, "Otro (compatible con OpenAI)"), h("span", { class: "muted" }, "Cualquier servidor con API de OpenAI: otro equipo con G3G3AI, vLLM, LiteLLM…")));
  };
  const open = (c) => {
    grid.classList.add("hidden"); search.closest(".row").classList.add("hidden"); detail.classList.remove("hidden"); detail.innerHTML = "";
    const name = h("input", { value: c.name, placeholder: "Nombre" });
    const url = h("input", { value: c.base_url, placeholder: "https://…/v1" });
    const key = h("input", { type: "password", placeholder: c.needs_key ? "Pega aquí tu clave API" : "Clave (si hace falta)", autocomplete: "off" });
    const type = selectEl("", c.type, [["openai", "Compatible con OpenAI"], ["anthropic", "Anthropic"]]);
    const out = h("div", { class: "prov-result muted" });
    const body = () => ({ preset: c.custom ? "" : c.id, id: c.custom ? "" : c.id, name: name.value.trim(), base_url: url.value.trim(), api_key: key.value.trim(), type: type.value });
    detail.append(
      h("button", { class: "ghost small", onclick: () => { detail.classList.add("hidden"); grid.classList.remove("hidden"); search.closest(".row").classList.remove("hidden"); } }, "← Volver"),
      h("h3", {}, c.name || "Proveedor personalizado"), c.description ? h("p", { class: "muted" }, c.description) : null,
      c.key_url ? h("p", {}, h("a", { href: c.key_url, target: "_blank", rel: "noopener" }, c.needs_key ? "Conseguir una clave ↗" : "Descargar / documentación ↗")) : null,
      h("div", { class: "form-grid" },
        c.custom ? h("label", {}, "Nombre") : null, c.custom ? name : null,
        h("label", {}, "Clave API"), key,
        h("label", {}, "URL base"), url,
        c.custom ? h("label", {}, "Tipo") : null, c.custom ? type : null),
      out,
      h("div", { class: "row end" },
        h("button", { class: "ghost small", onclick: async () => {
          out.textContent = "Probando…";
          try {
            const r = await api("/api/providers/test", { method: "POST", body: body() });
            out.textContent = r.ok ? `Conectado: ${r.count} modelos (${r.sample.slice(0, 4).join(", ")}${r.count > 4 ? "…" : ""})` : "No funciona: " + r.error;
            out.className = "prov-result " + (r.ok ? "ok" : "err");
          } catch (e) { out.textContent = e.message; out.className = "prov-result err"; }
        } }, "Probar conexión"),
        h("button", { class: "primary small", onclick: async () => {
          try {
            await api("/api/providers/add", { method: "POST", body: body() });
            dlg.close(); toast(`${c.name || name.value} añadido`, 3000);
            S.settings = await api("/api/settings"); loadSettingsProvidersOnly(); loadProviders();
          } catch (e) { out.textContent = e.message; out.className = "prov-result err"; }
        } }, "Añadir")));
    (c.needs_key ? key : url).focus();
  };
  search.oninput = draw;
  draw();
  dlg.showModal();
  if (focusId) { const c = list.find((x) => x.id === focusId); if (c) open(c); } else search.focus();
}
$("#add-provider").addEventListener("click", () => providerDialog());
$("#add-provider-legacy")?.addEventListener("click", () => {
  const kind = prompt("¿Qué quieres añadir?\n1 = Otro equipo con G3G3AI (PC ↔ portátil)\n2 = Ollama / LM Studio / servidor compatible con OpenAI", "1");
  if (!kind) return;
  let name, url, key = "";
  if (kind.trim() === "1") {
    const ip = prompt("IP o nombre del otro equipo (p.ej. 192.168.1.50 o mi-portatil.local)"); if (!ip) return;
    name = prompt("Nombre", "G3G3AI en " + ip) || ip;
    url = `http://${ip.replace(/^https?:\/\//, "").replace(/\/.*$/, "")}${ip.includes(":") ? "" : ":8800"}/v1`;
    key = prompt("Contraseña de G3G3AI en ese equipo (Ajustes → Acceso remoto)") || "";
  } else {
    name = prompt("Nombre (p.ej. Ollama del portátil)"); if (!name) return;
    url = prompt("URL base compatible con OpenAI (termina en /v1)", "http://192.168.1.10:11434/v1"); if (!url) return;
    key = prompt("Clave API (vacío si no hace falta)") || "";
  }
  S.settings.providers.push({ id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 24) + "-" + Date.now().toString(36).slice(-4),
    name, type: "openai", base_url: url, api_key: key, enabled: true });
  loadSettingsProvidersOnly(); autosaveSettings(); toast("Añadido");
});
// Los ajustes se guardan solos al cambiar algo (como en cualquier app moderna): nada se pierde por olvidar un botón
function setSaveState(st, msg) {
  const el = $("#save-state"); if (!el) return;
  el.dataset.state = st;
  el.textContent = { saving: "Guardando…", saved: "✓ Guardado", error: "No se pudo guardar: " + (msg || ""), idle: "Los cambios se guardan solos" }[st];
}
let autosaveTimer = null;
function autosaveSettings() {
  if (!S.settings) return;
  setSaveState("saving"); clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => saveSettings(true), 350);
}
$("#view-settings").addEventListener("change", (e) => {
  if (e.target.id === "settings-search" || e.target.id?.startsWith("bk-") || e.target.closest("dialog, .no-autosave")) return;
  autosaveSettings();
});
$("#save-settings")?.addEventListener("click", () => saveSettings(false));
async function saveSettings(quiet = false) {
  const f = $("#settings-form"), out = { providers: S.settings.providers };
  for (const [key, , type] of FIELDS) {
    const el = f.elements[key];
    if (type === "checkbox") out[key] = el.checked;
    else if (["perm", "router", "model", "sandbox", "profile", "webprov", "voiceeng", "imgprov", "imgmode", "imgsize"].includes(type)) out[key] = el.value;
    else if (type === "number") out[key] = el.value === "" ? 0 : Number(el.value);
    else if (type === "lines") out[key] = el.value.split("\n").map((s) => s.trim()).filter(Boolean);
    else out[key] = el.value;
  }
  try {
    S.settings = await api("/api/settings", { method: "PUT", body: out });
    setSaveState("saved");
    S.models = {}; refreshStatus(); loadProviders();
    if (!quiet) loadSettings();
  } catch (e) { setSaveState("error", e.message); toast(e.message, 6000); }
}
$("#logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); location.href = "/"; });


// --- Tus datos en la nube: carpeta de OneDrive / Google Drive + contraseña ---------------------------
async function renderCloud() {
  const box = $("#cloud-box"); if (!box) return;
  let st; try { st = await api("/api/cloud"); } catch (e) { box.textContent = e.message; return; }
  box.innerHTML = "";
  const when = (t) => t ? new Date(t * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : "nunca";
  if (st.enabled) {
    const kind = st.candidates.find((c) => st.dir.startsWith(c.path))?.kind || "la nube";
    box.append(
      h("p", {}, h("b", { class: "ok-text" }, "✓ Activada"), ` · ${kind}: `, h("code", {}, st.dir)),
      h("p", { class: "muted" }, `Tus claves, ajustes, proyectos${st.conversations ? ", conversaciones" : ""} y recuerdos se guardan cifrados y se ponen al día solos cada pocos minutos. `
        + `Última subida: ${when(st.last_push)} · última bajada: ${when(st.last_pull)}.`),
      st.error ? h("p", { class: "err-text" }, "⚠ " + st.error) : null,
      h("div", { class: "row" },
        h("button", { class: "ghost small", onclick: async (e) => {
          e.target.disabled = true;
          try { const r = await api("/api/cloud/now", { method: "POST" }); toast(r.pulled ? `Al día: ${r.pulled} cambios traídos de la nube` : "Al día ✔"); S.settings = null; }
          catch (err) { toast(err.message, 6000); }
          renderCloud();
        } }, "Sincronizar ahora"),
        h("button", { class: "ghost small", onclick: async () => {
          if (!confirm("¿Dejar de usar la copia en la nube en este equipo? El archivo de la nube no se borra.")) return;
          await api("/api/cloud/disable", { method: "POST" }); renderCloud();
        } }, "Desactivar")));
    return;
  }
  box.append(h("p", { class: "muted" }, "Guarda tus claves API, ajustes, proyectos y conversaciones en tu OneDrive o Google Drive, cifrados con una contraseña. "
    + "En otro equipo eliges la misma carpeta y contraseña y lo tienes todo. Microsoft y Google sólo ven un archivo ilegible."));
  let dir = st.candidates[0]?.path || "";
  const pass = h("input", { type: "password", class: "grow", placeholder: "Contraseña (la misma en todos tus equipos, mín. 6)", autocomplete: "new-password" });
  const convs = h("input", { type: "checkbox", checked: true });
  const hint = h("p", { class: "muted small" });
  const opts = h("div", { class: "cloud-opts" });
  const drawOpts = () => {
    opts.innerHTML = "";
    for (const c of st.candidates) opts.append(h("button", { class: "cloud-opt" + (c.path === dir ? " sel" : ""), onclick: () => { dir = c.path; drawOpts(); } },
      h("b", {}, c.kind), h("small", { class: "muted" }, c.path), c.has_copy ? h("span", { class: "badge ok" }, "ya hay copia") : null));
    if (dir && !st.candidates.some((c) => c.path === dir)) opts.append(h("button", { class: "cloud-opt sel" }, h("b", {}, "Otra carpeta"), h("small", { class: "muted" }, dir)));
    opts.append(h("button", { class: "cloud-opt", onclick: () => pickFolder("Carpeta de la nube", (p) => { dir = p; drawOpts(); }) }, h("b", {}, "Elegir otra carpeta…"),
      h("small", { class: "muted" }, st.candidates.length ? "Cualquier carpeta que sincronice tu nube" : "No encontré OneDrive ni Google Drive: elige su carpeta")));
    const has = st.candidates.find((c) => c.path === dir)?.has_copy;
    hint.textContent = has ? "Ya hay una copia de otro equipo en esa carpeta: escribe su misma contraseña y se juntará con lo de aquí." : "";
  };
  drawOpts();
  box.append(opts, hint,
    h("label", { class: "check" }, convs, " Incluir las conversaciones"),
    h("div", { class: "row" }, pass, h("button", { class: "primary small", onclick: async (e) => {
      if (!dir) return toast("Elige la carpeta de tu OneDrive o Google Drive");
      e.target.disabled = true; e.target.textContent = "Activando…";
      try {
        const r = await api("/api/cloud/setup", { method: "POST", body: { dir, password: pass.value, conversations: convs.checked } });
        toast(r.pulled ? `Activada: se trajeron ${r.pulled} elementos de la nube` : "Activada ✔ Tus datos ya están en la nube", 6000);
        S.settings = null; loadProviders(); loadConversations(); loadProjects();
        renderCloud();
      } catch (err) { toast(err.message, 7000); e.target.disabled = false; e.target.textContent = "Activar"; }
    } }, "Activar")));
}

// --- Actualizar G3G3AI a la última versión publicada -----------------------------------------------
const UPD = { info: null };
async function checkUpdate(force = false, quiet = true) {
  try { UPD.info = await api("/api/update/check" + (force ? "?force=true" : "")); }
  catch (e) { if (!quiet) toast(e.message, 7000); UPD.error = e.message; drawUpdateCard(); return null; }
  UPD.error = null;
  const i = UPD.info, btn = $("#update-btn");
  btn.classList.toggle("hidden", !i.newer);
  if (i.newer) {
    btn.querySelector(".ub-text").textContent = `Actualizar a ${i.latest}`;
    if (quiet && store.get("update_seen") !== i.latest) {
      store.set("update_seen", i.latest);
      toast(`Hay una versión nueva de G3G3AI (${i.latest}). Pulsa «Actualizar» abajo a la izquierda.`, 8000);
    }
  }
  drawUpdateCard();
  return i;
}
function drawUpdateCard() {
  const box = $("#update-card"); if (!box) return;
  box.innerHTML = "";
  const i = UPD.info;
  const head = h("div", { class: "row" }, h("span", { class: "conn-ico" }, ico("spark")),
    h("div", { class: "grow" }, h("b", {}, `G3G3AI ${S.status?.version || i?.current || ""}`),
      h("div", { class: "muted small" }, UPD.error ? UPD.error : !i ? "Comprobando si hay versión nueva…" : i.newer ? `Disponible la versión ${i.latest}` : "Tienes la última versión")),
    i?.newer ? h("button", { class: "primary small", onclick: openUpdateDialog }, ico("download"), `Actualizar a ${i.latest}`)
      : h("button", { class: "ghost small", onclick: async (e) => { e.currentTarget.disabled = true; await checkUpdate(true, false); } }, "Buscar actualizaciones"));
  box.append(head);
}
function openUpdateDialog() {
  const i = UPD.info; if (!i) return;
  const notes = h("div", { class: "md update-notes" }); notes.innerHTML = md(i.notes || "Sin notas.");
  const bar = h("div", { class: "meter-bar hidden" }, h("span", { style: "width:0%" }));
  const state = h("p", { class: "muted small" }, i.can_install ? `Se descargará ${i.asset.name} (${(i.asset.size / 1048576).toFixed(0)} MB), se comprobará su huella y G3G3AI se reiniciará solo. Tus conversaciones y ajustes se conservan.`
    : (i.reason || "No se puede actualizar automáticamente."));
  const go = h("button", { class: "primary", disabled: !i.can_install }, ico("download"), "Actualizar y reiniciar");
  const dlg = h("dialog", { class: "export-dialog update-dialog" },
    h("h3", {}, `${i.name}`), h("p", { class: "muted small" }, `Tienes la ${i.current}` + (i.published ? ` · publicada el ${new Date(i.published).toLocaleDateString()}` : "")),
    notes, bar, state,
    h("div", { class: "row end" },
      i.url ? h("a", { class: "ghost small btn-link", href: i.url, target: "_blank", rel: "noopener" }, "Ver en GitHub ↗") : null,
      h("button", { class: "ghost", onclick: () => dlg.close() }, "Ahora no"), go));
  go.onclick = async () => {
    go.disabled = true; go.textContent = "Descargando…"; bar.classList.remove("hidden");
    try { await api("/api/update/install", { method: "POST" }); } catch (e) { state.textContent = e.message; go.disabled = false; go.textContent = "Reintentar"; return; }
    const poll = setInterval(async () => {
      let st; try { st = await api("/api/update/status"); } catch { st = { phase: "restarting" }; }
      if (st.total) bar.firstChild.style.width = Math.round(100 * st.done / st.total) + "%";
      if (st.phase === "downloading") state.textContent = `Descargando… ${(st.done / 1048576).toFixed(0)} de ${(st.total / 1048576).toFixed(0)} MB`;
      else if (st.phase === "installing") state.textContent = "Comprobando la descarga…";
      else if (st.phase === "error") { clearInterval(poll); state.textContent = st.error; go.disabled = false; go.textContent = "Reintentar"; }
      else if (st.phase === "restarting") { clearInterval(poll); dlg.close(); waitForRestart(i.latest); }
    }, 700);
  };
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg); dlg.showModal();
}
function waitForRestart(version) {
  document.body.append(h("div", { class: "restart-veil" }, h("div", {}, h("span", { class: "dots" }, h("i"), h("i"), h("i")),
    h("b", {}, `Instalando G3G3AI ${version}…`), h("small", { class: "muted" }, "La aplicación se cerrará y se volverá a abrir sola en unos segundos."))));
  let tries = 0;
  const t = setInterval(async () => {
    tries++;
    try {
      const s = await (await fetch("/api/status", { cache: "no-store" })).json();
      if (s.version === version) { clearInterval(t); location.reload(); }
    } catch { /* aún reiniciando */ }
    if (tries > 120) { clearInterval(t); location.reload(); }
  }, 1500);
}
$("#update-btn").addEventListener("click", () => (UPD.info ? openUpdateDialog() : checkUpdate(true, false).then((i) => i?.newer && openUpdateDialog())));
setTimeout(() => checkUpdate(false, true), 4000);
setInterval(() => checkUpdate(false, true), 6 * 3600 * 1000);
