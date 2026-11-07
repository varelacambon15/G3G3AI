"use strict";
/* G3G3AI · Chat directo (dentro de la app de Android): habla con las APIs sin pasar por un equipo.
   Las peticiones HTTP las hace la app (puente G3Native) para no depender de CORS. */

const $ = (s) => document.querySelector(s);
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
function toast(msg, ms = 3000) { const d = h("div", {}, msg); $("#toast").append(d); setTimeout(() => d.remove(), ms); }

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

// --- Markdown (copiado de la interfaz principal) ---------------------------------------
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


// --- Puente con la app -------------------------------------------------------------------
const Native = window.G3Native;
const pending = new Map();
window.__g3net = (id, kind, data) => {
  const p = pending.get(id);
  if (!p) return;
  if (kind === "status") p.status = Number(data);
  else if (kind === "line") { p.lines.push(data); p.onLine && p.onLine(data); }
  else if (kind === "end") { pending.delete(id); p.resolve({ status: p.status, text: p.lines.join("\n") }); }
  else if (kind === "error") { pending.delete(id); p.reject(new Error(data)); }
};
let reqSeq = 0;
function request({ method = "GET", url, headers = {}, body = null, onLine = null }) {
  const id = "r" + (++reqSeq);
  const promise = new Promise((resolve, reject) => pending.set(id, { status: 0, lines: [], onLine, resolve, reject }));
  Native.request(id, method, url, JSON.stringify(headers), body == null ? "" : JSON.stringify(body));
  promise.id = id;
  return promise;
}
const store = {
  get(k, d) { try { const v = Native.getStore(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { Native.setStore(k, JSON.stringify(v)); },
};

// --- Datos -----------------------------------------------------------------------------
const PRESETS = [
  { id: "deepseek", name: "DeepSeek", type: "openai", base_url: "https://api.deepseek.com", api_key: "", enabled: false },
  { id: "anthropic", name: "Anthropic (Claude)", type: "anthropic", base_url: "https://api.anthropic.com", api_key: "", enabled: false },
  { id: "openai", name: "OpenAI", type: "openai", base_url: "https://api.openai.com/v1", api_key: "", enabled: false },
  { id: "gemini", name: "Google Gemini", type: "openai", base_url: "https://generativelanguage.googleapis.com/v1beta/openai", api_key: "", enabled: false },
  { id: "openrouter", name: "OpenRouter", type: "openai", base_url: "https://openrouter.ai/api/v1", api_key: "", enabled: false },
  { id: "groq", name: "Groq", type: "openai", base_url: "https://api.groq.com/openai/v1", api_key: "", enabled: false },
];
const S = {
  providers: store.get("providers", PRESETS),
  settings: store.get("settings", { system: "Eres un asistente útil. Responde en el idioma del usuario.", temperature: 0.7, max_tokens: 8192 }),
  models: store.get("models", {}),
  convs: JSON.parse(localStorage.getItem("g3d:convs") || "[]"),
  current: null, attachments: [], streaming: null,
};
const saveConvs = () => { try { localStorage.setItem("g3d:convs", JSON.stringify(S.convs)); } catch { toast("No queda espacio para guardar la conversación"); } };
const ready = () => S.providers.filter((p) => p.enabled && p.api_key);

// --- Modelos ---------------------------------------------------------------------------
async function fetchModels(p) {
  const base = p.base_url.replace(/\/$/, "");
  const r = p.type === "anthropic"
    ? await request({ url: base + "/v1/models?limit=100", headers: { "x-api-key": p.api_key, "anthropic-version": "2023-06-01" } })
    : await request({ url: base + "/models", headers: { Authorization: "Bearer " + p.api_key } });
  if (r.status >= 400) throw new Error(`HTTP ${r.status}`);
  return (JSON.parse(r.text).data || []).map((m) => m.id).sort();
}
async function renderModels(refresh = false) {
  const sel = $("#model"), prev = store.get("model", "");
  sel.innerHTML = "";
  const provs = ready();
  if (!provs.length) { sel.append(h("option", { value: "" }, "Configura una API en ⚙")); return; }
  for (const p of provs) {
    if (refresh || !S.models[p.id]) {
      try { S.models[p.id] = await fetchModels(p); } catch (e) { S.models[p.id] = S.models[p.id] || []; toast(`${p.name}: ${e.message}`); }
    }
    const g = h("optgroup", { label: p.name });
    for (const m of S.models[p.id]) g.append(h("option", { value: `${p.id}::${m}` }, m));
    if (!S.models[p.id].length) g.append(h("option", { disabled: true }, "(sin modelos: revisa la clave)"));
    sel.append(g);
  }
  store.set("models", S.models);
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
}
$("#model").addEventListener("change", (e) => store.set("model", e.target.value));

// --- Conversaciones ----------------------------------------------------------------------
function renderConvs() {
  const box = $("#convs"); box.innerHTML = "";
  for (const c of S.convs) {
    box.append(h("div", { class: "conv" + (S.current === c ? " active" : ""), onclick: () => { open(c); document.body.classList.remove("drawer-open"); } },
      h("span", {}, c.title),
      h("button", { onclick: (e) => { e.stopPropagation(); if (!confirm("¿Borrar esta conversación?")) return;
        S.convs = S.convs.filter((x) => x !== c); saveConvs(); if (S.current === c) open(null); else renderConvs(); } }, "🗑")));
  }
}
function open(c) { S.current = c; renderMessages(); renderConvs(); }
$("#new-chat").addEventListener("click", () => { open(null); document.body.classList.remove("drawer-open"); $("#input").focus(); });
$("#menu").addEventListener("click", () => document.body.classList.toggle("drawer-open"));
$("#scrim").addEventListener("click", () => document.body.classList.remove("drawer-open"));

// --- Mensajes ----------------------------------------------------------------------------
function assistantBody(text, reasoning, streaming) {
  const frag = document.createDocumentFragment();
  const { think, body } = splitThink(text || "");
  const r = [reasoning, think].filter(Boolean).join("\n");
  if (r) frag.append(h("details", {}, h("summary", {}, "💭 Razonamiento"), h("pre", {}, r)));
  const b = h("div", { class: "bubble" + (streaming ? " cursor" : "") });
  b.innerHTML = md(body);
  frag.append(b);
  return frag;
}
function messageEl(m) {
  const el = h("div", { class: "msg " + m.role });
  if (m.role === "user") {
    for (const img of m.images || []) el.append(h("img", { src: img, alt: "" }));
    if (m.content) el.append(h("div", { class: "bubble" }, m.content));
  } else {
    el.append(assistantBody(m.content, m.reasoning));
    el.append(h("div", { class: "meta" },
      h("button", { onclick: () => { copyText(m.content); } }, "⧉"),
      m.error ? h("span", { class: "error" }, m.error) : null, h("span", {}, m.model || "")));
  }
  return el;
}
function renderMessages() {
  const box = $("#messages"); box.innerHTML = "";
  if (!S.current?.messages.length) {
    box.append(h("div", { class: "empty" }, h("h1", {}, h("span", { class: "logo" }, "✦ "), "Hola"),
      h("p", {}, ready().length ? "Escribe abajo. Hablas directamente con la API, sin necesidad de tener el equipo encendido."
        : "Pulsa ⚙ para importar tus APIs desde la Konkr o el PC, o pega una clave.")));
    return;
  }
  for (const m of S.current.messages) box.append(messageEl(m));
  box.scrollTop = box.scrollHeight;
}
document.addEventListener("click", (e) => {
  if (e.target.classList?.contains("copy")) {
    copyText(e.target.closest("pre").querySelector("code").textContent, "Código copiado");
  }
});

// --- Fotos ------------------------------------------------------------------------------
$("#photo").addEventListener("click", () => $("#photo-input").click());
$("#photo-input").addEventListener("change", async (e) => {
  for (const f of e.target.files) S.attachments.push(await shrink(f));
  e.target.value = ""; renderChips();
});
function shrink(file) {
  return new Promise((resolve, reject) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, 1568 / Math.max(img.width, img.height));
      const c = document.createElement("canvas"); c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = reject; img.src = url;
  });
}
function renderChips() {
  const box = $("#attachments"); box.innerHTML = "";
  S.attachments.forEach((src, i) => box.append(h("span", { class: "chip" }, h("img", { src }),
    h("button", { onclick: () => { S.attachments.splice(i, 1); renderChips(); } }, "✕"))));
}

// --- Envío con streaming ---------------------------------------------------------------------
const input = $("#input");
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; });
$("#send").addEventListener("click", () => {
  if (S.streaming) { Native.abort(S.streaming); return; }
  const text = input.value.trim();
  if (!text && !S.attachments.length) return;
  const [pid, ...rest] = ($("#model").value || "").split("::");
  const p = S.providers.find((x) => x.id === pid);
  if (!p) { toast("Elige un modelo (o configura una API en ⚙)"); return; }
  if (!S.current) { S.current = { title: (text || "Foto").slice(0, 50), messages: [], created: Date.now() }; S.convs.unshift(S.current); }
  S.current.messages.push({ role: "user", content: text, images: S.attachments.slice() });
  input.value = ""; input.style.height = "auto"; S.attachments = []; renderChips();
  saveConvs(); renderMessages(); renderConvs();
  stream(p, rest.join("::"));
});

function apiMessages(p) {
  const out = [];
  for (const m of S.current.messages) {
    if (m.role === "user" && m.images?.length) {
      const parts = [{ type: "text", text: m.content || "(imagen)" }];
      for (const src of m.images) {
        if (p.type === "anthropic") {
          const [head, data] = src.split(",");
          parts.push({ type: "image", source: { type: "base64", media_type: head.slice(5, head.indexOf(";")), data } });
        } else parts.push({ type: "image_url", image_url: { url: src } });
      }
      out.push({ role: "user", content: parts });
    } else if (m.content) out.push({ role: m.role, content: m.content });
  }
  return out;
}

async function stream(p, model) {
  const st = S.settings, base = p.base_url.replace(/\/$/, "");
  const msg = { role: "assistant", content: "", reasoning: "", model };
  const conv = S.current;
  const el = h("div", { class: "msg assistant" }); $("#messages").append(el);
  let raf = 0;
  const paint = () => { raf = 0; el.innerHTML = ""; el.append(assistantBody(msg.content, msg.reasoning, true)); const b = $("#messages"); b.scrollTop = b.scrollHeight; };
  const onLine = (line) => {
    if (!line.startsWith("data:")) return;
    const data = line.slice(5).trim();
    if (data === "[DONE]") return;
    let j; try { j = JSON.parse(data); } catch { return; }
    if (p.type === "anthropic") {
      if (j.type === "content_block_delta") {
        if (j.delta.type === "text_delta") msg.content += j.delta.text;
        else if (j.delta.type === "thinking_delta") msg.reasoning += j.delta.thinking;
      } else if (j.type === "error") msg.error = j.error?.message;
      else if (j.type === "message_delta" && j.delta?.stop_reason === "max_tokens") msg.error = "Respuesta cortada por longitud: escribe «continúa».";
    } else {
      if (j.choices?.[0]?.finish_reason === "length") msg.error = "Respuesta cortada por longitud: escribe «continúa».";
      const d = j.choices?.[0]?.delta || {};
      if (d.content) msg.content += d.content;
      if (d.reasoning_content || d.reasoning) msg.reasoning += d.reasoning_content || d.reasoning;
    }
    if (!raf) raf = requestAnimationFrame(paint);
  };
  let req;
  if (p.type === "anthropic") {
    // Claude actual: razona antes de responder (cuenta en max_tokens) y no admite temperature
    const body = { model, max_tokens: Math.max(Number(st.max_tokens) || 0, 16000), stream: true, messages: apiMessages(p) };
    if (st.system) body.system = st.system;
    req = request({ method: "POST", url: base + "/v1/messages", onLine, body,
      headers: { "x-api-key": p.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json" } });
  } else {
    const messages = (st.system ? [{ role: "system", content: st.system }] : []).concat(apiMessages(p));
    req = request({ method: "POST", url: base + "/chat/completions", onLine,
      headers: { Authorization: "Bearer " + p.api_key, "content-type": "application/json" },
      body: { model, messages, stream: true, temperature: Number(st.temperature), max_tokens: Math.max(Number(st.max_tokens) || 0, 8192) } });
  }
  S.streaming = req.id;
  $("#send").textContent = "■"; $("#send").classList.add("stop");
  try {
    const r = await req;
    if (r.status >= 400) {
      let detail = r.text;
      try { const j = JSON.parse(r.text); detail = j.error?.message || j.error || detail; } catch { /* texto plano */ }
      msg.error = `HTTP ${r.status}: ${String(detail).slice(0, 300)}`;
    }
  } catch (e) {
    if (!/abort/i.test(e.message)) msg.error = e.message;
  } finally {
    S.streaming = null;
    $("#send").textContent = "↑"; $("#send").classList.remove("stop");
    if (msg.content || msg.reasoning || msg.error) conv.messages.push(msg);
    saveConvs();
    if (S.current === conv) renderMessages();
  }
}

// --- Ajustes ------------------------------------------------------------------------------
$("#settings-btn").addEventListener("click", openSettings);
$("#settings-close").addEventListener("click", () => $("#settings").classList.add("hidden"));
function openSettings() {
  $("#system").value = S.settings.system || "";
  $("#temperature").value = S.settings.temperature;
  $("#max-tokens").value = S.settings.max_tokens;
  renderProviders(); renderServers();
  $("#settings").classList.remove("hidden");
}
function renderProviders() {
  const box = $("#providers"); box.innerHTML = "";
  S.providers.forEach((p, i) => {
    const set = (k) => (e) => { p[k] = e.target.type === "checkbox" ? e.target.checked : e.target.value; };
    box.append(h("div", { class: "prov" },
      h("label", { class: "head" }, h("input", { type: "checkbox", checked: !!p.enabled, onchange: set("enabled") }), h("b", {}, p.name),
        p.api_key ? h("span", { class: "muted small" }, "✔ clave") : null),
      h("div", { class: "fields" },
        h("input", { value: p.base_url, placeholder: "URL base", oninput: set("base_url") }),
        h("input", { type: "password", value: p.api_key || "", placeholder: "Clave API", oninput: set("api_key") }),
        PRESETS.some((x) => x.id === p.id) ? null : h("button", { class: "ghost", onclick: () => { S.providers.splice(i, 1); renderProviders(); } }, "Quitar"))));
  });
}
$("#add-provider").addEventListener("click", () => {
  const name = prompt("Nombre (p.ej. Mi servidor)"); if (!name) return;
  const url = prompt("URL base compatible con OpenAI (termina en /v1)", "https://"); if (!url) return;
  S.providers.push({ id: "custom-" + Date.now().toString(36), name, type: "openai", base_url: url, api_key: "", enabled: true });
  renderProviders();
});
function renderServers() {
  const box = $("#servers"); box.innerHTML = "";
  let servers = [];
  try { servers = JSON.parse(Native.getServers() || "[]"); } catch { /* sin equipos */ }
  if (!servers.length) { box.append(h("p", { class: "muted small" }, "Primero añade un equipo en la pantalla de inicio de la app.")); return; }
  for (const s of servers) box.append(h("div", { class: "server" }, h("span", {}, s.name || s.url),
    h("button", { class: "ghost", onclick: (e) => importFrom(s, e.target) }, "Importar")));
}
async function importFrom(server, btn) {
  btn.disabled = true; btn.textContent = "Importando…";
  try {
    const r = await request({ url: server.url.replace(/\/$/, "") + "/api/providers/export", headers: { Authorization: "Bearer " + server.token } });
    if (r.status === 401) throw new Error("contraseña incorrecta");
    if (r.status >= 400) throw new Error("HTTP " + r.status);
    const data = JSON.parse(r.text);
    let n = 0;
    for (const p of data.providers) {
      const cur = S.providers.find((x) => x.id === p.id);
      const clean = { id: p.id, name: p.name, type: p.type, base_url: p.base_url, api_key: p.api_key, enabled: true };
      if (cur) Object.assign(cur, clean); else S.providers.push(clean);
      n++;
    }
    if (data.system) S.settings.system = data.system;
    store.set("providers", S.providers); store.set("settings", S.settings);
    S.models = {}; renderProviders(); openSettings();
    toast(n ? `${n} API(s) importadas de ${server.name || server.url}` : "Ese equipo no tiene APIs configuradas");
    await renderModels(true);
  } catch (e) {
    toast("No se pudo importar: " + e.message + ". ¿Está el equipo encendido y en la misma red?", 5000);
  } finally { btn.disabled = false; btn.textContent = "Importar"; }
}
$("#settings-save").addEventListener("click", async () => {
  S.settings = { system: $("#system").value, temperature: $("#temperature").value, max_tokens: $("#max-tokens").value };
  store.set("providers", S.providers); store.set("settings", S.settings);
  S.models = {}; $("#settings").classList.add("hidden"); toast("Guardado");
  await renderModels(true); renderMessages();
});

// --- Arranque ---------------------------------------------------------------------------
renderConvs(); renderMessages(); renderModels();
