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
      out += `<pre><button class="copy">copiar</button><code data-lang="${esc(fence[1])}">${esc(buf.join("\n"))}</code></pre>`;
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
function setView(v) {
  S.view = v;
  $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
  $("#menu-btn").style.visibility = v === "chat" ? "visible" : "hidden";
  if (v === "models") refreshModels();
  if (v === "files") loadFiles(S.filesPath);
  if (v === "settings") loadSettings();
  store.set("view", v);
}
$$(".tabs button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$("#menu-btn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
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
async function loadProviders() {
  S.providers = await api("/api/providers");
  const sel = $("#model-select"), prev = store.get("model", "local::local");
  sel.innerHTML = "";
  updateAutoTitle();
  const local = h("optgroup", { label: "Local (llama.cpp)" });
  const lm = S.status?.llama?.model;
  local.append(h("option", { value: "local::local" }, lm ? `💻 ${lm}` : "💻 Modelo local (cárgalo en Modelos)"));
  sel.append(local);
  for (const p of S.providers.filter((p) => !["local", "auto"].includes(p.id) && p.enabled)) {
    const g = h("optgroup", { label: p.name });
    let models = S.models[p.id];
    if (!models) {
      try { models = S.models[p.id] = await api(`/api/providers/${p.id}/models`); }
      catch (e) { models = []; toast(`${p.name}: ${e.message}`); }
    }
    for (const m of models) g.append(h("option", { value: `${p.id}::${m}` }, `☁ ${m}`));
    if (!models.length) g.append(h("option", { disabled: true }, "(sin modelos — revisa la clave API)"));
    sel.append(g);
  }
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
}
$("#model-select").addEventListener("change", (e) => store.set("model", e.target.value));
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
$("#auto-toggle").addEventListener("change", (e) => { store.set("auto", e.target.checked); updateAutoTitle(); });
if (matchMedia("(pointer: coarse)").matches) $("#input").placeholder = "Escribe un mensaje…";
$("#web-toggle").checked = store.get("web", false);
$("#web-toggle").addEventListener("change", (e) => store.set("web", e.target.checked));
$("#tools-toggle").checked = store.get("tools", false);
$("#tools-toggle").addEventListener("change", (e) => store.set("tools", e.target.checked));

// --- Conversaciones -------------------------------------------------------------------
async function loadConversations() {
  const list = await api("/api/conversations"), ul = $("#conv-list");
  ul.innerHTML = "";
  for (const c of list) {
    const li = h("li", { class: c.id === S.convId ? "active" : "", onclick: () => openConversation(c.id) },
      h("span", { class: "t", title: c.title }, c.title),
      h("span", { class: "acts" },
        h("button", { title: "Renombrar", onclick: async (e) => {
          e.stopPropagation();
          const t = prompt("Nuevo título", c.title);
          if (t) { await api(`/api/conversations/${c.id}`, { method: "PATCH", body: { title: t } }); loadConversations(); }
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
    if ([...$("#model-select").options].some((o) => o.value === v)) $("#model-select").value = v;
  }
  renderMessages(); loadConversations();
  $("#sidebar").classList.remove("open");
}
function newChat() {
  S.convId = null; S.conv = null; S.system = undefined; store.set("conv", null);
  renderMessages(); loadConversations(); $("#sidebar").classList.remove("open"); $("#input").focus();
}
$("#new-chat").addEventListener("click", newChat);

// --- Mensajes -----------------------------------------------------------------------
function renderMessages() {
  const box = $("#messages"); box.innerHTML = "";
  const msgs = S.conv?.messages || [];
  if (!msgs.length) {
    box.append(h("div", { class: "empty-state" }, h("h2", {}, "¿En qué te ayudo?"),
      h("p", {}, "Elige un modelo abajo. Los modelos locales se descargan y cargan en ", h("b", {}, "Modelos"), ".")));
    return;
  }
  for (const m of msgs) box.append(messageEl(m));
  box.scrollTop = box.scrollHeight;
}
function approvalCard(a) {
  const args = a.args || {};
  const what = a.name === "run_command" ? h("pre", {}, (args.cwd ? `[${args.cwd}] ` : "") + "$ " + args.command)
    : a.name === "edit_file" ? h("pre", {}, `${args.path}\n--- antes\n${args.old_text}\n+++ después\n${args.new_text}`)
    : a.name === "write_file" ? h("pre", {}, `${args.path}\n\n${String(args.content || "").slice(0, 3000)}`)
    : h("pre", {}, JSON.stringify(args, null, 2));
  const title = { run_command: "ejecutar un comando", edit_file: "editar un archivo", write_file: "escribir un archivo" }[a.name] || a.name;
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
      att.filter((a) => !imgs.includes(a)).map((a) => h("span", { class: "chip" }, (a.kind === "document" || a.kind === "pdf_scan" ? "📄 " : "📎 ") + a.name)),
      h("button", { onclick: () => editFrom(m) }, "✎ editar")));
  } else {
    el.append(assistantInner(m.content, m.reasoning, m.meta?.tools, false, { images: m.meta?.images || [] }));
    const st = m.meta?.stats || {};
    el.append(h("div", { class: "meta" },
      h("span", { title: m.meta?.route || "" }, (m.meta?.provider === "local" ? "💻 " : "☁ ") + (m.meta?.model || "")),
      m.meta?.route ? h("span", {}, "🔀 " + m.meta.route) : null,
      st.tokens_per_second ? h("span", {}, `${st.tokens_per_second.toFixed(1)} tok/s`) : null,
      st.tokens ? h("span", {}, `${st.tokens} tokens`) : null,
      h("button", { onclick: () => { navigator.clipboard?.writeText(m.content); toast("Copiado"); } }, "⧉ copiar"),
      h("button", { onclick: () => regenerate(m) }, "↻ regenerar")));
  }
  return el;
}
$("#messages").addEventListener("click", (e) => {
  if (e.target.classList.contains("copy")) {
    navigator.clipboard?.writeText(e.target.nextElementSibling.textContent); toast("Código copiado");
  }
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
  $("#send-btn").textContent = "Detener"; $("#send-btn").classList.add("danger");
  let content = "", reasoning = "", tools = [], errorMsg = null, raf = 0;
  const extra = { route: null, fallbacks: [], images: [] };
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
    $("#send-btn").textContent = "Enviar"; $("#send-btn").classList.remove("danger");
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
      : h("p", {}, h("b", {}, "Falta el motor llama.cpp."), " En la Konkr se instala con ./install.sh (compilado para su CPU). En PC puedes descargarlo ya compilado:"));
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
$("#hub-search").addEventListener("submit", (e) => { e.preventDefault(); hubSearch($("#hub-q").value); });
$$(".suggestions [data-q]").forEach((b) => b.addEventListener("click", () => { $("#hub-q").value = b.dataset.q; hubSearch(b.dataset.q); }));
async function hubSearch(q) {
  const ul = $("#hub-results"); ul.innerHTML = ""; ul.append(h("li", { class: "muted" }, "Buscando…"));
  try {
    const res = await api("/api/hub/search?" + qs({ q }));
    ul.innerHTML = "";
    if (!res.length) ul.append(h("li", { class: "muted" }, "Sin resultados."));
    for (const r of res) {
      const files = h("div", { class: "repo-files hidden" });
      ul.append(h("li", {},
        h("div", { class: "name" }, r.id, h("div", { class: "sub" }, `⬇ ${r.downloads.toLocaleString()} · ♥ ${r.likes}`)),
        h("button", { class: "ghost small", onclick: () => toggleRepo(r.id, files) }, "Ver archivos"), files));
    }
  } catch (e) { ul.innerHTML = ""; ul.append(h("li", { class: "error" }, e.message)); }
}
async function toggleRepo(repo, box) {
  if (!box.classList.contains("hidden")) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden"); box.innerHTML = "Cargando…";
  try {
    const groups = await api("/api/hub/files?" + qs({ repo }));
    box.innerHTML = "";
    const projs = groups.filter((g) => g.mmproj);
    const proj = projs.find((g) => /f16/i.test(g.name)) || projs[0];
    if (proj) box.append(h("p", { class: "muted" }, "👁 Este modelo tiene visión: al descargarlo se añade también su proyector (" + proj.name + ")."));
    const ul = h("ul", { class: "list" });
    for (const g of groups) {
      ul.append(h("li", {},
        h("div", { class: "name" }, g.name, h("div", { class: "sub" }, [g.quant, fmtSize(g.size), g.files.length > 1 ? `${g.files.length} partes` : ""].filter(Boolean).join(" · "))),
        g.mmproj ? h("span", { class: "badge" }, "visión") : fitBadge(g.size),
        h("button", { class: "primary small", onclick: async () => {
          await api("/api/hub/download", { method: "POST", body: { repo, files: g.files } });
          if (proj && !g.mmproj) await api("/api/hub/download", { method: "POST", body: { repo, files: proj.files } });
          toast("Descarga iniciada"); refreshDownloads();
        } }, "Descargar")));
    }
    if (!groups.length) ul.append(h("li", { class: "muted" }, "Este repositorio no tiene archivos GGUF."));
    box.append(ul);
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
      const opts = [...$("#model-select").options].filter((o) => o.value && !o.disabled).map((o) => [o.value, o.textContent]);
      if (key === "vision_fallback") opts.unshift(["", "Automático (el modelo local si tiene visión)"]);
      if (v && !opts.some((o) => o[0] === v)) opts.push([v, v + " (no disponible ahora)"]);
      inp = selectEl(key, v, opts);
    }
    else inp = h("input", { type, name: key, value: v ?? "", step: type === "number" ? "any" : null });
    f.append(h("label", {}, label), inp);
    if (hint) f.append(h("div", { class: "hint" }, hint));
  }
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
  setInterval(refreshStatus, 8000);
}
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("/sw.js").catch(() => {});
init();
