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


// --- Iconos de línea (los mismos que en el escritorio) ------------------------------------------
const ICON_PATHS = {
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>',
  camera: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7H8l1.5-2h5L16 7h2.5A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5v-9Z"/><circle cx="12" cy="13" r="3.5"/>',
  arrowUp: '<path d="M12 19V5M6 11l6-6 6 6"/>', stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
  retry: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>', pencil: '<path d="M16.5 3.8a2 2 0 0 1 2.8 2.8L8 18l-4 1 1-4L16.5 3.8Z"/>',
  trash: '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>', spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
  brain: '<path d="M9 4.5A2.5 2.5 0 0 0 6.5 7v.3A3 3 0 0 0 4.5 10c0 .9.4 1.7 1 2.2A3 3 0 0 0 7 17.5 2.5 2.5 0 0 0 12 18V6.5A2 2 0 0 0 9 4.5ZM15 4.5A2.5 2.5 0 0 1 17.5 7v.3a3 3 0 0 1 2 2.7c0 .9-.4 1.7-1 2.2a3 3 0 0 1-1.5 5.3A2.5 2.5 0 0 1 12 18"/>',
  doc: '<path d="M14 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8L14 3.5Z"/><path d="M14 3.5V8h4.5M9 12.5h6M9 16h6"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.4 3.5 5.3 3.5 8.5s-1 6.1-3.5 8.5c-2.5-2.4-3.5-5.3-3.5-8.5s1-6.1 3.5-8.5Z"/>',
  pen: '<path d="M12 20h8M16.5 3.8a2 2 0 0 1 2.8 2.8L8 18l-4 1 1-4L16.5 3.8Z"/>', bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z"/>',
};
function ico(name) {
  const s = document.createElement("span");
  s.className = "ico";
  s.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
  return s;
}
document.querySelectorAll("[data-icon]").forEach((el) => el.append(ico(el.dataset.icon)));
const setSendIcon = (on) => { const b = $("#send"); b.innerHTML = ""; b.append(ico(on ? "stop" : "arrowUp")); b.classList.toggle("stop", on); };

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
// Catálogo compartido con el escritorio (catalog.js); lo guardado se conserva y se añaden los proveedores nuevos.
const CATALOG = (window.G3_CATALOG || []).map((c) => ({ id: c.id, name: c.name, type: c.type, base_url: c.base_url,
  key_url: c.key_url, description: c.description, tags: c.tags, api_key: "", enabled: false }));
function mergeCatalog(saved) {
  const out = Array.isArray(saved) ? saved.slice() : [];
  for (const c of CATALOG) {
    const cur = out.find((p) => p.id === c.id);
    if (cur) Object.assign(cur, { key_url: c.key_url, description: c.description, tags: c.tags });
    else out.push({ ...c });
  }
  return out;
}
const S = {
  providers: mergeCatalog(store.get("providers", PRESETS)),
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
  const q = ($("#conv-search")?.value || "").trim().toLowerCase();
  const list = S.convs.filter((c) => !q || c.title.toLowerCase().includes(q) || c.messages.some((m) => (m.content || "").toLowerCase().includes(q)));
  if (!list.length) box.append(h("p", { class: "muted small" }, q ? "Sin resultados." : "Aún no hay conversaciones."));
  for (const c of list) {
    box.append(h("div", { class: "conv" + (S.current === c ? " active" : ""), onclick: () => { open(c); document.body.classList.remove("drawer-open"); } },
      h("span", {}, c.title),
      h("button", { onclick: (e) => { e.stopPropagation(); if (!confirm("¿Borrar esta conversación?")) return;
        S.convs = S.convs.filter((x) => x !== c); saveConvs(); if (S.current === c) open(null); else renderConvs(); } }, ico("trash"))));
  }
}
function open(c) { S.current = c; renderMessages(); renderConvs(); }
$("#conv-search").addEventListener("input", renderConvs);
// Editar un mensaje propio: vuelve al cuadro de texto y se descarta lo posterior
function editFrom(m) {
  if (S.streaming || !S.current) return;
  const i = S.current.messages.indexOf(m);
  if (i < 0) return;
  S.current.messages = S.current.messages.slice(0, i);
  saveConvs(); renderMessages();
  input.value = m.content || ""; input.dispatchEvent(new Event("input")); input.focus();
}
// Volver a generar la última respuesta con el modelo elegido
function regenerate(m) {
  if (S.streaming || !S.current) return;
  const i = S.current.messages.indexOf(m);
  if (i < 0) return;
  S.current.messages = S.current.messages.slice(0, i);
  saveConvs(); renderMessages();
  const [pid, ...rest] = ($("#model").value || "").split("::");
  const p = S.providers.find((x) => x.id === pid);
  if (!p) { toast("Elige un modelo"); return; }
  stream(p, rest.join("::"));
}
$("#new-chat").addEventListener("click", () => { open(null); document.body.classList.remove("drawer-open"); $("#input").focus(); });
$("#menu").addEventListener("click", () => document.body.classList.toggle("drawer-open"));
$("#scrim").addEventListener("click", () => document.body.classList.remove("drawer-open"));

// --- Mensajes ----------------------------------------------------------------------------
function assistantBody(text, reasoning, streaming) {
  const frag = document.createDocumentFragment();
  const { think, body } = splitThink(text || "");
  const r = [reasoning, think].filter(Boolean).join("\n");
  if (r) frag.append(h("details", {}, h("summary", {}, ico("brain"), streaming && !body ? " Pensando…" : " Razonamiento"), h("pre", {}, r)));
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
    el.append(h("div", { class: "meta" },
      h("button", { "aria-label": "Copiar", onclick: () => { copyText(m.content); } }, ico("copy")),
      h("button", { "aria-label": "Editar", onclick: () => editFrom(m) }, ico("pencil"))));
  } else {
    el.append(assistantBody(m.content, m.reasoning));
    el.append(h("div", { class: "meta" },
      h("button", { "aria-label": "Copiar", onclick: () => { copyText(m.content); } }, ico("copy")),
      h("button", { "aria-label": "Volver a generar", onclick: () => regenerate(m) }, ico("retry")),
      m.error ? h("span", { class: "error" }, m.error) : null, h("span", { class: "model" }, m.model || "")));
  }
  return el;
}
function renderMessages() {
  const box = $("#messages"); box.innerHTML = "";
  if (!S.current?.messages.length) {
    const hr = new Date().getHours();
    const hello = hr < 6 ? "Buenas noches" : hr < 13 ? "Buenos días" : hr < 21 ? "Buenas tardes" : "Buenas noches";
    const ok = ready().length > 0;
    const ideas = [["doc", "Resume este texto", "Resume en 5 puntos clave el siguiente texto:\n\n"],
      ["pen", "Redacta un correo", "Redacta un correo breve y cordial para "],
      ["bulb", "Explícame algo", "Explícame de forma sencilla cómo funciona "],
      ["globe", "Traduce", "Traduce al inglés manteniendo el tono:\n\n"]];
    box.append(h("div", { class: "empty" }, h("h1", {}, ico("spark"), hello),
      ok ? h("div", { class: "ideas" }, ideas.map(([i, label, text]) => h("button", { onclick: () => { input.value = text; input.focus(); input.dispatchEvent(new Event("input")); } }, ico(i), label)))
        : h("div", {}, h("p", {}, "Para empezar, añade un proveedor de IA (OpenCode Go, OpenRouter, DeepSeek, Claude…) o importa los de tu PC."),
          h("button", { class: "primary", onclick: openSettings }, "Configurar un proveedor"))));
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
  setSendIcon(true);
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
    setSendIcon(false);
    if (document.hidden && window.G3Notify) {     // estabas en otra app: aviso del sistema
      try { window.G3Notify.notify(msg.error ? "G3G3AI: no se pudo responder" : "G3G3AI ha respondido", (msg.error || msg.content || "").slice(0, 200)); } catch { /* */ }
    }
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
  const q = ($("#prov-search")?.value || "").trim().toLowerCase();
  S.providers.forEach((p, i) => {
    if (q && !(p.name + " " + (p.description || "") + " " + (p.tags || []).join(" ")).toLowerCase().includes(q)) return;
    const test = h("span", { class: "muted small test-out" });
    const chk = h("input", { type: "checkbox", onchange: (e) => { p.enabled = e.target.checked; } });
    chk.checked = !!p.enabled;
    box.append(h("details", { class: "prov" + (p.api_key ? " on" : "") },
      h("summary", {}, h("b", {}, p.name), p.api_key ? h("span", { class: "tag ok" }, "Configurado") : (p.tags || []).slice(0, 2).map((t) => h("span", { class: "tag" }, t))),
      p.description ? h("p", { class: "muted small" }, p.description) : null,
      p.key_url ? h("p", { class: "small" }, h("a", { href: p.key_url, target: "_blank", rel: "noopener" }, "Conseguir una clave ↗")) : null,
      h("div", { class: "fields" },
        h("input", { type: "password", value: p.api_key || "", placeholder: "Pega aquí tu clave API", autocomplete: "off",
          oninput: (e) => { p.api_key = e.target.value.trim(); p.enabled = !!p.api_key; chk.checked = p.enabled; } }),
        h("input", { value: p.base_url, placeholder: "URL base", oninput: (e) => { p.base_url = e.target.value.trim(); } }),
        h("div", { class: "prov-actions" },
          h("button", { class: "ghost", onclick: async (e) => {
            e.preventDefault(); test.textContent = "Probando…"; test.className = "small test-out muted";
            try { const ms = await fetchModels(p); test.textContent = `Funciona: ${ms.length} modelos`; test.className = "small test-out ok"; p.enabled = true; chk.checked = true; }
            catch (er) { test.textContent = "No funciona: " + er.message + (/(401|403)/.test(er.message) ? " (clave incorrecta)" : ""); test.className = "small test-out error"; }
          } }, "Probar"),
          h("label", { class: "toggle" }, chk, " Activo"),
          CATALOG.some((x) => x.id === p.id) || PRESETS.some((x) => x.id === p.id) ? null
            : h("button", { class: "ghost", onclick: (e) => { e.preventDefault(); S.providers.splice(i, 1); renderProviders(); } }, "Quitar")),
        test)));
  });
}
$("#prov-search").addEventListener("input", renderProviders);
function renderProvidersOld() {
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

// «Compartir con G3G3AI»: texto al cuadro; fotos como adjuntos. Los documentos necesitan el PC (allí se leen y se hace OCR).
window.g3Share = async ({ text = "", files = [] } = {}) => {
  if (window.G3Notify) { try { window.G3Notify.requestPermission(); } catch { /* */ } }
  const imgs = files.filter((f) => /^image\//.test(f.mime)), others = files.length - imgs.length;
  for (const f of imgs) {
    const bin = atob(f.data), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    try { S.attachments.push(await shrink(new File([bytes], f.name, { type: f.mime }))); } catch { /* imagen no válida */ }
  }
  renderChips();
  if (text) { input.value = text; input.dispatchEvent(new Event("input")); }
  if (others) toast(`${others} documento(s) no se pueden leer en el chat directo: conéctate a tu PC para analizarlos.`, 6000);
  input.focus();
};
