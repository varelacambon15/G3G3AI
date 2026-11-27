// G3G3AI · Tareas, Equipo, «Comprobar todo», asistente inicial y medidor de contexto.
// Parte 3/8 de la interfaz: se cargan en orden y comparten el ámbito global.
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
          h("b", {}, (t.running ? "⏳ " : "") + t.name), " ", h("span", { class: "muted" }, `· ${t.when}${t.mode === "edits" ? " · puede editar" : ""}${t.level ? " · " + { manual: "🔒 Manual", semi: "🤝 Semi-auto", auto: "⚡ Auto" }[t.level] : ""}`),
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
  if (kind === "daily") {   // días de la semana (todos marcados = cada día)
    const days = h("span", { class: "task-days" }, ["L", "M", "X", "J", "V", "S", "D"].map((d, i) =>
      h("label", { class: "day-chip", title: ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][i] },
        h("input", { type: "checkbox", name: "day", value: i, checked: true }), d)));
    w.append(days);
  }
}
taskWhenInput();
$("#task-form").elements.kind.addEventListener("change", taskWhenInput);
$("#task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, kind = f.elements.kind.value, when = f.elements.when.value;
  const days = [...f.querySelectorAll("input[name=day]:checked")].map((x) => +x.value);
  if (kind === "daily" && !days.length) { toast("Marca al menos un día"); return; }
  const schedule = kind === "daily" ? { kind, time: when, days: days.length === 7 ? undefined : days } : kind === "interval" ? { kind, minutes: +when } : { kind, at: new Date(when).getTime() / 1000 };
  const { provider, model } = currentModel();
  try {
    await api("/api/tasks", { method: "POST", body: { name: f.elements.name.value, prompt: f.elements.prompt.value, schedule,
      provider, model, workdir: f.elements.workdir.value.trim() || null, mode: f.elements.edits.checked ? "edits" : "plan",
      level: f.elements.level.value } });
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
const TEAM = { data: null, sel: null, dirty: false, cur: "general", all: null };
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
  const all = await api("/api/teams");
  if (ticket !== TEAM.ticket || TEAM.dirty) return;          // llegó tarde: ya hay otra carga o cambios nuevos
  TEAM.all = all;
  if (TEAM.cur !== "general" && TEAM.cur !== "new" && !all.saved.some((t) => t.id === TEAM.cur)) TEAM.cur = "general";
  selectTeam(TEAM.cur, true);
}
// Equipo que se está editando: el general (el de siempre, con interruptor) o uno guardado (se asigna a proyectos)
function selectTeam(id, force = false) {
  if (!force && TEAM.dirty && !confirm("Hay cambios sin guardar en este equipo. ¿Descartarlos?")) { drawTeamBar(); return; }
  const all = TEAM.all, g = all.general;
  TEAM.cur = id;
  if (id === "general") TEAM.data = JSON.parse(JSON.stringify(g));
  else if (id === "new") TEAM.data = { id: Math.random().toString(36).slice(2, 10), name: "", members: [], enabled: true, show_claude: g.show_claude, isNew: true };
  else { const t = all.saved.find((x) => x.id === id); TEAM.data = { ...JSON.parse(JSON.stringify(t)), enabled: true, show_claude: g.show_claude }; }
  TEAM.sel = null; TEAM.dirty = id === "new";
  $("#team-enabled").checked = TEAM.data.enabled;
  $(".team-switch").classList.toggle("hidden", id !== "general");
  $("#team-templates").innerHTML = "";
  $("#team-templates").append(h("span", { class: "muted small" }, "Añadir:"),
    ...TEAM_TEMPLATES.map(([n, role, tools]) => h("button", { class: "ghost small", onclick: () => addMember(n, role, tools) }, ico("plus"), n)),
    h("button", { class: "ghost small", onclick: () => addMember("Nuevo miembro", "", "none") }, ico("plus"), "Personalizado"));
  drawTeamBar();
  drawTeam();
}
function drawTeamBar() {
  const bar = $("#team-bar"), all = TEAM.all, t = TEAM.data;
  bar.innerHTML = "";
  const pick = h("select", { id: "team-pick", "aria-label": "Equipo que estás editando", onchange: (e) => selectTeam(e.target.value) },
    h("option", { value: "general" }, "Equipo general"),
    all.saved.length ? h("optgroup", { label: "Equipos guardados" }, all.saved.map((x) => h("option", { value: x.id }, x.name))) : null,
    TEAM.cur === "new" ? h("option", { value: "new" }, "Equipo nuevo (sin guardar)") : null);
  pick.value = TEAM.cur;
  const names = (ps) => ps.map((p) => `«${p.name}»`).join(", ");
  let info;
  if (TEAM.cur === "general") {
    info = h("span", { class: "muted small grow" }, "Trabaja en las conversaciones sin proyecto y en los proyectos sin equipo propio"
      + (all.general_projects.length ? ` (${names(all.general_projects)})` : "") + ".");
  } else {
    const used = (all.saved.find((x) => x.id === TEAM.cur) || {}).projects || [];
    info = h("span", { class: "muted small grow" }, used.length ? `Lo usan los proyectos ${names(used)}.` : "Aún no lo usa ningún proyecto: asígnalo desde la página del proyecto.");
  }
  bar.append(h("label", { class: "team-pick" }, "Editando", pick));
  if (TEAM.cur !== "general") {
    bar.append(h("input", { class: "team-name", placeholder: "Nombre del equipo (p. ej. «Juego 3D»)", value: t.name || "",
      oninput: (e) => { t.name = e.target.value; TEAM.dirty = true; } }));
  }
  bar.append(info,
    h("button", { class: "ghost small", title: "Guardar estos miembros como un equipo nuevo con nombre", onclick: () => {
      const copy = JSON.parse(JSON.stringify(TEAM.data.members)).map((m) => ({ ...m, id: Math.random().toString(36).slice(2, 10) }));
      selectTeam("new"); if (TEAM.cur !== "new") return;
      TEAM.data.members = copy; TEAM.data.name = ""; drawTeamBar(); drawTeam(); $(".team-name")?.focus();
    } }, ico("copy"), TEAM.cur === "general" ? "Guardar como equipo…" : "Duplicar"),
    h("button", { class: "ghost small", onclick: () => { selectTeam("new"); if (TEAM.cur === "new") { drawTeamBar(); drawTeam(); $(".team-name")?.focus(); } } }, ico("plus"), "Nuevo equipo"),
    TEAM.cur !== "general" && TEAM.cur !== "new" ? h("button", { class: "ghost small danger", onclick: async () => {
      if (!confirm(`¿Borrar el equipo «${t.name}»? Los proyectos que lo usan pasarán al equipo general.`)) return;
      try { TEAM.all = await api(`/api/teams/${TEAM.cur}`, { method: "DELETE" }); TEAM.dirty = false; selectTeam("general", true); toast("Equipo borrado", 2500); }
      catch (e) { toast(e.message, 6000); }
    } }, ico("trash"), "Borrar") : null);
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
  c.append(teamNode("dir", "G3G3AI", "director · el modelo del chat", t.enabled ? `${members.length} miembro(s)` + (t.name ? ` · ${t.name}` : "") : "equipo desactivado",
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
  try {
    if (TEAM.cur === "general") {
      await api("/api/team", { method: "PUT", body: TEAM.data });
      TEAM.all = await api("/api/teams");
    } else {
      if (!(TEAM.data.name || "").trim()) { toast("Ponle un nombre al equipo"); $(".team-name")?.focus(); return; }
      TEAM.all = await api(`/api/teams/${TEAM.data.id}`, { method: "PUT", body: { name: TEAM.data.name, members: TEAM.data.members } });
      TEAM.cur = TEAM.data.id;
    }
    TEAM.dirty = false; selectTeam(TEAM.cur, true); toast("Equipo guardado", 2500);
  } catch (e) { toast(e.message, 6000); }
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
