// G3G3AI · Adjuntos, proyectos e instrucciones por conversación.
// Parte 5/8 de la interfaz: se cargan en orden y comparten el ámbito global.
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
$("#attach-btn").addEventListener("click", () => openPicker("Adjuntar archivo", null));
// --- Proyectos ------------------------------------------------------------------------------------
// Conversaciones agrupadas con instrucciones y documentos que la IA tiene siempre presentes.
const PJ = { list: [], cur: null };
async function loadProjects() {
  try { PJ.list = await api("/api/projects"); } catch { PJ.list = []; }
  return PJ.list;
}
function projectName(id) { return PJ.list.find((p) => p.id === id)?.name; }
async function renderProjects() {
  const page = $("#projects-page"); page.innerHTML = "";
  if (PJ.cur) return renderProject(PJ.cur);
  await loadProjects();
  page.append(h("div", { class: "page-head" }, h("h1", { class: "page-title" }, "Proyectos"),
    h("button", { class: "primary", onclick: newProject }, ico("plus"), "Nuevo proyecto")));
  if (!PJ.list.length) {
    page.append(h("div", { class: "card proj-empty" },
      h("h2", {}, "Agrupa tu trabajo"),
      h("p", { class: "muted" }, "Un proyecto reúne conversaciones sobre un mismo tema con unas instrucciones y unos documentos que la IA tiene siempre presentes: tus plantillas, criterios, el contrato de referencia… Así no tienes que adjuntarlos ni explicarlos en cada conversación."),
      h("button", { class: "primary", onclick: newProject }, "Crear el primero")));
    return;
  }
  page.append(h("div", { class: "proj-grid" }, PJ.list.map((p) => h("button", { class: "proj-card", onclick: () => openProject(p.id) },
    h("b", {}, p.name),
    h("span", { class: "muted" }, (p.instructions || "Sin instrucciones").slice(0, 140)),
    h("small", { class: "muted" }, `${p.conversations} ${p.conversations === 1 ? "conversación" : "conversaciones"} · ${p.files.length} documento${p.files.length === 1 ? "" : "s"}` +
      (p.last_used ? ` · ${ago(p.last_used * 1000)}` : ""))))));
}
async function newProject() {
  const name = prompt("Nombre del proyecto"); if (!name?.trim()) return;
  try { const p = await api("/api/projects", { method: "POST", body: { name: name.trim() } }); await loadProjects(); openProject(p.id); }
  catch (e) { toast(e.message); }
}
async function openProject(id) {
  PJ.cur = id; if (S.view !== "projects") setView("projects"); else renderProjects();
}
async function renderProject(id) {
  const page = $("#projects-page");
  let p; try { p = await api(`/api/projects/${id}`); } catch (e) { PJ.cur = null; toast(e.message); return renderProjects(); }
  page.innerHTML = "";
  $("#top-title").textContent = p.name;
  const save = async (fields) => {
    try { Object.assign(p, await api(`/api/projects/${id}`, { method: "PATCH", body: fields })); loadProjects(); toast("Guardado", 1500); }
    catch (e) { toast(e.message, 6000); }
  };
  const name = h("input", { class: "proj-name", value: p.name, onchange: () => name.value.trim() && save({ name: name.value.trim() }) });
  const instr = h("textarea", { rows: 6, placeholder: "Por ejemplo: «Soy técnico de RRHH. Responde en tablas cuando compares datos y cita siempre de qué documento sale cada cifra.»" }, p.instructions || "");
  instr.addEventListener("change", () => save({ instructions: instr.value }));
  const teamSel = h("select", { "aria-label": "Equipo del proyecto", onchange: (e) => save({ team_id: e.target.value || null }) },
    h("option", { value: "" }, "Equipo general (si está activo)"), h("option", { value: "none" }, "Sin equipo"));
  api("/api/teams").then((all) => {
    if (all.saved.length) teamSel.append(h("optgroup", { label: "Equipos guardados" }, all.saved.map((t) => h("option", { value: t.id }, `${t.name} · ${t.members.length} miembro(s)`))));
    teamSel.value = p.team_id || "";
  }).catch(() => {});
  const docs = h("div", { class: "proj-docs" });
  const drawDocs = () => {
    docs.innerHTML = "";
    if (!p.files.length) docs.append(h("p", { class: "muted" }, "Aún no hay documentos. Añade los que la IA deba consultar siempre (PDF, Word, Excel, texto…)."));
    for (const f of p.files) docs.append(h("div", { class: "proj-doc" }, ico("doc"), h("span", { class: "grow", title: f }, baseName(f)),
      h("button", { class: "icon-btn", title: "Quitar del proyecto", onclick: async () => { await save({ files: p.files.filter((x) => x !== f) }); drawDocs(); } }, "✕")));
  };
  drawDocs();
  const convs = h("div", { class: "proj-convs" });
  if (!p.conversations.length) convs.append(h("p", { class: "muted" }, "Todavía no hay conversaciones en este proyecto."));
  for (const c of p.conversations) convs.append(h("button", { class: "proj-conv", onclick: () => { setView("chat"); openConversation(c.id); } },
    h("span", { class: "grow" }, c.title), h("small", { class: "muted" }, ago(c.updated * 1000))));
  page.append(
    h("button", { class: "ghost small back", onclick: () => { PJ.cur = null; renderProjects(); $("#top-title").textContent = "Proyectos"; } }, "‹ Proyectos"),
    h("div", { class: "proj-head" }, name, h("button", { class: "primary", onclick: () => newChatInProject(id) }, ico("plus"), "Nueva conversación")),
    h("div", { class: "proj-cols" },
      h("div", { class: "card" }, h("h2", {}, "Conversaciones"), convs),
      h("div", {},
        h("div", { class: "card" }, h("h2", {}, "Instrucciones"), h("p", { class: "muted small" }, "Se aplican a todas las conversaciones del proyecto."), instr),
        h("div", { class: "card" }, h("h2", {}, "Equipo"), h("p", { class: "muted small" }, "Las IAs en las que el chat delega el trabajo en este proyecto. Los equipos se crean en la sección Equipo."),
          h("div", { class: "row" }, teamSel, h("button", { class: "ghost small", onclick: () => setView("team") }, "Editar equipos"))),
        h("div", { class: "card" }, h("h2", {}, "Documentos"), docs,
          h("button", { class: "ghost small", onclick: () => openPicker("Añadir documento al proyecto", async (path) => {
            if (!p.files.includes(path)) { await save({ files: [...p.files, path] }); drawDocs(); }
          }) }, ico("plus"), "Añadir documentos")),
        h("button", { class: "ghost small danger", onclick: async () => {
          if (!confirm(`¿Borrar el proyecto «${p.name}»? Sus conversaciones se conservan, fuera del proyecto.`)) return;
          await api(`/api/projects/${id}`, { method: "DELETE" }); PJ.cur = null; renderProjects(); loadConversations();
        } }, "Borrar proyecto"))));
}
function newChatInProject(id) {
  setView("chat"); newChat(); S.projectId = id; renderProjectChip();
}
function renderProjectChip() {
  const id = S.conv?.project_id || (!S.convId ? S.projectId : null);
  $("#project-chip")?.remove();
  if (!id) return;
  const chip = h("button", { id: "project-chip", class: "project-chip", title: "Esta conversación usa las instrucciones y documentos del proyecto", onclick: () => openProject(id) },
    ico("project"), projectName(id) || "Proyecto");
  $(".composer-wrap").prepend(chip);
}
async function moveToProject(c) {
  await loadProjects();
  const sel = h("select", {}, h("option", { value: "" }, "— Sin proyecto —"), ...PJ.list.map((p) => h("option", { value: p.id }, p.name)));
  sel.value = c.project_id || "";
  const dlg = h("dialog", { class: "export-dialog" }, h("h3", {}, "Mover a un proyecto"), h("p", { class: "muted" }, c.title), sel,
    h("div", { class: "row end" }, h("button", { class: "ghost", onclick: () => dlg.close() }, "Cancelar"),
      h("button", { class: "primary", onclick: async () => {
        await api(`/api/conversations/${c.id}`, { method: "PATCH", body: { project_id: sel.value || null } });
        dlg.close(); loadConversations(); if (S.convId === c.id) { S.conv.project_id = sel.value || null; renderProjectChip(); }
        toast(sel.value ? `Movida a «${projectName(sel.value)}»` : "Quitada del proyecto");
      } }, "Mover")));
  dlg.addEventListener("close", () => dlg.remove()); document.body.append(dlg); dlg.showModal();
}
function openPicker(title, handler, folder = false) {
  S.pickHandler = handler; S.pickFolder = folder; $("#picker-title").textContent = title;
  $("#picker-use-dir").classList.toggle("hidden", !folder);
  $("#picker-upload").closest("label").classList.toggle("hidden", folder);
  $("#picker").showModal(); loadPicker(S.pickerPath);
}
// Elegir una carpeta navegando (en vez de escribir la ruta a mano)
function pickFolder(title, onPick) { openPicker(title, onPick, true); }
$("#picker-use-dir").addEventListener("click", () => { const p = S.pickerPath; const fn = S.pickHandler; $("#picker").close(); if (p && fn) fn(p); });
$("#picker").addEventListener("close", () => {
  S.pickHandler = null; S.pickFolder = false; $("#picker-title").textContent = "Adjuntar archivo";
  $("#picker-use-dir").classList.add("hidden"); $("#picker-upload").closest("label").classList.remove("hidden");
});
$("#code-dir-pick").addEventListener("click", () => pickFolder("Carpeta del proyecto", (p) => { $("#code-dir").value = p; $("#code-dir-set").click(); }));
$("#project-dir-pick").addEventListener("click", () => pickFolder("Carpeta del proyecto", (p) => { $("#project-dir").value = p; }));
const pickFile = (path) => (S.pickHandler ? S.pickHandler(path) : addAttachment(path));

async function loadPicker(path) {
  try {
    const d = await api("/api/files/list?" + qs({ path: path || "" }));
    S.pickerPath = d.path; $("#picker-path").textContent = d.path;
    $("#picker-up").disabled = !d.parent; $("#picker-up").onclick = () => loadPicker(d.parent);
    const ul = $("#picker-list"); ul.innerHTML = "";
    for (const e of d.entries.filter((x) => !S.pickFolder || x.is_dir)) ul.append(h("li", { onclick: () => {
      if (e.is_dir) loadPicker(e.path); else if (!S.pickFolder) { pickFile(e.path); $("#picker").close(); }
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
  res.forEach((r) => pickFile(r.path)); e.target.value = ""; $("#picker").close();
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
  $("#system-text").value = cur || ""; $("#project-dir").value = S.workdir ?? S.conv?.workdir ?? ""; $("#system-dialog").showModal();
});
$("#system-save").addEventListener("click", async () => {
  S.system = $("#system-text").value;
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { system: S.system } });
  S.workdir = $("#project-dir").value.trim();
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { workdir: S.workdir || null } });
  $("#system-dialog").close(); toast("Instrucciones aplicadas");
});
$("#system-reset").addEventListener("click", async () => {
  S.system = null;
  if (S.convId) await api(`/api/conversations/${S.convId}`, { method: "PATCH", body: { system: null } });
  $("#system-dialog").close(); toast("Se usarán las instrucciones predeterminadas");
});
