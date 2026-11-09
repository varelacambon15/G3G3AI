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
  $$("[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
  $("#top-title").textContent = v === "chat" ? (S.conv?.title || "") : { models: "Modelos", files: "Archivos", settings: "Ajustes" }[v];
  closeSide();
  if (v === "models") refreshModels();
  if (v === "files") loadFiles(S.filesPath);
  if (v === "settings") loadSettings();
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
  MS.catalog = [{ value: "local::local", label: lm ? `💻 ${lm}` : "💻 Modelo local (cárgalo en Modelos)", group: "Local (llama.cpp)", pid: "local" }];
  const empty = [];
  for (const p of S.providers.filter((p) => !["local", "auto"].includes(p.id) && p.enabled)) {
    let models = S.models[p.id];
    if (!models) {
      try { models = S.models[p.id] = await api(`/api/providers/${p.id}/models`); }
      catch (e) { models = []; toast(`${p.name}: ${e.message}`); }
    }
    if (!models.length) empty.push(p.name);
    for (const m of models) MS.catalog.push({ value: `${p.id}::${m}`, label: `☁ ${m}`, group: p.name, pid: p.id });
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
$("#tools-toggle").checked = store.get("tools", false);
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
function renderActiveTools() {
  const box = $("#active-tools"); box.innerHTML = "";
  const items = [["auto-toggle", "🔀 Auto"], ["web-toggle", "🌐 Web"], ["tools-toggle", "🛠 Agente"]];
  let any = false;
  for (const [id, label] of items) {
    if (!$("#" + id).checked) continue;
    any = true;
    box.append(h("span", { title: "Pulsa para desactivar", onclick: () => { $("#" + id).checked = false; $("#" + id).dispatchEvent(new Event("change")); } }, label + " ✕"));
  }
  $("#tools-btn").classList.toggle("on", any);
}
["auto-toggle", "web-toggle", "tools-toggle"].forEach((id) => $("#" + id).addEventListener("change", renderActiveTools));

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
  renderMessages(); loadConversations();
  if (S.view === "chat") $("#top-title").textContent = S.conv.title;
  closeSide();
}
function newChat() {
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
      ["📄 Resume un documento", "Resume el documento que te adjunto en 5 puntos clave.", "attach"],
      ["🌐 Busca en la web", "Busca las últimas novedades sobre ", "web"],
      ["🎨 Crea una imagen", "/imagen ", null],
      ["🎮 Arreglar un juego", "El juego … no arranca (o va mal). Diagnostica qué le pasa y propón cómo arreglarlo.", "agent"],
      ["📗 Crear un Excel", "Crea un Excel con ", "agent"],
      ["💡 Explícame algo", "Explícame de forma sencilla cómo funciona ", null],
    ];
    box.append(h("div", { class: "empty-state" },
      h("h1", { class: "greeting" }, h("span", { class: "logo" }, "✦"), hello),
      h("p", {}, S.status?.llama?.model ? "Modelo local listo: " + S.status.llama.model : "Elige un modelo abajo o carga uno local en Modelos."),
      h("div", { class: "suggest" }, ideas.map(([label, text, mode]) => h("button", { onclick: () => {
        input.value = text; input.focus(); input.dispatchEvent(new Event("input"));
        if (mode === "web") { $("#web-toggle").checked = true; $("#web-toggle").dispatchEvent(new Event("change")); }
        if (mode === "agent") { $("#tools-toggle").checked = true; $("#tools-toggle").dispatchEvent(new Event("change")); }
        if (mode === "attach") $("#attach-btn").click();
      } }, label)))));
    return;
  }
  for (const m of msgs) box.append(messageEl(m));
  box.scrollTop = box.scrollHeight;
}
function approvalCard(a) {
  const args = a.args || {};
  const what = a.name === "build_exe" ? h("pre", {}, `${args.script}` + (args.packages?.length ? `\npaquetes: ${args.packages.join(", ")}` : "") + (args.windowed ? "\n(con ventana)" : ""))
    : a.name === "run_command" ? h("pre", {}, (args.cwd ? `[${args.cwd}] ` : "") + "$ " + args.command)
    : a.name === "edit_file" ? h("pre", {}, `${args.path}\n--- antes\n${args.old_text}\n+++ después\n${args.new_text}`)
    : a.name === "write_file" || a.name === "create_document" ? h("pre", {}, `${args.path}\n\n${String(args.content || "").slice(0, 3000)}`)
    : h("pre", {}, JSON.stringify(args, null, 2));
  const title = { run_command: "ejecutar un comando", edit_file: "editar un archivo", write_file: "escribir un archivo", build_exe: "compilar un programa",
    create_document: "crear un documento", git_commit: "crear un commit de git" }[a.name] || a.name;
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
      a.can_always !== false ? h("button", { class: "ghost small", title: "No volver a preguntar por esta herramienta en esta conversación (salvo acciones peligrosas)", onclick: () => answer("always") }, "Permitir siempre aquí") : null,
      h("button", { class: "danger small", onclick: () => answer("no") }, "Denegar")));
  }
  return card;
}
function assistantInner(content, reasoning, tools, streaming, extra = {}) {
  const frag = document.createDocumentFragment();
  if (extra.compacted) frag.append(h("div", { class: "route" }, `🗜 Se resumieron ${extra.compacted} mensajes antiguos para que la conversación quepa en el contexto`));
  if (extra.status && streaming) frag.append(h("div", { class: "route" }, extra.status));
  if (extra.route) frag.append(h("div", { class: "route" }, `🔀 ${extra.route.provider === "local" ? "💻" : "☁"} ${extra.route.model}` + (extra.route.reason ? ` — ${extra.route.reason}` : "")));
  for (const f of extra.fallbacks || []) frag.append(h("div", { class: "route warn" }, "↪ falló " + f + ", probando el otro modelo…"));
  const { think, body, open } = splitThink(content || "");
  const r = [reasoning, think].filter(Boolean).join("\n");
  if (r) frag.append(h("details", { open: streaming && (open || !body) ? true : false }, h("summary", {}, "💭 Razonamiento"), h("pre", {}, r)));
  for (const t of tools || []) {
    if (t.name && t.name.startsWith("memory_")) {
      if (t.type === "tool_call") {
        let a = {}; try { a = JSON.parse(t.args || "{}"); } catch { /* */ }
        frag.append(h("div", { class: "memory-note", title: "Gestiona la memoria en Ajustes → Memoria" },
          t.name === "memory_save" ? `💾 Recordado: ${a.content || ""}` : `🗑 Olvidado el recuerdo ${a.id}`));
      } else if (/^No guardado|^Error/.test(t.result || "")) frag.append(h("div", { class: "memory-note warn" }, t.result));
      continue;
    }
    if (t.type === "tool_call") frag.append(h("details", { class: "tool" }, h("summary", {}, `🔧 ${t.name}`), h("pre", {}, t.args)));
    else if (t.type === "approval") frag.append(approvalCard(t));
    else if (t.type === "tool_result") frag.append(h("details", { class: "tool" }, h("summary", {}, `↳ resultado de ${t.name}`), h("pre", {}, t.result)));
  }
  const b = h("div", { class: "bubble" + (streaming ? " cursor" : "") });
  b.innerHTML = md(body);
  frag.append(b);
  const fileIcon = (p) => ({ docx: "📘", doc: "📘", xlsx: "📗", xlsm: "📗", csv: "📗", pptx: "📙", pdf: "📕", exe: "⚙️", py: "🐍" }[String(p).split(".").pop().toLowerCase()] || "📄");
  const outs = [...new Set(extra.files || [])];
  if (outs.length) frag.append(h("div", { class: "file-cards" }, outs.map((p) => fileCard(p, fileIcon(p)))));
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
      att.filter((a) => !imgs.includes(a)).map((a) => h("span", { class: "chip" }, (a.kind === "folder" ? "📁 " : a.kind === "document" || a.kind === "pdf_scan" ? "📄 " : "📎 ") + a.name)),
      h("button", { class: "act", title: "Copiar", onclick: () => { copyText(m.content); } }, "⧉"),
      h("button", { class: "act", title: "Editar", onclick: () => editFrom(m) }, "✎")));
  } else {
    el.append(assistantInner(m.content, m.reasoning, m.meta?.tools, false, { images: m.meta?.images || [], files: m.meta?.files || [] }));
    const st = m.meta?.stats || {};
    el.append(h("div", { class: "meta" },
      h("button", { class: "act", title: "Copiar", onclick: () => { copyText(m.content); } }, "⧉"),
      h("button", { class: "act", title: "Volver a generar", onclick: () => regenerate(m) }, "↻"),
      h("span", { title: m.meta?.route || "" }, (m.meta?.provider === "local" ? "💻 " : m.meta?.provider === "imagen" ? "🎨 " : "☁ ") + (m.meta?.model || "")),
      m.meta?.route ? h("span", {}, "🔀 " + m.meta.route) : null,
      st.tokens_per_second ? h("span", {}, `${st.tokens_per_second.toFixed(1)} tok/s`) : null));
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
  b.textContent = on ? "■" : "↑"; b.classList.toggle("stop", on);
  b.title = on ? "Detener" : "Enviar"; b.dataset.state = on ? "sending" : "idle";
}
const input = $("#input");
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && !matchMedia("(pointer: coarse)").matches) {
    e.preventDefault(); $("#send-btn").click();
  }
});
$("#send-btn").addEventListener("click", () => {
  if (S.streaming) { S.streaming.abort(); return; }
  const text = input.value.trim();
  if (!text && !S.attachments.length) return;
  const att = S.attachments.map((a) => a.path);
  input.value = ""; input.style.height = "auto"; S.attachments = []; renderAttachments();
  send(text, att);
});

async function send(text, attachments, isContinue = false) {
  const { provider, model } = currentModel();
  const box = $("#messages");
  if (!S.conv?.messages?.length) box.innerHTML = "";
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
  const extra = { route: null, fallbacks: [], images: [], files: [] };
  const paint = () => {
    raf = 0;
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    el.innerHTML = ""; el.append(assistantInner(content, reasoning, tools, true, extra));
    if (stick) box.scrollTop = box.scrollHeight;
  };
  try {
    const body = { conversation_id: S.convId, message: text, attachments, provider, model,
      use_tools: $("#tools-toggle").checked, use_web: $("#web-toggle").checked, continue: isContinue };
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
        else if (ev.type === "tool_call" || ev.type === "tool_result") tools.push(ev);
        else if (ev.type === "approval") { tools.push(ev); notifyApproval(ev); }
        else if (ev.type === "approval_result") { const a = tools.find((t) => t.id === ev.id); if (a) a.state = ev.approved ? "approved" : "denied"; }
        else if (ev.type === "route") extra.route = ev;
        else if (ev.type === "status") extra.status = ev.text;
        else if (ev.type === "image") extra.images.push(ev.path);
        else if (ev.type === "file") extra.files.push(ev.path);
        else if (ev.type === "compacted") extra.compacted = ev.messages;
        else if (ev.type === "route_fallback") extra.fallbacks.push(ev.message);
        else if (ev.type === "error") errorMsg = ev.message;
        if (!raf) raf = requestAnimationFrame(paint);
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") errorMsg = e.message;
  } finally {
    S.streaming = null;
    setSending(false);
    if (errorMsg) toast("Error: " + errorMsg, 7000);
    if (S.convId) { await new Promise((r) => setTimeout(r, 150)); await openConversation(S.convId).catch(() => {}); }
    else el.remove();
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
// --- Archivos generados por la IA: «Guardar» (diálogo) + menú con flecha (Abrir, Guardar como…, Mostrar en carpeta) ---
async function saveGenerated(path) {
  const name = baseName(path);
  try {
    if (window.pywebview?.api?.save_file) {              // ventana de escritorio: diálogo nativo
      const r = await window.pywebview.api.save_file(path, name);
      if (r?.ok) toast("Guardado en " + r.path, 5000);
      else if (!r?.cancelled) toast("No se pudo guardar: " + (r?.error || "error desconocido"), 5000);
      return;
    }
    if (window.showSaveFilePicker) {                      // navegadores con File System Access
      const ext = (name.match(/\.[^.]+$/) || [""])[0];
      const fh = await window.showSaveFilePicker({ suggestedName: name,
        types: ext ? [{ description: ext.slice(1).toUpperCase(), accept: { "application/octet-stream": [ext] } }] : undefined });
      const res = await fetch("/api/files/download?" + qs({ path }));
      if (!res.ok) throw new Error(res.statusText);
      const w = await fh.createWritable(); await w.write(await res.blob()); await w.close();
      toast("Guardado ✔"); return;
    }
    const a = h("a", { href: "/api/files/download?" + qs({ path }), download: name }); document.body.append(a); a.click(); a.remove();
  } catch (e) { if (e?.name !== "AbortError") toast("No se pudo guardar: " + (e.message || e), 5000); }
}
async function openGenerated(path, reveal = false) {
  try { await api("/api/files/open", { method: "POST", body: { path, reveal } }); }
  catch (e) { toast(e.message, 5000); }
}
function fileCard(path, icon) {
  const menu = h("div", { class: "popover file-menu hidden" },
    h("button", { onclick: () => openGenerated(path) }, h("span", { class: "ico" }, "↗"), "Abrir"),
    h("button", { onclick: () => saveGenerated(path) }, h("span", { class: "ico" }, "💾"), "Guardar como…"),
    h("button", { onclick: () => openGenerated(path, true) }, h("span", { class: "ico" }, "📂"), "Mostrar en carpeta"),
    h("button", { onclick: () => navigator.clipboard?.writeText(path).then(() => toast("Ruta copiada")) }, h("span", { class: "ico" }, "📋"), "Copiar ruta"));
  const arrow = h("button", { class: "fc-arrow", title: "Más opciones", "aria-label": "Más opciones", onclick: (e) => {
    e.stopPropagation(); const open = menu.classList.contains("hidden");
    $$(".popover").forEach((p) => p.classList.add("hidden")); menu.classList.toggle("hidden", !open);
  } }, "▾");
  menu.addEventListener("click", () => menu.classList.add("hidden"));
  return h("div", { class: "file-card", title: path },
    h("span", { class: "fi" }, icon),
    h("span", { class: "fn" }, baseName(path), h("small", {}, "Documento generado")),
    h("div", { class: "split" },
      h("button", { class: "fc-main", onclick: () => saveGenerated(path) }, "Guardar"), arrow, menu));
}
function renderAttachments() {
  const c = $("#attachments"); c.innerHTML = "";
  S.attachments.forEach((a, i) => c.append(h("span", { class: "chip" },
    isImage(a.name) ? h("img", { class: "thumb", src: fileUrl(a.path), alt: "" }) : (a.dir ? "📁 " : "📎 "), a.name,
    h("button", { onclick: () => { S.attachments.splice(i, 1); renderAttachments(); } }, "✕"))));
}
function addAttachment(path, dir = false) {
  if (!S.attachments.some((a) => a.path === path)) S.attachments.push({ path, name: baseName(path), dir });
  renderAttachments();
}
// Con una carpeta adjunta, la IA necesita herramientas para leerla/modificarla: sugerir el modo Agente.
function enableAgentHint() {
  if ($("#tools-toggle").checked) return;
  $("#tools-toggle").checked = true; $("#tools-toggle").dispatchEvent(new Event("change"));
  toast("🛠 Modo Agente activado para que la IA pueda trabajar con la carpeta", 4000);
}
// Adjuntar una ruta escrita a mano (archivo o carpeta del equipo)
async function attachPath(raw) {
  const p = raw.trim().replace(/^["'`@]+|["'`]+$/g, "");
  if (!p) return false;
  try {
    const d = await api("/api/files/list?" + qs({ path: p }));
    addAttachment(d.path, true); enableAgentHint(); return true;
  } catch { /* no es carpeta: probar como archivo */ }
  try {
    const f = await api("/api/files/read?" + qs({ path: p }));
    addAttachment(f.path); return true;
  } catch { /* puede ser binario (docx, pdf, imagen): probar la descarga */ }
  try {
    const r = await fetch("/api/files/download?" + qs({ path: p, inline: true }), { headers: { Range: "bytes=0-0" } });
    r.body?.cancel?.();
    if (r.ok) { addAttachment(p); return true; }
  } catch { /* */ }
  toast("No encuentro esa ruta o está fuera de las carpetas permitidas (Ajustes → Carpetas visibles)", 4500);
  return false;
}
const looksLikePath = (t) => /^\s*["'`@]?(~[\\/]|\/|[A-Za-z]:[\\/]|\\\\)[^\n]*$/.test(t) && t.trim().length < 400;
$("#path-btn").addEventListener("click", async () => {
  const p = prompt("Ruta de un archivo o carpeta del equipo (p. ej. ~/proyectos/mi-app):");
  if (p) await attachPath(p);
});
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
// Arrastrar y soltar archivos en cualquier punto de la ventana:
//  - vista Chat (o selector de adjuntos): se suben y se adjuntan al mensaje
//  - vista Archivos: se suben a la carpeta que se está viendo
const composer = $(".composer");
const dropOverlay = h("div", { id: "drop-overlay", class: "hidden" }, h("div", {}, "📎 Suelta aquí los archivos"));
document.body.append(dropOverlay);
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
let dragDepth = 0;
function endDrag() { dragDepth = 0; dropOverlay.classList.add("hidden"); composer.classList.remove("drop"); }
function dropHint() {
  const files = S.view === "files";
  dropOverlay.firstChild.textContent = files ? "⬆ Suelta para subir a esta carpeta" : "📎 Suelta aquí para adjuntar al chat";
  return files || S.view === "chat";
}
window.addEventListener("dragenter", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault(); dragDepth++;
  if (dropHint()) { dropOverlay.classList.remove("hidden"); composer.classList.add("drop"); }
});
window.addEventListener("dragover", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault(); e.dataTransfer.dropEffect = "copy";
});
window.addEventListener("dragleave", (e) => {
  if (!hasFiles(e)) return;
  if (--dragDepth <= 0) endDrag();
});
// Recorre lo soltado (archivos y carpetas). Debe empezar de forma síncrona: tras un await el DataTransfer se vacía.
const SKIP_DIRS = new Set([".git", "node_modules", "__pycache__", ".venv", "venv"]);
const MAX_DROP_FILES = 500;
const readAll = (reader) => new Promise((ok, ko) => {
  const acc = [];
  const next = () => reader.readEntries((b) => (b.length ? (acc.push(...b), next()) : ok(acc)), ko);
  next();
});
async function walkEntry(entry, prefix, out) {
  if (out.length >= MAX_DROP_FILES) return;
  if (entry.isFile) {
    const file = await new Promise((ok, ko) => entry.file(ok, ko));
    out.push({ file, rel: prefix + entry.name });
  } else if (entry.isDirectory && !SKIP_DIRS.has(entry.name)) {
    for (const c of await readAll(entry.createReader())) await walkEntry(c, prefix + entry.name + "/", out);
  }
}
async function collectDropped(dt) {
  const entries = [...(dt.items || [])].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.length) return { files: [...dt.files].map((f) => ({ file: f, rel: f.name })), folders: [] };
  const files = [], folders = [];
  for (const en of entries) {
    if (en.isDirectory) folders.push(en.name);
    await walkEntry(en, "", files);
  }
  return { files, folders };
}
// Sube lo recogido; las carpetas conservan su estructura. Devuelve las rutas de nivel superior.
async function uploadDropped(items, folders, dir) {
  const tops = [];
  const sub = (r) => r.includes("/") ? r : "";
  let n = 0;
  for (const { file, rel } of items) {
    const fd = new FormData(); fd.append("dir", dir || ""); fd.append("file", file);
    if (sub(rel)) fd.append("relpath", rel);
    try {
      const r = await api("/api/files/upload", { method: "POST", body: fd });
      n++;
      if (!sub(rel)) tops.push(r.path);
    } catch (e) { toast(`${rel}: ${e.message}`); }
  }
  for (const f of folders) tops.push(joinPath(dir, f));
  return { tops, n };
}
window.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault(); endDrag();
  if (S.view !== "files" && S.view !== "chat") { toast("Ve a Chat o Archivos para soltar documentos"); return; }
  const view = S.view, pending = collectDropped(e.dataTransfer); // síncrono: captura el DataTransfer
  (async () => {
    const { files, folders } = await pending;
    if (!files.length && !folders.length) { toast("No hay nada que subir"); return; }
    if (files.length >= MAX_DROP_FILES) toast(`Carpeta muy grande: se suben los primeros ${MAX_DROP_FILES} archivos`, 4000);
    toast("Subiendo…", 1500);
    const dir = view === "files" ? S.filesPath : await uploadsDir();
    const { tops, n } = await uploadDropped(files, folders, dir);
    if (view === "files") { if (n) toast(`${n} archivo(s) subido(s)`); loadFiles(S.filesPath); }
    else { if ($("#picker").open) $("#picker").close(); tops.forEach(addAttachment); if (folders.length) enableAgentHint(); }
  })();
});
input.addEventListener("paste", (e) => {
  const imgs = [...(e.clipboardData?.files || [])];
  if (imgs.length) { e.preventDefault(); attachLocalFiles(imgs); return; }
  const t = e.clipboardData?.getData("text") || "";
  if (looksLikePath(t) && !input.value.trim()) {
    e.preventDefault();
    attachPath(t).then((ok) => { if (!ok) { input.value = t; input.dispatchEvent(new Event("input")); } });
  }
});
$("#picker-folder").addEventListener("click", () => { addAttachment(S.pickerPath, true); enableAgentHint(); $("#picker").close(); });
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
  $("#system-text").value = cur || ""; $("#system-dialog").showModal();
});
$("#system-save").addEventListener("click", async () => {
  S.system = $("#system-text").value;
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { system: S.system } });
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
      ? h("p", {}, h("b", {}, "Motor de imágenes (stable-diffusion.cpp)."), " En la Konkr: ./install.sh --with-sd. En PC puedes descargarlo ya compilado:")
      : h("p", {}, h("b", {}, "Falta el motor llama.cpp."), " En la Konkr se instala con ./install.sh (compilado para su CPU). En PC puedes descargarlo ya compilado:",
        h("br"), h("span", { class: "muted" }, "Si usas Ollama no lo necesitas: descarga un modelo en la tarjeta de Ollama y elígelo en el selector del chat.")));
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
const CAP_BADGE = { vision: "👁 visión", code: "🧑‍💻 código", reasoning: "🧠 razonamiento", image: "🎨 imágenes" };

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
  ["sd_max_side", "🎨 Local: tamaño máximo (px)", "number", "En la Konkr, 512 es razonable; más grande tarda mucho más."],
  ["router_mode", "Modo Auto: estrategia", "router"],
  ["router_fast", "Modo Auto: modelo rápido", "model", "Normalmente el local (gratis, privado)."],
  ["router_strong", "Modo Auto: modelo potente", "model", "Normalmente una API (DeepSeek, Claude…). Se usa para código, análisis, documentos largos y el modo agente."],
  ["default_system_prompt", "Instrucciones del sistema", "textarea"],
  ["temperature", "Temperatura", "number", "0 = preciso · 1 = creativo"],
  ["max_tokens", "Máx. tokens por respuesta", "number"],
  ["models_dir", "Carpeta de modelos", "text"],
  ["llama_server_path", "Ruta de llama-server", "text", "Vacío = autodetectar (~/.local/share/g3g3ai/llama.cpp)"],
  ["llama_ctx", "Contexto por defecto", "number", "Más contexto = más RAM. 8192 es razonable con 8 GB."],
  ["llama_threads", "Hilos (0 = auto)", "number"],
  ["llama_gpu_layers", "Capas en GPU", "number", "Sólo si compilaste llama.cpp con Vulkan (Adreno)."],
  ["llama_extra_args", "Argumentos extra de llama-server", "text", "p.ej. --flash-attn on --cache-type-k q8_0"],
  ["autoload_last_model", "Cargar el último modelo al arrancar", "checkbox"],
  ["file_roots", "Carpetas visibles (una por línea)", "lines", "La interfaz y la IA sólo pueden ver (leer) estas carpetas."],
  ["ai_write", "Agente: escribir/editar archivos", "perm"],
  ["ai_commands", "Agente: ejecutar comandos", "perm", "«Preguntar» muestra cada acción para que la apruebes (también desde el móvil). Con aislamiento activo, los comandos sólo pueden escribir en las carpetas modificables; sin él, siempre se pide confirmación. Los comandos peligrosos se bloquean."],
  ["agent_workdir", "Carpeta de trabajo del agente", "text", "Debe estar dentro de las carpetas que la IA puede modificar."],
  ["ai_game_write", "🎮 La IA puede trabajar con los juegos de Steam", "checkbox", "Lee y, pidiendo permiso cada vez, modifica las carpetas de los juegos y sus prefijos de Proton. Antes de cambiar un archivo guarda una copia «.g3g3ai-original»."],
  ["write_roots", "Carpetas que la IA puede modificar (una por línea)", "lines", "Añade aquí tus proyectos. Fuera de estas carpetas la IA sólo puede leer."],
  ["blocked_paths", "Rutas protegidas (una por línea)", "lines", "Nadie puede verlas desde G3G3AI, ni la IA ni la interfaz. Sin barra = patrón de nombre (p.ej. .env, *.pem)."],
  ["command_sandbox", "Aislamiento de comandos", "sandbox"],
  ["web_provider", "Búsqueda web: proveedor", "webprov", "DuckDuckGo no necesita clave pero a veces bloquea. Brave y Tavily tienen plan gratuito y son más fiables."],
  ["web_api_key", "Búsqueda web: clave API", "password", "Sólo para Brave o Tavily."],
  ["hf_token", "Token de Hugging Face (opcional)", "password", "Sólo para modelos restringidos."],
  ["localhost_without_token", "El propio Konkr entra sin contraseña", "checkbox"],
  ["port", "Puerto", "number", "Requiere reiniciar el servicio."],
];
async function loadSettings() {
  S.settings = await api("/api/settings");
  await refreshStatus();
  const st = S.status, acc = $("#access-info"); acc.innerHTML = "";
  acc.append(h("p", {}, "Conecta el móvil o portátil a la misma red Wi-Fi y abre:"));
  for (const u of st.urls) acc.append(h("code", { class: "access-url" }, st.token ? `${u}/?token=${st.token}` : u));
  if (!st.urls.length) acc.append(h("p", { class: "muted" }, "No se detectó ninguna IP de red local."));
  acc.append(h("p", {}, "Contraseña: ", st.token ? h("code", {}, st.token) : h("span", { class: "muted" }, "(sólo visible desde el propio Konkr)")));
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
    else if (type === "webprov") inp = selectEl(key, v, [["duckduckgo", "DuckDuckGo (sin clave)"], ["brave", "Brave Search (clave)"], ["tavily", "Tavily (clave)"]]);
    else if (type === "router") inp = selectEl(key, v, [["smart", "Inteligente (según la tarea)"], ["local_first", "Local primero"], ["api_first", "API primero"]]);
    else if (type === "model") {
      const opts = MS.catalog.map((m) => [m.value, `${m.label} · ${m.group}`]);  // todos, también los ocultos
      if (key === "vision_fallback") opts.unshift(["", "Automático (el modelo local si tiene visión)"]);
      if (v && !opts.some((o) => o[0] === v)) opts.push([v, v + " (no disponible ahora)"]);
      inp = selectEl(key, v, opts);
    }
    else inp = h("input", { type, name: key, value: v ?? "", step: type === "number" ? "any" : null });
    f.append(h("label", {}, label), inp);
    if (hint) f.append(h("div", { class: "hint" }, hint));
  }
}
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
  box.append(h("p", { class: "muted" }, "Pon la misma clave en todos tus equipos con G3G3AI (Konkr, PC…) y añade la dirección del otro. "
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
$("#add-provider").addEventListener("click", () => {
  const kind = prompt("¿Qué quieres añadir?\n1 = Otro equipo con G3G3AI (Konkr ↔ PC)\n2 = Ollama / LM Studio / servidor compatible con OpenAI", "1");
  if (!kind) return;
  let name, url, key = "";
  if (kind.trim() === "1") {
    const ip = prompt("IP o nombre del otro equipo (p.ej. 192.168.1.50 o konkr-pocket-fit.local)"); if (!ip) return;
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
    else if (["perm", "router", "model", "sandbox", "webprov", "imgprov", "imgmode", "imgsize"].includes(type)) out[key] = el.value;
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
  if (last) await openConversation(last).catch(newChat);
  setView(store.get("view", "chat"));
  renderActiveTools(); setSending(false);
  setInterval(refreshStatus, 8000);
}
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("/sw.js").catch(() => {});
init();
