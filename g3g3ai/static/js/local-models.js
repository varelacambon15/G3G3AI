// G3G3AI · Modelos locales, Ollama, buscador de Hugging Face y explorador de archivos.
// Parte 6/8 de la interfaz: se cargan en orden y comparten el ámbito global.
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
      l.state === "stopped" ? h("span", { class: "sub muted" }, " — se carga solo cuando escribes en el chat") : null,
      l.model ? ` — ${l.model}` : "", l.params?.ctx ? h("span", { class: "sub muted" }, ` (ctx ${l.params.ctx}, ${l.params.threads} hilos)`) : null),
    l.state === "ready" ? h("button", { class: "ghost", title: "Comprueba si el modelo sabe usar herramientas y a qué velocidad va", onclick: async (ev) => {
      const b = ev.target; b.disabled = true; b.textContent = "Probando…";
      try {
        const r = await api("/api/llama/selftest", { method: "POST" });
        const icon = { ok: "✅", text: "⚠", none: "❌", error: "❌" }[r.verdict];
        alert(`${icon} ${r.message}\n\nTiempo: ${r.seconds} s` + (r.tokens_per_second ? ` · ${r.tokens_per_second.toFixed(1)} tok/s` : "")
          + `\nPerfil: ${r.profile} · ${r.tools_sent} herramientas · contexto ${r.context}`);
      } catch (e) { alert("❌ " + e.message); }
      b.disabled = false; b.textContent = "🧪 Probar con el agente";
    } }, "🧪 Probar con el agente") : null,
    l.state === "ready" || l.state === "loading" ? h("button", { class: "ghost", title: "Cierra el modelo y libera la memoria que ocupa (no lo borra del disco)", onclick: async () => { await api("/api/llama/unload", { method: "POST" }); refreshStatus(); refreshModels(); loadProviders(); } }, "Liberar memoria") : null));
  if (l.error) box.append(h("pre", { class: "logs error" }, l.error));
  if (!l.binary) box.append(engineBox());
  if (mem?.total) box.append(h("p", { class: "muted" }, `RAM disponible: ${fmtSize(mem.available)} de ${fmtSize(mem.total)}`));
  $("#disk-free").textContent = S.status.disk_free ? `· ${fmtSize(S.status.disk_free)} libres` : "";
}
let hwShown = false;
async function renderHardware(refresh = false) {
  const box = $("#hw-box"); if (!box || (hwShown && !refresh)) return;
  let d;
  try { d = await api("/api/hardware" + (refresh ? "?refresh=true" : "")); } catch (e) { box.textContent = e.message; return; }
  hwShown = true;
  const r = d.recommendation, sm = r.summary;
  const where = { gpu: "entero en la gráfica (rápido)", cpu: "en el procesador", mixto: "repartido entre gráfica y procesador" }[r.main.where];
  box.innerHTML = "";
  box.append(h("p", { class: "muted" }, `Tu equipo: ${sm.ram_gb} GB de RAM · ` + (sm.vram_gb ? `gráfica ${sm.gpu} (${sm.vram_gb} GB)` : "sin gráfica dedicada")
    + ` → modelos de hasta ${r.main.tier}.`));
  // Modelos concretos, con un clic: descargar (si hace falta) y cargar
  const list = h("div", { class: "picks" });
  (r.picks || []).forEach((pk, i) => {
    const btn = h("button", { class: i === 0 ? "primary small" : "ghost small" }, pk.path ? "Usar" : "Descargar y usar");
    btn.onclick = () => quickModel(pk, btn);
    list.append(h("div", { class: "pick" + (i === 0 ? " best" : "") },
      h("div", { class: "pick-info" }, h("b", {}, pk.name, i === 0 ? h("span", { class: "badge ok" }, "Recomendado") : null),
        h("span", { class: "muted" }, pk.why), h("small", { class: "muted" }, pk.path ? "✔ Descargado" : `~${pk.gb} GB`)),
      btn));
  });
  box.append(list);
  if (r.notes.length) box.append(h("ul", { class: "warnings-list" }, r.notes.map((n) => h("li", {}, n))));
  // Lo técnico, plegado
  const st = r.settings;
  const searchBtn = (q, label) => h("button", { class: "ghost small", onclick: () => { $("#hub-q").value = q; hubSearch(q); $("#hub-q").scrollIntoView({ behavior: "smooth", block: "center" }); } }, label);
  box.append(h("details", { class: "tech" }, h("summary", {}, "Detalles técnicos"),
    h("p", { class: "muted" }, `${sm.cpu} · ${sm.cores} núcleos · ${sm.ram_gb} GB de RAM · gráfica: ${sm.gpu}` + (sm.vram_gb ? ` (${sm.vram_gb} GB)` : "")),
    h("p", {}, "Tamaño ideal: ", h("b", {}, r.main.tier), ` en ${r.quant}, ${where}. Motor: `, h("b", {}, r.engine === "vulkan" ? "Vulkan (gráfica)" : "CPU"), "."),
    h("p", { class: "muted" }, `Ajustes sugeridos: contexto ${st.llama_ctx} · hilos ${st.llama_threads} · capas GPU ${st.llama_gpu_layers}` + (st.llama_extra_args ? ` · ${st.llama_extra_args}` : "")),
    r.images ? h("p", { class: "muted" }, "🎨 " + r.images) : null,
    h("div", { class: "row" },
      h("button", { class: "ghost small", onclick: async () => {
        await api("/api/hardware/apply", { method: "POST" }); S.settings = null;
        $("#p-ctx").value = st.llama_ctx; $("#p-threads").value = st.llama_threads; $("#p-ngl").value = st.llama_gpu_layers;
        toast("Ajustes aplicados ✔ (se usan al cargar el próximo modelo)");
      } }, "Aplicar ajustes sugeridos"),
      r.main.searches.map((q) => searchBtn(q, "🔎 " + q)),
      h("button", { class: "ghost small", onclick: () => renderHardware(true) }, "Volver a analizar"))));
}
// «Descargar y usar»: descarga el archivo adecuado (con su visión si la tiene), lo carga y lleva al chat
async function quickModel(pk, btn) {
  const label = btn.textContent; btn.disabled = true;
  const load = async (path) => {
    btn.textContent = "Cargando…";
    await api("/api/llama/load", { method: "POST", body: { path } });
    S.ms = null; await loadProviders(); refreshStatus(); refreshModels();
    const sel = $("#model-select"); if ([...sel.options].some((o) => o.value === "local::local")) { sel.value = "local::local"; sel.dispatchEvent(new Event("change")); }
    toast(`${pk.name} se está cargando. Ya puedes escribir en el chat.`, 5000);
    btn.textContent = "✔ En uso"; renderHardware(true);
  };
  try {
    if (pk.path) return await load(pk.path);
    btn.textContent = "Preparando…";
    const d = await api("/api/models/quick", { method: "POST", body: { repo: pk.repo, vision: pk.vision } });
    if (!d.id) return await load(d.dest);
    const tick = setInterval(async () => {
      const x = (await api("/api/hub/downloads")).find((y) => y.id === d.id);
      if (!x) return;
      if (x.status === "downloading") btn.textContent = `Descargando ${x.total ? Math.round(100 * x.done / x.total) : 0} %`;
      if (["done", "error", "cancelled"].includes(x.status)) {
        clearInterval(tick);
        if (x.status === "done") await load(d.dest);
        else { toast("No se pudo descargar: " + (x.error || x.status), 7000); btn.disabled = false; btn.textContent = label; }
      }
    }, 1000);
  } catch (e) { toast(e.message, 7000); btn.disabled = false; btn.textContent = label; }
}
// --- Ollama -----------------------------------------------------------------------------------
let ollamaTimer = null;
async function renderOllama() {
  const box = $("#ollama-box"); if (!box) return;
  let d;
  try { d = await api("/api/ollama"); } catch (e) { box.textContent = e.message; return; }
  box.innerHTML = "";
  const job = d.job;
  const post = (url, body) => api(url, { method: "POST", body: body || {} });
  box.append(h("p", { class: "muted" }, "Motor alternativo a llama.cpp: descarga modelos por su nombre (p.ej. qwen3:8b) y usa la gráfica automáticamente. Cómodo en el PC."));
  if (!d.installed) {
    box.append(h("p", {}, "Ollama no está instalado en este equipo."));
    if (d.can_install) box.append(h("button", { class: "primary small", disabled: job.status === "running",
      onclick: async () => { await post("/api/ollama/install"); renderOllama(); } }, "⬇ Instalar Ollama"));
    else if (d.linux_command) box.append(h("p", {}, "En Linux se instala desde una terminal (pide la contraseña de administrador):", h("code", { class: "access-url" }, d.linux_command)));
  } else if (!d.running) {
    box.append(h("p", {}, "Ollama está instalado pero no está en marcha."),
      h("button", { class: "primary small", onclick: async () => {
        try { await post("/api/ollama/start"); toast("Iniciando Ollama…"); setTimeout(renderOllama, 2500); } catch (e) { toast(e.message); }
      } }, "▶ Iniciar Ollama"));
  } else {
    box.append(h("div", { class: "row" },
      h("span", { class: "grow" }, h("b", {}, "✔ Ollama en marcha"), h("span", { class: "muted" }, ` · versión ${d.version || "?"} · ${d.url}`)),
      h("label", { class: "toggle", title: "Muestra los modelos de Ollama en el selector del chat" },
        h("input", { type: "checkbox", checked: d.provider_enabled, onchange: async (e) => {
          await post("/api/ollama/enable", { enabled: e.target.checked }); S.models = {}; await loadProviders();
          toast(e.target.checked ? "Ollama aparece ahora en el selector de modelos" : "Ollama oculto del selector");
        } }), "Usar en el chat")));
    const ul = h("ul", { class: "list" });
    if (!d.models.length) ul.append(h("li", { class: "muted" }, "Aún no hay modelos. Descarga uno abajo."));
    for (const m of d.models) ul.append(h("li", {},
      h("div", { class: "name" }, m.name, h("div", { class: "sub" }, [m.params, m.quant, fmtSize(m.size)].filter(Boolean).join(" · "))),
      fitBadge(m.size),
      h("button", { class: "ghost small", title: "Borrar", onclick: async () => {
        if (!confirm(`¿Borrar ${m.name} de Ollama?`)) return;
        await api("/api/ollama/models?" + qs({ name: m.name }), { method: "DELETE" }).catch((e) => toast(e.message)); renderOllama();
      } }, "🗑")));
    box.append(ul);
    const inp = h("input", { class: "grow", placeholder: "Nombre del modelo, p.ej. qwen3:8b" });
    const pull = async (name) => { if (!name) return; await post("/api/ollama/pull", { name }); toast("Descargando " + name + "…"); renderOllama(); };
    box.append(h("form", { class: "row", onsubmit: (e) => { e.preventDefault(); pull(inp.value.trim()); } },
      inp, h("button", { class: "primary small", disabled: job.status === "running" }, "Descargar")));
    box.append(h("div", { class: "suggestions" }, `Recomendados para este equipo (${d.tier}): `,
      d.suggestions.models.map((n) => h("button", { class: "link", onclick: () => pull(n) }, n)),
      " · con visión: ", h("button", { class: "link", onclick: () => pull(d.suggestions.vision) }, d.suggestions.vision),
      " · ", h("a", { href: "https://ollama.com/library", target: "_blank", rel: "noopener" }, "ver todos")));
  }
  if (job.status !== "idle") {
    const pct = job.total ? Math.round(100 * job.completed / job.total) : null;
    box.append(h("p", {}, job.status === "running" ? `⏳ ${job.what}…` + (pct != null ? ` ${pct}%` : "")
      : job.status === "done" ? `✔ ${job.what}: hecho` : `✕ ${job.what}: ${job.error}`));
    if (pct != null && job.status === "running") box.append(h("div", { class: "progress" }, h("div", { style: `width:${pct}%` })));
    if (job.log.length) box.append(h("details", { open: job.status === "error" }, h("summary", {}, "Registro"), h("pre", { class: "logs" }, job.log.join("\n"))));
  }
  clearTimeout(ollamaTimer);
  if (job.status === "running" && S.view === "models") ollamaTimer = setTimeout(renderOllama, 1500);
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
      ? h("p", {}, h("b", {}, "Motor de imágenes (stable-diffusion.cpp)."), " En Linux: ./install.sh --with-sd. En Windows puedes descargarlo ya compilado:")
      : h("p", {}, h("b", {}, "Falta el motor llama.cpp."), " En Linux se instala con ./install.sh (compilado para tu CPU). En Windows puedes descargarlo ya compilado:"));
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
  renderHardware();
  renderOllama();
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
// --- Buscador de modelos (Hugging Face) ------------------------------------------------------
const HUB = { results: [], shown: 20, budget: null };
const fmtNum = (n) => n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + " M" : n >= 1e3 ? Math.round(n / 1e3) + " k" : String(n || 0);
function ago(iso) {
  if (!iso) return "";
  const d = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (d < 1) return "hoy";
  if (d < 2) return "ayer";
  if (d < 31) return `hace ${Math.round(d)} días`;
  if (d < 365) return `hace ${Math.round(d / 30)} meses`;
  return `hace ${(d / 365).toFixed(1).replace(".0", "")} años`;
}
async function hubBudget() {
  if (HUB.budget == null) {
    try { HUB.budget = (await api("/api/hardware")).recommendation.summary.budget_gb; } catch { HUB.budget = 0; }
  }
  return HUB.budget;
}
function fitInfo(gb) {
  if (!gb || !HUB.budget) return null;
  if (gb <= HUB.budget * 0.75) return h("span", { class: "badge ok", title: `~${gb} GB de ${HUB.budget} GB disponibles` }, "cabe bien");
  if (gb <= HUB.budget) return h("span", { class: "badge warn", title: `~${gb} GB de ${HUB.budget} GB disponibles` }, "justo");
  return h("span", { class: "badge bad", title: `~${gb} GB; este equipo tiene ~${HUB.budget} GB disponibles` }, "no cabe");
}
const sizeBucket = (r) => !r.params ? "" : r.params <= 2 ? "xs" : r.params <= 4.5 ? "s" : r.params <= 9.5 ? "m" : r.params <= 15 ? "l" : "xl";
const CAP_BADGE = { vision: "visión", code: "código", reasoning: "razonamiento", image: "imágenes" };

$("#hub-search").addEventListener("submit", (e) => { e.preventDefault(); hubSearch($("#hub-q").value.trim()); });
$("#hub-sort").addEventListener("change", () => { if ($("#hub-q").value.trim()) hubSearch($("#hub-q").value.trim()); });
["f-size", "f-vision", "f-code", "f-reason", "f-fits", "f-order"].forEach((id) =>
  $("#" + id).addEventListener("change", () => { HUB.shown = 20; renderHub(); }));
$$(".hub-explore [data-q]").forEach((b) => b.addEventListener("click", () => {
  $("#hub-q").value = b.dataset.q;
  $("#f-vision").checked = b.dataset.cap === "vision"; $("#f-code").checked = b.dataset.cap === "code";
  $("#f-reason").checked = b.dataset.cap === "reasoning"; $("#f-size").value = b.dataset.size || "";
  hubSearch(b.dataset.q);
}));

async function hubSearch(q) {
  if (!q) { $("#hub-q").focus(); return; }
  const ul = $("#hub-results"); ul.innerHTML = ""; ul.append(h("li", { class: "muted" }, "Buscando en Hugging Face…"));
  $("#hub-count").textContent = "";
  await hubBudget();
  try {
    HUB.results = await api("/api/hub/search?" + qs({ q, sort: $("#hub-sort").value }));
    HUB.shown = 20; $("#hub-filters").classList.remove("hidden"); renderHub();
  } catch (e) { ul.innerHTML = ""; ul.append(h("li", { class: "error" }, e.message)); }
}

function renderHub() {
  const ul = $("#hub-results"); ul.innerHTML = "";
  const size = $("#f-size").value, needs = [["f-vision", "vision"], ["f-code", "code"], ["f-reason", "reasoning"]]
    .filter(([id]) => $("#" + id).checked).map(([, c]) => c);
  let list = HUB.results.filter((r) =>
    (!size || (size === "moe" ? r.moe : sizeBucket(r) === size)) &&
    needs.every((c) => r.caps.includes(c)) &&
    (!$("#f-fits").checked || (r.est_gb && HUB.budget && r.est_gb <= HUB.budget)));
  const order = $("#f-order").value;
  if (order === "small") list = [...list].sort((a, b) => (a.params ?? 1e9) - (b.params ?? 1e9));
  if (order === "big") list = [...list].sort((a, b) => (b.params ?? -1) - (a.params ?? -1));
  if (order === "recent") list = [...list].sort((a, b) => new Date(b.updated || 0) - new Date(a.updated || 0));
  $("#hub-count").textContent = HUB.results.length
    ? `${list.length} de ${HUB.results.length} resultados` + (HUB.budget ? ` · memoria disponible en este equipo: ~${HUB.budget} GB` : "") : "";
  if (!list.length) {
    ul.append(h("li", { class: "muted" }, HUB.results.length ? "Ningún resultado con estos filtros." : "Sin resultados. Prueba con otro nombre (p.ej. «qwen», «gemma», «llama»)."));
    return;
  }
  for (const r of list.slice(0, HUB.shown)) {
    const files = h("div", { class: "repo-files hidden" });
    const sizeLabel = r.params ? (r.moe && r.active ? `${r.params}B (${r.active}B activos)` : `${r.params}B`) : null;
    ul.append(h("li", { class: "hub-item" },
      h("div", { class: "name" },
        h("div", { class: "hub-title" }, h("b", {}, r.name), h("span", { class: "muted" }, " · " + r.author)),
        h("div", { class: "hub-badges" },
          sizeLabel ? h("span", { class: "badge" }, sizeLabel) : null,
          r.moe ? h("span", { class: "badge", title: "Mezcla de expertos: rápido para su tamaño" }, "⚡ MoE") : null,
          r.caps.map((c) => h("span", { class: "badge" }, CAP_BADGE[c] || c)),
          r.est_gb ? h("span", { class: "badge", title: "Tamaño aproximado en Q4_K_M" }, `~${r.est_gb} GB`) : null,
          fitInfo(r.est_gb),
          r.downloaded ? h("span", { class: "badge ok" }, "✔ descargado") : null),
        h("div", { class: "sub" }, `⬇ ${fmtNum(r.downloads)} · ♥ ${fmtNum(r.likes)}` + (r.updated ? ` · actualizado ${ago(r.updated)}` : ""))),
      h("div", { class: "hub-actions" },
        h("button", { class: "ghost small", onclick: (e) => toggleRepo(r, files, e.target) }, "Ver archivos"),
        h("a", { class: "ghost small btn-like", href: r.url, target: "_blank", rel: "noopener", title: "Abrir en Hugging Face" }, "↗")),
      files));
  }
  if (list.length > HUB.shown) ul.append(h("li", { class: "hub-more" },
    h("button", { class: "ghost", onclick: () => { HUB.shown += 20; renderHub(); } }, `Mostrar más (${list.length - HUB.shown})`)));
}

async function toggleRepo(r, box, btn) {
  const repo = r.id;
  if (!box.classList.contains("hidden")) { box.classList.add("hidden"); btn.textContent = "Ver archivos"; return; }
  box.classList.remove("hidden"); btn.textContent = "Ocultar"; box.innerHTML = "Cargando archivos…";
  try {
    const groups = await api("/api/hub/files?" + qs({ repo }));
    box.innerHTML = "";
    const projs = groups.filter((g) => g.mmproj);
    const proj = projs.find((g) => /f16/i.test(g.name)) || projs[0];
    const models = groups.filter((g) => !g.mmproj);
    // Recomendado: Q4_K_M si cabe; si no, la mejor calidad que quepa
    const budget = HUB.budget ? HUB.budget * 1024 ** 3 : null;
    const fits = (g) => !budget || g.size <= budget;
    let best = models.find((g) => g.quant === "Q4_K_M" && fits(g));
    if (!best) best = [...models].filter(fits).sort((a, b) => b.level - a.level || b.size - a.size)[0];
    if (proj) box.append(h("p", { class: "muted" }, "👁 Tiene visión: al descargar un modelo se añade también su proyector (" + proj.name + ")."));
    if (!models.length) { box.append(h("p", { class: "muted" }, "Este repositorio no tiene archivos GGUF de modelo.")); return; }
    const ul = h("ul", { class: "list files-table" });
    for (const g of models) {
      const gb = Math.round(g.size / 1024 ** 3 * 10) / 10;
      ul.append(h("li", { class: g === best ? "recommended" : "" },
        h("div", { class: "name" },
          h("b", {}, g.quant || g.name), g === best ? h("span", { class: "badge ok" }, "⭐ recomendado para este equipo") : null,
          h("div", { class: "sub" }, [g.quality, fmtSize(g.size), g.files.length > 1 ? `${g.files.length} partes` : "", g.name].filter(Boolean).join(" · "))),
        fitInfo(gb),
        g.downloaded ? h("span", { class: "badge ok" }, "✔ descargado")
          : h("button", { class: g === best ? "primary small" : "ghost small", onclick: async (e) => {
            e.target.disabled = true;
            await api("/api/hub/download", { method: "POST", body: { repo, files: g.files } });
            if (proj && !proj.downloaded) await api("/api/hub/download", { method: "POST", body: { repo, files: proj.files } });
            toast("Descarga iniciada: " + (g.quant || g.name)); refreshDownloads();
          } }, "Descargar")));
    }
    box.append(ul);
    box.append(h("p", { class: "muted small-text" }, "Guía: Q4_K_M = equilibrio · Q5/Q6 = más calidad y más memoria · Q8 = casi sin pérdida · Q3/Q2 = cuando no cabe otra cosa."));
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
