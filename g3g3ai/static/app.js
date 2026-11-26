"use strict";
/* G3G3AI — interfaz web (sin dependencias) */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
};
const store = {
  get(k, d) { try { const v = localStorage.getItem("g3:" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("g3:" + k, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
};
const fmtSize = (b) => {
  if (!b) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b.toFixed(b < 10 && i ? 1 : 0)} ${u[i]}`;
};
const baseName = (p) => String(p).split(/[\\/]/).pop();
const joinPath = (dir, name) => dir.replace(/[\\/]+$/, "") + (dir.includes("\\") && !dir.includes("/") ? "\\" : "/") + name;
function toast(msg, ms = 3500) {
  const d = h("div", {}, msg); $("#toast").append(d); setTimeout(() => d.remove(), ms);
}

// Copiar al portapapeles: navigator.clipboard sólo existe en conexiones seguras (https o localhost);
// al entrar por la IP de la red local o desde la app se usa el método clásico.
async function copyText(text, okMsg = "Copiado") {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); toast(okMsg); return; }
  } catch { /* se intenta el método clásico */ }
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.append(ta); ta.select(); ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  ta.remove();
  toast(ok ? okMsg : "No se pudo copiar: selecciona el texto y usa Ctrl+C");
}

// --- API ---------------------------------------------------------------------------
async function api(path, opts = {}) {
  const o = { headers: {}, ...opts };
  if (o.body && !(o.body instanceof FormData) && typeof o.body !== "string") {
    o.body = JSON.stringify(o.body); o.headers["Content-Type"] = "application/json";
  }
  const r = await fetch(path, o);
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("No autorizado"); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch { /* */ }
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}
const qs = (o) => new URLSearchParams(o).toString();

// --- Markdown mínimo y seguro --------------------------------------------------------------
const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function inlineMd(s) {
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  s = esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/~~(.+?)~~/g, "<del>$1</del>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[+i])}</code>`);
}
function md(src) {
  const lines = src.replace(/\r/g, "").split("\n");
  let out = "", i = 0, para = [];
  const flush = () => { if (para.length) { out += `<p>${para.map(inlineMd).join("<br>")}</p>`; para = []; } };
  while (i < lines.length) {
    const l = lines[i];
    const fence = l.match(/^\s*```(\S*)/);
    if (fence) {
      flush(); const buf = []; i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      const lang = (fence[1] || "").toLowerCase();
      const canPreview = ["html", "svg", "xml"].includes(lang) || (lang === "" && /^\s*<(!doctype|html|svg)/i.test(buf.join("\n")));
      out += `<pre><div class="code-head"><span class="lang">${esc(lang || "código")}</span>`
        + (canPreview ? `<button class="preview">▶ Vista previa</button>` : "")
        + `<button class="copy">Copiar</button></div><code data-lang="${esc(lang)}">${esc(buf.join("\n"))}</code></pre>`;
      continue;
    }
    let m;
    if ((m = l.match(/^(#{1,4})\s+(.*)/))) { flush(); out += `<h${m[1].length}>${inlineMd(m[2])}</h${m[1].length}>`; i++; continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)) { flush(); out += "<hr>"; i++; continue; }
    if (/^\s*>/.test(l)) {
      flush(); const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out += `<blockquote>${md(buf.join("\n"))}</blockquote>`; continue;
    }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|?[\s:-]+\|[\s|:-]*$/.test(lines[i + 1])) {
      flush();
      const row = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      let t = "<table><thead><tr>" + row(l).map((c) => `<th>${inlineMd(c)}</th>`).join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) t += "<tr>" + row(lines[i++]).map((c) => `<td>${inlineMd(c)}</td>`).join("") + "</tr>";
      out += t + "</tbody></table>"; continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
      flush();
      const ordered = /^\s*\d/.test(l); let items = "";
      while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
        let item = lines[i++].replace(/^\s*([-*+]|\d+[.)])\s+/, "");
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) item += " " + lines[i++].trim();
        items += `<li>${inlineMd(item)}</li>`;
      }
      out += ordered ? `<ol>${items}</ol>` : `<ul>${items}</ul>`; continue;
    }
    if (!l.trim()) { flush(); i++; continue; }
    para.push(l); i++;
  }
  flush();
  return out;
}
// Separa <think>…</think> que algunos modelos meten en el contenido.
function splitThink(text) {
  const m = text.match(/^\s*<think>([\s\S]*?)(<\/think>|$)([\s\S]*)/);
  if (!m) return { think: "", body: text };
  return { think: m[1].trim(), body: m[3] || "" , open: !m[2] };
}

// --- Estado -----------------------------------------------------------------------------
const S = {
  view: "chat", convId: null, conv: null, providers: [], models: {}, attachments: [],
  streaming: null, status: null, settings: null, filesPath: "", pickerPath: "", system: undefined,
  hubRepoOpen: null,
};

// --- Login ---------------------------------------------------------------------------
function showLogin() { $("#login").classList.remove("hidden"); $("#login-token").focus(); }
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/login", { method: "POST", body: { token: $("#login-token").value.trim() } });
    $("#login").classList.add("hidden"); $("#login-error").textContent = ""; init();
  } catch (err) { $("#login-error").textContent = err.message; }
});

// --- Navegación ----------------------------------------------------------------------
const isMobile = () => matchMedia("(max-width: 860px)").matches;
function closeSide() { document.body.classList.remove("side-open"); }
function setView(v) {
  S.view = v;
  const real = v === "code" ? "chat" : v;
  const wasCode = !!S.code;
  S.code = v === "code";
  document.body.classList.toggle("code-mode", S.code);
  $$("[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + real));
  $("#top-title").textContent = real === "chat" ? (S.conv?.title || (S.code ? "Code" : "")) : { models: "Modelos", team: "Equipo", tasks: "Tareas", files: "Archivos", settings: "Ajustes" }[real];
  closeSide();
  if (S.code && !wasCode) enterCode();
  if (real === "models") refreshModels();
  if (real === "files") loadFiles(S.filesPath);
  if (real === "tasks") loadTasks();
  if (real === "team") loadTeam();
  if (real === "settings") loadSettings();
  store.set("view", v);
}
$$("[data-view]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$("#menu-btn").addEventListener("click", () => {
  if (isMobile()) document.body.classList.toggle("side-open");
  else { document.body.classList.remove("side-collapsed"); store.set("collapsed", false); }
});
$("#side-collapse").addEventListener("click", () => { document.body.classList.add("side-collapsed"); store.set("collapsed", true); });
$("#scrim").addEventListener("click", closeSide);
$("#top-new").addEventListener("click", () => { setView("chat"); newChat(); });
if (store.get("collapsed", false)) document.body.classList.add("side-collapsed");
$$("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));

// --- Iconos (línea, monocromos, como en Claude) ---------------------------------------------------
const ICON_PATHS = {
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12Z"/>',
  code: '<path d="m8 9-4 3 4 3M16 9l4 3-4 3M13.5 5l-3 14"/>',
  cube: '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  folder: '<path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5v-10Z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  sidebar: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9.5 4.5v15"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  new: '<path d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6"/><path d="M18.4 3.6a2 2 0 0 1 2.9 2.9L12 15.8 8 17l1.2-4 9.2-9.4Z"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
  retry: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
  pencil: '<path d="M16.5 3.8a2 2 0 0 1 2.8 2.8L8 18l-4 1 1-4L16.5 3.8Z"/>',
  rewind: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  play: '<path d="m7 5 12 7-12 7V5Z"/>',
  file: '<path d="M14 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8L14 3.5Z"/><path d="M14 3.5V8h4.5"/>',
  doc: '<path d="M14 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8L14 3.5Z"/><path d="M14 3.5V8h4.5M9 12.5h6M9 16h6"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.4-4.4"/>',
  terminal: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="m7.5 9.5 3 2.5-3 2.5M12.5 15h4"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.4 3.5 5.3 3.5 8.5s-1 6.1-3.5 8.5c-2.5-2.4-3.5-5.3-3.5-8.5s1-6.1 3.5-8.5Z"/>',
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4 7 8 6 8-6"/>',
  git: '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="9" r="2"/><path d="M6 8v8M18 11c0 4-6 3-11 6"/>',
  cpu: '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5"/><path d="M9.5 3.5v3M14.5 3.5v3M9.5 17.5v3M14.5 17.5v3M3.5 9.5h3M3.5 14.5h3M17.5 9.5h3M17.5 14.5h3"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c.5-3.5 3-5.5 6-5.5s5.5 2 6 5.5M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.7.7 2.8 2.5 3 5.2"/>',
  lock: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
  clip: '<path d="m20 11.5-8.2 8.2a5 5 0 0 1-7.1-7.1l8.6-8.6a3.4 3.4 0 0 1 4.8 4.8l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9"/>',
  camera: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7H8l1.5-2h5L16 7h2.5A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5v-9Z"/><circle cx="12" cy="13" r="3.5"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="m20.5 16-5-5-9 8.5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  arrowUp: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
  brain: '<path d="M9 4.5A2.5 2.5 0 0 0 6.5 7v.3A3 3 0 0 0 4.5 10c0 .9.4 1.7 1 2.2A3 3 0 0 0 7 17.5 2.5 2.5 0 0 0 12 18V6.5A2 2 0 0 0 9 4.5ZM15 4.5A2.5 2.5 0 0 1 17.5 7v.3a3 3 0 0 1 2 2.7c0 .9-.4 1.7-1 2.2a3 3 0 0 1-1.5 5.3A2.5 2.5 0 0 1 12 18"/>',
  alert: '<path d="M12 4 2.8 19.5h18.4L12 4Z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8v.1"/>',
  minus: '<path d="M6 12h12"/>',
  trash: '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>',
  key: '<circle cx="8" cy="15" r="3.5"/><path d="m10.5 12.5 8-8M16 7l2.5 2.5M14 9l2 2"/>',
};
function ico(name, cls = "") {
  const s = document.createElement("span");
  s.className = "ico" + (cls ? " " + cls : "");
  s.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ICON_PATHS.file}</svg>`;
  return s;
}
function paintIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    if (el.dataset.painted) return;
    el.dataset.painted = "1";
    el.prepend(ico(el.dataset.icon));
    if (el.classList.contains("ico") || el.classList.contains("logo") || el.classList.contains("plus")) el.replaceWith(...el.childNodes);
  });
}
paintIcons();

// Herramientas en lenguaje normal (como Claude Code): «Leyó app.py», «Ejecutó `pytest`»
const TOOL_UI = {
  list_dir: ["folder", "Listó", "Listando", "path"], read_file: ["file", "Leyó", "Leyendo", "path"],
  grep_files: ["search", "Buscó", "Buscando", "pattern"], search_files: ["search", "Buscó archivos", "Buscando archivos", "query"],
  write_file: ["doc", "Escribió", "Escribiendo", "path"], edit_file: ["pencil", "Editó", "Editando", "path"],
  create_document: ["doc", "Creó", "Creando", "path"], run_command: ["terminal", "Ejecutó", "Ejecutando", "command"],
  build_exe: ["terminal", "Compiló", "Compilando", "script"], web_search: ["globe", "Buscó en la web", "Buscando en la web", "query"],
  fetch_url: ["globe", "Abrió", "Abriendo", "url"], mail_search: ["mail", "Buscó en el correo", "Buscando en el correo", "query"],
  mail_read: ["mail", "Leyó el correo", "Leyendo el correo", "id"], mail_save_attachments: ["clip", "Guardó adjuntos en", "Guardando adjuntos en", "folder"],
  compare_dirs: ["folder", "Comparó carpetas", "Comparando carpetas", "a"], system_info: ["cpu", "Consultó el equipo", "Consultando el equipo", null],
  delegate: ["users", "Ayudante", "Ayudante trabajando", "task"], delegate_edit: ["users", "Ayudante (copia aislada)", "Ayudante trabajando", "task"],
  apply_patch: ["check", "Aplicó la propuesta", "Aplicando la propuesta", "id"], github: ["git", "GitHub", "GitHub", "action"],
  request_folder_access: ["lock", "Pidió acceso a", "Pidiendo acceso a", "path"], app_settings: ["gear", "Ajustes", "Ajustes", "action"], team_delegate: ["users", "Delegó en", "Delegando en", "member"], diagnose: ["check", "Comprobó G3G3AI", "Comprobando G3G3AI", null], steam_games: ["cube", "Juegos de Steam", "Juegos de Steam", "query"],
  game_diagnostics: ["cube", "Diagnosticó", "Diagnosticando", "game"], generate_image: ["image", "Generó una imagen", "Generando una imagen", null],
  ask_local_model: ["cpu", "Consultó el modelo local", "Consultando el modelo local", null],
};

// --- Estado general ----------------------------------------------------------------------
async function refreshStatus() {
  try {
    S.status = await api("/api/status");
    const l = S.status.llama, pill = $("#status-pill");
    pill.className = "pill " + l.state;
    pill.textContent = { ready: "● " + l.model, loading: "◌ cargando…", error: "✕ error", stopped: "○ sin modelo local" }[l.state];
    pill.title = l.error || l.model_path || "";
    if (S.view === "models") renderLlamaStatus();
  } catch { /* */ }
}

// --- Proveedores y selector de modelo -------------------------------------------------------
// Favoritos y ocultos del selector (se guardan en el servidor y se sincronizan entre equipos)
const MS = { favs: [], hidden: [], catalog: [] };  // catalog: [{value, label, group}]
async function loadModelPrefs() {
  if (!S.settings) { try { S.settings = await api("/api/settings"); } catch { S.settings = null; } }
  MS.favs = S.settings?.model_favorites || []; MS.hidden = S.settings?.model_hidden || [];
}
async function saveModelPrefs() {
  try {
    S.settings = await api("/api/settings", { method: "PUT", body: { model_favorites: MS.favs, model_hidden: MS.hidden } });
  } catch (e) { toast(e.message); }
}
async function loadProviders() {
  S.providers = await api("/api/providers");
  await loadModelPrefs();
  const prev = store.get("model", "local::local");
  updateAutoTitle();
  const lm = S.status?.llama?.model;
  MS.catalog = [{ value: "local::local", label: lm ? `${lm}` : "Modelo local (cárgalo en Modelos)", group: "Local (llama.cpp)", pid: "local" }];
  const empty = [];
  for (const p of S.providers.filter((p) => !["local", "auto"].includes(p.id) && p.enabled)) {
    let models = S.models[p.id];
    if (!models) {
      try { models = S.models[p.id] = await api(`/api/providers/${p.id}/models`); }
      catch (e) { models = []; toast(`${p.name}: ${e.message}`); }
    }
    if (!models.length) empty.push(p.name);
    for (const m of models) MS.catalog.push({ value: `${p.id}::${m}`, label: `${m}`, group: p.name, pid: p.id });
  }
  renderModelSelect(prev, empty);
}
function renderModelSelect(prev, empty = []) {
  const sel = $("#model-select");
  prev = prev || sel.value || store.get("model", "local::local");
  sel.innerHTML = "";
  const favs = MS.catalog.filter((m) => MS.favs.includes(m.value));
  if (favs.length) {
    const g = h("optgroup", { label: "⭐ Favoritos" });
    favs.forEach((m) => g.append(h("option", { value: m.value }, `${m.label.replace(/^(💻|☁) /, "")} · ${m.group}`)));
    sel.append(g);
  }
  const groups = new Map();
  for (const m of MS.catalog) {
    if (MS.favs.includes(m.value)) continue;
    if (MS.hidden.includes(m.value) && m.value !== prev) continue;  // el seleccionado siempre se ve
    if (!groups.has(m.group)) groups.set(m.group, h("optgroup", { label: m.group }));
    groups.get(m.group).append(h("option", { value: m.value }, m.label + (MS.hidden.includes(m.value) ? " (oculto)" : "")));
  }
  for (const g of groups.values()) sel.append(g);
  for (const name of empty) sel.append(h("optgroup", { label: name }, h("option", { disabled: true }, "(sin modelos — revisa la clave API)")));
  const nHidden = MS.catalog.filter((m) => MS.hidden.includes(m.value)).length;
  sel.append(h("optgroup", { label: "──────" }, h("option", { value: "__manage__" }, "⚙ Gestionar modelos…" + (nHidden ? ` (${nHidden} ocultos)` : ""))));
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
  updateFavButton();
}
function updateFavButton() {
  const v = $("#model-select").value, on = MS.favs.includes(v);
  const b = $("#fav-btn");
  b.textContent = on ? "★" : "☆"; b.classList.toggle("on", on);
  b.title = on ? "Quitar de favoritos" : "Marcar este modelo como favorito";
  b.disabled = !v || v === "__manage__" || $("#auto-toggle").checked;
}
$("#fav-btn").addEventListener("click", async () => {
  const v = $("#model-select").value;
  if (!v || v === "__manage__") return;
  MS.favs = MS.favs.includes(v) ? MS.favs.filter((x) => x !== v) : [...MS.favs, v];
  MS.hidden = MS.hidden.filter((x) => x !== v);
  renderModelSelect(v); await saveModelPrefs();
  toast(MS.favs.includes(v) ? "⭐ Añadido a favoritos" : "Quitado de favoritos");
});
// Ventana «Gestionar modelos»
function openModelsDialog() { $("#md-search").value = ""; renderModelsDialog(); $("#models-dialog").showModal(); $("#md-search").focus(); }
$("#md-search").addEventListener("input", renderModelsDialog);
$("#md-filter").addEventListener("change", renderModelsDialog);
function renderModelsDialog() {
  const box = $("#md-list"); box.innerHTML = "";
  const q = $("#md-search").value.trim().toLowerCase(), f = $("#md-filter").value;
  const list = MS.catalog.filter((m) => (!q || m.value.toLowerCase().includes(q) || m.label.toLowerCase().includes(q)) &&
    (f !== "fav" || MS.favs.includes(m.value)) && (f !== "hidden" || MS.hidden.includes(m.value)) &&
    (f !== "visible" || !MS.hidden.includes(m.value)));
  if (!list.length) { box.append(h("p", { class: "muted" }, "Ningún modelo coincide.")); return; }
  const byGroup = new Map();
  list.forEach((m) => { if (!byGroup.has(m.group)) byGroup.set(m.group, []); byGroup.get(m.group).push(m); });
  const update = async (fn) => { fn(); renderModelsDialog(); renderModelSelect(); await saveModelPrefs(); };
  for (const [group, models] of byGroup) {
    const values = models.map((m) => m.value);
    box.append(h("div", { class: "md-group" },
      h("b", { class: "grow" }, `${group} `, h("span", { class: "muted" }, `(${models.length})`)),
      h("button", { class: "ghost small", title: "Oculta todos menos los favoritos",
        onclick: () => update(() => { MS.hidden = [...new Set([...MS.hidden, ...values.filter((v) => !MS.favs.includes(v))])]; }) }, "🙈 Ocultar todos"),
      h("button", { class: "ghost small", onclick: () => update(() => { MS.hidden = MS.hidden.filter((x) => !values.includes(x)); }) }, "👁 Mostrar todos")));
    for (const m of models) {
      const fav = MS.favs.includes(m.value), hid = MS.hidden.includes(m.value);
      box.append(h("div", { class: "md-row" + (hid ? " hidden-model" : "") },
        h("span", { class: "grow md-name" }, m.label.replace(/^(💻|☁) /, "")),
        h("button", { class: "icon-btn" + (fav ? " star-on" : ""), title: fav ? "Quitar de favoritos" : "Añadir a favoritos",
          onclick: () => update(() => { MS.favs = fav ? MS.favs.filter((x) => x !== m.value) : [...MS.favs, m.value]; if (!fav) MS.hidden = MS.hidden.filter((x) => x !== m.value); }) }, fav ? "★" : "☆"),
        h("button", { class: "icon-btn", title: hid ? "Mostrar en el selector" : "Ocultar del selector",
          onclick: () => update(() => { MS.hidden = hid ? MS.hidden.filter((x) => x !== m.value) : [...MS.hidden, m.value]; if (!hid) MS.favs = MS.favs.filter((x) => x !== m.value); }) }, hid ? "🙈" : "👁")));
    }
  }
}
let lastModel = null;
$("#model-select").addEventListener("focus", (e) => { lastModel = e.target.value; });
$("#model-select").addEventListener("change", (e) => {
  if (e.target.value === "__manage__") {  // no es un modelo: abre la ventana y vuelve al anterior
    e.target.value = lastModel || store.get("model", "local::local"); updateFavButton(); openModelsDialog(); return;
  }
  lastModel = e.target.value; store.set("model", e.target.value); updateFavButton();
});
function currentModel() {
  if ($("#auto-toggle").checked) return { provider: "auto", model: "auto" };
  const [provider, ...rest] = $("#model-select").value.split("::");
  return { provider, model: rest.join("::") };
}
// Casilla Auto: desactivada por defecto; si se activa, el modelo se elige solo en cada mensaje.
function updateAutoTitle() {
  const r = S.status?.router, on = $("#auto-toggle").checked;
  $("#model-select").disabled = on;
  $("#auto-label").title = r
    ? `Elige solo entre ${r.fast.split("::").pop()} (${r.fast_ok ? "disponible" : "no disponible"}) y ${r.strong.split("::").pop()} (${r.strong_ok ? "disponible" : "no disponible"}). Se configura en Ajustes.`
    : "Elige automáticamente entre el modelo local y la API en cada mensaje";
}
$("#auto-toggle").checked = store.get("auto", false);
$("#auto-toggle").addEventListener("change", (e) => { store.set("auto", e.target.checked); updateAutoTitle(); updateFavButton(); });
$("#web-toggle").checked = store.get("web", false);
$("#web-toggle").addEventListener("change", (e) => store.set("web", e.target.checked));
$("#tools-toggle").checked = store.get("tools", true);   // el agente viene activado: sin él el modelo no puede ver nada del equipo
$("#tools-toggle").addEventListener("change", (e) => store.set("tools", e.target.checked));

// --- Menús «+» y herramientas --------------------------------------------------------------
function togglePopover(menu, btn) {
  const open = menu.classList.contains("hidden");
  $$(".popover").forEach((p) => p.classList.add("hidden"));
  $$(".round-btn").forEach((b) => b.classList.remove("open"));
  if (open) { menu.classList.remove("hidden"); btn.classList.add("open"); }
}
$("#plus-btn").addEventListener("click", (e) => { e.stopPropagation(); togglePopover($("#plus-menu"), e.currentTarget); });
$("#tools-btn").addEventListener("click", (e) => { e.stopPropagation(); togglePopover($("#tools-menu"), e.currentTarget); });
$$(".popover").forEach((p) => p.addEventListener("click", (e) => e.stopPropagation()));
$$("#plus-menu > button, #tools-menu > button").forEach((b) => b.addEventListener("click", () => {
  $$(".popover").forEach((p) => p.classList.add("hidden")); $$(".round-btn").forEach((x) => x.classList.remove("open"));
}));
document.addEventListener("click", () => { $$(".popover").forEach((p) => p.classList.add("hidden")); $$(".round-btn").forEach((b) => b.classList.remove("open")); });
const MODE_HINT = { normal: "Pregunta según Ajustes", plan: "Sólo lee y propone un plan; no cambia nada", edits: "Edita archivos sin preguntar; los comandos sí preguntan" };
$("#mode-select").value = store.get("mode", "normal");
$("#mode-select").addEventListener("change", (e) => { store.set("mode", e.target.value); renderActiveTools(); });
function renderActiveTools() {
  const box = $("#active-tools"); box.innerHTML = "";
  const mode = $("#mode-select").value;
  $("#mode-hint").textContent = MODE_HINT[mode];
  if (mode !== "normal" && $("#tools-toggle").checked) {
    box.append(h("span", { title: "Pulsa para volver al modo normal", onclick: () => { $("#mode-select").value = "normal"; $("#mode-select").dispatchEvent(new Event("change")); } },
      (mode === "plan" ? "📝 Plan" : "✏ Ediciones") + " ✕"));
  }
  const items = [["auto-toggle", "Auto"], ["web-toggle", "Web"], ["tools-toggle", "Agente"]];
  let any = false;
  for (const [id, label] of items) {
    if (!$("#" + id).checked) continue;
    any = true;
    box.append(h("span", { title: "Pulsa para desactivar", onclick: () => { $("#" + id).checked = false; $("#" + id).dispatchEvent(new Event("change")); } }, label + " ✕"));
  }
  $("#tools-btn").classList.toggle("on", any || (mode !== "normal" && $("#tools-toggle").checked));
}
["auto-toggle", "web-toggle", "tools-toggle"].forEach((id) => $("#" + id).addEventListener("change", renderActiveTools));

// --- Deshacer los cambios que la IA hizo en archivos ------------------------------------------
async function refreshChanges() {
  const b = $("#undo-btn");
  if (!S.convId) { b.classList.add("hidden"); S.changes = []; if (S.code) renderCodeChanges(); return; }
  try {
    const { files } = await api(`/api/conversations/${S.convId}/changes`);
    S.changes = files;
    b.classList.toggle("hidden", !files.length);
    b.textContent = `↩ Deshacer cambios (${files.length})`;
  } catch { b.classList.add("hidden"); S.changes = []; }
  codeState.diffs = {};
  if (S.code) renderCodeChanges();
}
$("#undo-btn").addEventListener("click", async () => {
  const list = (S.changes || []).map((c) => (c.created ? "🆕 se borrará: " : "↩ se restaurará: ") + c.path).join("\n");
  if (!confirm(`Los archivos que la IA tocó en esta conversación volverán a como estaban antes:\n\n${list}\n\n(No se pueden deshacer los comandos que haya ejecutado.) ¿Continuar?`)) return;
  try {
    const r = await api(`/api/conversations/${S.convId}/undo`, { method: "POST" });
    toast(`Deshecho: ${r.restored.length} restaurados, ${r.deleted.length} borrados` + (r.failed.length ? `, ${r.failed.length} con problemas` : ""), 5000);
    if (r.failed.length) console.warn(r.failed);
  } catch (e) { toast(e.message); }
  refreshChanges();
});

// --- Tareas programadas ---------------------------------------------------------------------
const fmtWhen = (ts) => ts ? new Date(ts * 1000).toLocaleString(undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
async function loadTasks() {
  const box = $("#task-list"); box.innerHTML = "";
  try {
    const { tasks } = await api("/api/tasks");
    S.taskSeen = S.taskSeen || {};
    if (!tasks.length) box.append(h("p", { class: "muted" }, "Aún no hay tareas."));
    for (const t of tasks) {
      S.taskSeen[t.id] = t.last_run;
      box.append(h("div", { class: "task" + (t.enabled ? "" : " off") },
        h("div", { class: "grow" },
          h("b", {}, (t.running ? "⏳ " : "") + t.name), " ", h("span", { class: "muted" }, `· ${t.when}${t.mode === "edits" ? " · puede editar" : ""}`),
          h("div", { class: "muted" }, `${t.provider || "local"} · ${t.model || ""} · próxima: ${t.enabled ? fmtWhen(t.next_run) : "pausada"}`),
          t.last_status ? h("div", { class: "muted" }, `Última (${fmtWhen(t.last_run)}): ${t.last_status}`) : null),
        h("div", { class: "row" },
          t.last_conv ? h("button", { class: "ghost small", onclick: async () => { setView("chat"); await openConversation(t.last_conv); } }, "Ver resultado") : null,
          h("button", { class: "ghost small", disabled: t.running, onclick: async () => { await api(`/api/tasks/${t.id}/run`, { method: "POST" }).catch((e) => toast(e.message)); toast("Ejecutando…"); setTimeout(loadTasks, 800); } }, "Ejecutar ahora"),
          h("button", { class: "ghost small", onclick: async () => { await api(`/api/tasks/${t.id}`, { method: "PATCH", body: { enabled: !t.enabled } }); loadTasks(); } }, t.enabled ? "Pausar" : "Reanudar"),
          h("button", { class: "danger small", onclick: async () => { if (confirm(`¿Borrar la tarea «${t.name}»?`)) { await api(`/api/tasks/${t.id}`, { method: "DELETE" }); loadTasks(); } } }, "Borrar"))));
    }
  } catch (e) { box.append(h("p", { class: "muted" }, e.message)); }
}
function taskWhenInput() {
  const f = $("#task-form"), kind = f.elements.kind.value, w = $("#task-when-wrap");
  w.innerHTML = "";
  const label = { daily: "Hora", interval: "Minutos", once: "Fecha y hora" }[kind];
  const inp = h("input", { name: "when", type: kind === "daily" ? "time" : kind === "once" ? "datetime-local" : "number", required: true });
  if (kind === "daily") inp.value = "03:00"; if (kind === "interval") { inp.value = 60; inp.min = 5; }
  w.append(label + " ", inp);
}
$("#task-form").elements.kind.addEventListener("change", taskWhenInput);
$("#task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, kind = f.elements.kind.value, when = f.elements.when.value;
  const schedule = kind === "daily" ? { kind, time: when } : kind === "interval" ? { kind, minutes: +when } : { kind, at: new Date(when).getTime() / 1000 };
  const { provider, model } = currentModel();
  try {
    await api("/api/tasks", { method: "POST", body: { name: f.elements.name.value, prompt: f.elements.prompt.value, schedule,
      provider, model, workdir: f.elements.workdir.value.trim() || null, mode: f.elements.edits.checked ? "edits" : "plan" } });
    f.reset(); taskWhenInput(); toast("Tarea creada"); loadTasks();
  } catch (er) { toast(er.message, 6000); }
});
// Aviso cuando una tarea termina (sondeo suave mientras la página está abierta)
setInterval(async () => {
  if (document.hidden) return;
  try {
    const { tasks } = await api("/api/tasks");
    S.taskSeen = S.taskSeen || {};
    for (const t of tasks) {
      if (S.taskSeen[t.id] !== undefined && t.last_run && t.last_run !== S.taskSeen[t.id]) toast(`🕒 «${t.name}»: ${t.last_status}`, 8000);
      S.taskSeen[t.id] = t.last_run;
    }
    if (S.view === "tasks") loadTasks();
  } catch { /* sin sesión o sin red */ }
}, 30000);

// --- Equipo: organigrama visual (director y miembros) ---------------------------------------------
const TEAM = { data: null, sel: null, dirty: false };
const TEAM_TEMPLATES = [
  ["Investigador", "Busca información en la web y en los archivos, contrasta fuentes y resume lo importante con enlaces.", "read"],
  ["Programador", "Escribe y revisa código: propone el cambio exacto y explica cómo probarlo.", "none"],
  ["Correo privado", "Busca y resume correos del usuario. Usa el modelo local para que el correo no salga del equipo.", "read"],
  ["Revisor", "Revisa críticamente el trabajo que le pasen: errores, riesgos, cosas que faltan. Breve y concreto.", "none"],
  ["Redactor", "Redacta textos claros y bien escritos (correos, informes, resúmenes) con el tono que se le pida.", "none"],
];
const modelLabel = (v) => { if (!v) return "sin modelo"; const [p, m] = v.split("::"); return p === "local" ? "Modelo local" : m; };
const modelKind = (v) => (v || "").startsWith("local::") ? "cpu" : "globe";
async function loadTeam() {
  if (TEAM.data && TEAM.dirty) { drawTeam(); return; }      // hay cambios sin guardar: no se pisan
  const ticket = TEAM.ticket = (TEAM.ticket || 0) + 1;
  const data = await api("/api/team");
  if (ticket !== TEAM.ticket || TEAM.dirty) return;          // llegó tarde: ya hay otra carga o cambios nuevos
  TEAM.data = data;
  TEAM.sel = null; TEAM.dirty = false;
  $("#team-enabled").checked = TEAM.data.enabled;
  $("#team-templates").innerHTML = "";
  $("#team-templates").append(h("span", { class: "muted small" }, "Añadir:"),
    ...TEAM_TEMPLATES.map(([n, role, tools]) => h("button", { class: "ghost small", onclick: () => addMember(n, role, tools) }, ico("plus"), n)),
    h("button", { class: "ghost small", onclick: () => addMember("Nuevo miembro", "", "none") }, ico("plus"), "Personalizado"));
  drawTeam();
}
function addMember(name, role, tools) {
  let n = name, i = 2;
  while (TEAM.data.members.some((m) => m.name.toLowerCase() === n.toLowerCase())) n = `${name} ${i++}`;
  const local = MS.catalog.find((m) => m.pid === "local");
  const def = name === "Correo privado" && local ? local.value : (MS.catalog.find((m) => m.pid !== "local") || local || {}).value || "";
  const m = { id: Math.random().toString(36).slice(2, 10), name: n, role, model: def, tools };
  TEAM.data.members.push(m); TEAM.sel = m.id; TEAM.dirty = true;
  if (!TEAM.data.enabled) { TEAM.data.enabled = true; $("#team-enabled").checked = true; }
  drawTeam();
}
function teamNode(kind, title, sub, extra, opts = {}) {
  return h("button", { class: "tnode " + kind + (opts.selected ? " sel" : "") + (opts.dim ? " dim" : ""), onclick: opts.onclick, style: opts.style || "" },
    h("span", { class: "tnode-ico" }, ico(opts.icon || "spark")), h("span", { class: "tnode-t" }, title),
    sub ? h("span", { class: "tnode-s" }, sub) : null, extra ? h("span", { class: "tnode-x" }, extra) : null);
}
function drawTeam(withEditor = true) {
  const c = $("#team-canvas"); c.innerHTML = "";
  const t = TEAM.data, W = c.clientWidth || 800, members = t.members;
  const NW0 = W < 700 ? 150 : 190;                                   // ancho de cada recuadro
  const perRow = Math.max(1, Math.min(4, Math.floor((W - 16) / (NW0 + 14))));
  const rows = []; for (let i = 0; i < members.length; i += perRow) rows.push(members.slice(i, i + perRow));
  const yClaude = 20, yDir = t.show_claude ? 150 : 30, yMem = yDir + 150;
  const H = yMem + Math.max(1, rows.length) * 150 + 10;
  c.style.height = H + "px";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "tlines"); svg.setAttribute("width", W); svg.setAttribute("height", H);
  const line = (x1, y1, x2, y2, dashed) => {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const my = (y1 + y2) / 2;
    p.setAttribute("d", `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`);
    p.setAttribute("class", dashed ? "dashed" : "");
    svg.append(p);
  };
  const NW = NW0, cx = W / 2;
  c.style.setProperty("--tnode-w", NW + "px");
  if (t.show_claude) {
    line(cx, yClaude + 70, cx, yDir, true);
    c.append(teamNode("ext", "Claude Code", "director externo (MCP)", "puede delegar en G3G3AI", { icon: "terminal", style: `left:${cx - NW / 2}px;top:${yClaude}px`,
      selected: TEAM.sel === "claude", onclick: () => { TEAM.sel = "claude"; drawTeam(); } }));
  }
  c.append(teamNode("dir", "G3G3AI", "director · el modelo del chat", t.enabled ? `${members.length} miembro(s)` : "equipo desactivado",
    { icon: "spark", dim: !t.enabled, style: `left:${cx - NW / 2}px;top:${yDir}px`, selected: TEAM.sel === "dir", onclick: () => { TEAM.sel = "dir"; drawTeam(); } }));
  rows.forEach((row, r) => {
    const gap = W / (row.length + 1), y = yMem + r * 150;
    row.forEach((m, i) => {
      const x = gap * (i + 1);
      line(cx, yDir + 78, x, y, false);
      c.append(teamNode("mem", m.name, modelLabel(m.model), (m.role || "sin papel").slice(0, 70) + ((m.role || "").length > 70 ? "…" : ""),
        { icon: modelKind(m.model), dim: !t.enabled, style: `left:${x - NW / 2}px;top:${y}px`, selected: TEAM.sel === m.id,
          onclick: () => { TEAM.sel = m.id; drawTeam(); } }));
    });
  });
  if (!members.length) c.append(h("p", { class: "muted team-empty", style: `top:${yMem + 20}px` }, "Aún no hay miembros: añade uno con los botones de arriba."));
  c.prepend(svg);
  if (withEditor) drawTeamEditor();
}
function drawTeamEditor() {
  const ed = $("#team-editor"); ed.innerHTML = "";
  const t = TEAM.data;
  if (!TEAM.sel) { ed.classList.add("hidden"); return; }
  ed.classList.remove("hidden");
  const close = h("button", { class: "icon-btn", "aria-label": "Cerrar", onclick: () => { TEAM.sel = null; drawTeam(); } }, ico("x"));
  if (TEAM.sel === "claude") {
    const cmd = `claude mcp add --transport http g3g3ai http://127.0.0.1:${S.settings?.port || 8800}/mcp`;
    ed.append(h("div", { class: "dialog-head" }, h("b", {}, "Claude Code dirige a G3G3AI"), close),
      h("p", { class: "muted" }, "Al revés: Claude Code puede usar G3G3AI como subagente (para tu modelo local, otros proveedores, tus archivos o tu correo). Ejecuta una vez:"),
      h("code", { class: "access-url" }, cmd), h("button", { class: "ghost small", onclick: () => copyText(cmd, "Orden copiada") }, ico("copy"), "Copiar"),
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: t.show_claude, onchange: (e) => { t.show_claude = e.target.checked; TEAM.dirty = true; TEAM.sel = null; drawTeam(); } }), " Mostrar en el esquema"));
    return;
  }
  if (TEAM.sel === "dir") {
    ed.append(h("div", { class: "dialog-head" }, h("b", {}, "G3G3AI (director)"), close),
      h("p", { class: "muted" }, "El director es el modelo que elijas en el chat. Cuando el equipo está activo, conoce a sus miembros y les delega lo que encaje con su papel (puede encargar varias tareas a la vez), revisa lo que le devuelven y te responde."),
      h("p", { class: "muted" }, "Consejo: un director potente (Claude, GPT, DeepSeek…) reparte mejor; los miembros pueden ser modelos más baratos o el local."));
    return;
  }
  const m = t.members.find((x) => x.id === TEAM.sel);
  if (!m) { TEAM.sel = null; drawTeam(); return; }
  const set = (k) => (e) => { m[k] = e.target.value; TEAM.dirty = true; drawTeamSoon(); };
  const sel = h("select", { onchange: set("model") });
  const groups = {};
  for (const o of MS.catalog) (groups[o.group] ||= []).push(o);
  for (const [g, opts] of Object.entries(groups)) sel.append(h("optgroup", { label: g }, opts.map((o) => h("option", { value: o.value }, o.label))));
  if (m.model && ![...sel.options].some((o) => o.value === m.model)) sel.append(h("option", { value: m.model }, modelLabel(m.model) + " (no disponible ahora)"));
  sel.value = m.model;
  ed.append(h("div", { class: "dialog-head" }, h("b", {}, m.name), close),
    h("label", {}, "Nombre", h("input", { value: m.name, oninput: set("name") })),
    h("label", {}, "Papel (qué hace y cuándo delegarle)", h("textarea", { rows: 4, oninput: set("role") }, m.role || "")),
    h("label", {}, "Modelo", sel),
    h("label", {}, "Puede…", (() => { const t2 = selectEl("", m.tools, [["none", "Solo responder (sin herramientas)"], ["read", "Leer archivos, web y correo (sin modificar nada)"]]); t2.onchange = (e) => { m.tools = e.target.value; TEAM.dirty = true; }; return t2; })()),
    h("div", { class: "row" }, h("button", { class: "danger small", onclick: () => { t.members = t.members.filter((x) => x !== m); TEAM.sel = null; TEAM.dirty = true; drawTeam(); } }, ico("trash"), "Quitar del equipo")));
}
let teamTimer = 0;
function drawTeamSoon() { clearTimeout(teamTimer); teamTimer = setTimeout(() => drawTeam(false), 200); }  // sólo el esquema: el editor conserva el foco
$("#team-enabled").addEventListener("change", (e) => { if (TEAM.data) { TEAM.data.enabled = e.target.checked; TEAM.dirty = true; drawTeam(); } });
$("#team-save").addEventListener("click", async () => {
  try { TEAM.data = await api("/api/team", { method: "PUT", body: TEAM.data }); TEAM.dirty = false; toast("Equipo guardado", 2500); drawTeam(); }
  catch (e) { toast(e.message, 6000); }
});
window.addEventListener("resize", () => { if (S.view === "team" && TEAM.data) drawTeam(); });

// --- «Comprobar todo» ---------------------------------------------------------------------------
const DIAG_ICON = { ok: "check", warn: "alert", error: "x", info: "info", skip: "minus" };
function diagAction(a) {
  if (!a) return null;
  if (a.startsWith("copy:")) return h("button", { class: "ghost small", onclick: () => copyText(a.slice(5), "Orden copiada") }, ico("copy"), "Copiar orden");
  const go = { providers: ["settings", "providers"], agent: ["settings", "agent"], mail: ["settings", "mail"], general: ["settings", "general"], models: ["models"] }[a];
  if (!go) return null;
  return h("button", { class: "ghost small", onclick: () => { $$("dialog[open]").forEach((d) => d.close()); setView(go[0]); if (go[1]) setTimeout(() => showSettingsTab(go[1]), 300); } },
    { providers: "Abrir proveedores", agent: "Abrir permisos", mail: "Abrir correo", general: "Abrir ajustes", models: "Abrir modelos" }[a]);
}
async function renderDiagnostics(box) {
  box.innerHTML = "";
  box.append(h("p", { class: "muted diag-wait" }, h("span", { class: "spinner" }), " Comprobando todo… (puede tardar hasta un minuto si hay modelos o proveedores lentos)"));
  let d;
  try { d = await api("/api/diagnostics"); } catch (e) { box.innerHTML = ""; box.append(h("p", { class: "error" }, e.message)); return null; }
  box.innerHTML = "";
  const s = d.summary;
  box.append(h("p", { class: "diag-summary" }, s.error ? `${s.error} cosa(s) por arreglar` : s.warn ? "Todo funciona, con algún aviso" : "Todo funciona",
    h("span", { class: "muted" }, ` · ${s.ok} correctas` + (s.warn ? ` · ${s.warn} avisos` : "") + (s.error ? ` · ${s.error} errores` : ""))));
  const list = h("div", { class: "diag-list" });
  for (const c of d.checks) list.append(h("div", { class: "diag " + c.status },
    h("span", { class: "diag-ico" }, ico(DIAG_ICON[c.status] || "info")),
    h("div", { class: "grow" }, h("b", {}, c.title), h("div", { class: "muted" }, c.detail), c.fix ? h("div", { class: "diag-fix" }, c.fix) : null),
    diagAction(c.action)));
  box.append(list);
  return d;
}
async function openDiagnostics() {
  let dlg = $("#diag-dialog");
  if (!dlg) { dlg = h("dialog", { id: "diag-dialog" }); document.body.append(dlg); }
  dlg.innerHTML = "";
  const box = h("div");
  dlg.append(h("div", { class: "dialog-head" }, h("b", {}, "Comprobar todo"),
    h("span", {}, h("button", { class: "ghost small", onclick: () => renderDiagnostics(box) }, ico("retry"), "Repetir"),
      h("button", { class: "icon-btn", "aria-label": "Cerrar", onclick: () => dlg.close() }, ico("x")))), box);
  dlg.showModal();
  renderDiagnostics(box);
}
$("#open-diag").addEventListener("click", openDiagnostics);

// --- Asistente de primer arranque --------------------------------------------------------------
async function openWizard() {
  let dlg = $("#wizard");
  if (!dlg) { dlg = h("dialog", { id: "wizard" }); document.body.append(dlg); }
  let ob = await api("/api/onboarding");
  let step = 0;
  const steps = ["ai", "folder", "mail", "check"];
  const finish = async () => { await api("/api/onboarding/done", { method: "POST" }).catch(() => {}); dlg.close(); loadProviders(); };
  const draw = async () => {
    dlg.innerHTML = "";
    const body = h("div", { class: "wiz-body" });
    const dots = h("div", { class: "wiz-dots" }, steps.map((_, i) => h("span", { class: i === step ? "on" : i < step ? "done" : "" })));
    const back = h("button", { class: "ghost", onclick: () => { step = Math.max(0, step - 1); draw(); } }, "Atrás");
    const next = h("button", { class: "primary", onclick: () => { if (step === steps.length - 1) finish(); else { step++; draw(); } } }, step === steps.length - 1 ? "Empezar" : "Siguiente");
    dlg.append(h("div", { class: "dialog-head" }, h("b", {}, "Configurar G3G3AI"), h("button", { class: "ghost small", onclick: finish }, "Saltar")), dots, body,
      h("div", { class: "row end wiz-nav" }, step ? back : null, next));
    const kind = steps[step];
    if (kind === "ai") {
      ob = await api("/api/onboarding");
      body.append(h("h2", {}, "¿Con qué IA quieres trabajar?"),
        h("p", { class: "muted" }, "Puedes usar las dos: un modelo en tu equipo (privado y gratis, pero más lento) y un proveedor en la nube (rápido y potente)."),
        h("div", { class: "wiz-cards" },
          h("div", { class: "wiz-card" + (ob.has_provider ? " done" : "") }, h("b", {}, ico("globe"), " En la nube"),
            h("p", { class: "muted" }, "OpenCode Go, OpenRouter, DeepSeek, Claude, Gemini… Solo necesitas una clave."),
            ob.has_provider ? h("p", { class: "ok" }, ico("check"), " Ya tienes un proveedor configurado") : null,
            h("button", { class: ob.has_provider ? "ghost small" : "primary small", onclick: async () => { await providerDialog(); $("#provider-dialog").addEventListener("close", () => draw(), { once: true }); } },
              ob.has_provider ? "Añadir otro" : "Elegir proveedor")),
          h("div", { class: "wiz-card" + (ob.has_local ? " done" : "") }, h("b", {}, ico("cpu"), " En este equipo"),
            h("p", { class: "muted" }, ob.recommendation ? `Para tu equipo (${ob.recommendation.ram_gb} GB de RAM, ${/^ninguna$/i.test(ob.recommendation.gpu) ? "sin gráfica dedicada" : ob.recommendation.gpu}) encaja un modelo ${ob.recommendation.tier}.` : "Descarga un modelo y se ejecuta sin internet."),
            ob.has_local ? h("p", { class: "ok" }, ico("check"), " Modelo local cargado") : null,
            h("button", { class: "ghost small", onclick: () => { dlg.close(); setView("models"); toast("Descarga y carga un modelo; luego vuelve a Ajustes → Asistente inicial", 6000); } }, "Ir a Modelos"))));
    } else if (kind === "folder") {
      const inp = h("input", { value: ob.write_roots[0] || ob.suggested_folder });
      const out = h("p", { class: "muted" });
      body.append(h("h2", {}, "¿Dónde puede trabajar?"),
        h("p", { class: "muted" }, "La IA solo podrá crear y modificar archivos dentro de las carpetas que elijas (y siempre se puede deshacer). Puede leer más carpetas si se lo permites en Ajustes."),
        h("div", { class: "row" }, inp, h("button", { class: "ghost small", onclick: async () => {
          try { const r = await api("/api/onboarding/folder", { method: "POST", body: { path: inp.value } }); out.className = "ok"; out.textContent = "Listo: " + r.path; ob = await api("/api/onboarding"); }
          catch (e) { out.className = "error"; out.textContent = e.message; }
        } }, "Usar esta carpeta")), out,
        ob.write_roots.length ? h("p", { class: "muted small" }, "Ya puede trabajar en: " + ob.write_roots.join(", ")) : null);
    } else if (kind === "mail") {
      body.append(h("h2", {}, "¿Quieres que busque en tu correo?"));
      if (!ob.thunderbird) body.append(h("p", { class: "muted" }, "No he encontrado Thunderbird en este equipo. Si usas otro programa, puedes indicar la carpeta del correo más tarde en Ajustes → Correo e integraciones."));
      else {
        const sw = h("input", { type: "checkbox", checked: ob.mail_enabled, onchange: async (e) => {
          await api("/api/settings", { method: "PUT", body: { ...(await api("/api/settings")), mail_enabled: e.target.checked } }).catch((er) => toast(er.message));
          if (e.target.checked) await api("/api/mail/index", { method: "POST", body: {} }).catch(() => {});
          ob = await api("/api/onboarding");
        } });
        body.append(h("p", { class: "muted" }, "He encontrado Thunderbird. Si lo activas, podrás pedir cosas como «¿qué me mandó jmoreno esta semana?» o «guarda sus adjuntos en una carpeta». Es solo lectura y cada búsqueda te pide permiso; con un modelo en la nube, lo que lea se envía a ese servicio."),
          h("label", { class: "check big" }, sw, " Sí, la IA puede buscar en mi correo"));
      }
    } else {
      body.append(h("h2", {}, "Comprobación final"));
      const box = h("div"); body.append(box);
      renderDiagnostics(box);
    }
  };
  dlg.showModal();
  draw();
}
$("#open-wizard").addEventListener("click", openWizard);

// --- Medidor de contexto y /compact ----------------------------------------------------------
async function refreshContext() {
  const m = $("#ctx-meter");
  if (!S.convId || !S.conv?.messages?.length) { m.classList.add("hidden"); return; }
  try {
    const { provider } = currentModel();
    const c = await api(`/api/conversations/${S.convId}/context?` + qs({ provider }));
    const pct = Math.min(100, Math.round(100 * c.used / Math.max(1, c.budget)));
    const k = (n) => n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "k" : n;
    m.textContent = `${pct}% · ${k(c.used)}/${k(c.budget)}`;
    m.title = `Contexto usado (estimado): ${c.used} de ${c.budget} tokens` + (c.summarized ? ". Ya se resumió una parte antigua." : ". Al llenarse, lo antiguo se resume solo; /compact lo resume ahora.");
    m.classList.toggle("warn", pct >= 70 && pct < 90); m.classList.toggle("full", pct >= 90);
    m.classList.remove("hidden");
  } catch { m.classList.add("hidden"); }
}
async function compactNow() {
  if (!S.convId) { toast("No hay conversación que resumir"); return; }
  toast("Resumiendo…", 4000);
  try {
    const { provider, model } = currentModel();
    const r = await api(`/api/conversations/${S.convId}/compact`, { method: "POST", body: { provider, model } });
    toast(`Resumida: ${r.before} → ${r.used} tokens`, 5000);
    await openConversation(S.convId);
  } catch (e) { toast(e.message, 6000); }
}

// --- Code: proyecto, cambios, terminal y plan -------------------------------------------------
const codeState = { tab: "changes", open: new Set(), diffs: {} };
function enterCode() {
  const t = $("#tools-toggle"); if (!t.checked) { t.checked = true; renderActiveTools(); }
  if (S.workdir === undefined && !S.conv?.workdir) { const d = store.get("code_dir", ""); if (d) S.workdir = d; }
  renderCodePanel();
}
$$("[data-ctab]").forEach((b) => b.addEventListener("click", () => {
  codeState.tab = b.dataset.ctab;
  $$("[data-ctab]").forEach((x) => x.classList.toggle("active", x === b));
  ["changes", "term", "plan"].forEach((n) => $("#ctab-" + n).classList.toggle("hidden", n !== codeState.tab));
}));
$("#code-dir-set").addEventListener("click", async () => {
  const dir = $("#code-dir").value.trim();
  S.workdir = dir; store.set("code_dir", dir);
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { workdir: dir || null } }).catch((e) => toast(e.message));
  toast(dir ? "Proyecto: " + dir : "Sin carpeta de proyecto");
});
function diffPre(text) {
  const pre = h("pre", {});
  for (const line of text.split("\n")) {
    pre.append(h("span", { class: line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : "" }, line + "\n"));
  }
  return pre;
}
function renderCodeChanges() {
  const box = $("#ctab-changes"); box.innerHTML = "";
  const files = S.convId && S.code ? (S.changes || []) : [];
  $("#ct-changes").textContent = files.length;
  if (!files.length) { box.append(h("p", { class: "muted" }, "Aún no hay cambios. Los archivos que la IA cree o edite aparecerán aquí con su diff y podrás deshacerlos uno a uno.")); return; }
  box.append(h("div", { class: "row" }, h("button", { class: "ghost small", onclick: () => $("#undo-btn").click() }, "↩ Deshacer todo")));
  for (const f of files) {
    const open = codeState.open.has(f.path);
    const card = h("div", { class: "cfile" }, h("div", { class: "cfile-head", onclick: async () => {
      if (open) codeState.open.delete(f.path); else {
        codeState.open.add(f.path);
        try { codeState.diffs[f.path] = (await api(`/api/conversations/${S.convId}/changes/diff?` + qs({ path: f.path }))).diff; } catch (e) { toast(e.message); }
      }
      renderCodeChanges();
    } }, h("span", {}, f.created ? "🆕" : "✎"), h("span", { class: "path", title: f.path }, f.path),
      h("button", { class: "ghost small", title: "Deshacer este archivo", onclick: async (e) => {
        e.stopPropagation();
        if (!confirm(`${f.created ? "Se borrará" : "Se restaurará"}: ${f.path}`)) return;
        try { await api(`/api/conversations/${S.convId}/undo_file`, { method: "POST", body: { path: f.path } }); } catch (er) { toast(er.message); }
        refreshChanges();
      } }, "↩")));
    if (open && codeState.diffs[f.path] !== undefined) card.append(diffPre(codeState.diffs[f.path]));
    box.append(card);
  }
}
function renderCodePanel(live) {
  if (!S.code) return;
  const dirIn = $("#code-dir");
  if (document.activeElement !== dirIn) dirIn.value = S.workdir ?? S.conv?.workdir ?? "";
  renderCodeChanges();
  const calls = [];
  const take = (tools) => {
    const found = [];
    for (const t of tools || []) {
      if (t.type === "tool_call" && t.name === "run_command") {
        let a = {}; try { a = typeof t.args === "string" ? JSON.parse(t.args) : t.args; } catch { /* */ }
        found.push({ cmd: (a && a.command) || "", out: null });
      } else if (t.type === "tool_result" && t.name === "run_command") {
        const last = found.find((x) => x.out === null); if (last) last.out = t.result;
      }
    }
    calls.push(...found);
  };
  for (const m of S.conv?.messages || []) if (m.role === "assistant") take(m.meta?.tools);
  if (live?.tools) take(live.tools);
  const term = $("#ctab-term"); term.innerHTML = "";
  if (!calls.length) term.append(h("p", { class: "muted" }, "Los comandos que ejecute la IA aparecerán aquí."));
  for (const c of calls.slice(-30)) term.append(h("div", { class: "term-line" }, h("span", { class: "cmd" }, "$ " + c.cmd), "\n", c.out === null ? (live?.liveOut ? live.liveOut.slice(-3000) + "\n⏳ ejecutando…" : "⏳ ejecutando…") : c.out));
  const plan = $("#ctab-plan"); plan.innerHTML = "";
  const withTodos = (S.conv?.messages || []).filter((m) => m.role === "assistant" && m.meta?.todos);
  const todos = live?.todos?.length ? live.todos : (withTodos.length ? withTodos[withTodos.length - 1].meta.todos : []);
  plan.append(todos.length ? todoCard(todos) : h("p", { class: "muted" }, "Cuando la tarea sea larga, la IA mostrará aquí su plan y lo irá marcando."));
}

// Comandos con «/» en el cuadro de texto
const SLASH = {
  "/plan": () => { const m = $("#mode-select"); m.value = m.value === "plan" ? "normal" : "plan"; m.dispatchEvent(new Event("change")); toast("Modo: " + m.value); },
  "/clear": () => { setView(S.code ? "code" : "chat"); newChat(); },
  "/undo": () => $("#undo-btn").click(),
  "/compact": () => { compactNow(); },
  "/init": () => "Explora este proyecto (estructura, tecnologías, cómo se ejecutan los tests y la build) y crea un archivo G3G3AI.md en la raíz con instrucciones breves y útiles para trabajar en él. No inventes nada que no hayas comprobado.",
  "/review": () => "Revisa los cambios que acabas de hacer en esta conversación: relee los archivos modificados, busca errores, casos límite y cosas que falten, y ejecuta los tests si existen. Corrige lo que encuentres.",
  "/test": () => "Ejecuta los tests del proyecto y, si fallan, diagnostica la causa y corrígela.",
  "/help": () => { toast("/plan · /clear · /undo · /compact · /init · /review · /test", 6000); },
};
function runSlash(text) {
  const cmd = text.split(/\s+/)[0].toLowerCase();
  if (!SLASH[cmd]) return null;
  const extra = text.slice(cmd.length).trim();
  const r = SLASH[cmd]();
  return typeof r === "string" ? (extra ? r + "\n\n" + extra : r) : "";
}

// --- Conversaciones -------------------------------------------------------------------
function dateGroup(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff <= 0) return "Hoy";
  if (diff === 1) return "Ayer";
  if (diff < 7) return "Últimos 7 días";
  if (diff < 30) return "Últimos 30 días";
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}
let convCache = [];
$("#conv-search").addEventListener("input", () => renderConvList());
async function loadConversations() {
  convCache = await api("/api/conversations");
  renderConvList();
}
function renderConvList() {
  const ul = $("#conv-list"), q = $("#conv-search").value.trim().toLowerCase();
  ul.innerHTML = "";
  let group = null;
  const list = convCache.filter((c) => !q || c.title.toLowerCase().includes(q));
  if (!list.length) ul.append(h("div", { class: "conv-group" }, q ? "Sin resultados" : "Aún no hay conversaciones"));
  for (const c of list) {
    const g = dateGroup(c.updated);
    if (g !== group) { group = g; ul.append(h("div", { class: "conv-group" }, g)); }
    const li = h("div", { class: "conv-item" + (c.id === S.convId ? " active" : ""), onclick: () => { setView("chat"); openConversation(c.id); } },
      h("span", { class: "t", title: c.title }, c.title),
      h("span", { class: "acts" },
        h("button", { title: "Renombrar", onclick: async (e) => {
          e.stopPropagation();
          const t = prompt("Nuevo título", c.title);
          if (t) { await api(`/api/conversations/${c.id}`, { method: "PATCH", body: { title: t } }); loadConversations(); if (S.convId === c.id) $("#top-title").textContent = t; }
        } }, "✎"),
        h("button", { title: "Borrar", onclick: async (e) => {
          e.stopPropagation();
          if (!confirm("¿Borrar esta conversación?")) return;
          await api(`/api/conversations/${c.id}`, { method: "DELETE" });
          if (S.convId === c.id) newChat(); else loadConversations();
        } }, "🗑")));
    ul.append(li);
  }
}
async function openConversation(id) {
  S.conv = await api(`/api/conversations/${id}`);
  S.convId = id; S.system = undefined; store.set("conv", id);
  if (S.conv.provider) {
    const v = `${S.conv.provider}::${S.conv.model}`;  // las conversaciones en Auto no cambian el selector
    if ([...$("#model-select").options].some((o) => o.value === v)) { $("#model-select").value = v; updateFavButton(); }
  }
  S.workdir = undefined;
  renderMessages(); loadConversations(); refreshChanges(); refreshContext();
  if (S.code) { S.workdir = S.conv.workdir || undefined; renderCodePanel(); }
  if (S.view === "chat" || S.view === "code") $("#top-title").textContent = S.conv.title;
  closeSide();
}
function newChat() {
  if (S.code) queueMicrotask(() => { S.workdir = store.get("code_dir", "") || undefined; renderCodePanel(); });
  S.convId = null; S.conv = null; S.system = undefined; store.set("conv", null);
  renderMessages(); loadConversations(); closeSide(); $("#top-title").textContent = "";
  if (!isMobile()) $("#input").focus();
}
$("#new-chat").addEventListener("click", () => { setView("chat"); newChat(); });

// --- Mensajes -----------------------------------------------------------------------
function renderMessages() {
  const box = $("#messages"); box.innerHTML = "";
  const msgs = S.conv?.messages || [];
  if (!msgs.length) {
    const hr = new Date().getHours();
    const hello = hr < 6 ? "Buenas noches" : hr < 13 ? "Buenos días" : hr < 21 ? "Buenas tardes" : "Buenas noches";
    const ideas = [
      ["doc", "Resumir un documento", "Resume el documento que te adjunto en 5 puntos clave.", "attach"],
      ["globe", "Buscar en la web", "Busca las últimas novedades sobre ", "web"],
      ["folder", "Revisar una carpeta", "Revisa la carpeta … y dime qué contiene y qué falta.", "agent"],
      ["mail", "Buscar en mi correo", "Busca en mi correo el último mensaje de ", "agent"],
    ];
    $("#view-chat").classList.add("is-empty");
    box.append(h("div", { class: "empty-state" },
      h("h1", { class: "greeting" }, ico("spark", "logo"), hello)));
    $("#welcome-ideas")?.remove();
    $(".composer-wrap").append(h("div", { id: "welcome-ideas", class: "suggest" }, ideas.map(([icon, label, text, mode]) => h("button", { onclick: () => {
        input.value = text; input.focus(); input.dispatchEvent(new Event("input"));
        if (mode === "web") { $("#web-toggle").checked = true; $("#web-toggle").dispatchEvent(new Event("change")); }
        if (mode === "agent") { $("#tools-toggle").checked = true; $("#tools-toggle").dispatchEvent(new Event("change")); }
        if (mode === "attach") $("#attach-btn").click();
      } }, ico(icon), label))));
    return;
  }
  $("#view-chat").classList.remove("is-empty"); $("#welcome-ideas")?.remove();
  for (const m of msgs) box.append(messageEl(m));
  box.scrollTop = box.scrollHeight;
}
function diffBlock(path, diff) {
  const pre = h("pre", { class: "diff" }, h("div", { class: "diff-file" }, path));
  for (const line of diff.split("\n")) {
    const cls = line.startsWith("+++") || line.startsWith("---") ? "meta" : line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : line.startsWith("@@") ? "hunk" : "";
    pre.append(h("div", { class: "dl " + cls }, line || " "));
  }
  return pre;
}
const TOOL_ARG_KEYS = ["path", "script", "command", "pattern", "query", "url", "game", "prompt"];
function toolRow(name, argsJson, result) {
  let a = {}; try { a = JSON.parse(argsJson || "{}"); } catch { /* */ }
  const key = TOOL_ARG_KEYS.find((k) => a[k]);
  let arg = key ? String(a[key]).replace(/\s+/g, " ") : "";
  if (key === "path" || key === "script") { const seg = arg.split(/[\\/]/).filter(Boolean); arg = seg.length > 2 ? "…/" + seg.slice(-2).join("/") : arg; }
  arg = arg.slice(0, 80);
  const failed = result != null && /^(Error|Bloqueado|El usuario ha denegado|Has repetido|Denegado)/.test(result);
  let pretty = argsJson || ""; try { pretty = JSON.stringify(JSON.parse(argsJson), null, 2); } catch { /* */ }
  const ui = TOOL_UI[name] || (name.startsWith("mcp__") ? ["cube", name.split("__").slice(1).join(" · "), name.split("__").slice(1).join(" · "), null] : ["cube", name, name, null]);
  const pick = ui[3] && a[ui[3]] != null ? String(a[ui[3]]) : arg;
  let shown = (pick || "").replace(/\s+/g, " ");
  if (ui[3] === "path" || ui[3] === "folder" || ui[3] === "a") { const seg = shown.split(/[\\/]/).filter(Boolean); shown = seg.slice(-2).join("/") || shown; }
  if (name === "mail_read" || name === "apply_patch") shown = "#" + shown;
  if (name === "list_dir" && !shown) shown = "carpeta de trabajo";
  if (name === "mail_search" && !a.query) shown = [a.sender && "de " + a.sender, a.person, a.subject, a.since && "desde " + a.since].filter(Boolean).join(" · ");
  shown = shown.slice(0, 90);
  const running = result == null;
  return h("details", { class: "tool" + (failed ? " failed" : "") + (running ? " running" : "") },
    h("summary", {}, ico(ui[0]), h("span", { class: "tool-verb" }, running ? ui[2] : ui[1]),
      shown ? (name === "run_command" ? h("code", { class: "tool-arg" }, shown) : h("span", { class: "tool-arg" }, shown)) : null,
      running ? h("span", { class: "spinner" }) : failed ? h("span", { class: "tool-err" }, "error") : null),
    h("pre", {}, pretty), result != null ? h("pre", {}, result) : null);
}
function todoCard(items) {
  const done = items.filter((t) => t.status === "completed").length;
  const icon = { completed: "✔", in_progress: "●", pending: "○" };
  return h("div", { class: "todo-card" },
    h("div", { class: "todo-head" }, h("b", {}, "Plan"), h("span", { class: "muted" }, `${done}/${items.length}`),
      h("div", { class: "todo-bar" }, h("div", { style: `width:${Math.round(100 * done / items.length)}%` }))),
    h("ul", {}, items.map((t) => h("li", { class: t.status }, h("span", { class: "ti" }, icon[t.status] || "○"), t.content))));
}
function approvalCard(a) {
  const args = a.args || {};
  const what = a.name === "build_exe" ? h("pre", {}, `${args.script}` + (args.packages?.length ? `\npaquetes: ${args.packages.join(", ")}` : "") + (args.windowed ? "\n(con ventana)" : ""))
    : a.name === "run_command" ? h("pre", {}, (args.cwd ? `[${args.cwd}] ` : "") + "$ " + args.command)
    : (a.name === "edit_file" || a.name === "write_file") && a.diff ? diffBlock(args.path, a.diff)
    : a.name === "edit_file" ? h("pre", {}, `${args.path}\n` + (args.edits || [{ old_text: args.old_text, new_text: args.new_text }]).map((e) => `--- antes\n${e.old_text}\n+++ después\n${e.new_text}`).join("\n\n"))
    : a.name === "write_file" || a.name === "create_document" ? h("pre", {}, `${args.path}\n\n${String(args.content || "").slice(0, 3000)}`)
    : h("pre", {}, JSON.stringify(args, null, 2));
  const title = { run_command: "ejecutar un comando", edit_file: "editar un archivo", write_file: "escribir un archivo", build_exe: "compilar un programa",
    create_document: "crear un documento" }[a.name] || a.name;
  const card = h("div", { class: "approval" + (a.state ? " " + a.state : "") + (a.dangerous ? " dangerous" : "") },
    h("b", {}, a.state === "approved" ? "✔ Permitido: " : a.state === "denied" ? "✕ Denegado: " : (a.dangerous ? "⛔ Atención: la IA quiere " : "⚠ La IA quiere ")), title,
    a.sandboxed === true ? h("span", { class: "badge ok", title: "El comando sólo puede escribir en las carpetas permitidas" }, "🛡 aislado") : null,
    what,
    (a.warnings || []).length ? h("ul", { class: "warnings" }, a.warnings.map((w) => h("li", {}, w))) : null);
  if (!a.state) {
    const answer = async (ans) => {
      card.querySelectorAll("button").forEach((b) => (b.disabled = true));
      try { await api("/api/chat/approve", { method: "POST", body: { id: a.id, answer: ans } }); }
      catch (e) { toast(e.message); }
    };
    card.append(h("div", { class: "row" },
      h("button", { class: "primary small", onclick: () => answer("yes") }, "Permitir"),
      a.can_trust ? h("button", { class: "ghost small", title: "Activa en Ajustes «Confiar en mis carpetas»: las ediciones en tus carpetas modificables y los comandos de desarrollo habituales (python/pytest sobre scripts del proyecto, git de lectura, npm test) dejan de pedir permiso. Lo peligroso sigue preguntando.", onclick: async () => {
        if (!confirm("¿Confiar en mis carpetas?\n\n• Editar y crear archivos dentro de tus carpetas modificables ya no pedirá permiso (se puede deshacer).\n• Se ejecutarán sin preguntar python/pytest sobre scripts de esas carpetas, git de solo lectura y npm test/build.\n• Siguen pidiendo permiso: pip install, git push, python -c, comandos encadenados y cualquier cosa fuera de tus carpetas.\n\nUn script de Python puede hacer lo mismo que tú: actívalo solo si confías en lo que escribe la IA. Puedes desactivarlo en Ajustes.")) return;
        try { await api("/api/settings", { method: "PUT", body: { ...(await api("/api/settings")), commands_trusted: true } }); toast("Confianza activada", 4000); } catch (e) { toast(e.message); }
        answer("yes");
      } }, "Confiar en mis carpetas") : null,
      a.can_rule ? h("button", { class: "ghost small", title: "Guarda este comando en Ajustes → «Comandos permitidos» y no vuelve a preguntar", onclick: () => answer("rule") }, "Permitir este comando siempre") : null,
      a.can_always !== false ? h("button", { class: "ghost small", title: "No volver a preguntar por esta herramienta en esta conversación (salvo acciones peligrosas)", onclick: () => answer("always") }, "Permitir siempre aquí") : null,
      h("button", { class: "danger small", onclick: () => answer("no") }, "Denegar")));
  }
  return card;
}
function assistantInner(content, reasoning, tools, streaming, extra = {}) {
  const frag = document.createDocumentFragment();
  if (extra.todos?.length) frag.append(todoCard(extra.todos));
  if (extra.compacted) frag.append(h("div", { class: "route" }, `Se resumieron ${extra.compacted} mensajes antiguos para que la conversación quepa en el contexto`));
  if (extra.liveOut && streaming) frag.append(h("pre", { class: "live-out" }, extra.liveOut.slice(-4000)));
  if (extra.status && streaming) frag.append(h("div", { class: "route" }, extra.status));
  if (extra.route) frag.append(h("div", { class: "route" }, `Auto: ${extra.route.model}` + (extra.route.reason ? ` — ${extra.route.reason}` : "")));
  for (const f of extra.fallbacks || []) frag.append(h("div", { class: "route warn" }, "↪ falló " + f + ", probando el otro modelo…"));
  const { think, body, open } = splitThink(content || "");
  const r = [reasoning, think].filter(Boolean).join("\n");
  if (r) frag.append(h("details", { class: "thinking", open: streaming && (open || !body) ? true : false }, h("summary", {}, ico("brain"), streaming && !body ? "Pensando…" : "Razonamiento"), h("pre", {}, r)));
  const pendingCalls = {};
  const toolList = () => {  // filas de herramientas seguidas: un único bloque discreto
    const last = frag.lastChild;
    if (last && last.classList?.contains("tools")) return last;
    const box = h("div", { class: "tools" }); frag.append(box); return box;
  };
  for (const t of tools || []) {
    if (t.name && t.name.startsWith("memory_")) {
      if (t.type === "tool_call") {
        let a = {}; try { a = JSON.parse(t.args || "{}"); } catch { /* */ }
        frag.append(h("div", { class: "memory-note", title: "Gestiona la memoria en Ajustes → Memoria" },
          t.name === "memory_save" ? `Recordado: ${a.content || ""}` : `Olvidado el recuerdo ${a.id}`));
      } else if (/^No guardado|^Error/.test(t.result || "")) frag.append(h("div", { class: "memory-note warn" }, t.result));
      continue;
    }
    if (t.name === "todo_write") continue;  // ya se ve en la tarjeta del plan
    if (t.type === "tool_call") pendingCalls[t.name] = t;  // se muestra junto a su resultado
    else if (t.type === "approval") frag.append(approvalCard(t));
    else if (t.type === "tool_result") { toolList().append(toolRow(t.name, pendingCalls[t.name]?.args, t.result)); delete pendingCalls[t.name]; }
  }
  if (streaming) for (const [name, c] of Object.entries(pendingCalls)) {  // en curso
    if (!(tools || []).some((x) => x.type === "approval" && x.name === name && !x.state)) toolList().append(toolRow(name, c.args, null));
  }
  const b = h("div", { class: "bubble" + (streaming ? " cursor" : "") });
  b.innerHTML = md(body);
  frag.append(b);
  const fileIcon = (p) => ({ docx: "📘", doc: "📘", xlsx: "📗", xlsm: "📗", csv: "📗", pptx: "📙", pdf: "📕", exe: "⚙️", py: "🐍" }[String(p).split(".").pop().toLowerCase()] || "📄");
  const outs = [...new Set(extra.files || [])];
  if (outs.length) frag.append(h("div", { class: "file-cards" }, outs.map((p) =>
    h("a", { class: "file-card", href: "/api/files/download?" + qs({ path: p }), title: p },
      h("span", { class: "fi" }, ico("file"), h("small", {}, String(p).split(".").pop().toUpperCase().slice(0, 4))), h("span", { class: "fn" }, baseName(p), h("small", {}, "Descargar")))))); 
  const imgs = extra.images || [];
  if (imgs.length) frag.append(h("div", { class: "gen-images" }, imgs.map((p) =>
    h("a", { href: fileUrl(p), target: "_blank", title: p }, h("img", { src: fileUrl(p), alt: "imagen generada", loading: "lazy" })))));
  return frag;
}
function messageEl(m) {
  const el = h("div", { class: `msg ${m.role}`, "data-id": m.id });
  if (m.role === "user") {
    el.append(h("div", { class: "bubble" }, m.content));
    const att = m.meta?.attachments || [];
    const imgs = att.filter((a) => a.kind === "image" || (!a.kind && isImage(a.name)));
    if (imgs.length) el.append(h("div", { class: "msg-images" }, imgs.map((a) =>
      h("img", { src: fileUrl(a.path), alt: a.name, loading: "lazy", onclick: () => previewFile(a.path) }))));
    el.append(h("div", { class: "meta" },
      att.filter((a) => !imgs.includes(a)).map((a) => h("span", { class: "chip" }, ico(a.kind === "document" || a.kind === "pdf_scan" ? "doc" : "clip"), a.name)),
      h("button", { class: "act", title: "Copiar", onclick: () => { copyText(m.content); } }, ico("copy")),
      h("button", { class: "act", title: "Editar", onclick: () => editFrom(m) }, ico("pencil")),
      (S.checkpoints || []).some((c) => c.id >= m.id) ? h("button", { class: "act", title: "Volver aquí: los archivos que la IA tocó desde este mensaje vuelven a como estaban antes", onclick: () => rewindTo(m) }, ico("rewind")) : null));
  } else {
    el.append(assistantInner(m.content, m.reasoning, m.meta?.tools, false, { images: m.meta?.images || [], files: m.meta?.files || [], todos: m.meta?.todos || [] }));
    const st = m.meta?.stats || {};
    el.append(h("div", { class: "meta" },
      h("button", { class: "act", title: "Copiar", onclick: () => { copyText(m.content); } }, ico("copy")),
      h("button", { class: "act", title: "Volver a generar", onclick: () => regenerate(m) }, ico("retry")),
      m.meta?.finish ? h("button", { class: "act continue", title: "La respuesta quedó incompleta",
        onclick: () => { if (!S.streaming) send("Continúa exactamente donde lo dejaste.", []); } }, ico("play"), "Continuar") : null,
      h("span", { class: "meta-model", title: (m.meta?.provider === "local" ? "Modelo local" : "API") + (m.meta?.route ? " · " + m.meta.route : "") }, m.meta?.model || ""),
      st.tokens_per_second ? h("span", {}, `${st.tokens_per_second.toFixed(1)} tok/s`) : null,
      m.meta?.usage ? h("span", { title: "Tokens de entrada/salida de toda la respuesta (incluidas las herramientas)" }, `↑${m.meta.usage.in} ↓${m.meta.usage.out}` + (m.meta.usage.cost ? ` · ~$${m.meta.usage.cost.toFixed(m.meta.usage.cost < 0.01 ? 4 : 3)}` : "")) : null));
  }
  return el;
}
$("#messages").addEventListener("click", (e) => {
  const pre = e.target.closest("pre");
  if (!pre) return;
  const code = pre.querySelector("code")?.textContent || "";
  if (e.target.classList.contains("copy")) copyText(code, "Código copiado");
  if (e.target.classList.contains("preview")) openArtifact(code, pre.querySelector("code")?.dataset.lang);
});
// --- Panel de vista previa (HTML / SVG en un iframe aislado) -----------------------------------
function openArtifact(code, lang) {
  const isSvg = lang === "svg" || /^\s*<svg/i.test(code);
  const doc = isSvg ? `<!doctype html><meta charset="utf-8"><body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#fff">${code}</body>` : code;
  $("#artifact-frame").srcdoc = doc;
  $("#artifact-src").textContent = code;
  $("#artifact-title").textContent = isSvg ? "Vista previa (SVG)" : "Vista previa (HTML)";
  $("#artifact-frame").classList.remove("hidden"); $("#artifact-src").classList.add("hidden");
  $("#artifact-code").textContent = "Código";
  $("#artifact").classList.remove("hidden");
  $("#artifact-open").onclick = () => {
    const url = URL.createObjectURL(new Blob([doc], { type: "text/html" }));
    window.open(url, "_blank", "noopener");
  };
}
$("#artifact-close").addEventListener("click", () => $("#artifact").classList.add("hidden"));
$("#artifact-code").addEventListener("click", () => {
  const showCode = !$("#artifact-frame").classList.contains("hidden");
  $("#artifact-frame").classList.toggle("hidden", showCode); $("#artifact-src").classList.toggle("hidden", !showCode);
  $("#artifact-code").textContent = showCode ? "Vista previa" : "Código";
});
async function loadCheckpoints() {
  if (!S.convId) { S.checkpoints = []; return; }
  try { S.checkpoints = (await api(`/api/conversations/${S.convId}/checkpoints`)).checkpoints; } catch { S.checkpoints = []; }
}
async function rewindTo(m) {
  if (S.streaming) return;
  const touched = (S.checkpoints || []).filter((c) => c.id >= m.id).flatMap((c) => c.files);
  const list = [...new Set(touched)].slice(0, 12).map((p) => "• " + p).join("\n");
  if (!confirm(`Volver a antes de este mensaje:\n\n• Los archivos que la IA modificó desde aquí vuelven a su estado anterior:\n${list}\n• Se borran este mensaje y los siguientes (tu texto vuelve al cuadro para editarlo).\n\nLo que hicieran los comandos no se deshace. ¿Continuar?`)) return;
  try {
    const r = await api(`/api/conversations/${S.convId}/restore`, { method: "POST", body: { id: m.id, truncate: true } });
    toast(`Restaurado: ${r.restored.length} archivos, ${r.deleted.length} borrados` + (r.failed.length ? `, ${r.failed.length} con problemas` : ""), 5000);
    input.value = m.content; input.dispatchEvent(new Event("input")); input.focus();
    await openConversation(S.convId);
  } catch (e) { toast(e.message); }
}
async function editFrom(m) {
  if (S.streaming) return;
  const t = prompt("Editar mensaje (se borrarán las respuestas posteriores):", m.content);
  if (t == null) return;
  S.conv = await api(`/api/conversations/${S.convId}/messages/${m.id}`, { method: "DELETE" });
  renderMessages();
  send(t, (m.meta?.attachments || []).map((a) => a.path));
}
async function regenerate(m) {
  if (S.streaming) return;
  S.conv = await api(`/api/conversations/${S.convId}/messages/${m.id}`, { method: "DELETE" });
  renderMessages();
  send("", [], true);
}

// --- Envío con streaming -----------------------------------------------------------------
function setSending(on) {
  const b = $("#send-btn");
  b.innerHTML = ""; b.append(ico(on ? "stop" : "arrowUp")); b.classList.toggle("stop", on);
  b.title = on ? "Detener" : "Enviar"; b.dataset.state = on ? "sending" : "idle";
}
const input = $("#input");
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && !matchMedia("(pointer: coarse)").matches) {
    e.preventDefault();
    if (S.streaming) {  // mientras trabaja se puede ir escribiendo: el mensaje se envía al terminar
      const t = input.value.trim();
      if (t) { S.queued = t; input.value = ""; input.style.height = "auto"; toast("En cola: se enviará cuando termine (Esc para detener)", 3500); }
      return;
    }
    $("#send-btn").click();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && S.streaming && !document.querySelector("dialog[open]")) { S.queued = null; S.streaming.abort(); toast("Detenido"); }
  if (e.key === "Tab" && e.shiftKey && document.activeElement === input) {  // Mayús+Tab: cambia el modo de permisos
    e.preventDefault();
    const m = $("#mode-select"), order = ["normal", "edits", "plan"];
    m.value = order[(order.indexOf(m.value) + 1) % order.length]; m.dispatchEvent(new Event("change"));
    toast("Modo: " + { normal: "Normal", edits: "Aceptar ediciones", plan: "Plan" }[m.value]);
  }
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "o") { e.preventDefault(); setView(S.code ? "code" : "chat"); newChat(); }
});
$("#send-btn").addEventListener("click", () => {
  if (S.streaming) { S.streaming.abort(); return; }
  const text = input.value.trim();
  if (!text && !S.attachments.length) return;
  const att = S.attachments.map((a) => a.path);
  let outgoing = text;
  if (text.startsWith("/")) {
    const r = runSlash(text);
    if (r !== null) { input.value = ""; input.style.height = "auto"; if (!r) return; outgoing = r; }
  }
  input.value = ""; input.style.height = "auto"; S.attachments = []; renderAttachments();
  send(outgoing, att);
});

async function send(text, attachments, isContinue = false) {
  const { provider, model } = currentModel();
  const box = $("#messages");
  if (!S.conv?.messages?.length) { box.innerHTML = ""; $("#view-chat").classList.remove("is-empty"); $("#welcome-ideas")?.remove(); }
  if (text || attachments.length) {
    const um = { id: 0, role: "user", content: text, meta: { attachments: attachments.map((p) => ({ name: baseName(p), path: p })) } };
    box.append(messageEl(um));
  }
  const el = h("div", { class: "msg assistant" });
  el.append(h("div", { class: "bubble cursor" }));
  box.append(el); box.scrollTop = box.scrollHeight;

  const ctrl = new AbortController(); S.streaming = ctrl;
  setSending(true);
  let content = "", reasoning = "", tools = [], errorMsg = null, raf = 0;
  const extra = { route: null, fallbacks: [], images: [], files: [], todos: [] };
  const paint = () => {
    raf = 0;
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    el.innerHTML = ""; el.append(assistantInner(content, reasoning, tools, true, extra));
    if (stick) box.scrollTop = box.scrollHeight;
  };
  try {
    const body = { conversation_id: S.convId, message: text, attachments, provider, model,
      use_tools: $("#tools-toggle").checked, use_web: $("#web-toggle").checked, continue: isContinue,
      mode: $("#mode-select").value };
    if (S.workdir !== undefined) body.workdir = S.workdir;
    if (S.system !== undefined) body.system = S.system;
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: ctrl.signal });
    if (r.status === 401) { showLogin(); throw new Error("No autorizado"); }
    if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail; } catch { /* */ } throw new Error(d); }
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
        if (!chunk.startsWith("data:")) continue;
        const ev = JSON.parse(chunk.slice(5));
        if (ev.type === "start") { if (!S.convId) { S.convId = ev.conversation_id; store.set("conv", S.convId); loadConversations(); } }
        else if (ev.type === "content") { content += ev.text; extra.status = null; }
        else if (ev.type === "reasoning") reasoning += ev.text;
        else if (ev.type === "tool_output") { extra.liveOut = (extra.liveOut || "") + ev.text; if (S.code) { const t = $("#ctab-term"); if (t) renderCodePanel({ tools, todos: extra.todos, liveOut: extra.liveOut }); } }
        else if (ev.type === "tool_call" || ev.type === "tool_result") {
          tools.push(ev);
          if (ev.type === "tool_result") { extra.liveOut = ""; if (ev.name === "app_settings" || ev.name === "request_folder_access") S.settings = null; }
        }
        else if (ev.type === "approval") { tools.push(ev); notifyApproval(ev); }
        else if (ev.type === "approval_result") { const a = tools.find((t) => t.id === ev.id); if (a) a.state = ev.approved ? "approved" : "denied"; }
        else if (ev.type === "route") extra.route = ev;
        else if (ev.type === "status") extra.status = ev.text;
        else if (ev.type === "image") extra.images.push(ev.path);
        else if (ev.type === "todos") extra.todos = ev.items;
        else if (ev.type === "retract") { if (content.endsWith(ev.text)) content = content.slice(0, content.length - ev.text.length); }
        else if (ev.type === "file") extra.files.push(ev.path);
        else if (ev.type === "compacted") extra.compacted = ev.messages;
        else if (ev.type === "route_fallback") extra.fallbacks.push(ev.message);
        else if (ev.type === "budget") toast(ev.pct >= 100 ? `⚠ Has superado tu límite mensual (${ev.cost} de ${ev.limit} $)` : `Gasto del mes: ${ev.pct}% de tu límite (${ev.cost} de ${ev.limit} $)`, 7000);
        else if (ev.type === "error") errorMsg = ev.message;
        if (S.code && (ev.type === "tool_call" || ev.type === "tool_result" || ev.type === "todos")) {
          renderCodePanel({ tools, todos: extra.todos }); if (ev.type === "tool_result") refreshChanges();
        }
        // En respuestas muy largas repintar todo el markdown en cada frame congela la página: máx. ~7 veces/s
        if (!raf) raf = setTimeout(() => requestAnimationFrame(paint), content.length > 4000 ? 140 : 0);
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") errorMsg = e.message;
  } finally {
    S.streaming = null;
    setSending(false);
    if (errorMsg) toast("Error: " + errorMsg, 7000);
    if (S.convId) { await new Promise((r) => setTimeout(r, 150)); const wd = S.workdir; await openConversation(S.convId).catch(() => {}); S.workdir = wd; }
    else el.remove();
    refreshContext();
    if (S.queued) { const q = S.queued; S.queued = null; setTimeout(() => send(q, []), 200); }
  }
}

function notifyApproval(ev) {
  if (document.hidden && "Notification" in window && Notification.permission === "granted") {
    new Notification("G3G3AI necesita tu permiso", { body: ev.name + ": " + (ev.args?.command || ev.args?.path || "") });
  }
}
if ("Notification" in window && Notification.permission === "default") {
  document.addEventListener("click", () => Notification.requestPermission().catch(() => {}), { once: true });
}

// --- Adjuntos --------------------------------------------------------------------------
const isImage = (name) => /\.(png|jpe?g|gif|webp|bmp)$/i.test(name || "");
const fileUrl = (path) => "/api/files/download?" + qs({ path, inline: true });
function renderAttachments() {
  const c = $("#attachments"); c.innerHTML = "";
  S.attachments.forEach((a, i) => c.append(h("span", { class: "chip" },
    isImage(a.name) ? h("img", { class: "thumb", src: fileUrl(a.path), alt: "" }) : "📎 ", a.name,
    h("button", { onclick: () => { S.attachments.splice(i, 1); renderAttachments(); } }, "✕"))));
}
function addAttachment(path) {
  if (!S.attachments.some((a) => a.path === path)) S.attachments.push({ path, name: baseName(path) });
  renderAttachments();
}
async function attachLocalFiles(fileList) {
  if (!fileList || !fileList.length) return;
  toast("Subiendo…", 1500);
  const res = await uploadFiles(fileList, await uploadsDir());
  res.forEach((r) => addAttachment(r.path));
}
$("#camera-input").addEventListener("change", async (e) => { await attachLocalFiles(e.target.files); e.target.value = ""; });
$("#camera-btn").addEventListener("click", () => $("#camera-input").click());
$("#image-btn").addEventListener("click", () => {
  if (!input.value.startsWith("/imagen ")) input.value = "/imagen " + input.value;
  input.focus(); toast("Describe la imagen y pulsa Enviar (o pídeselo a la IA en el chat)", 3000);
});
const composer = $(".composer");
composer.addEventListener("dragover", (e) => { e.preventDefault(); composer.classList.add("drop"); });
composer.addEventListener("dragleave", () => composer.classList.remove("drop"));
composer.addEventListener("drop", (e) => { e.preventDefault(); composer.classList.remove("drop"); attachLocalFiles(e.dataTransfer.files); });
input.addEventListener("paste", (e) => {
  const imgs = [...(e.clipboardData?.files || [])];
  if (imgs.length) { e.preventDefault(); attachLocalFiles(imgs); }
});
$("#attach-btn").addEventListener("click", () => { $("#picker").showModal(); loadPicker(S.pickerPath); });
async function loadPicker(path) {
  try {
    const d = await api("/api/files/list?" + qs({ path: path || "" }));
    S.pickerPath = d.path; $("#picker-path").textContent = d.path;
    $("#picker-up").disabled = !d.parent; $("#picker-up").onclick = () => loadPicker(d.parent);
    const ul = $("#picker-list"); ul.innerHTML = "";
    for (const e of d.entries) ul.append(h("li", { onclick: () => {
      if (e.is_dir) loadPicker(e.path); else { addAttachment(e.path); $("#picker").close(); }
    } }, h("span", { class: "name" }, (e.is_dir ? "📁 " : "📄 ") + e.name), e.is_dir ? null : h("span", { class: "sub" }, fmtSize(e.size))));
  } catch (e) { toast(e.message); }
}
async function uploadFiles(fileList, dir) {
  const out = [];
  for (const f of fileList) {
    const fd = new FormData(); fd.append("dir", dir || ""); fd.append("file", f);
    try { out.push(await api("/api/files/upload", { method: "POST", body: fd })); }
    catch (e) { toast(`${f.name}: ${e.message}`); }
  }
  return out;
}
$("#picker-upload").addEventListener("change", async (e) => {
  const res = await uploadFiles(e.target.files, await uploadsDir());
  res.forEach((r) => addAttachment(r.path)); e.target.value = ""; $("#picker").close();
  if (res.length) toast(`Subido a ${res[0].path.replace(/[\\/][^\\/]*$/, "")}`);
});
async function uploadsDir() {
  // Los archivos subidos desde el móvil se guardan en ~/G3G3AI-subidas
  const roots = await api("/api/files/roots");
  const dir = joinPath(roots[0], "G3G3AI-subidas");
  await api("/api/files/mkdir", { method: "POST", body: { path: dir } }).catch(() => {});
  return dir;
}

// --- Instrucciones del sistema por conversación ------------------------------------------------------
$("#system-btn").addEventListener("click", async () => {
  if (!S.settings) S.settings = await api("/api/settings");
  const cur = S.system !== undefined ? S.system : (S.conv?.system ?? S.settings.default_system_prompt);
  $("#system-text").value = cur || ""; $("#project-dir").value = S.workdir ?? S.conv?.workdir ?? ""; $("#system-dialog").showModal();
});
$("#system-save").addEventListener("click", async () => {
  S.system = $("#system-text").value;
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { system: S.system } });
  S.workdir = $("#project-dir").value.trim();
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { workdir: S.workdir || null } });
  $("#system-dialog").close(); toast("Instrucciones aplicadas");
});
$("#system-reset").addEventListener("click", async () => {
  S.system = null;
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { system: null } });
  $("#system-dialog").close(); toast("Se usarán las instrucciones predeterminadas");
});

// --- Modelos -----------------------------------------------------------------------------
function fitBadge(size) {
  const total = S.status?.memory?.total || 0;
  if (!total) return null;
  const ratio = size / total;
  if (ratio < 0.5) return h("span", { class: "badge ok" }, "cabe bien");
  if (ratio < 0.7) return h("span", { class: "badge warn" }, "justo");
  return h("span", { class: "badge bad" }, "demasiado grande");
}
function renderLlamaStatus() {
  const l = S.status.llama, box = $("#llama-status"); box.innerHTML = "";
  const mem = S.status.memory;
  box.append(h("div", { class: "row" },
    h("span", { class: "grow" }, h("b", {}, { ready: "Listo", loading: "Cargando…", error: "Error", stopped: "Ningún modelo cargado" }[l.state]),
      l.model ? ` — ${l.model}` : "", l.params?.ctx ? h("span", { class: "sub muted" }, ` (ctx ${l.params.ctx}, ${l.params.threads} hilos)`) : null),
    l.state === "ready" ? h("button", { class: "ghost", title: "Comprueba si el modelo sabe usar herramientas y a qué velocidad va", onclick: async (ev) => {
      const b = ev.target; b.disabled = true; b.textContent = "Probando…";
      try {
        const r = await api("/api/llama/selftest", { method: "POST" });
        const icon = { ok: "✅", text: "⚠", none: "❌", error: "❌" }[r.verdict];
        alert(`${icon} ${r.message}\n\nTiempo: ${r.seconds} s` + (r.tokens_per_second ? ` · ${r.tokens_per_second.toFixed(1)} tok/s` : "")
          + `\nPerfil: ${r.profile} · ${r.tools_sent} herramientas · contexto ${r.context}`);
      } catch (e) { alert("❌ " + e.message); }
      b.disabled = false; b.textContent = "🧪 Probar con el agente";
    } }, "🧪 Probar con el agente") : null,
    l.state === "ready" || l.state === "loading" ? h("button", { class: "danger", onclick: async () => { await api("/api/llama/unload", { method: "POST" }); refreshStatus(); refreshModels(); loadProviders(); } }, "Descargar de memoria") : null));
  if (l.error) box.append(h("pre", { class: "logs error" }, l.error));
  if (!l.binary) box.append(engineBox());
  if (mem?.total) box.append(h("p", { class: "muted" }, `RAM disponible: ${fmtSize(mem.available)} de ${fmtSize(mem.total)}`));
  $("#disk-free").textContent = S.status.disk_free ? `· ${fmtSize(S.status.disk_free)} libres` : "";
}
let hwShown = false;
async function renderHardware(refresh = false) {
  const box = $("#hw-box"); if (!box || (hwShown && !refresh)) return;
  let d;
  try { d = await api("/api/hardware" + (refresh ? "?refresh=true" : "")); } catch (e) { box.textContent = e.message; return; }
  hwShown = true;
  const r = d.recommendation, sm = r.summary;
  const where = { gpu: "entero en la gráfica (rápido)", cpu: "en el procesador", mixto: "repartido entre gráfica y procesador" }[r.main.where];
  box.innerHTML = "";
  box.append(h("p", { class: "muted" }, `${sm.cpu} · ${sm.cores} núcleos · ${sm.ram_gb} GB de RAM · gráfica: ${sm.gpu}` + (sm.vram_gb ? ` (${sm.vram_gb} GB)` : "")));
  box.append(h("p", {}, "Modelo ideal: ", h("b", {}, r.main.tier), ` en ${r.quant}, ${where}. Motor: `, h("b", {}, r.engine === "vulkan" ? "Vulkan (gráfica)" : "CPU"), "."));
  const st = r.settings;
  box.append(h("p", { class: "muted" }, `Ajustes: contexto ${st.llama_ctx} · hilos ${st.llama_threads} · capas GPU ${st.llama_gpu_layers}` + (st.llama_extra_args ? ` · ${st.llama_extra_args}` : "")));
  if (r.notes.length) box.append(h("ul", { class: "warnings-list" }, r.notes.map((n) => h("li", {}, n))));
  if (r.images) box.append(h("p", { class: "muted" }, "🎨 " + r.images));
  const searchBtn = (q, label) => h("button", { class: "ghost small", onclick: () => { $("#hub-q").value = q; hubSearch(q); $("#hub-q").scrollIntoView({ behavior: "smooth", block: "center" }); } }, label);
  box.append(h("div", { class: "row" },
    h("button", { class: "primary small", onclick: async () => {
      await api("/api/hardware/apply", { method: "POST" }); S.settings = null;
      $("#p-ctx").value = st.llama_ctx; $("#p-threads").value = st.llama_threads; $("#p-ngl").value = st.llama_gpu_layers;
      toast("Ajustes aplicados ✔ (se usan al cargar el próximo modelo)");
    } }, "Aplicar ajustes"),
    r.main.searches.map((q) => searchBtn(q, "🔎 " + q)),
    searchBtn(r.vision_search, "👁 con visión"),
    h("button", { class: "ghost small", onclick: () => renderHardware(true) }, "Volver a analizar")));
}
// --- Ollama -----------------------------------------------------------------------------------
let ollamaTimer = null;
async function renderOllama() {
  const box = $("#ollama-box"); if (!box) return;
  let d;
  try { d = await api("/api/ollama"); } catch (e) { box.textContent = e.message; return; }
  box.innerHTML = "";
  const job = d.job;
  const post = (url, body) => api(url, { method: "POST", body: body || {} });
  box.append(h("p", { class: "muted" }, "Motor alternativo a llama.cpp: descarga modelos por su nombre (p.ej. qwen3:8b) y usa la gráfica automáticamente. Cómodo en el PC."));
  if (!d.installed) {
    box.append(h("p", {}, "Ollama no está instalado en este equipo."));
    if (d.can_install) box.append(h("button", { class: "primary small", disabled: job.status === "running",
      onclick: async () => { await post("/api/ollama/install"); renderOllama(); } }, "⬇ Instalar Ollama"));
    else if (d.linux_command) box.append(h("p", {}, "En Linux se instala desde una terminal (pide la contraseña de administrador):", h("code", { class: "access-url" }, d.linux_command)));
  } else if (!d.running) {
    box.append(h("p", {}, "Ollama está instalado pero no está en marcha."),
      h("button", { class: "primary small", onclick: async () => {
        try { await post("/api/ollama/start"); toast("Iniciando Ollama…"); setTimeout(renderOllama, 2500); } catch (e) { toast(e.message); }
      } }, "▶ Iniciar Ollama"));
  } else {
    box.append(h("div", { class: "row" },
      h("span", { class: "grow" }, h("b", {}, "✔ Ollama en marcha"), h("span", { class: "muted" }, ` · versión ${d.version || "?"} · ${d.url}`)),
      h("label", { class: "toggle", title: "Muestra los modelos de Ollama en el selector del chat" },
        h("input", { type: "checkbox", checked: d.provider_enabled, onchange: async (e) => {
          await post("/api/ollama/enable", { enabled: e.target.checked }); S.models = {}; await loadProviders();
          toast(e.target.checked ? "Ollama aparece ahora en el selector de modelos" : "Ollama oculto del selector");
        } }), "Usar en el chat")));
    const ul = h("ul", { class: "list" });
    if (!d.models.length) ul.append(h("li", { class: "muted" }, "Aún no hay modelos. Descarga uno abajo."));
    for (const m of d.models) ul.append(h("li", {},
      h("div", { class: "name" }, m.name, h("div", { class: "sub" }, [m.params, m.quant, fmtSize(m.size)].filter(Boolean).join(" · "))),
      fitBadge(m.size),
      h("button", { class: "ghost small", title: "Borrar", onclick: async () => {
        if (!confirm(`¿Borrar ${m.name} de Ollama?`)) return;
        await api("/api/ollama/models?" + qs({ name: m.name }), { method: "DELETE" }).catch((e) => toast(e.message)); renderOllama();
      } }, "🗑")));
    box.append(ul);
    const inp = h("input", { class: "grow", placeholder: "Nombre del modelo, p.ej. qwen3:8b" });
    const pull = async (name) => { if (!name) return; await post("/api/ollama/pull", { name }); toast("Descargando " + name + "…"); renderOllama(); };
    box.append(h("form", { class: "row", onsubmit: (e) => { e.preventDefault(); pull(inp.value.trim()); } },
      inp, h("button", { class: "primary small", disabled: job.status === "running" }, "Descargar")));
    box.append(h("div", { class: "suggestions" }, `Recomendados para este equipo (${d.tier}): `,
      d.suggestions.models.map((n) => h("button", { class: "link", onclick: () => pull(n) }, n)),
      " · con visión: ", h("button", { class: "link", onclick: () => pull(d.suggestions.vision) }, d.suggestions.vision),
      " · ", h("a", { href: "https://ollama.com/library", target: "_blank", rel: "noopener" }, "ver todos")));
  }
  if (job.status !== "idle") {
    const pct = job.total ? Math.round(100 * job.completed / job.total) : null;
    box.append(h("p", {}, job.status === "running" ? `⏳ ${job.what}…` + (pct != null ? ` ${pct}%` : "")
      : job.status === "done" ? `✔ ${job.what}: hecho` : `✕ ${job.what}: ${job.error}`));
    if (pct != null && job.status === "running") box.append(h("div", { class: "progress" }, h("div", { style: `width:${pct}%` })));
    if (job.log.length) box.append(h("details", { open: job.status === "error" }, h("summary", {}, "Registro"), h("pre", { class: "logs" }, job.log.join("\n"))));
  }
  clearTimeout(ollamaTimer);
  if (job.status === "running" && S.view === "models") ollamaTimer = setTimeout(renderOllama, 1500);
}
async function renderImageEngine() {
  const box = $("#image-engine"); box.innerHTML = "";
  const st = await api("/api/images/status");
  box.append(h("p", {}, "Proveedor actual: ", h("b", {}, st.provider || "desactivado"),
    st.provider && st.provider !== "local" ? ` (${st.model || "sin modelo"})` : ""));
  box.append(h("p", { class: "muted" }, "Para generar en local: instala el motor, descarga un modelo de imagen GGUF (p.ej. «sd-turbo») y pulsa 🎨 en él. Por API se configura en Ajustes."));
  if (st.sd_binary) box.append(h("p", {}, "✔ stable-diffusion.cpp instalado", h("span", { class: "sub muted" }, " " + st.sd_binary)));
  else box.append(engineBox("sd"));
  box.append(h("p", { class: "muted" }, "Imágenes guardadas en ", h("code", {}, st.dir)));
}
function engineBox(kind = "llama") {
  const box = h("div", { class: "engine" },
    kind === "sd"
      ? h("p", {}, h("b", {}, "Motor de imágenes (stable-diffusion.cpp)."), " En Linux: ./install.sh --with-sd. En Windows puedes descargarlo ya compilado:")
      : h("p", {}, h("b", {}, "Falta el motor llama.cpp."), " En Linux se instala con ./install.sh (compilado para tu CPU). En Windows puedes descargarlo ya compilado:"));
  const list = h("div", {}, h("span", { class: "muted" }, "Consultando versiones…"));
  box.append(list);
  api("/api/engine/assets?kind=" + kind).then((r) => {
    list.innerHTML = "";
    if (r.note) list.append(h("p", { class: "muted" }, r.note));
    for (const a of r.assets) list.append(h("div", { class: "row" },
      h("span", { class: "grow" }, h("b", {}, a.variant.toUpperCase()), " — ", a.description, h("span", { class: "sub muted" }, ` (${fmtSize(a.size)}, ${r.release})`)),
      h("button", { class: "primary small", onclick: () => installEngine(a, kind) }, "Instalar")));
  }).catch((e) => { list.innerHTML = ""; list.append(h("p", { class: "error" }, e.message)); });
  return box;
}
async function installEngine(a, kind = "llama") {
  await api("/api/engine/install", { method: "POST", body: { url: a.url, name: a.name, kind } });
  toast("Descargando motor…");
  const t = setInterval(async () => {
    const st = await api("/api/engine/status?kind=" + kind);
    const pill = $("#status-pill");
    if (st.status === "downloading") pill.textContent = `⬇ motor ${st.total ? Math.round(100 * st.done / st.total) : 0}%`;
    if (st.status === "extracting") pill.textContent = "⬇ motor: descomprimiendo";
    if (st.status === "done" || st.status === "error") {
      clearInterval(t);
      toast(st.status === "done" ? "Motor instalado ✔" : "Error: " + st.error, 6000);
      refreshModels();
    }
  }, 1000);
}
async function refreshModels() {
  await refreshStatus();
  if (!S.settings) S.settings = await api("/api/settings");
  if (!$("#p-ctx").value) {
    $("#p-ctx").value = S.settings.llama_ctx; $("#p-threads").value = S.settings.llama_threads || "";
    $("#p-ngl").value = S.settings.llama_gpu_layers;
  }
  const models = await api("/api/models/local"), ul = $("#local-models"); ul.innerHTML = "";
  if (!models.length) ul.append(h("li", { class: "muted" }, "Aún no hay modelos. Busca y descarga uno abajo."));
  const loaded = S.status.llama.model_path;
  for (const m of models) {
    ul.append(h("li", {},
      h("div", { class: "name" }, m.name, h("div", { class: "sub" }, [m.repo, m.quant, fmtSize(m.size)].filter(Boolean).join(" · "))),
      m.mmproj ? h("span", { class: "badge" }, "proyector visión") : fitBadge(m.size),
      m.vision ? h("span", { class: "badge ok", title: "Tiene proyector de visión: podrá ver imágenes" }, "👁 visión") : null,
      m.mmproj ? null : (loaded === m.path
        ? h("span", { class: "badge ok" }, "cargado")
        : h("button", { class: "primary small", onclick: () => loadModel(m.path) }, "Cargar")),
      m.mmproj ? null : h("button", { class: "ghost small", title: "Usar este modelo para generar imágenes en local (stable-diffusion.cpp)",
        onclick: async () => {
          const st = await api("/api/settings");
          await api("/api/settings", { method: "PUT", body: { ...st, sd_model: m.path, image_provider: "local" } });
          S.settings = null; toast("🎨 " + m.name + " se usará para generar imágenes"); refreshModels();
        } }, S.settings?.sd_model === m.path ? "🎨 ✔" : "🎨"),
      h("button", { class: "ghost small", title: "Borrar del disco", onclick: async () => {
        if (!confirm(`¿Borrar ${m.name} (${fmtSize(m.size)}) del disco?`)) return;
        await api("/api/models/local?" + qs({ path: m.path }), { method: "DELETE" }); refreshModels();
      } }, "🗑")));
  }
  renderImageEngine();
  renderHardware();
  renderOllama();
  const logs = await api("/api/llama/logs");
  $("#llama-logs").textContent = logs.lines.join("\n");
  refreshDownloads();
}
async function loadModel(path) {
  const body = { path, ctx: +$("#p-ctx").value || null, threads: +$("#p-threads").value || null, gpu_layers: +$("#p-ngl").value || 0 };
  await api("/api/llama/load", { method: "POST", body });
  toast("Cargando modelo…");
  await refreshModels();
  const t = setInterval(async () => {
    await refreshStatus();
    const st = S.status.llama.state;
    if (st !== "loading") {
      clearInterval(t);
      if (st === "ready") { toast("Modelo listo ✔"); store.set("model", "local::local"); loadProviders(); }
      if (S.view === "models") refreshModels();
    }
  }, 1500);
}
// --- Buscador de modelos (Hugging Face) ------------------------------------------------------
const HUB = { results: [], shown: 20, budget: null };
const fmtNum = (n) => n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + " M" : n >= 1e3 ? Math.round(n / 1e3) + " k" : String(n || 0);
function ago(iso) {
  if (!iso) return "";
  const d = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (d < 1) return "hoy";
  if (d < 2) return "ayer";
  if (d < 31) return `hace ${Math.round(d)} días`;
  if (d < 365) return `hace ${Math.round(d / 30)} meses`;
  return `hace ${(d / 365).toFixed(1).replace(".0", "")} años`;
}
async function hubBudget() {
  if (HUB.budget == null) {
    try { HUB.budget = (await api("/api/hardware")).recommendation.summary.budget_gb; } catch { HUB.budget = 0; }
  }
  return HUB.budget;
}
function fitInfo(gb) {
  if (!gb || !HUB.budget) return null;
  if (gb <= HUB.budget * 0.75) return h("span", { class: "badge ok", title: `~${gb} GB de ${HUB.budget} GB disponibles` }, "cabe bien");
  if (gb <= HUB.budget) return h("span", { class: "badge warn", title: `~${gb} GB de ${HUB.budget} GB disponibles` }, "justo");
  return h("span", { class: "badge bad", title: `~${gb} GB; este equipo tiene ~${HUB.budget} GB disponibles` }, "no cabe");
}
const sizeBucket = (r) => !r.params ? "" : r.params <= 2 ? "xs" : r.params <= 4.5 ? "s" : r.params <= 9.5 ? "m" : r.params <= 15 ? "l" : "xl";
const CAP_BADGE = { vision: "visión", code: "código", reasoning: "razonamiento", image: "imágenes" };

$("#hub-search").addEventListener("submit", (e) => { e.preventDefault(); hubSearch($("#hub-q").value.trim()); });
$("#hub-sort").addEventListener("change", () => { if ($("#hub-q").value.trim()) hubSearch($("#hub-q").value.trim()); });
["f-size", "f-vision", "f-code", "f-reason", "f-fits", "f-order"].forEach((id) =>
  $("#" + id).addEventListener("change", () => { HUB.shown = 20; renderHub(); }));
$$(".hub-explore [data-q]").forEach((b) => b.addEventListener("click", () => {
  $("#hub-q").value = b.dataset.q;
  $("#f-vision").checked = b.dataset.cap === "vision"; $("#f-code").checked = b.dataset.cap === "code";
  $("#f-reason").checked = b.dataset.cap === "reasoning"; $("#f-size").value = b.dataset.size || "";
  hubSearch(b.dataset.q);
}));

async function hubSearch(q) {
  if (!q) { $("#hub-q").focus(); return; }
  const ul = $("#hub-results"); ul.innerHTML = ""; ul.append(h("li", { class: "muted" }, "Buscando en Hugging Face…"));
  $("#hub-count").textContent = "";
  await hubBudget();
  try {
    HUB.results = await api("/api/hub/search?" + qs({ q, sort: $("#hub-sort").value }));
    HUB.shown = 20; $("#hub-filters").classList.remove("hidden"); renderHub();
  } catch (e) { ul.innerHTML = ""; ul.append(h("li", { class: "error" }, e.message)); }
}

function renderHub() {
  const ul = $("#hub-results"); ul.innerHTML = "";
  const size = $("#f-size").value, needs = [["f-vision", "vision"], ["f-code", "code"], ["f-reason", "reasoning"]]
    .filter(([id]) => $("#" + id).checked).map(([, c]) => c);
  let list = HUB.results.filter((r) =>
    (!size || (size === "moe" ? r.moe : sizeBucket(r) === size)) &&
    needs.every((c) => r.caps.includes(c)) &&
    (!$("#f-fits").checked || (r.est_gb && HUB.budget && r.est_gb <= HUB.budget)));
  const order = $("#f-order").value;
  if (order === "small") list = [...list].sort((a, b) => (a.params ?? 1e9) - (b.params ?? 1e9));
  if (order === "big") list = [...list].sort((a, b) => (b.params ?? -1) - (a.params ?? -1));
  if (order === "recent") list = [...list].sort((a, b) => new Date(b.updated || 0) - new Date(a.updated || 0));
  $("#hub-count").textContent = HUB.results.length
    ? `${list.length} de ${HUB.results.length} resultados` + (HUB.budget ? ` · memoria disponible en este equipo: ~${HUB.budget} GB` : "") : "";
  if (!list.length) {
    ul.append(h("li", { class: "muted" }, HUB.results.length ? "Ningún resultado con estos filtros." : "Sin resultados. Prueba con otro nombre (p.ej. «qwen», «gemma», «llama»)."));
    return;
  }
  for (const r of list.slice(0, HUB.shown)) {
    const files = h("div", { class: "repo-files hidden" });
    const sizeLabel = r.params ? (r.moe && r.active ? `${r.params}B (${r.active}B activos)` : `${r.params}B`) : null;
    ul.append(h("li", { class: "hub-item" },
      h("div", { class: "name" },
        h("div", { class: "hub-title" }, h("b", {}, r.name), h("span", { class: "muted" }, " · " + r.author)),
        h("div", { class: "hub-badges" },
          sizeLabel ? h("span", { class: "badge" }, sizeLabel) : null,
          r.moe ? h("span", { class: "badge", title: "Mezcla de expertos: rápido para su tamaño" }, "⚡ MoE") : null,
          r.caps.map((c) => h("span", { class: "badge" }, CAP_BADGE[c] || c)),
          r.est_gb ? h("span", { class: "badge", title: "Tamaño aproximado en Q4_K_M" }, `~${r.est_gb} GB`) : null,
          fitInfo(r.est_gb),
          r.downloaded ? h("span", { class: "badge ok" }, "✔ descargado") : null),
        h("div", { class: "sub" }, `⬇ ${fmtNum(r.downloads)} · ♥ ${fmtNum(r.likes)}` + (r.updated ? ` · actualizado ${ago(r.updated)}` : ""))),
      h("div", { class: "hub-actions" },
        h("button", { class: "ghost small", onclick: (e) => toggleRepo(r, files, e.target) }, "Ver archivos"),
        h("a", { class: "ghost small btn-like", href: r.url, target: "_blank", rel: "noopener", title: "Abrir en Hugging Face" }, "↗")),
      files));
  }
  if (list.length > HUB.shown) ul.append(h("li", { class: "hub-more" },
    h("button", { class: "ghost", onclick: () => { HUB.shown += 20; renderHub(); } }, `Mostrar más (${list.length - HUB.shown})`)));
}

async function toggleRepo(r, box, btn) {
  const repo = r.id;
  if (!box.classList.contains("hidden")) { box.classList.add("hidden"); btn.textContent = "Ver archivos"; return; }
  box.classList.remove("hidden"); btn.textContent = "Ocultar"; box.innerHTML = "Cargando archivos…";
  try {
    const groups = await api("/api/hub/files?" + qs({ repo }));
    box.innerHTML = "";
    const projs = groups.filter((g) => g.mmproj);
    const proj = projs.find((g) => /f16/i.test(g.name)) || projs[0];
    const models = groups.filter((g) => !g.mmproj);
    // Recomendado: Q4_K_M si cabe; si no, la mejor calidad que quepa
    const budget = HUB.budget ? HUB.budget * 1024 ** 3 : null;
    const fits = (g) => !budget || g.size <= budget;
    let best = models.find((g) => g.quant === "Q4_K_M" && fits(g));
    if (!best) best = [...models].filter(fits).sort((a, b) => b.level - a.level || b.size - a.size)[0];
    if (proj) box.append(h("p", { class: "muted" }, "👁 Tiene visión: al descargar un modelo se añade también su proyector (" + proj.name + ")."));
    if (!models.length) { box.append(h("p", { class: "muted" }, "Este repositorio no tiene archivos GGUF de modelo.")); return; }
    const ul = h("ul", { class: "list files-table" });
    for (const g of models) {
      const gb = Math.round(g.size / 1024 ** 3 * 10) / 10;
      ul.append(h("li", { class: g === best ? "recommended" : "" },
        h("div", { class: "name" },
          h("b", {}, g.quant || g.name), g === best ? h("span", { class: "badge ok" }, "⭐ recomendado para este equipo") : null,
          h("div", { class: "sub" }, [g.quality, fmtSize(g.size), g.files.length > 1 ? `${g.files.length} partes` : "", g.name].filter(Boolean).join(" · "))),
        fitInfo(gb),
        g.downloaded ? h("span", { class: "badge ok" }, "✔ descargado")
          : h("button", { class: g === best ? "primary small" : "ghost small", onclick: async (e) => {
            e.target.disabled = true;
            await api("/api/hub/download", { method: "POST", body: { repo, files: g.files } });
            if (proj && !proj.downloaded) await api("/api/hub/download", { method: "POST", body: { repo, files: proj.files } });
            toast("Descarga iniciada: " + (g.quant || g.name)); refreshDownloads();
          } }, "Descargar")));
    }
    box.append(ul);
    box.append(h("p", { class: "muted small-text" }, "Guía: Q4_K_M = equilibrio · Q5/Q6 = más calidad y más memoria · Q8 = casi sin pérdida · Q3/Q2 = cuando no cabe otra cosa."));
  } catch (e) { box.textContent = e.message; }
}
let dlTimer = null;
const seenDone = new Set();
async function refreshDownloads() {
  const list = await api("/api/hub/downloads"), box = $("#downloads"); box.innerHTML = "";
  for (const d of list) {
    const pct = d.total ? (100 * d.done / d.total) : 0;
    box.append(h("div", { class: "card" },
      h("div", { class: "row" }, h("b", { class: "grow" }, baseName(d.dest)),
        h("span", { class: "sub muted" }, d.status === "downloading" ? `${fmtSize(d.done)} / ${fmtSize(d.total)} · ${fmtSize(d.speed)}/s` : { done: "✔ completado", error: "✕ " + d.error, cancelled: "cancelado", pending: "preparando…" }[d.status]),
        h("button", { class: "ghost small", onclick: async () => { await api(`/api/hub/downloads/${d.id}`, { method: "DELETE" }); refreshDownloads(); } }, d.status === "downloading" ? "Cancelar" : "Quitar")),
      h("div", { class: "progress" }, h("div", { style: `width:${pct.toFixed(1)}%` }))));
  }
  const active = list.some((d) => d.status === "downloading" || d.status === "pending");
  clearTimeout(dlTimer);
  if (active && S.view === "models") dlTimer = setTimeout(refreshDownloads, 1500);
  const fresh = list.filter((d) => d.status === "done" && !seenDone.has(d.id));
  if (fresh.length) {
    fresh.forEach((d) => seenDone.add(d.id));
    toast("Descarga completada ✔"); refreshModels();
  }
}

// --- Explorador de archivos ----------------------------------------------------------------
async function loadFiles(path) {
  try {
    const d = await api("/api/files/list?" + qs({ path: path || "", hidden: $("#files-hidden").checked }));
    S.filesPath = d.path; $("#files-path").value = d.path; $("#files-up").disabled = !d.parent;
    $("#files-up").onclick = () => loadFiles(d.parent);
    renderFileList(d.entries);
  } catch (e) { toast(e.message); }
}
function renderFileList(entries) {
  const ul = $("#files-list"); ul.innerHTML = "";
  if (!entries.length) ul.append(h("li", { class: "muted" }, "Carpeta vacía"));
  for (const e of entries) {
    ul.append(h("li", { onclick: () => (e.is_dir ? loadFiles(e.path) : previewFile(e.path)) },
      h("span", { class: "name" }, (e.is_dir ? "📁 " : "📄 ") + (e.name || e.path)),
      e.is_dir && e.ai_write ? h("span", { class: "badge ok", title: "La IA puede modificar esta carpeta" }, "IA ✎") : null,
      e.is_dir ? null : h("span", { class: "sub" }, fmtSize(e.size)),
      e.mtime ? h("span", { class: "sub" }, new Date(e.mtime * 1000).toLocaleDateString()) : null));
  }
}
$("#files-go").addEventListener("click", () => loadFiles($("#files-path").value));
$("#files-path").addEventListener("keydown", (e) => { if (e.key === "Enter") loadFiles(e.target.value); });
$("#files-hidden").addEventListener("change", () => loadFiles(S.filesPath));
$("#files-upload").addEventListener("change", async (e) => {
  const res = await uploadFiles(e.target.files, S.filesPath); e.target.value = "";
  if (res.length) toast(`${res.length} archivo(s) subido(s)`); loadFiles(S.filesPath);
});
$("#files-mkdir").addEventListener("click", async () => {
  const n = prompt("Nombre de la nueva carpeta"); if (!n) return;
  await api("/api/files/mkdir", { method: "POST", body: { path: joinPath(S.filesPath, n) } }).catch((e) => toast(e.message));
  loadFiles(S.filesPath);
});
$("#files-search-form").addEventListener("submit", async (e) => {
  e.preventDefault(); const q = $("#files-search").value.trim(); if (!q) return loadFiles(S.filesPath);
  const res = await api("/api/files/search?" + qs({ q, path: S.filesPath }));
  renderFileList(res.map((r) => ({ ...r, name: r.path })));
});
const IMG = /\.(png|jpe?g|gif|webp|svg|bmp)$/i, VID = /\.(mp4|webm|mov|mkv)$/i, AUD = /\.(mp3|ogg|wav|flac|m4a)$/i;
async function previewFile(path) {
  const name = baseName(path), body = $("#preview-body"), url = "/api/files/download?" + qs({ path });
  $("#preview-title").textContent = name; $("#preview-download").href = url;
  $("#preview-attach").onclick = () => { addAttachment(path); $("#preview").close(); setView("chat"); toast("Adjuntado al chat"); };
  body.innerHTML = "Cargando…"; $("#preview").showModal();
  const inline = url + "&inline=true";
  if (IMG.test(name)) { body.innerHTML = ""; body.append(h("img", { src: inline, alt: name })); return; }
  if (VID.test(name)) { body.innerHTML = ""; body.append(h("video", { src: inline, controls: true })); return; }
  if (AUD.test(name)) { body.innerHTML = ""; body.append(h("audio", { src: inline, controls: true })); return; }
  try {
    const f = await api("/api/files/read?" + qs({ path }));
    body.innerHTML = ""; body.append(h("pre", {}, f.content + (f.truncated ? "\n\n[… truncado …]" : "")));
  } catch (e) { body.innerHTML = ""; body.append(h("p", { class: "muted" }, e.message + " — puedes descargarlo.")); }
}

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
  ["mcp_servers", "Servidores MCP (uno por línea)", "lines", "Formato: nombre = [VAR=valor] comando args. Se guardan al pulsar «Guardar ajustes»; luego usa «Probar servidores»."],
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
  renderUsage();
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
  "port hf_token agent_temperature image_model web_api_key").split(" "));
const SETTINGS_SECTION = {};
for (const [sec, keys] of Object.entries({
  local: "image_provider image_model image_mode image_size image_dir sd_steps sd_cfg sd_max_side models_dir llama_server_path llama_ctx llama_threads llama_gpu_layers llama_extra_args autoload_last_model hf_token agent_temperature local_thinking",
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
      h("button", { class: "ghost small", onclick: () => { S.settings.providers.splice(idx, 1); loadSettingsProvidersOnly(); } }, "Quitar")),
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
  loadSettingsProvidersOnly(); toast("Añadido. Pulsa «Guardar ajustes».");
});
$("#save-settings").addEventListener("click", async () => {
  const f = $("#settings-form"), out = { providers: S.settings.providers };
  for (const [key, , type] of FIELDS) {
    const el = f.elements[key];
    if (type === "checkbox") out[key] = el.checked;
    else if (["perm", "router", "model", "sandbox", "profile", "webprov", "imgprov", "imgmode", "imgsize"].includes(type)) out[key] = el.value;
    else if (type === "number") out[key] = el.value === "" ? 0 : Number(el.value);
    else if (type === "lines") out[key] = el.value.split("\n").map((s) => s.trim()).filter(Boolean);
    else out[key] = el.value;
  }
  try {
    S.settings = await api("/api/settings", { method: "PUT", body: out });
    S.models = {}; await refreshStatus(); await loadProviders(); toast("Ajustes guardados ✔"); loadSettings();
  } catch (e) { toast(e.message); }
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); location.href = "/"; });

// --- Arranque --------------------------------------------------------------------------
async function init() {
  if (location.search.includes("token=")) history.replaceState(null, "", "/");
  try { await refreshStatus(); await api("/api/conversations"); } catch { return; }
  await loadProviders();
  await loadConversations();
  const last = store.get("conv", null);
  if (last) await openConversation(last).catch(newChat); else newChat();
  api("/api/onboarding").then((o) => { if (o.needed) openWizard(); }).catch(() => {});
  setView(store.get("view", "chat"));
  renderActiveTools(); setSending(false);
  setInterval(refreshStatus, 8000);
}
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("/sw.js").catch(() => {});
init();
