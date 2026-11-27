// G3G3AI · Arranque y paleta de comandos (Ctrl+K).
// Parte 8/8 de la interfaz: se cargan en orden y comparten el ámbito global.
// --- Arranque --------------------------------------------------------------------------
async function init() {
  if (location.search.includes("token=")) history.replaceState(null, "", "/");
  try { await refreshStatus(); await api("/api/conversations"); } catch { return; }
  await loadProviders();
  await loadConversations();
  loadProjects().then(renderProjectChip);
  const v = store.get("view", "chat");
  setView(v, true);
  S.code = v === "code";
  const last = store.get(convKey(), null);
  const lc = last && convCache.find((x) => x.id === last);
  if (lc && convSpace(lc) === space()) await openConversation(last).catch(newChat); else newChat();
  api("/api/onboarding").then((o) => { if (o.needed) openWizard(); }).catch(() => {});
  renderActiveTools(); setSending(false);
  setInterval(refreshStatus, 8000);
}
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("/sw.js").catch(() => {});
init();

// --- Paleta de comandos (Ctrl+K): conversaciones, acciones, secciones y ajustes en un solo buscador ---
function openPalette() {
  if ($("#palette")) { $("#palette").remove(); return; }
  const actions = [
    ["new", "Nueva conversación", () => { setView("chat"); newChat(); }],
    ["chat", "Ir a Chats", () => setView("chat")],
    ["project", "Ir a Proyectos", () => setView("projects")],
    ["code", "Ir a Code", () => setView("code")],
    ["cube", "Ir a Modelos", () => setView("models")],
    ["users", "Ir a Equipo", () => setView("team")],
    ["clock", "Ir a Tareas", () => setView("tasks")],
    ["folder", "Ir a Archivos", () => setView("files")],
    ["gear", "Abrir Ajustes", () => setView("settings")],
    ["globe", "Cambiar de modelo", () => { setView(S.code ? "code" : "chat"); openModelPicker(); }],
    ["mic", "Dictar por voz", () => { setView(S.code ? "code" : "chat"); toggleDictation(); }],
    ["download", "Exportar esta conversación", () => S.convId ? exportDialog(S.convId) : toast("No hay ninguna conversación abierta")],
    ["check", "Comprobar todo (diagnóstico)", () => { setView("settings"); openDiagnostics(); }],
  ];
  const input = h("input", { type: "search", placeholder: "Buscar conversaciones, acciones o ajustes…", autocomplete: "off" });
  const list = h("div", { class: "mp-list", role: "listbox" });
  const box = h("div", { class: "model-picker palette-box" }, input, list,
    h("div", { class: "mp-foot muted small" }, "↑↓ para moverte · Enter para abrir · Esc para cerrar"));
  const wrap = h("div", { id: "palette", class: "palette", onmousedown: (e) => { if (e.target === wrap) wrap.remove(); } }, box);
  let rows = [], hi = 0, ticket = 0;
  const row = (icon, title, sub, run) => {
    const el = h("div", { class: "mp-row", role: "option", onclick: () => { wrap.remove(); run(); } },
      h("span", { class: "mp-ico" }, ico(icon)), h("span", { class: "mp-name" }, h("b", {}, title), sub ? h("small", {}, sub) : null));
    rows.push({ el, run }); return el;
  };
  const mark = () => rows.forEach((r, i) => { r.el.classList.toggle("hi", i === hi); if (i === hi) r.el.scrollIntoView({ block: "nearest" }); });
  const sec = (t) => list.append(h("div", { class: "mp-sec" }, t));
  const draw = async () => {
    const q = input.value.trim(), nq = norm(q), t = ++ticket;
    list.innerHTML = ""; rows = []; hi = 0;
    const acts = actions.filter(([, title]) => !nq || norm(title).includes(nq));
    const convs = convCache.filter((c) => !nq || norm(c.title).includes(nq)).slice(0, q ? 8 : 6);
    if (acts.length) { sec("Acciones"); acts.forEach(([i, title, run]) => list.append(row(i, title, "", run))); }
    if (convs.length) { sec(q ? "Conversaciones" : "Recientes"); convs.forEach((c) => list.append(row("chat", c.title, dateGroup(c.updated), () => { setView("chat"); openConversation(c.id); }))); }
    if (nq.length >= 2) {
      const opts = FIELDS.filter(([k, label, , help]) => norm(label + " " + (help || "") + " " + k).includes(nq)).slice(0, 5);
      if (opts.length) { sec("Ajustes"); opts.forEach(([k, label]) => list.append(row("gear", label, "Ajustes", () => { setView("settings"); const s = $("#settings-search"); s.value = label; s.dispatchEvent(new Event("input")); }))); }
    }
    mark();
    if (q.length >= 3) {                       // también dentro de los mensajes
      try {
        const res = (await api("/api/search?" + qs({ q }))).filter((r) => r.snippet && !convs.some((c) => c.id === r.id)).slice(0, 6);
        if (t !== ticket || !res.length) return;
        sec("En los mensajes");
        res.forEach((r) => list.append(row("search", r.title, r.snippet, () => { setView("chat"); openConversation(r.id, r.message_id, q); })));
        mark();
      } catch { /* */ }
    }
  };
  input.addEventListener("input", draw);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); hi = Math.min(rows.length - 1, hi + 1); mark(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); hi = Math.max(0, hi - 1); mark(); }
    else if (e.key === "Enter") { e.preventDefault(); const r = rows[hi]; if (r) { wrap.remove(); r.run(); } }
    else if (e.key === "Escape") { e.preventDefault(); wrap.remove(); }
  });
  document.body.append(wrap); draw(); input.focus();
}
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
});
