// G3G3AI · Iconos, estado, proveedores, selector de modelos, menús y permisos.
// Parte 2/8 de la interfaz: se cargan en orden y comparten el ámbito global.
// --- Iconos (línea, monocromos, como en Claude) ---------------------------------------------------
const ICON_PATHS = {
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12Z"/>',
  code: '<path d="m8 9-4 3 4 3M16 9l4 3-4 3M13.5 5l-3 14"/>',
  cube: '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>',
  project: '<path d="M4 7.5V18a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 18V9.5A1.5 1.5 0 0 0 18.5 8h-6L10.5 5.5h-5A1.5 1.5 0 0 0 4 7Z"/><path d="M8.5 13h7M8.5 16h4"/>',
  share: '<circle cx="6" cy="12" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="18" cy="18" r="2.2"/><path d="M8 11l8-4M8 13l8 4"/>',
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
  download: '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
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
  mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5"/>',
  speaker: '<path d="M4.5 9.5h3l4.5-4v13l-4.5-4h-3z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
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
    updateModelBtn();
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
// --- Selector de modelos con buscador ---------------------------------------------------------
const shortModel = (m) => {
  if (!m) return "Elige un modelo";
  if (m.pid === "local") return S.status?.llama?.model ? S.status.llama.model.replace(/\.gguf$/i, "") : "Modelo local";
  return m.label.split("/").pop();
};
function updateModelBtn() {
  const b = $("#model-btn"); if (!b) return;
  const auto = $("#auto-toggle").checked;
  const m = MS.catalog.find((x) => x.value === $("#model-select").value);
  b.querySelector(".mb-name").textContent = auto ? "Auto (local ↔ API)" : shortModel(m);
  b.title = auto ? "En modo Auto el modelo se elige solo; desactívalo en ⚙ para elegir" : (m ? `${m.label} · ${m.group} — Ctrl+Mayús+M` : "Elegir modelo");
  b.disabled = auto;
}
function pickModel(value) {
  const sel = $("#model-select");
  if (![...sel.options].some((o) => o.value === value)) renderModelSelect(value);   // un modelo oculto también se puede elegir
  sel.value = value; sel.dispatchEvent(new Event("change"));
  const rec = [value, ...store.get("recent_models", []).filter((x) => x !== value)].slice(0, 5);
  store.set("recent_models", rec);
  updateModelBtn(); closeModelPicker();
}
function closeModelPicker() { $("#model-picker")?.remove(); document.removeEventListener("mousedown", pickerOutside, true); }
function pickerOutside(e) { if (!e.target.closest("#model-picker") && !e.target.closest("#model-btn")) closeModelPicker(); }
function openModelPicker() {
  if ($("#model-picker")) { closeModelPicker(); return; }
  if ($("#auto-toggle").checked) { toast("Estás en modo Auto: desactívalo en ⚙ para elegir modelo"); return; }
  const cur = $("#model-select").value;
  const search = h("input", { type: "search", placeholder: "Buscar modelo o proveedor…", autocomplete: "off" });
  const list = h("div", { class: "mp-list", role: "listbox" });
  const pop = h("div", { id: "model-picker", class: "model-picker" }, search, list,
    h("div", { class: "mp-foot" },
      h("button", { class: "ghost small", onclick: () => { closeModelPicker(); openModelsDialog(); } }, "Gestionar modelos"),
      h("button", { class: "ghost small", onclick: () => { closeModelPicker(); providerDialog(); } }, ico("plus"), "Añadir proveedor")));
  let rows = [], hi = 0;
  const row = (m) => {
    const fav = MS.favs.includes(m.value);
    const el = h("div", { class: "mp-row" + (m.value === cur ? " cur" : ""), role: "option", onclick: () => pickModel(m.value) },
      h("span", { class: "mp-ico" }, ico(m.pid === "local" ? "cpu" : "globe")),
      h("span", { class: "mp-name" }, h("b", {}, shortModel(m)), h("small", {}, m.group)),
      m.value === cur ? h("span", { class: "mp-check" }, ico("check")) : null,
      h("button", { class: "mp-star" + (fav ? " on" : ""), title: fav ? "Quitar de favoritos" : "Añadir a favoritos", onclick: async (e) => {
        e.stopPropagation();
        MS.favs = fav ? MS.favs.filter((x) => x !== m.value) : [...MS.favs, m.value];
        MS.hidden = MS.hidden.filter((x) => x !== m.value);
        renderModelSelect(); draw(); await saveModelPrefs();
      } }, fav ? "★" : "☆"));
    rows.push({ el, value: m.value });
    return el;
  };
  const draw = () => {
    list.innerHTML = ""; rows = [];
    const q = search.value.trim().toLowerCase();
    const words = q.split(/\s+/).filter(Boolean);
    const match = (m) => words.every((w) => (m.label + " " + m.group + " " + m.value).toLowerCase().includes(w));
    const section = (title, items) => { if (items.length) list.append(h("div", { class: "mp-sec" }, title), ...items.map(row)); };
    if (q) section("Resultados", MS.catalog.filter(match).slice(0, 80));
    else {
      const favs = MS.catalog.filter((m) => MS.favs.includes(m.value));
      const rec = store.get("recent_models", []).map((v) => MS.catalog.find((m) => m.value === v)).filter((m) => m && !MS.favs.includes(m.value));
      section("Favoritos", favs); section("Recientes", rec);
      const seen = new Set([...favs, ...rec].map((m) => m.value));
      const groups = new Map();
      for (const m of MS.catalog) {
        if (seen.has(m.value) || MS.hidden.includes(m.value)) continue;
        if (!groups.has(m.group)) groups.set(m.group, []);
        groups.get(m.group).push(m);
      }
      for (const [g, items] of groups) section(g, items);
    }
    if (!rows.length) list.append(h("p", { class: "muted mp-empty" }, q ? "Ningún modelo coincide." : "No hay modelos: añade un proveedor o carga uno local."));
    hi = Math.max(0, rows.findIndex((r) => r.value === cur)); if (q) hi = 0;
    mark();
  };
  const mark = () => rows.forEach((r, i) => { r.el.classList.toggle("hi", i === hi); if (i === hi) r.el.scrollIntoView({ block: "nearest" }); });
  search.addEventListener("input", draw);
  search.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); hi = Math.min(rows.length - 1, hi + 1); mark(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); hi = Math.max(0, hi - 1); mark(); }
    else if (e.key === "Enter") { e.preventDefault(); if (rows[hi]) pickModel(rows[hi].value); }
    else if (e.key === "Escape") { e.preventDefault(); closeModelPicker(); $("#input").focus(); }
  });
  $(".composer").append(pop);
  draw();
  search.focus();
  setTimeout(() => document.addEventListener("mousedown", pickerOutside, true), 0);
}
$("#model-btn").addEventListener("click", openModelPicker);
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "m") { e.preventDefault(); openModelPicker(); }
});

function updateFavButton() {
  updateModelBtn();
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
  if ($("#tools-toggle").checked) box.append(permChip());
}
// --- Nivel de permisos en el propio chat: Manual / Semi-auto / Auto ----------------------------------
const PERM_LEVELS = {
  manual: { label: "Manual", icon: "🔒", desc: "Te pregunta antes de cada comando y de cada cambio en tus archivos.",
            set: { ai_write: "ask", ai_commands: "ask", commands_trusted: false } },
  semi: { label: "Semi-auto", icon: "🤝", desc: "Crea y edita en tus carpetas y ejecuta lo habitual (python, pruebas, git de lectura) sin preguntar; pregunta ante lo nuevo o arriesgado.",
          set: { ai_write: "ask", ai_commands: "ask", commands_trusted: true } },
  auto: { label: "Auto", icon: "⚡", desc: "Hace lo que haga falta sin preguntar (siempre dentro de tus carpetas; lo peligroso se sigue bloqueando).",
          set: { ai_write: "auto", ai_commands: "auto", commands_trusted: true } },
};
function permLevel(st) {
  if (!st) return null;
  if (st.ai_write === "auto" && st.ai_commands === "auto") return "auto";
  return st.commands_trusted ? "semi" : "manual";
}
function permChip() {
  const lvl = permLevel(S.settings) || "manual", L = PERM_LEVELS[lvl];
  const chip = h("span", { class: "perm-chip perm-" + lvl, title: "Permisos del agente: " + L.desc, onclick: (e) => { e.stopPropagation(); permMenu(chip); } }, L.icon + " " + L.label + " ▾");
  if (!S.settings) api("/api/settings").then((st) => { S.settings = st; renderActiveTools(); }).catch(() => {});
  return chip;
}
function permMenu(anchor) {
  $("#perm-menu")?.remove();
  const cur = permLevel(S.settings);
  const menu = h("div", { id: "perm-menu", class: "file-menu perm-menu" },
    h("div", { class: "pm-title" }, "¿Cuánta libertad tiene el agente?"),
    Object.entries(PERM_LEVELS).map(([k, L]) => h("button", { class: k === cur ? "on" : "", onclick: async () => {
      menu.remove();
      try { S.settings = await api("/api/settings", { method: "PUT", body: L.set }); toast(`Permisos: ${L.label}`); }
      catch (e) { toast(e.message, 6000); }
      renderActiveTools();
    } }, h("span", { class: "pm-ico" }, L.icon), h("span", { class: "pm-text" }, h("b", {}, L.label), h("small", {}, L.desc)))));
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();
  menu.style.left = Math.max(8, Math.min(innerWidth - menu.offsetWidth - 8, r.left)) + "px";
  menu.style.top = Math.max(8, r.top - menu.offsetHeight - 6) + "px";
  setTimeout(() => document.addEventListener("mousedown", function off(e) { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener("mousedown", off); } }), 0);
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
