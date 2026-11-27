// G3G3AI · Utilidades, API, Markdown, archivos en el chat, estado, acceso y navegación.
// Parte 1/8 de la interfaz: se cargan en orden y comparten el ámbito global.
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
// --- Archivos en el chat: tarjeta con «Abrir» y una flecha con más opciones ---------------------------
const IS_LOCAL = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
const downloadUrl = (p) => "/api/files/download?" + qs({ path: p });
async function openPath(p, reveal = false) {
  if (!IS_LOCAL) { location.href = downloadUrl(p); return; }       // desde el móvil: se descarga
  try { await api("/api/files/open", { method: "POST", body: { path: p, reveal } }); toast(reveal ? "Abriendo la carpeta…" : "Abriendo " + baseName(p) + "…", 2500); }
  catch (e) { toast(e.message, 6000); }
}
function fileMenu(p, anchor) {
  $("#file-menu")?.remove();
  const item = (icon, label, fn) => h("button", { onclick: () => { menu.remove(); fn(); } }, ico(icon), label);
  const menu = h("div", { id: "file-menu", class: "file-menu" },
    IS_LOCAL ? item("file", "Abrir", () => openPath(p)) : null,
    IS_LOCAL ? item("folder", "Mostrar en la carpeta", () => openPath(p, true)) : null,
    item("download", "Descargar", () => { location.href = downloadUrl(p); }),
    item("copy", "Copiar ruta", () => copyText(p, "Ruta copiada")),
    item("search", "Vista previa", () => previewFile(p)));
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();
  menu.style.top = Math.min(innerHeight - menu.offsetHeight - 8, r.bottom + 4) + "px";
  menu.style.left = Math.max(8, Math.min(innerWidth - menu.offsetWidth - 8, r.right - menu.offsetWidth)) + "px";
  setTimeout(() => document.addEventListener("mousedown", function off(e) { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener("mousedown", off); } }), 0);
}
function fileCard(p) {
  const ext = (String(p).split(".").pop() || "").toUpperCase().slice(0, 4);
  return h("div", { class: "file-card", title: p },
    h("button", { class: "fc-main", onclick: () => openPath(p) },
      h("span", { class: "att-ext", "data-ext": ext }, ext),
      h("span", { class: "fn" }, baseName(p), h("small", {}, IS_LOCAL ? "Abrir" : "Descargar"))),
    h("button", { class: "fc-more", title: "Más opciones", onclick: (e) => fileMenu(p, e.currentTarget) }, "▾"));
}
// Rutas que escribe la IA (`C:\…\informe.xlsx` o enlaces file:///…): clicables, con el mismo menú
const PATH_RX = /^(?:[A-Za-z]:[\\/]|\/(?:home|Users|mnt|tmp|root)\/|~[\\/])[^<>"|?*\n]*\.[A-Za-z0-9]{1,5}$/;
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-path]");
  if (!a || !e.target.closest("#messages")) return;
  e.preventDefault(); fileMenu(a.dataset.path, a);
});
function inlineMd(s) {
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  s = esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/~~(.+?)~~/g, "<del>$1</del>")
    .replace(/\[([^\]]+)\]\(file:\/\/\/?([^)]+)\)/g, (_, t, p) => {
      const path = decodeURIComponent(p).replace(/^\/(?=[A-Za-z]:)/, "");
      return `<a href="#" class="path-link" data-path="${esc(path)}">📄 ${t}</a>`;
    })
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => {
    const c = codes[+i].trim();
    return PATH_RX.test(c) ? `<code class="path-link" data-path="${esc(c)}" title="Abrir / descargar">${esc(codes[+i])}</code>` : `<code>${esc(codes[+i])}</code>`;
  });
}
function md(src) {
  src = src.replace(/\s*<registro_de_herramientas>[\s\S]*?(<\/registro_de_herramientas>|$)/g, "");   // registro interno que el modelo imita
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
      const kind = artKind(lang, buf.join("\n"));
      if (kind && (kind === "mermaid" || buf.length >= 15)) {   // pieza grande o diagrama: tarjeta que se abre al lado
        const code = buf.join("\n"), meta = artMeta(kind, code);
        out += `<div class="art-card" data-kind="${kind}"><span class="art-ico">${ico(meta.icon).outerHTML}</span>`
          + `<span class="art-info"><b>${esc(meta.title)}</b><small>${meta.label} · ${buf.length} líneas</small></span>`
          + `<button class="art-open">Abrir</button><code class="art-code" hidden>${esc(code)}</code></div>`;
        continue;
      }
      const canPreview = !!kind;
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
      const ordered = /^\s*\d/.test(l), start = ordered ? parseInt(l.trim(), 10) : 1; let items = "";
      while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
        let item = lines[i++].replace(/^\s*([-*+]|\d+[.)])\s+/, "");
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) item += " " + lines[i++].trim();
        items += `<li>${inlineMd(item)}</li>`;
      }
      out += ordered ? `<ol${start > 1 ? ` start="${start}"` : ""}>${items}</ol>` : `<ul>${items}</ul>`; continue;
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
// Chats y Code son apartados distintos (como en Claude): cada uno con su lista y su última conversación abierta
const space = () => (S.code ? "code" : "chat");
const convSpace = (c) => (c && c.kind === "code" ? "code" : "chat");
const convKey = (sp = space()) => (sp === "code" ? "conv_code" : "conv");
function setView(v, keepConv = false) {
  S.view = v;
  const real = v === "code" ? "chat" : v;
  const wasCode = !!S.code;
  if (v === "chat" || v === "code") S.code = v === "code";
  else S.code = false;
  document.body.classList.toggle("code-mode", S.code);
  $("#new-chat").lastChild.textContent = S.code ? " Nueva sesión de Code" : " Nueva conversación";
  $("#conv-search").placeholder = S.code ? "Buscar sesiones de Code…" : "Buscar conversaciones…";
  if (!keepConv && (v === "chat" || v === "code") && S.conv && convSpace(S.conv) !== v) openSpaceConv();
  else if (!keepConv && (v === "chat" || v === "code") && !S.conv && wasCode !== S.code) openSpaceConv();
  if (wasCode !== S.code && typeof renderConvList === "function") renderConvList();
  $$("[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + real));
  $("#top-title").textContent = real === "chat" ? (S.conv?.title || (S.code ? "Code" : "")) : { models: "Modelos", team: "Equipo", connectors: "Conectores", tasks: "Tareas", files: "Archivos", settings: "Ajustes", projects: "Proyectos" }[real];
  closeSide();
  if (S.code && !wasCode) enterCode();
  if (real === "models") refreshModels();
  if (real === "files") loadFiles(S.filesPath);
  if (real === "tasks") loadTasks();
  if (real === "projects") renderProjects();
  if (real === "team") loadTeam();
  if (real === "connectors") loadConnectors();
  if (real === "settings") { loadSettings(); if (typeof drawUpdateCard === "function") { drawUpdateCard(); if (!UPD.info) checkUpdate(false, true); } }
  store.set("view", v);
}
// Abre la última conversación del apartado actual (o una nueva si no hay)
function openSpaceConv() {
  const last = store.get(convKey(), null);
  const c = last && convCache.find((x) => x.id === last);
  if (c && convSpace(c) === space()) openConversation(last).catch(newChat); else newChat();
}
$$("[data-view]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$("#menu-btn").addEventListener("click", () => {
  if (isMobile()) document.body.classList.toggle("side-open");
  else { document.body.classList.remove("side-collapsed"); store.set("collapsed", false); }
});
$("#side-collapse").addEventListener("click", () => { document.body.classList.add("side-collapsed"); store.set("collapsed", true); });
$("#scrim").addEventListener("click", closeSide);
$("#top-new").addEventListener("click", () => { setView(S.code ? "code" : "chat", true); newChat(); });
if (store.get("collapsed", false)) document.body.classList.add("side-collapsed");
$$("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
