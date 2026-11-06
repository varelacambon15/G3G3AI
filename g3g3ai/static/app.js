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
  const local = h("optgroup", { label: "Local (llama.cpp)" });
  const lm = S.status?.llama?.model;
  local.append(h("option", { value: "local::local" }, lm ? `💻 ${lm}` : "💻 Modelo local (cárgalo en Modelos)"));
  sel.append(local);
  for (const p of S.providers.filter((p) => p.id !== "local" && p.enabled)) {
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
  const [provider, ...rest] = $("#model-select").value.split("::");
  return { provider, model: rest.join("::") };
}
if (matchMedia("(pointer: coarse)").matches) $("#input").placeholder = "Escribe un mensaje…";
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
    const v = `${S.conv.provider}::${S.conv.model}`;
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
function assistantInner(content, reasoning, tools, streaming) {
  const frag = document.createDocumentFragment();
  const { think, body, open } = splitThink(content || "");
  const r = [reasoning, think].filter(Boolean).join("\n");
  if (r) frag.append(h("details", { open: streaming && (open || !body) ? true : false }, h("summary", {}, "💭 Razonamiento"), h("pre", {}, r)));
  for (const t of tools || []) {
    if (t.type === "tool_call") frag.append(h("details", { class: "tool" }, h("summary", {}, `🔧 ${t.name}`), h("pre", {}, t.args)));
    else frag.append(h("details", { class: "tool" }, h("summary", {}, `↳ resultado de ${t.name}`), h("pre", {}, t.result)));
  }
  const b = h("div", { class: "bubble" + (streaming ? " cursor" : "") });
  b.innerHTML = md(body);
  frag.append(b);
  return frag;
}
function messageEl(m) {
  const el = h("div", { class: `msg ${m.role}`, "data-id": m.id });
  if (m.role === "user") {
    el.append(h("div", { class: "bubble" }, m.content));
    const att = m.meta?.attachments || [];
    el.append(h("div", { class: "meta" },
      att.map((a) => h("span", { class: "chip" }, "📎 " + a.name)),
      h("button", { onclick: () => editFrom(m) }, "✎ editar")));
  } else {
    el.append(assistantInner(m.content, m.reasoning, m.meta?.tools));
    const st = m.meta?.stats || {};
    el.append(h("div", { class: "meta" },
      h("span", {}, m.meta?.model && m.meta.model !== "local" ? m.meta.model : (m.meta?.provider === "local" ? "local" : "")),
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
    const um = { id: 0, role: "user", content: text, meta: { attachments: attachments.map((p) => ({ name: p.split("/").pop(), path: p })) } };
    box.append(messageEl(um));
  }
  const el = h("div", { class: "msg assistant" });
  el.append(h("div", { class: "bubble cursor" }));
  box.append(el); box.scrollTop = box.scrollHeight;

  const ctrl = new AbortController(); S.streaming = ctrl;
  $("#send-btn").textContent = "Detener"; $("#send-btn").classList.add("danger");
  let content = "", reasoning = "", tools = [], errorMsg = null, raf = 0;
  const paint = () => {
    raf = 0;
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    el.innerHTML = ""; el.append(assistantInner(content, reasoning, tools, true));
    if (stick) box.scrollTop = box.scrollHeight;
  };
  try {
    const body = { conversation_id: S.convId, message: text, attachments, provider, model,
      use_tools: $("#tools-toggle").checked, continue: isContinue };
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
        else if (ev.type === "content") content += ev.text;
        else if (ev.type === "reasoning") reasoning += ev.text;
        else if (ev.type === "tool_call" || ev.type === "tool_result") tools.push(ev);
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

// --- Adjuntos --------------------------------------------------------------------------
function renderAttachments() {
  const c = $("#attachments"); c.innerHTML = "";
  S.attachments.forEach((a, i) => c.append(h("span", { class: "chip" }, "📎 " + a.name,
    h("button", { onclick: () => { S.attachments.splice(i, 1); renderAttachments(); } }, "✕"))));
}
function addAttachment(path) {
  if (!S.attachments.some((a) => a.path === path)) S.attachments.push({ path, name: path.split("/").pop() });
  renderAttachments();
}
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
  if (res.length) toast(`Subido a ${res[0].path.replace(/\/[^/]*$/, "")}`);
});
async function uploadsDir() {
  // Los archivos subidos desde el móvil se guardan en ~/G3G3AI-subidas
  const roots = await api("/api/files/roots");
  const dir = roots[0] + "/G3G3AI-subidas";
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
  if (!l.binary) box.append(h("p", { class: "error" }, "No se encontró llama-server. Ejecuta ./install.sh en el Konkr."));
  if (mem?.total) box.append(h("p", { class: "muted" }, `RAM disponible: ${fmtSize(mem.available)} de ${fmtSize(mem.total)}`));
  $("#disk-free").textContent = S.status.disk_free ? `· ${fmtSize(S.status.disk_free)} libres` : "";
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
      m.mmproj ? null : (loaded === m.path
        ? h("span", { class: "badge ok" }, "cargado")
        : h("button", { class: "primary small", onclick: () => loadModel(m.path) }, "Cargar")),
      h("button", { class: "ghost small", title: "Borrar del disco", onclick: async () => {
        if (!confirm(`¿Borrar ${m.name} (${fmtSize(m.size)}) del disco?`)) return;
        await api("/api/models/local?" + qs({ path: m.path }), { method: "DELETE" }); refreshModels();
      } }, "🗑")));
  }
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
    const ul = h("ul", { class: "list" });
    for (const g of groups) {
      ul.append(h("li", {},
        h("div", { class: "name" }, g.name, h("div", { class: "sub" }, [g.quant, fmtSize(g.size), g.files.length > 1 ? `${g.files.length} partes` : ""].filter(Boolean).join(" · "))),
        g.mmproj ? h("span", { class: "badge" }, "visión") : fitBadge(g.size),
        h("button", { class: "primary small", onclick: async () => {
          await api("/api/hub/download", { method: "POST", body: { repo, files: g.files } });
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
      h("div", { class: "row" }, h("b", { class: "grow" }, d.dest.split("/").pop()),
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
  await api("/api/files/mkdir", { method: "POST", body: { path: S.filesPath + "/" + n } }).catch((e) => toast(e.message));
  loadFiles(S.filesPath);
});
$("#files-search-form").addEventListener("submit", async (e) => {
  e.preventDefault(); const q = $("#files-search").value.trim(); if (!q) return loadFiles(S.filesPath);
  const res = await api("/api/files/search?" + qs({ q, path: S.filesPath }));
  renderFileList(res.map((r) => ({ ...r, name: r.path })));
});
const IMG = /\.(png|jpe?g|gif|webp|svg|bmp)$/i, VID = /\.(mp4|webm|mov|mkv)$/i, AUD = /\.(mp3|ogg|wav|flac|m4a)$/i;
async function previewFile(path) {
  const name = path.split("/").pop(), body = $("#preview-body"), url = "/api/files/download?" + qs({ path });
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
  ["file_roots", "Carpetas accesibles (una por línea)", "lines", "La interfaz y la IA sólo pueden ver estas carpetas."],
  ["allow_ai_file_write", "Permitir que la IA escriba archivos", "checkbox"],
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

  const pe = $("#providers-edit"); pe.innerHTML = "";
  S.settings.providers.forEach((p, idx) => pe.append(providerBox(p, idx)));

  const f = $("#settings-form"); f.innerHTML = "";
  for (const [key, label, type, hint] of FIELDS) {
    const v = S.settings[key];
    let inp;
    if (type === "textarea") inp = h("textarea", { name: key, rows: 3 }, v || "");
    else if (type === "lines") inp = h("textarea", { name: key, rows: 2 }, (v || []).join("\n"));
    else if (type === "checkbox") inp = h("input", { type: "checkbox", name: key, checked: !!v });
    else inp = h("input", { type, name: key, value: v ?? "", step: type === "number" ? "any" : null });
    f.append(h("label", {}, label), inp);
    if (hint) f.append(h("div", { class: "hint" }, hint));
  }
}
function providerBox(p, idx) {
  const set = (k) => (e) => { S.settings.providers[idx][k] = e.target.type === "checkbox" ? e.target.checked : e.target.value; };
  return h("div", { class: "provider-box" },
    h("div", { class: "row" },
      h("label", { class: "toggle grow" }, h("input", { type: "checkbox", checked: !!p.enabled, onchange: set("enabled") }), h("b", {}, p.name), h("span", { class: "badge" }, p.type)),
      h("button", { class: "ghost small", onclick: () => { S.settings.providers.splice(idx, 1); loadSettingsProvidersOnly(); } }, "Quitar")),
    h("div", { class: "form-grid" },
      h("label", {}, "Nombre"), h("input", { value: p.name, oninput: set("name") }),
      h("label", {}, "URL base"), h("input", { value: p.base_url, oninput: set("base_url") }),
      h("label", {}, "Clave API"), h("input", { type: "password", value: p.api_key || "", placeholder: "sk-…", oninput: set("api_key") })));
}
function loadSettingsProvidersOnly() {
  const pe = $("#providers-edit"); pe.innerHTML = "";
  S.settings.providers.forEach((p, idx) => pe.append(providerBox(p, idx)));
}
$("#add-provider").addEventListener("click", () => {
  const name = prompt("Nombre (p.ej. Groq, Ollama en el portátil, LM Studio…)"); if (!name) return;
  const url = prompt("URL base compatible con OpenAI (termina en /v1)", "http://192.168.1.10:11434/v1"); if (!url) return;
  S.settings.providers.push({ id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-") + "-" + Date.now().toString(36).slice(-4),
    name, type: "openai", base_url: url, api_key: "", enabled: true });
  loadSettingsProvidersOnly();
});
$("#save-settings").addEventListener("click", async () => {
  const f = $("#settings-form"), out = { providers: S.settings.providers };
  for (const [key, , type] of FIELDS) {
    const el = f.elements[key];
    if (type === "checkbox") out[key] = el.checked;
    else if (type === "number") out[key] = el.value === "" ? 0 : Number(el.value);
    else if (type === "lines") out[key] = el.value.split("\n").map((s) => s.trim()).filter(Boolean);
    else out[key] = el.value;
  }
  try {
    S.settings = await api("/api/settings", { method: "PUT", body: out });
    S.models = {}; await loadProviders(); toast("Ajustes guardados ✔"); loadSettings();
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
