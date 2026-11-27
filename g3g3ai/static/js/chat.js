// G3G3AI · Code, conversaciones, mensajes, vista previa, envío, dictado y lectura en voz alta.
// Parte 4/8 de la interfaz: se cargan en orden y comparten el ámbito global.
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
  "/export": () => { S.convId ? exportDialog(S.convId) : toast("No hay ninguna conversación abierta"); },
  "/help": () => { toast("/plan · /clear · /undo · /compact · /export · /init · /review · /test", 6000); },
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
// Búsqueda: títulos al instante y, al dejar de escribir, también dentro de los mensajes (en el servidor)
const CS = { ticket: 0, res: null, timer: null };
$("#conv-search").addEventListener("input", () => {
  const q = $("#conv-search").value.trim();
  renderConvList(); clearTimeout(CS.timer);
  if (q.length < 2) { CS.res = null; return; }
  const t = ++CS.ticket;
  CS.timer = setTimeout(async () => {
    try { const items = await api("/api/search?" + qs({ q })); if (t === CS.ticket) { CS.res = { q, items }; renderConvList(); } } catch { /* */ }
  }, 220);
});
$("#conv-search").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.target.value = ""; CS.res = null; renderConvList(); }
  else if (e.key === "Enter") $("#conv-list .conv-item")?.click();
});
// Resalta las palabras buscadas (sin tener en cuenta tildes ni mayúsculas)
function highlight(text, q) {
  const words = norm(q).split(/\s+/).filter(Boolean), frag = document.createDocumentFragment();
  if (!words.length || norm(text).length !== text.length) { frag.append(text); return frag; }
  const n = norm(text), marks = new Array(text.length).fill(false);
  for (const w of words) for (let i = n.indexOf(w); i >= 0; i = n.indexOf(w, i + 1)) marks.fill(true, i, i + w.length);
  let i = 0;
  while (i < text.length) {
    let j = i; while (j < text.length && marks[j] === marks[i]) j++;
    frag.append(marks[i] ? h("mark", {}, text.slice(i, j)) : text.slice(i, j)); i = j;
  }
  return frag;
}
function markIn(root, q) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  const words = norm(q).split(/\s+/).filter(Boolean);
  for (const t of nodes) if (words.some((w) => norm(t.nodeValue).includes(w))) t.replaceWith(highlight(t.nodeValue, q));
}
function renderSearchResults(ul, q, items) {
  if (!items.length) { ul.append(h("div", { class: "conv-group" }, "Sin resultados")); return; }
  ul.append(h("div", { class: "conv-group" }, `${items.length} ${items.length > 1 ? "conversaciones" : "conversación"}`));
  for (const c of items) {
    ul.append(h("div", { class: "conv-item search-hit" + (c.id === S.convId ? " active" : ""), onclick: () => { setView("chat"); openConversation(c.id, c.message_id, q); } },
      h("span", { class: "t", title: c.title }, highlight(c.title, q)),
      c.snippet ? h("span", { class: "snip" }, highlight(c.snippet, q)) : null,
      c.hits > 1 ? h("span", { class: "hits" }, `${c.hits} mensajes`) : null));
  }
}
async function loadConversations() {
  convCache = await api("/api/conversations");
  renderConvList();
}
// Exportar una conversación a Markdown, Word o PDF
async function exportConversation(id, fmt, tools = false) {
  const r = await fetch(`/api/conversations/${id}/export?` + qs({ fmt, tools }));
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  const cd = r.headers.get("Content-Disposition") || "", m = cd.match(/filename\*=UTF-8''([^;]+)/);
  const a = h("a", { href: URL.createObjectURL(await r.blob()), download: m ? decodeURIComponent(m[1]) : `conversacion.${fmt}` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 30000);
}
function exportDialog(id) {
  const tools = h("input", { type: "checkbox" });
  const fmts = [["md", "Markdown", "Texto con formato; se abre en cualquier editor, Obsidian, GitHub…"],
                ["docx", "Word", "Para editar, compartir o imprimir"],
                ["pdf", "PDF", "Para enviar o archivar tal cual"]];
  const dlg = h("dialog", { class: "export-dialog" },
    h("h3", {}, "Exportar conversación"),
    h("div", { class: "export-opts" }, ...fmts.map(([f, name, sub]) =>
      h("button", { class: "export-opt", "data-fmt": f, onclick: async (e) => {
        const b = e.currentTarget; b.disabled = true;
        try { await exportConversation(id, f, tools.checked); dlg.close(); toast(`Exportada como ${name}`); }
        catch (err) { toast(err.message, 6000); } finally { b.disabled = false; }
      } }, h("b", {}, name), h("small", {}, sub)))),
    h("label", { class: "check" }, tools, " Incluir qué herramientas usó la IA"),
    h("div", { class: "row end" }, h("button", { class: "ghost", onclick: () => dlg.close() }, "Cancelar")));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg); dlg.showModal();
}
$("#top-export").addEventListener("click", () => S.convId && exportDialog(S.convId));

// Fijar (arriba del todo) y favoritas (estrella; filtro con el botón ☆ junto al buscador)
let favOnly = store.get("conv_fav_only", false);
async function markConv(c, fields) {
  Object.assign(c, { ...fields, pinned: "pinned" in fields ? (fields.pinned ? Date.now() / 1000 : null) : c.pinned });
  renderConvList();
  try { await api(`/api/conversations/${c.id}`, { method: "PATCH", body: fields }); }
  catch (e) { toast(e.message, 5000); loadConversations(); }
}
function syncFavButton() {
  const b = $("#conv-favs"); b.classList.toggle("on", favOnly); b.setAttribute("aria-pressed", String(favOnly));
  b.title = favOnly ? "Mostrar todas las conversaciones" : "Ver sólo las favoritas";
}
$("#conv-favs").addEventListener("click", () => { favOnly = !favOnly; store.set("conv_fav_only", favOnly); syncFavButton(); renderConvList(); });
syncFavButton();
function renderConvList() {
  $("#top-export").classList.toggle("hidden", !S.convId);
  const ul = $("#conv-list"), q = $("#conv-search").value.trim().toLowerCase();
  const frag = document.createDocumentFragment();
  let group = null;
  if (q && CS.res && CS.res.q.toLowerCase() === q) { ul.innerHTML = ""; renderSearchResults(ul, CS.res.q, CS.res.items.filter((c) => convSpace(c) === space())); return; }
  const list = convCache.filter((c) => convSpace(c) === space() && (!q || norm(c.title).includes(norm(q))) && (!favOnly || c.favorite));
  const pinned = list.filter((c) => c.pinned).sort((a, b) => b.pinned - a.pinned);
  if (!list.length) frag.append(h("div", { class: "conv-group" }, q ? "Sin resultados" : favOnly ? "Aún no hay favoritas: pulsa ☆ en una conversación" : S.code ? "Aún no hay sesiones de Code: elige una carpeta y pide lo que quieras" : "Aún no hay conversaciones"));
  if (pinned.length) frag.append(h("div", { class: "conv-group" }, "Fijadas"), ...pinned.map(convItem));
  for (const c of list) {
    if (c.pinned) continue;
    const g = dateGroup(c.updated);
    if (g !== group) { group = g; frag.append(h("div", { class: "conv-group" }, g)); }
    frag.append(convItem(c));
  }
  ul.replaceChildren(frag);
}
function convItem(c) {
  return h("div", { class: "conv-item" + (c.id === S.convId ? " active" : "") + (c.pinned ? " pinned" : ""), "data-id": c.id, onclick: () => { setView("chat"); openConversation(c.id); } },
      c.favorite ? h("span", { class: "conv-star", title: "Favorita" }, ico("star")) : null,
      h("span", { class: "t", title: c.title + (c.workdir ? `\n${c.workdir}` : "") }, c.title,
        c.kind === "code" && c.workdir ? h("small", { class: "conv-dir" }, baseName(c.workdir)) : null),
      h("span", { class: "acts" },
        h("button", { title: c.pinned ? "Desfijar" : "Fijar arriba", "aria-label": c.pinned ? "Desfijar" : "Fijar arriba", class: c.pinned ? "on" : "",
          onclick: (e) => { e.stopPropagation(); markConv(c, { pinned: !c.pinned }); } }, ico("pin")),
        h("button", { title: c.favorite ? "Quitar de favoritas" : "Marcar como favorita", "aria-label": c.favorite ? "Quitar de favoritas" : "Marcar como favorita", class: c.favorite ? "on" : "",
          onclick: (e) => { e.stopPropagation(); markConv(c, { favorite: !c.favorite }); } }, ico("star")),
        h("button", { title: "Más acciones", "aria-label": "Más acciones", class: "conv-more", onclick: (e) => { e.stopPropagation(); convMenu(c, e.currentTarget); } }, "⋯")));
}
// Menú ⋯ de una conversación: renombrar, mover, exportar, borrar
function convMenu(c, anchor) {
  document.querySelector(".conv-menu")?.remove();
  const item = (icon, label, fn, cls = "") => h("button", { class: cls, onclick: (e) => { e.stopPropagation(); menu.remove(); fn(); } }, icon, label);
  const menu = h("div", { class: "conv-menu", role: "menu" },
    item(ico("pencil"), "Renombrar", async () => {
      const t = prompt("Nuevo título", c.title);
      if (t) { await api(`/api/conversations/${c.id}`, { method: "PATCH", body: { title: t } }); loadConversations(); if (S.convId === c.id) $("#top-title").textContent = t; }
    }),
    item(ico("pin"), c.pinned ? "Desfijar" : "Fijar arriba", () => markConv(c, { pinned: !c.pinned })),
    item(ico("star"), c.favorite ? "Quitar de favoritas" : "Marcar como favorita", () => markConv(c, { favorite: !c.favorite })),
    item(ico("project"), "Mover a un proyecto", () => moveToProject(c)),
    item(ico("download"), "Exportar", () => exportDialog(c.id)),
    item(ico("trash"), "Borrar", async () => {
      if (!confirm("¿Borrar esta conversación?")) return;
      await api(`/api/conversations/${c.id}`, { method: "DELETE" });
      if (S.convId === c.id) newChat(); else loadConversations();
    }, "danger"));
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();
  menu.style.top = Math.min(r.bottom + 4, innerHeight - menu.offsetHeight - 8) + "px";
  menu.style.left = Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8)) + "px";
  setTimeout(() => document.addEventListener("click", function close(ev) {
    if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener("click", close); }
  }), 0);
}
async function openConversation(id, focusMsg, q) {
  const seq = S.openSeq = (S.openSeq || 0) + 1;
  const conv = await api(`/api/conversations/${id}`);
  if (seq !== S.openSeq) return;                         // se pidió abrir otra entretanto: gana la última
  S.conv = conv;
  if ((S.view === "chat" || S.view === "code") && convSpace(conv) !== S.view) setView(convSpace(conv), true);  // es del otro apartado
  S.convId = id; S.system = undefined; store.set(convKey(convSpace(conv)), id);
  if (S.conv.provider) {
    const v = `${S.conv.provider}::${S.conv.model}`;  // las conversaciones en Auto no cambian el selector
    if ([...$("#model-select").options].some((o) => o.value === v)) { $("#model-select").value = v; updateFavButton(); }
  }
  S.workdir = undefined;
  S.projectId = S.conv.project_id || null;
  if (focusMsg) { const k = S.conv.messages.findIndex((m) => String(m.id) === String(focusMsg)); if (k >= 0) S.focusIndex = k; }
  renderMessages(); renderConvList(); refreshChanges(); refreshContext(); renderProjectChip(); renderQueue();
  if (focusMsg) requestAnimationFrame(() => {      // desde la búsqueda: ir al mensaje y resaltarlo
    const el = $(`#messages .msg[data-id="${focusMsg}"]`); if (!el) return;
    el.scrollIntoView({ block: "center" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 2400);
    if (q) for (const b of el.querySelectorAll(".bubble, .md")) markIn(b, q);
  });
  if (S.code) { S.workdir = S.conv.workdir || undefined; renderCodePanel(); }
  if (S.view === "chat" || S.view === "code") $("#top-title").textContent = S.conv.title;
  closeSide();
}
function newChat() {
  if (S.code) queueMicrotask(() => { S.workdir = store.get("code_dir", "") || undefined; renderCodePanel(); });
  if (S.live) S.live.isNew = false;
  S.openSeq = (S.openSeq || 0) + 1;                     // una apertura pendiente ya no debe pisar la nueva
  S.convId = null; S.conv = null; S.system = undefined; S.projectId = null; store.set(convKey(), null); renderProjectChip();
  renderMessages(); loadConversations(); closeSide(); $("#top-title").textContent = ""; renderQueue();
  if (!isMobile()) $("#input").focus();
}
$("#new-chat").addEventListener("click", () => { setView(S.code ? "code" : "chat", true); newChat(); });

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
  // Conversaciones largas: primero los últimos mensajes (lo que se ve) y los anteriores al subir
  const FIRST = 40, want = S.focusIndex ?? msgs.length, from = Math.max(0, Math.min(msgs.length - FIRST, want - 5));
  S.focusIndex = undefined;
  if (from > 0) {
    const more = h("button", { class: "ghost small load-older" }, `Ver ${from} mensaje${from > 1 ? "s" : ""} anteriores`);
    let upto = from;
    const older = () => {
      if (!upto || !more.isConnected) return;
      const start = Math.max(0, upto - FIRST), prevH = box.scrollHeight, prevTop = box.scrollTop, frag = document.createDocumentFragment();
      msgs.slice(start, upto).forEach((m, k) => frag.append(messageEl(m, start + k)));
      more.after(frag); upto = start;
      box.scrollTop = prevTop + (box.scrollHeight - prevH);          // la vista no salta
      if (!upto) more.remove(); else more.textContent = `Ver ${upto} mensaje${upto > 1 ? "s" : ""} anteriores`;
    };
    more.onclick = older;
    box.append(more);
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting) && box.scrollTop > 0) older(); }, { root: box });
    io.observe(more);
  }
  msgs.slice(from).forEach((m, k) => box.append(messageEl(m, from + k)));
  if (S.live && S.streaming && S.live.conv && S.live.conv === S.convId) box.append(S.live.el);
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
  if (streaming && !content && !reasoning && !(tools || []).length && !extra.progress && extra.t0) {
    const secs = Math.round((Date.now() - extra.t0) / 1000);
    frag.append(h("div", { class: "waiting" }, h("span", { class: "dots" }, h("i"), h("i"), h("i")),
      extra.status ? "" : extra.reading ? `Leyendo ${extra.reading > 1 ? `los ${extra.reading} adjuntos` : "el adjunto"}… ${secs} s`
        : (secs < 2 ? "Pensando…" : `Pensando… ${secs} s`)));
  }
  const pg = extra.progress;
  if (pg && streaming && pg.done < pg.total) {
    const pct = Math.round(100 * pg.done / pg.total);
    const left = pg.ms && pg.done ? Math.round((pg.ms / pg.done) * (pg.total - pg.done) / 1000) : null;
    frag.append(h("div", { class: "read-progress", title: "El modelo local lee la conversación y los documentos antes de responder. La próxima vez reutiliza lo ya leído." },
      h("div", { class: "rp-text" }, `Leyendo el contexto… ${pct} % · ${fmtNum(pg.done)} de ${fmtNum(pg.total)} tokens` + (left != null && left > 2 ? ` · ~${left < 90 ? left + " s" : Math.round(left / 60) + " min"}` : "")),
      h("div", { class: "rp-bar" }, h("span", { style: `width:${pct}%` }))));
  }
  if (extra.route) frag.append(h("div", { class: "route" }, `Auto: ${extra.route.model}` + (extra.route.reason ? ` — ${extra.route.reason}` : "")));
  for (const f of extra.fallbacks || []) frag.append(h("div", { class: "route warn" }, "↪ falló " + f + ", probando el otro modelo…"));
  const { think, body, open } = splitThink(content || "");
  const r = [reasoning, think].filter(Boolean).join("\n");
  if (r) {
    const d = h("details", { class: "thinking", open: (extra.thinkOpen ?? (streaming && (open || !body))) ? true : false },
      h("summary", { onclick: () => { if (extra.onThinkToggle) extra.onThinkToggle(!d.open); } }, ico("brain"), streaming && !body ? "Pensando…" : "Razonamiento"), h("pre", {}, r));
    frag.append(d);
  }
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
  if (extra.liveBubble) frag.append(extra.liveBubble);       // respuesta en curso: el mismo nodo (ver liveMd)
  else {
    const b = h("div", { class: "bubble" + (streaming ? " cursor" : "") });
    b.innerHTML = md(body);
    frag.append(b);
  }
  const fileIcon = (p) => ({ docx: "📘", doc: "📘", xlsx: "📗", xlsm: "📗", csv: "📗", pptx: "📙", pdf: "📕", exe: "⚙️", py: "🐍" }[String(p).split(".").pop().toLowerCase()] || "📄");
  const outs = [...new Set(extra.files || [])];
  if (outs.length) frag.append(h("div", { class: "file-cards" }, outs.map(fileCard)));
  const imgs = extra.images || [];
  if (imgs.length) frag.append(h("div", { class: "gen-images" }, imgs.map((p) =>
    h("a", { href: fileUrl(p), target: "_blank", title: p }, h("img", { src: fileUrl(p), alt: "imagen generada", loading: "lazy" })))));
  return frag;
}
// ‹ 2/3 › para cambiar entre versiones (editar o regenerar guarda la anterior como rama)
function branchNav(pos) {
  const b = S.conv?.branches?.[String(pos)];
  if (!b || b.n < 2 || b.i < 0) return null;
  const go = async (step) => {
    if (S.streaming) return;
    S.conv = await api(`/api/conversations/${S.convId}/branch`, { method: "POST", body: { position: pos, step } });
    renderMessages(); refreshContext();
  };
  return h("span", { class: "branch-nav", title: "Versiones de este mensaje" },
    h("button", { class: "act", disabled: b.i === 0, title: "Versión anterior", onclick: () => go(-1) }, "‹"),
    h("span", {}, `${b.i + 1}/${b.n}`),
    h("button", { class: "act", disabled: b.i === b.n - 1, title: "Versión siguiente", onclick: () => go(1) }, "›"));
}
function messageEl(m, pos = -1) {
  const el = h("div", { class: `msg ${m.role}`, "data-id": m.id });
  if (m.role === "user") {
    // Adjuntos siempre visibles, encima del mensaje (como en Claude): imágenes en miniatura y tarjetas de archivo
    const att = m.meta?.attachments || [];
    const imgs = att.filter((a) => a.kind === "image" || (!a.kind && isImage(a.name)));
    const docs = att.filter((a) => !imgs.includes(a));
    if (imgs.length) el.append(h("div", { class: "msg-images" }, imgs.map((a) =>
      h("img", { src: fileUrl(a.path), alt: a.name, loading: "lazy", onclick: () => previewFile(a.path) }))));
    if (docs.length) el.append(h("div", { class: "msg-files" }, docs.map((a) => {
      const ext = (a.name.split(".").pop() || "").toUpperCase().slice(0, 4);
      return h("button", { class: "att-card", title: a.path, onclick: () => previewFile(a.path) },
        h("span", { class: "att-ext", "data-ext": ext }, ext),
        h("span", { class: "att-name" }, a.name));
    })));
    if (m.content) el.append(h("div", { class: "bubble" }, m.content));
    el.append(h("div", { class: "meta" },
      h("button", { class: "act", title: "Copiar", onclick: () => { copyText(m.content); } }, ico("copy")),
      h("button", { class: "act", title: "Editar", onclick: () => editFrom(m, el) }, ico("pencil")),
      branchNav(pos),
      (S.checkpoints || []).some((c) => c.id >= m.id) ? h("button", { class: "act", title: "Volver aquí: los archivos que la IA tocó desde este mensaje vuelven a como estaban antes", onclick: () => rewindTo(m) }, ico("rewind")) : null));
  } else {
    el.append(assistantInner(m.content, m.reasoning, m.meta?.tools, false, { images: m.meta?.images || [], files: m.meta?.files || [], todos: m.meta?.todos || [] }));
    const st = m.meta?.stats || {};
    el.append(h("div", { class: "meta" },
      h("button", { class: "act", title: "Copiar", onclick: () => { copyText(m.content); } }, ico("copy")),
      h("button", { class: "act", title: "Volver a generar (la respuesta actual se conserva)", onclick: () => regenerate(m) }, ico("retry")),
      m.meta?.log ? h("button", { class: "act", title: "Detalles: qué hizo la IA, avisos y tiempos", onclick: () => showGenLog(m) }, ico("info")) : null,
      "speechSynthesis" in window ? h("button", { class: "act speak", title: "Leer en voz alta", onclick: (e) => speak(m.content, e.currentTarget) }, ico("speaker")) : null,
      branchNav(pos),
      m.meta?.finish ? h("button", { class: "act continue", title: "La respuesta quedó incompleta",
        onclick: () => { if (!S.streaming) send("Continúa exactamente donde lo dejaste.", []); } }, ico("play"), "Continuar") : null,
      h("span", { class: "meta-model", title: (m.meta?.provider === "local" ? "Modelo local" : "API") + (m.meta?.route ? " · " + m.meta.route : "") }, m.meta?.model || ""),
      st.tokens_per_second ? h("span", {}, `${st.tokens_per_second.toFixed(1)} tok/s`) : null,
      m.meta?.usage ? h("span", { title: "Tokens de entrada/salida de toda la respuesta (incluidas las herramientas)" }, `↑${m.meta.usage.in} ↓${m.meta.usage.out}` + (m.meta.usage.cost ? ` · ~$${m.meta.usage.cost.toFixed(m.meta.usage.cost < 0.01 ? 4 : 3)}` : "")) : null));
  }
  return el;
}
$("#messages").addEventListener("click", (e) => {
  const card = e.target.closest(".art-card");
  if (card) { openArtifactCard(card); return; }
  const pre = e.target.closest("pre");
  if (!pre) return;
  const code = pre.querySelector("code")?.textContent || "";
  if (e.target.classList.contains("copy")) copyText(code, "Código copiado");
  if (e.target.classList.contains("preview")) openArtifact(code, artKind(pre.querySelector("code")?.dataset.lang || "", code));
});
// --- Panel de vista previa (HTML / SVG en un iframe aislado) -----------------------------------
function artKind(lang, code) {
  if (lang === "mermaid") return "mermaid";
  if (lang === "svg" || (["", "xml"].includes(lang) && /^\s*<svg/i.test(code))) return "svg";
  if (lang === "html" || (["", "xml"].includes(lang) && /^\s*<(!doctype|html)/i.test(code))) return "html";
  return null;
}
function artMeta(kind, code) {
  const t = code.match(/<title>([^<]{1,80})<\/title>/i)?.[1] || code.match(/<h1[^>]*>([^<]{1,80})<\/h1>/i)?.[1];
  if (kind === "mermaid") {
    const first = code.trim().split(/\s/)[0].toLowerCase();
    const names = { graph: "Diagrama de flujo", flowchart: "Diagrama de flujo", sequencediagram: "Diagrama de secuencia", classdiagram: "Diagrama de clases",
      gantt: "Diagrama de Gantt", pie: "Gráfico circular", erdiagram: "Diagrama entidad-relación", mindmap: "Mapa mental", timeline: "Cronología", statediagram: "Diagrama de estados" };
    return { icon: "share", title: code.match(/^\s*title\s+(.+)$/m)?.[1]?.trim() || names[first.replace(/-v2$/, "")] || "Diagrama", label: "Diagrama", ext: "mmd" };
  }
  if (kind === "svg") return { icon: "image", title: t || "Imagen SVG", label: "SVG", ext: "svg" };
  return { icon: "globe", title: t?.trim() || "Página web", label: "HTML", ext: "html" };
}
const ART = { list: [], idx: 0 };
function artifactsInView() {
  return [...$$("#messages .art-card")].map((c) => ({ kind: c.dataset.kind, code: c.querySelector(".art-code").textContent, card: c }));
}
function openArtifactCard(card) {
  ART.list = artifactsInView(); ART.idx = Math.max(0, ART.list.findIndex((a) => a.card === card));
  const a = ART.list[ART.idx]; openArtifact(a.code, a.kind, true);
}
let mermaidReady = null;
function loadMermaid() {
  mermaidReady ??= new Promise((ok, fail) => {
    const s = document.createElement("script"); s.src = "/static/vendor/mermaid.min.js";
    s.onload = () => { window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default" }); ok(window.mermaid); };
    s.onerror = () => { mermaidReady = null; fail(new Error("No se pudo cargar el motor de diagramas")); };
    document.head.append(s);
  });
  return mermaidReady;
}
async function artDoc(code, kind) {
  const wrap = (body, bg = "#fff") => `<!doctype html><meta charset="utf-8"><body style="margin:0;display:grid;place-items:center;min-height:100vh;background:${bg};font-family:system-ui,sans-serif">${body}</body>`;
  if (kind === "svg") return wrap(code);
  if (kind === "mermaid") {
    try {
      const m = await loadMermaid();
      const { svg } = await m.render("mmd" + Date.now(), code);
      return wrap(`<div style="padding:16px;max-width:100%">${svg}</div>`);
    } catch (e) {
      return wrap(`<pre style="color:#b3261e;white-space:pre-wrap;padding:16px">El diagrama tiene un error de sintaxis:\n${esc(String(e.message || e))}</pre>`);
    }
  }
  return code;
}
async function openArtifact(code, kind, fromCard = false) {
  if (!fromCard) ART.list = [];
  kind = kind || "html";
  const meta = artMeta(kind, code), doc = await artDoc(code, kind);
  $("#artifact-frame").srcdoc = doc;
  $("#artifact-src").textContent = code;
  $("#artifact-title").textContent = meta.title;
  $("#artifact-frame").classList.remove("hidden"); $("#artifact-src").classList.add("hidden");
  $("#artifact-code").textContent = "Código";
  const multi = ART.list.length > 1;
  $("#artifact-ver").classList.toggle("hidden", !multi);
  if (multi) {
    $("#artifact-vn").textContent = `${ART.idx + 1} / ${ART.list.length}`;
    $("#artifact-prev").disabled = ART.idx === 0; $("#artifact-next").disabled = ART.idx === ART.list.length - 1;
  }
  $$("#messages .art-card").forEach((c) => c.classList.toggle("open", fromCard && c === ART.list[ART.idx]?.card));
  $("#artifact").classList.remove("hidden");
  $("#artifact-open").onclick = () => window.open(URL.createObjectURL(new Blob([doc], { type: "text/html" })), "_blank", "noopener");
  $("#artifact-copy").onclick = () => copyText(code, "Código copiado");
  $("#artifact-dl").onclick = () => {
    const a = h("a", { href: URL.createObjectURL(new Blob([code], { type: "text/plain" })), download: meta.title.replace(/[\\/:*?"<>|]+/g, " ").trim() + "." + meta.ext });
    document.body.append(a); a.click(); a.remove();
  };
}
const artStep = (d) => { const i = ART.idx + d; if (ART.list[i]) { ART.idx = i; openArtifact(ART.list[i].code, ART.list[i].kind, true); ART.list[i].card.scrollIntoView({ block: "nearest", behavior: "smooth" }); } };
$("#artifact-prev").addEventListener("click", () => artStep(-1));
$("#artifact-next").addEventListener("click", () => artStep(1));
$("#artifact-close").addEventListener("click", () => { $("#artifact").classList.add("hidden"); $$("#messages .art-card.open").forEach((c) => c.classList.remove("open")); });
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
// Editar en el sitio, como en Claude: la versión anterior y sus respuestas se guardan como rama
function editFrom(m, el) {
  if (S.streaming || !el || el.querySelector(".edit-box")) return;
  const bubble = el.querySelector(".bubble"), meta = el.querySelector(".meta");
  const ta = h("textarea", { class: "edit-text", rows: 3 }, m.content);
  const done = () => { box.remove(); bubble.classList.remove("hidden"); meta?.classList.remove("hidden"); };
  const submit = async () => {
    const t = ta.value.trim(); if (!t) return;
    if (t === m.content.trim()) return done();
    S.conv = await api(`/api/conversations/${S.convId}/fork`, { method: "POST", body: { message_id: m.id } });
    renderMessages();
    send(t, (m.meta?.attachments || []).map((a) => a.path));
  };
  const box = h("div", { class: "edit-box" }, ta, h("div", { class: "row end" },
    h("button", { class: "ghost small", onclick: done }, "Cancelar"), h("button", { class: "primary small", onclick: submit }, "Enviar")));
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
    else if (e.key === "Escape") { e.preventDefault(); done(); }
  });
  bubble.classList.add("hidden"); meta?.classList.add("hidden"); bubble.after(box);
  ta.style.height = ta.scrollHeight + "px"; ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
}
async function regenerate(m) {
  if (S.streaming) return;
  S.conv = await api(`/api/conversations/${S.convId}/fork`, { method: "POST", body: { message_id: m.id } });
  renderMessages();
  send("", [], true);
}

// --- Envío con streaming -----------------------------------------------------------------
function setSending(on) {
  const b = $("#send-btn");
  b.innerHTML = ""; b.append(ico(on ? "stop" : "arrowUp")); b.classList.toggle("stop", on);
  b.title = on ? "Detener" : "Enviar"; b.dataset.state = on ? "sending" : "idle";
  if (on && typeof syncSendButton === "function") syncSendButton();
  if (typeof renderQueue === "function" && S.queue) renderQueue();
}
const input = $("#input");
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; });
// --- Dictado por voz ------------------------------------------------------------------------
// Graba en el navegador a WAV de 16 kHz (lo que usa Whisper, sin ffmpeg) y lo transcribe G3G3AI:
// con whisper.cpp local, con Groq/OpenAI, o —si no hay ninguno— con el reconocimiento del navegador.
const VOICE = { rec: null, timer: null };
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function insertDictation(text) {
  text = (text || "").trim(); if (!text) { toast("No se entendió nada; prueba a hablar más cerca del micrófono"); return; }
  const a = input.selectionStart ?? input.value.length, b = input.selectionEnd ?? a, before = input.value.slice(0, a);
  const sep = before && !/\s$/.test(before) ? " " : "";
  input.value = before + sep + text + input.value.slice(b);
  const pos = (before + sep + text).length; input.setSelectionRange(pos, pos);
  input.dispatchEvent(new Event("input")); input.focus();
}
function micState(state, label) {
  const b = $("#mic-btn"); b.dataset.state = state || "";
  b.title = { rec: "Detener y transcribir (Esc cancela)", busy: "Transcribiendo…" }[state] || "Dictar (Ctrl+Mayús+Espacio) · clic derecho: configurar";
  let t = $("#mic-time");
  if (state === "rec") { if (!t) { t = h("span", { id: "mic-time", class: "mic-time" }); b.before(t); } t.textContent = label || "0:00"; }
  else if (state === "busy") { if (!t) { t = h("span", { id: "mic-time", class: "mic-time" }); b.before(t); } t.textContent = "Transcribiendo…"; }
  else t?.remove();
}
function encodeWav(chunks, rate) {
  const len = chunks.reduce((n, c) => n + c.length, 0), target = 16000, ratio = rate / target;
  const out = new Int16Array(Math.floor(len / ratio));
  const all = new Float32Array(len); let o = 0; for (const c of chunks) { all.set(c, o); o += c.length; }
  for (let i = 0; i < out.length; i++) {          // promedio de cada tramo: submuestreo sin aliasing grave
    const s = Math.floor(i * ratio), e = Math.min(len, Math.floor((i + 1) * ratio)); let acc = 0;
    for (let j = s; j < e; j++) acc += all[j];
    const v = Math.max(-1, Math.min(1, acc / Math.max(1, e - s))); out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  const buf = new ArrayBuffer(44 + out.length * 2), dv = new DataView(buf);
  const str = (p, s) => [...s].forEach((ch, i) => dv.setUint8(p + i, ch.charCodeAt(0)));
  str(0, "RIFF"); dv.setUint32(4, 36 + out.length * 2, true); str(8, "WAVEfmt "); dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true); dv.setUint16(22, 1, true); dv.setUint32(24, target, true); dv.setUint32(28, target * 2, true);
  dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); str(36, "data"); dv.setUint32(40, out.length * 2, true);
  new Int16Array(buf, 44).set(out);
  return new Blob([buf], { type: "audio/wav" });
}
async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) { toast("El micrófono sólo funciona en este mismo equipo o con https.", 6000); return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } }); }
  catch (e) { toast("No hay acceso al micrófono: " + (e.name === "NotAllowedError" ? "permiso denegado" : e.message), 6000); return; }
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  const src = ac.createMediaStreamSource(stream), node = ac.createScriptProcessor(4096, 1, 1), chunks = [];
  node.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  src.connect(node); node.connect(ac.destination);
  const t0 = Date.now();
  VOICE.rec = { stream, ac, node, src, chunks, rate: ac.sampleRate };
  micState("rec");
  VOICE.timer = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    micState("rec", `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
    if (s >= 300) stopRecording(true);           // tope de 5 minutos
  }, 500);
}
async function stopRecording(send) {
  const r = VOICE.rec; if (!r) return;
  VOICE.rec = null; clearInterval(VOICE.timer);
  r.node.disconnect(); r.src.disconnect(); r.stream.getTracks().forEach((t) => t.stop()); r.ac.close();
  if (!send) { micState(""); return; }
  micState("busy");
  try {
    const res = await fetch("/api/voice/transcribe", { method: "POST", headers: { "Content-Type": "audio/wav" }, body: encodeWav(r.chunks, r.rate) });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(j.detail || res.statusText);
    insertDictation(j.text);
  } catch (e) { toast(e.message, 7000); }
  finally { micState(""); }
}
function browserDictation() {
  const r = new SR(); r.lang = navigator.language || "es-ES"; r.interimResults = false;
  VOICE.sr = r; micState("rec", "Escuchando…");
  r.onresult = (e) => insertDictation([...e.results].map((x) => x[0].transcript).join(" "));
  r.onerror = (e) => {
    if (e.error === "no-speech" || e.error === "aborted") return toast("No se oyó nada");
    voiceSetupDialog();          // p. ej. la ventana de escritorio no trae reconocimiento: se ofrecen las otras opciones
  };
  r.onend = () => { VOICE.sr = null; micState(""); };
  r.start();
}
async function toggleDictation() {
  if (VOICE.rec) return stopRecording(true);
  if (VOICE.sr) return VOICE.sr.stop();
  if ($("#mic-btn").dataset.state === "busy") return;
  let st; try { st = await api("/api/voice"); } catch { st = { use: null }; }
  if (st.use === "local" || st.use === "cloud") return startRecording();
  if (SR && (st.use === "browser" || st.engine === "auto")) return browserDictation();
  voiceSetupDialog(st);
}
async function voiceSetupDialog(st) {
  st = st || await api("/api/voice");
  const body = h("div", { class: "voice-setup" });
  const dlg = h("dialog", { class: "export-dialog" }, h("h3", {}, "Dictado por voz"), body,
    h("div", { class: "row end" }, h("button", { class: "ghost", onclick: () => dlg.close() }, "Cerrar")));
  dlg.addEventListener("close", () => dlg.remove());
  const status = st.use === "local" ? `Listo: se transcribe en este equipo con ${st.model}.`
    : st.use === "cloud" ? `Se transcribe con ${st.cloud} (el audio sale del equipo). Descarga un modelo para hacerlo en local.`
    : "Aún no está configurado.";
  body.append(h("p", {}, status));
  if (st.binary) {
    body.append(h("p", { class: "muted" }, "Modelo de voz para usar en local (privado, sin Internet):"));
    for (const [name, desc] of Object.entries(st.models)) {
      const btn = h("button", { class: "export-opt", onclick: async () => {
        btn.disabled = true;
        try {
          const d = await api("/api/voice/setup", { method: "POST", body: { model: name } });
          const tick = setInterval(async () => {
            const all = await api("/api/hub/downloads"), x = all.find((y) => y.id === d.id);
            if (!x) return;
            btn.querySelector("small").textContent = x.status === "downloading" ? `Descargando… ${x.total ? Math.round(100 * x.done / x.total) : 0} %` : x.status === "done" ? "✔ Listo" : x.status === "error" ? "✕ " + x.error : "Preparando…";
            if (["done", "error", "cancelled"].includes(x.status)) { clearInterval(tick); btn.disabled = false; if (x.status === "done") toast("Dictado listo: pulsa el micrófono y habla"); }
          }, 800);
        } catch (e) { toast(e.message, 6000); btn.disabled = false; }
      } }, h("b", {}, name.replace(/^ggml-|\.bin$/g, "") + (name === st.model ? " ✔" : "")), h("small", {}, desc));
      body.append(btn);
    }
  } else {
    body.append(h("p", { class: "muted" }, "Para dictar en local hace falta whisper.cpp: viene incluido en la edición completa para Windows. " +
      "En Linux instálalo (whisper-cli) o indica su ruta en Ajustes."),
      h("p", { class: "muted" }, "También puedes usar Groq (tiene plan gratuito) u OpenAI: añade el proveedor y el dictado lo usará."),
      h("button", { class: "primary", onclick: () => { dlg.close(); providerDialog("groq"); } }, "Añadir Groq"));
  }
  document.body.append(dlg); dlg.showModal();
}
$("#mic-btn").addEventListener("click", toggleDictation);
$("#mic-btn").addEventListener("contextmenu", (e) => { e.preventDefault(); voiceSetupDialog(); });   // clic derecho: configurar
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.code === "Space") { e.preventDefault(); toggleDictation(); }
  else if (e.key === "Escape" && VOICE.rec) { e.preventDefault(); stopRecording(false); toast("Dictado cancelado"); }
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && !matchMedia("(pointer: coarse)").matches) {
    e.preventDefault();
    if (S.streaming) { enqueueComposer(); return; }   // mientras trabaja se puede seguir escribiendo: va a la cola
    $("#send-btn").click();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && S.streaming && !document.querySelector("dialog[open]")) {
    S.stopped = true; S.streaming.abort(); toast(queueFor().length ? "Detenido. Lo que está en cola espera a que lo envíes" : "Detenido");
  }
  if (e.key === "Tab" && e.shiftKey && document.activeElement === input) {  // Mayús+Tab: cambia el modo de permisos
    e.preventDefault();
    const m = $("#mode-select"), order = ["normal", "edits", "plan"];
    m.value = order[(order.indexOf(m.value) + 1) % order.length]; m.dispatchEvent(new Event("change"));
    toast("Modo: " + { normal: "Normal", edits: "Aceptar ediciones", plan: "Plan" }[m.value]);
  }
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "o") { e.preventDefault(); setView(S.code ? "code" : "chat"); newChat(); }
});
$("#send-btn").addEventListener("click", () => {
  if (S.streaming) {
    if (input.value.trim() || S.attachments.length) { enqueueComposer(); return; }   // hay algo escrito: a la cola
    S.stopped = true; S.streaming.abort(); return;
  }
  const text = input.value.trim();
  if (!text && !S.attachments.length) return;
  const att = S.attachments.map((a) => a.path);
  input.value = ""; input.style.height = "auto"; S.attachments = []; renderAttachments(); syncSendButton();
  dispatchMessage(text, att);
});
// Envía un texto (con /comandos) y adjuntos
function dispatchMessage(text, att) {
  let outgoing = text;
  if (text.startsWith("/")) {
    const r = runSlash(text);
    if (r !== null) { if (!r) return; outgoing = r; }
  }
  send(outgoing, att);
}

// --- Cola de mensajes (como en Claude Code) ------------------------------------------------------
// Mientras la IA responde puedes seguir escribiendo: cada mensaje queda en la cola, a la vista, y se envía
// solo al terminar. «Enviar ahora» corta la respuesta en curso y lo manda ya; también se puede editar o quitar.
S.queue = [];
const qConv = (q) => q.conv || q.live?.conv || null;
function queueFor(cid = S.convId) { return S.queue.filter((q) => qConv(q) === (cid || null) || (!qConv(q) && q.live && q.live === S.live && !cid)); }
function enqueueComposer() {
  const text = input.value.trim(), att = S.attachments.map((a) => a.path);
  if (!text && !att.length) return;
  S.queue.push({ id: Math.random().toString(36).slice(2), text, att, conv: S.convId || null, live: S.live });
  input.value = ""; input.style.height = "auto"; S.attachments = []; renderAttachments();
  renderQueue(); syncSendButton();
}
function renderQueue() {
  const box = $("#queue"), items = queueFor();
  box.classList.toggle("hidden", !items.length);
  box.replaceChildren(...items.map((q, i) => h("div", { class: "queue-item", "data-id": q.id },
    h("span", { class: "q-badge", title: "En cola" }, String(i + 1)),
    h("span", { class: "q-text", title: q.text }, q.text || "(sólo adjuntos)",
      q.att.length ? h("small", { class: "muted" }, ` · ${q.att.length} adjunto${q.att.length > 1 ? "s" : ""}`) : null),
    h("span", { class: "q-acts" },
      h("button", { class: "ghost small q-now", title: S.streaming ? "Detener la respuesta actual y enviar este mensaje ya" : "Enviar este mensaje",
        onclick: () => sendQueuedNow(q.id) }, ico("arrowUp"), S.streaming ? "Enviar ahora" : "Enviar"),
      h("button", { class: "icon-btn", title: "Editar (vuelve al cuadro de texto)", "aria-label": "Editar", onclick: () => {
        S.queue = S.queue.filter((x) => x !== q);
        input.value = q.text + (input.value ? "\n" + input.value : ""); input.dispatchEvent(new Event("input")); input.focus();
        for (const p of q.att) addAttachment(p);
        renderQueue(); syncSendButton();
      } }, ico("pencil")),
      h("button", { class: "icon-btn", title: "Quitar de la cola", "aria-label": "Quitar de la cola", onclick: () => { S.queue = S.queue.filter((x) => x !== q); renderQueue(); } }, ico("x"))))));
}
function sendQueuedNow(id) {
  const q = S.queue.find((x) => x.id === id); if (!q) return;
  S.queue = [q, ...S.queue.filter((x) => x !== q)];            // pasa la primera
  if (S.streaming) { S.sendNow = true; S.streaming.abort(); }  // al cortarse, el final de send() la manda
  else { S.queue.shift(); renderQueue(); dispatchMessage(q.text, q.att); }
}
// Al acabar una respuesta: si no la paraste tú, se envía lo siguiente de la cola de esa conversación
function nextFromQueue(conv) {
  const stopped = S.stopped && !S.sendNow; S.stopped = false; S.sendNow = false;
  renderQueue();
  if (stopped || S.streaming || S.convId !== conv) return;
  const q = queueFor(conv)[0]; if (!q) return;
  S.queue = S.queue.filter((x) => x !== q); renderQueue();
  setTimeout(() => dispatchMessage(q.text, q.att), 150);
}
// El botón: ■ para detener; ↑ si hay algo escrito (se pone en cola)
function syncSendButton() {
  const b = $("#send-btn");
  if (!S.streaming) return;
  const typed = !!(input.value.trim() || S.attachments.length);
  b.innerHTML = ""; b.append(ico(typed ? "arrowUp" : "stop")); b.classList.toggle("stop", !typed);
  b.title = typed ? "Poner en cola (se envía al terminar)" : "Detener";
}
input.addEventListener("input", syncSendButton);

// --- Leer en voz alta (voces del sistema) --------------------------------------------------------
function plainForSpeech(md) {
  return md.replace(/```[\s\S]*?```/g, " (bloque de código) ").replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s*[#>|-]+\s*/gm, "").replace(/[*_~]+/g, "").replace(/\|/g, ", ").replace(/\n{2,}/g, ". ").trim();
}
let speakingBtn = null;
function speak(text, btn) {
  const synth = window.speechSynthesis;
  if (speakingBtn) { synth.cancel(); const was = speakingBtn; speakingBtn.classList.remove("on"); speakingBtn = null; if (was === btn) return; }
  const u = new SpeechSynthesisUtterance(plainForSpeech(text || ""));
  const lang = (navigator.language || "es-ES").slice(0, 2);
  const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang));
  u.voice = voices.find((v) => /natural|neural|online/i.test(v.name)) || voices[0] || null;   // las voces «naturales» suenan mucho mejor
  u.lang = u.voice?.lang || navigator.language || "es-ES";
  u.onend = u.onerror = () => { btn.classList.remove("on"); if (speakingBtn === btn) speakingBtn = null; };
  speakingBtn = btn; btn.classList.add("on"); btn.title = "Detener lectura";
  synth.speak(u);
}

// Registro de una respuesta: modelo, pasos, reintentos, avisos y tiempos (para entender qué pasó)
function showGenLog(m) {
  const meta = m.meta || {}, u = meta.usage || {}, st = meta.stats || {};
  const rows = (meta.log || []).map((l) => h("tr", {}, h("td", { class: "muted" }, `${l.t.toFixed(1)} s`), h("td", {}, l.text)));
  const text = [`Modelo: ${meta.model || "?"} (${meta.provider || "?"})`, `Tiempo total: ${meta.elapsed ?? "?"} s`,
    u.in || u.out ? `Tokens: ↑${u.in || 0} ↓${u.out || 0}` + (u.cost ? ` · ~$${u.cost.toFixed(4)}` : "") : "",
    st.tokens_per_second ? `Velocidad: ${st.tokens_per_second.toFixed(1)} tok/s` : "",
    ...(meta.log || []).map((l) => `${l.t.toFixed(1)} s  ${l.text}`)].filter(Boolean).join("\n");
  const dlg = h("dialog", { class: "export-dialog log-dialog" },
    h("h3", {}, "Detalles de la respuesta"),
    h("p", { class: "muted" }, `${meta.model || ""} · ${meta.elapsed ?? "?"} s` + (u.in || u.out ? ` · ↑${u.in || 0} ↓${u.out || 0} tokens` : "")
      + (st.tokens_per_second ? ` · ${st.tokens_per_second.toFixed(1)} tok/s` : "")),
    h("table", { class: "log-table" }, rows),
    h("div", { class: "row end" },
      h("button", { class: "ghost", onclick: () => copyText(text, "Registro copiado: pégalo donde quieras para revisarlo") }, ico("copy"), "Copiar"),
      h("button", { class: "primary", onclick: () => dlg.close() }, "Cerrar")));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg); dlg.showModal();
}

// Al acabar una respuesta: se trae la conversación guardada y sólo se cambian los mensajes nuevos (el del usuario y
// la respuesta) por su versión definitiva. Si algo no cuadra (resumen, ramas…), se repinta entera como antes.
async function finishInPlace(liveEl) {
  const cid = S.convId, old = S.conv?.messages || [];
  let conv = await api(`/api/conversations/${cid}`);
  if ((conv.messages || []).length <= old.length) { await new Promise((r) => setTimeout(r, 300)); conv = await api(`/api/conversations/${cid}`); }
  if (S.convId !== cid) return;
  const box = $("#messages"), msgs = conv.messages || [];
  const fromBottom = box.scrollHeight - box.scrollTop - box.clientHeight;
  const same = old.length < msgs.length && old.every((m, i) => m.id === msgs[i].id && m.content === msgs[i].content);
  S.conv = conv;
  if (!same || !liveEl.isConnected) { renderMessages(); return; }
  // fuera lo provisional (el mensaje del usuario pintado con id 0 y la respuesta en curso); dentro lo guardado
  box.querySelectorAll(':scope > .msg[data-id="0"]').forEach((x) => x.remove());
  liveEl.remove();
  const frag = document.createDocumentFragment();
  msgs.slice(old.length).forEach((m, i) => frag.append(messageEl(m, old.length + i)));
  box.append(frag);
  if (fromBottom < 80) box.scrollTop = box.scrollHeight;
  if (S.view === "chat" || S.view === "code") $("#top-title").textContent = conv.title;
  renderConvList(); refreshChanges();
}

// --- Respuesta en curso sin tirones -------------------------------------------------------------
// Antes se reconstruía TODO (markdown completo, razonamiento, herramientas) en cada fotograma: con respuestas
// largas la página se trababa, no se podía seleccionar texto y el razonamiento abierto se cerraba solo.
// Ahora: el «armazón» (razonamiento, herramientas, avisos) sólo se rehace cuando cambia, y del texto sólo se
// vuelve a convertir el último párrafo; lo anterior queda fijo.
function liveView() {
  const stable = h("div", { class: "md-part" }), tail = h("div", { class: "md-part" });
  return { key: null, body: null, prefix: "", stable, tail, bubble: h("div", { class: "bubble cursor" }, stable, tail), thinkOpen: undefined };
}
function stableCut(body) {
  let cut = body.lastIndexOf("\n\n");
  while (cut > 0 && ((body.slice(0, cut).match(/^\s*```/gm) || []).length % 2)) cut = body.lastIndexOf("\n\n", cut - 1);
  return cut > 0 ? cut : 0;
}
function liveMd(v, body) {
  if (body === v.body) return false;
  v.body = body;
  const prefix = body.slice(0, stableCut(body));
  if (prefix !== v.prefix) {
    // Una línea en blanco cierra cualquier bloque (párrafo, lista, tabla, cita): lo nuevo se añade sin rehacer lo anterior
    if (v.prefix && prefix.startsWith(v.prefix)) v.stable.insertAdjacentHTML("beforeend", md(prefix.slice(v.prefix.length)));
    else v.stable.innerHTML = prefix ? md(prefix) : "";
    v.prefix = prefix;
  }
  v.tail.innerHTML = md(body.slice(prefix.length));
  return true;
}
function liveKey(content, reasoning, tools, extra) {
  const { think, body } = splitThink(content || "");
  const waiting = !content && !reasoning && !(tools || []).length && !extra.progress;
  return JSON.stringify([reasoning.length, think.length, !body, (tools || []).map((t) => [t.type, t.name, t.state, (t.result || "").length]),
    extra.todos, extra.compacted, (extra.liveOut || "").length, extra.status, extra.progress, extra.route, extra.fallbacks.length,
    extra.files.length, extra.images.length, waiting ? Math.round((Date.now() - extra.t0) / 1000) : 0, extra.reading]);
}

// Un error no debe dejar la respuesta en blanco: queda en la conversación con su causa y un botón para reintentar
function showChatError(msg) {
  $("#chat-error")?.remove();
  const card = h("div", { id: "chat-error", class: "chat-error" },
    h("div", { class: "ce-text" }, h("b", {}, "No se pudo completar la respuesta"), h("span", {}, msg)),
    h("div", { class: "row" },
      h("button", { class: "ghost small", onclick: () => { card.remove(); if (!S.streaming) send("", [], true); } }, ico("retry"), "Reintentar"),
      /modelo local|Modelos/i.test(msg) ? h("button", { class: "primary small", onclick: () => { card.remove(); setView("models"); } }, "Abrir Modelos") : null,
      h("button", { class: "ghost small", onclick: () => { card.remove(); openModelPicker(); } }, "Cambiar de modelo"),
      h("button", { class: "ghost small", onclick: () => { card.remove(); openDiagnostics(); } }, "Diagnosticar")));
  $("#messages").append(card); card.scrollIntoView({ block: "nearest" });
}
async function send(text, attachments, isContinue = false) {
  $("#chat-error")?.remove();
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
  // Respuesta en curso: si te vas a otra conversación y vuelves, se vuelve a mostrar y sigue escribiéndose
  const live = S.live = { el, conv: S.convId || null, isNew: !S.convId, space: space() };

  const ctrl = new AbortController(); S.streaming = ctrl;
  setSending(true);
  let content = "", reasoning = "", tools = [], errorMsg = null, raf = 0;
  const extra = { route: null, fallbacks: [], images: [], files: [], todos: [], t0: Date.now(), reading: attachments.length };
  // Mientras no llegue nada, «Pensando… N s» (y la fase: leyendo adjuntos, conectando…) para que nunca parezca colgado
  const waitTick = setInterval(() => { if (!content && !reasoning && !tools.length && !extra.progress) paint(); }, 1000);
  const view = liveView();
  const paint = () => {
    raf = 0;
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    const key = liveKey(content, reasoning, tools, extra);
    if (key !== view.key) {
      view.key = key;
      el.replaceChildren(assistantInner(content, reasoning, tools, true,
        { ...extra, liveBubble: view.bubble, thinkOpen: view.thinkOpen, onThinkToggle: (o) => { view.thinkOpen = o; } }));
    }
    liveMd(view, splitThink(content || "").body);
    if (stick) box.scrollTop = box.scrollHeight;
  };
  try {
    const body = { conversation_id: S.convId, message: text, attachments, provider, model,
      use_tools: $("#tools-toggle").checked, use_web: $("#web-toggle").checked, continue: isContinue,
      mode: $("#mode-select").value };
    if (S.workdir !== undefined) body.workdir = S.workdir;
    if (S.system !== undefined) body.system = S.system;
    if (!S.convId && S.projectId) body.project_id = S.projectId;
    if (!S.convId) body.kind = space();
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
        if (ev.type === "start") {
          live.conv = ev.conversation_id; extra.reading = 0;
          for (const q of S.queue) if (!q.conv && q.live === live) q.conv = live.conv;
          if (!S.convId && live.isNew) { S.convId = ev.conversation_id; store.set(convKey(live.space), S.convId); }
          loadConversations();
        }
        else if (ev.type === "content") { content += ev.text; extra.status = null; extra.progress = null; }
        else if (ev.type === "reasoning") { reasoning += ev.text; extra.progress = null; }
        else if (ev.type === "progress") extra.progress = ev;
        else if (ev.type === "tool_output") { extra.liveOut = (extra.liveOut || "") + ev.text; if (S.code) { const t = $("#ctab-term"); if (t) renderCodePanel({ tools, todos: extra.todos, liveOut: extra.liveOut }); } }
        else if (ev.type === "tool_call" || ev.type === "tool_result") {
          tools.push(ev); extra.progress = null;
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
        // Un repintado por fotograma como mucho (y menos en respuestas enormes, donde el último párrafo pesa más)
        if (!raf) raf = setTimeout(() => requestAnimationFrame(paint), content.length > 30000 ? 120 : 0);
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") errorMsg = e.message;
  } finally {
    clearInterval(waitTick);
    S.streaming = null;
    setSending(false);
    if (S.live === live) S.live = null;
    const here = !!live.conv && S.convId === live.conv;
    if (here) {
      const wd = S.workdir; await finishInPlace(el).catch(() => openConversation(S.convId).catch(() => {})); S.workdir = wd;
      const cards = $$("#messages .msg.assistant:last-child .art-card");   // la IA acaba de crear una página o diagrama: se muestra al lado
      if (cards.length && !isMobile()) openArtifactCard(cards[cards.length - 1]);
    } else {
      el.remove();
      loadConversations();
      if (live.conv) {   // terminó mientras mirabas otra conversación: aviso con enlace
        const title = (convCache.find((c) => c.id === live.conv) || {}).title || "otra conversación";
        toast(errorMsg ? `No se pudo completar la respuesta en «${title}»` : `Respuesta lista en «${title}»`, 6000);
      }
    }
    if (errorMsg && (here || !live.conv)) showChatError(errorMsg);
    if (document.hidden) systemNotify(errorMsg ? "G3G3AI: no se pudo responder" : "G3G3AI ha respondido",
      errorMsg || plainForSpeech(content).slice(0, 180) || "La respuesta está lista");
    refreshContext(); refreshUsage(true);
    for (const q of S.queue) if (!q.conv && q.live === live) q.conv = live.conv;   // la conversación ya tiene id
    nextFromQueue(live.conv);
  }
}

// Avisos cuando estás en otra ventana o app: en Android, notificación del sistema (puente G3Notify);
// en el navegador, la API de notificaciones.
function systemNotify(title, body) {
  if (window.G3Notify) { try { window.G3Notify.notify(title, body); } catch { /* */ } return; }
  if ("Notification" in window && Notification.permission === "granted") new Notification(title, { body });
}
function notifyApproval(ev) {
  if (document.hidden) systemNotify("G3G3AI necesita tu permiso", ev.name + ": " + (ev.args?.command || ev.args?.path || ""));
}
document.addEventListener("click", () => {
  if (window.G3Notify) { try { window.G3Notify.requestPermission(); } catch { /* */ } }
  else if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {});
}, { once: true });

// «Compartir con G3G3AI» (Android): llega texto y/o archivos; se dejan en el cuadro sin enviar
window.g3Share = async ({ text = "", files = [] } = {}) => {
  setView("chat"); newChat();
  if (text) { input.value = text; input.dispatchEvent(new Event("input")); }
  if (files.length) {
    toast(`Subiendo ${files.length} archivo${files.length > 1 ? "s" : ""}…`);
    const list = files.map((f) => {
      const bin = atob(f.data), bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return new File([bytes], f.name, { type: f.mime });
    });
    const res = await uploadFiles(list, await uploadsDir());
    res.forEach((r) => addAttachment(r.path));
    if (!text) { input.value = res.length > 1 ? "Revisa estos archivos" : "Revisa este archivo"; input.dispatchEvent(new Event("input")); }
  }
  input.focus();
};
