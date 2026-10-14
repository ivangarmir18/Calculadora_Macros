/* Calculadora de macros - frontend sin dependencias */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const MEALS = ["desayuno", "comida", "merienda", "cena", "otro"];
const MEAL_ICON = { desayuno: "🌅", comida: "🍝", merienda: "🍎", cena: "🌙", otro: "🍴" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const r0 = (n) => Math.round(n);
const r1 = (n) => Math.round(n * 10) / 10;
const toNum = (v) => parseFloat(String(v).replace(",", ".")) || 0;

// La fecha se detecta en el navegador (hora local), así no depende de la zona horaria del servidor.
const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseISO = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const shiftDay = (s, n) => { const d = parseISO(s); d.setDate(d.getDate() + n); return isoDate(d); };
const guessMeal = () => { const h = new Date().getHours(); return h < 11 ? "desayuno" : h < 16 ? "comida" : h < 19 ? "merienda" : "cena"; };

const state = { tab: "today", date: isoDate(new Date()), foodQuery: "", histDays: 7 };

async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const res = await fetch(url, opt);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { toast(data.error || "Error"); throw new Error(data.error || res.statusText); }
  return data;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), 2200);
}

function openSheet(html) { $("#sheet").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeSheet() { $("#modal").classList.add("hidden"); $("#sheet").innerHTML = ""; }
$("#modal").addEventListener("mousedown", (e) => { if (e.target.id === "modal") closeSheet(); });
const sheetHead = (title) => `<h1>${esc(title)}<button class="close" onclick="closeSheet()">×</button></h1>`;

const macroLine = (m) => `<span class="macros"><b class="mp">P ${r1(m.protein)}</b> · <b class="mc">C ${r1(m.carbs)}</b> · <b class="mf">G ${r1(m.fat)}</b></span>`;
const thumb = (f) => f.photo ? `<img class="thumb" src="/uploads/${esc(f.photo)}" alt="">` : `<div class="thumb">🍽️</div>`;
const scaleFood = (f, g) => ({ kcal: f.kcal * g / 100, protein: f.protein * g / 100, carbs: f.carbs * g / 100, fat: f.fat * g / 100 });
const mealChips = (sel) => `<div class="chips" id="mealChips">${MEALS.map((m) => `<button class="chip ${m === sel ? "on" : ""}" data-meal="${m}">${MEAL_ICON[m]} ${m}</button>`).join("")}</div>`;
function bindMealChips(onChange) {
  $$("#mealChips .chip").forEach((b) => b.onclick = () => { $$("#mealChips .chip").forEach((x) => x.classList.remove("on")); b.classList.add("on"); onChange?.(b.dataset.meal); });
}
const selectedMeal = () => $("#mealChips .chip.on")?.dataset.meal || "otro";

// ------------------------------------------------------------------ navegación
$$("#tabs button").forEach((b) => b.onclick = () => go(b.dataset.tab));
function go(tab) {
  state.tab = tab;
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  render();
}
function render() { ({ today: renderToday, presets: renderPresets, foods: renderFoods, history: renderHistory })[state.tab](); window.scrollTo(0, 0); }

// ------------------------------------------------------------------------- HOY
async function renderToday() {
  const d = await api("GET", `/api/day/${state.date}`);
  const isToday = state.date === isoDate(new Date());
  const label = parseISO(state.date).toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
  const g = d.goals, t = d.totals;
  const pct = (v, goal) => Math.min(100, goal ? (v / goal) * 100 : 0);
  const over = (v, goal) => (v > goal ? "over" : "");
  const macro = (key, name, cls, color) => `<div><div class="lbl">${name}</div><div class="val ${cls}">${r0(t[key])} / ${r0(g[key])} g</div>
      <div class="bar ${over(t[key], g[key])}"><i style="width:${pct(t[key], g[key])}%;background:${color}"></i></div></div>`;
  const remaining = g.kcal - t.kcal;

  const byMeal = {};
  d.entries.forEach((e) => (byMeal[e.meal] ||= []).push(e));
  const meals = MEALS.filter((m) => byMeal[m]).map((m) => {
    const list = byMeal[m], sum = list.reduce((a, e) => a + e.kcal, 0);
    return `<h2>${MEAL_ICON[m]} ${m} · ${r0(sum)} kcal</h2>` + list.map((e) => `
      <div class="item" onclick="editEntry(${e.id})">
        <div class="grow"><div class="title">${e.kind === "quick" ? "⚡ " : ""}${esc(e.name)}${e.grams ? ` <span class="muted">${r0(e.grams)} g</span>` : ""}</div>
          ${e.protein || e.carbs || e.fat ? macroLine(e) : '<span class="macros">solo kcal</span>'}</div>
        <div class="kcal-tag">${r0(e.kcal)}</div></div>`).join("");
  }).join("");

  $("#view").innerHTML = `
    <div class="datebar">
      <button onclick="changeDay(-1)">‹</button>
      <div class="date"><strong>${isToday ? "Hoy" : label}</strong><span class="muted">${isToday ? label : state.date}</span>
        ${isToday ? "" : `<div><button class="chip" style="width:auto;height:auto;margin-top:4px" onclick="state.date=isoDate(new Date());renderToday()">Ir a hoy</button></div>`}</div>
      <button onclick="changeDay(1)">›</button>
    </div>
    <div class="card">
      <div class="row between"><div><div class="big">${r0(t.kcal)}</div><div class="muted">de ${r0(g.kcal)} kcal</div></div>
        <div style="text-align:right"><div class="big" style="font-size:1.4rem;color:${remaining < 0 ? "var(--danger)" : "var(--accent)"}">${r0(Math.abs(remaining))}</div>
        <div class="muted">${remaining < 0 ? "te has pasado" : "restantes"}</div></div></div>
      <div class="bar ${over(t.kcal, g.kcal)}"><i style="width:${pct(t.kcal, g.kcal)}%;background:var(--kcal)"></i></div>
      <div class="macro-grid">${macro("protein", "Proteína", "mp", "var(--p)")}${macro("carbs", "Hidratos", "mc", "var(--c)")}${macro("fat", "Grasa", "mf", "var(--f)")}</div>
    </div>
    <div class="actions">
      <button class="btn primary" onclick="addFood()">＋ Alimento</button>
      <button class="btn" onclick="addPreset()">⚡ Preset</button>
      <button class="btn" onclick="addQuick()">🔥 Solo kcal</button>
    </div>
    ${meals || '<div class="empty">Nada apuntado este día.<br>Pulsa arriba para añadir.</div>'}`;
}
function changeDay(n) { state.date = shiftDay(state.date, n); renderToday(); }

// --- añadir alimento
async function addFood() {
  const foods = await api("GET", "/api/foods");
  openSheet(`${sheetHead("Añadir alimento")}${mealChips(guessMeal())}
    <input id="q" placeholder="Buscar alimento…" autocomplete="off"><div id="foodList" style="margin-top:10px"></div>`);
  bindMealChips();
  const draw = () => {
    const q = $("#q").value.trim().toLowerCase();
    const list = foods.filter((f) => !q || (f.name + " " + f.brand).toLowerCase().includes(q));
    $("#foodList").innerHTML = list.map((f) => `<div class="item" data-id="${f.id}">${thumb(f)}
      <div class="grow"><div class="title">${esc(f.name)}${f.brand ? ` <span class="muted">${esc(f.brand)}</span>` : ""}</div>
      <span class="macros">por 100 g · P ${r1(f.protein)} · C ${r1(f.carbs)} · G ${r1(f.fat)}</span></div>
      <div class="kcal-tag">${r0(f.kcal)}</div></div>`).join("") || '<div class="empty">Sin resultados. Crea el alimento en la pestaña Alimentos.</div>';
    $$("#foodList .item").forEach((el) => el.onclick = () => pickFood(foods.find((f) => f.id == el.dataset.id), selectedMeal()));
  };
  $("#q").oninput = draw; draw(); $("#q").focus();
}
function pickFood(f, meal) {
  const hasUnit = f.unit_g > 0;
  openSheet(`${sheetHead(f.name)}${mealChips(meal)}
    <div class="grid2">${hasUnit ? `<div><label>${esc(f.unit_name || "unidades")}</label><input id="units" inputmode="decimal" value="1"></div>` : ""}
      <div><label>Gramos</label><input id="grams" inputmode="decimal" value="${hasUnit ? f.unit_g : 100}"></div></div>
    <div class="preview"><div class="big" id="pk"></div><div id="pm"></div></div>
    <button class="btn primary" style="width:100%" id="ok">Añadir</button>`);
  bindMealChips();
  const upd = () => { const m = scaleFood(f, toNum($("#grams").value)); $("#pk").textContent = `${r0(m.kcal)} kcal`; $("#pm").innerHTML = macroLine(m); };
  $("#grams").oninput = () => { if (hasUnit) $("#units").value = r1(toNum($("#grams").value) / f.unit_g); upd(); };
  if (hasUnit) $("#units").oninput = () => { $("#grams").value = r1(toNum($("#units").value) * f.unit_g); upd(); };
  $("#ok").onclick = async () => {
    await api("POST", "/api/entries", { date: state.date, meal: selectedMeal(), food_id: f.id, grams: toNum($("#grams").value) });
    closeSheet(); toast("Añadido ✓"); renderToday();
  };
  upd(); $("#grams").select();
}

// --- añadir preset
async function addPreset() {
  const presets = await api("GET", "/api/presets");
  openSheet(`${sheetHead("Añadir preset")}${presets.length ? presets.map((p) => `<div class="item" data-id="${p.id}">
      <div class="thumb">⚡</div><div class="grow"><div class="title">${esc(p.name)}</div>${macroLine(p.totals)}</div>
      <div class="kcal-tag">${r0(p.totals.kcal)}</div></div>`).join("") : '<div class="empty">Aún no tienes presets. Créalos en la pestaña Presets.</div>'}`);
  $$("#sheet .item").forEach((el) => el.onclick = () => pickPreset(presets.find((p) => p.id == el.dataset.id)));
}
function pickPreset(p) {
  openSheet(`${sheetHead(p.name)}${mealChips(p.meal || guessMeal())}
    <label>Multiplicador de todo el preset</label><input id="mult" inputmode="decimal" value="1">
    <label>Gramos por ingrediente (editables)</label>
    ${p.items.map((i, k) => `<div class="preset-ing" style="grid-template-columns:1fr 90px"><div class="title">${esc(i.name)}</div>
      <input data-k="${k}" data-base="${i.grams}" inputmode="decimal" value="${i.grams}"></div>`).join("")}
    <div class="preview"><div class="big" id="pk"></div><div id="pm"></div></div>
    <button class="btn primary" style="width:100%" id="ok">Añadir</button>`);
  bindMealChips();
  const upd = () => {
    const tot = { kcal: 0, protein: 0, carbs: 0, fat: 0 };
    $$("#sheet input[data-k]").forEach((inp) => { const m = scaleFood(p.items[inp.dataset.k], toNum(inp.value)); for (const k in tot) tot[k] += m[k]; });
    $("#pk").textContent = `${r0(tot.kcal)} kcal`; $("#pm").innerHTML = macroLine(tot);
  };
  $("#mult").oninput = () => { const m = toNum($("#mult").value); $$("#sheet input[data-k]").forEach((i) => i.value = r1(i.dataset.base * m)); upd(); };
  $$("#sheet input[data-k]").forEach((i) => i.oninput = upd);
  $("#ok").onclick = async () => {
    const items = $$("#sheet input[data-k]").map((i) => ({ food_id: p.items[i.dataset.k].food_id, grams: toNum(i.value) }));
    await api("POST", "/api/entries/preset", { date: state.date, meal: selectedMeal(), items });
    closeSheet(); toast("Preset añadido ✓"); renderToday();
  };
  upd();
}

// --- solo kcal (sin detallar)
function addQuick() {
  openSheet(`${sheetHead("Solo calorías")}${mealChips(guessMeal())}
    <label>¿Qué ha sido? (opcional)</label><input id="qn" placeholder="Cumple: papas, fuet, queso…">
    <label>Kcal aproximadas</label><input id="qk" inputmode="decimal" placeholder="500">
    <details style="margin-top:10px"><summary class="muted">Añadir macros (opcional)</summary>
      <div class="grid4"><div><label>Prot</label><input id="qp" inputmode="decimal"></div><div><label>Hidr</label><input id="qc" inputmode="decimal"></div><div><label>Grasa</label><input id="qf" inputmode="decimal"></div></div></details>
    <button class="btn primary" style="width:100%;margin-top:16px" id="ok">Añadir</button>`);
  bindMealChips(); $("#qk").focus();
  $("#ok").onclick = async () => {
    if (!toNum($("#qk").value)) return toast("Pon las kcal");
    await api("POST", "/api/entries", { kind: "quick", date: state.date, meal: selectedMeal(), name: $("#qn").value, kcal: toNum($("#qk").value), protein: toNum($("#qp").value), carbs: toNum($("#qc").value), fat: toNum($("#qf").value) });
    closeSheet(); toast("Añadido ✓"); renderToday();
  };
}

// --- editar / borrar entrada
async function editEntry(id) {
  const d = await api("GET", `/api/day/${state.date}`);
  const e = d.entries.find((x) => x.id === id);
  const isFood = e.kind === "food" && e.food_id;
  openSheet(`${sheetHead(e.name)}${mealChips(e.meal)}
    ${isFood ? `<label>Gramos</label><input id="eg" inputmode="decimal" value="${e.grams}"><p class="muted">Las macros se recalculan con los valores actuales del alimento.</p>` : `
    <label>Nombre</label><input id="en" value="${esc(e.name)}"><label>Kcal</label><input id="ek" inputmode="decimal" value="${e.kcal}">
    <div class="grid4"><div><label>Prot</label><input id="ep" inputmode="decimal" value="${e.protein}"></div><div><label>Hidr</label><input id="ec" inputmode="decimal" value="${e.carbs}"></div><div><label>Grasa</label><input id="ef" inputmode="decimal" value="${e.fat}"></div></div>`}
    <button class="btn primary" style="width:100%;margin-top:16px" id="ok">Guardar</button>
    <button class="btn danger" style="width:100%;margin-top:8px" id="del">Eliminar</button>`);
  bindMealChips();
  $("#ok").onclick = async () => {
    const body = isFood ? { grams: toNum($("#eg").value), meal: selectedMeal() }
      : { name: $("#en").value, kcal: toNum($("#ek").value), protein: toNum($("#ep").value), carbs: toNum($("#ec").value), fat: toNum($("#ef").value), meal: selectedMeal() };
    await api("PUT", `/api/entries/${id}`, body); closeSheet(); renderToday();
  };
  $("#del").onclick = async () => { await api("DELETE", `/api/entries/${id}`); closeSheet(); toast("Eliminado"); renderToday(); };
}

// -------------------------------------------------------------------- PRESETS
async function renderPresets() {
  const presets = await api("GET", "/api/presets");
  $("#view").innerHTML = `<h1>Presets</h1>
    <p class="muted">Combinaciones que repites (ej. tu batido). Al añadirlas puedes cambiar cantidades.</p>
    <button class="btn primary" style="width:100%;margin-bottom:12px" onclick="editPreset()">＋ Nuevo preset</button>
    ${presets.map((p) => `<div class="card"><div class="row between"><div class="grow"><div class="title" style="font-weight:700">${esc(p.name)}</div>
        <div class="muted">${p.items.map((i) => `${esc(i.name)} ${r0(i.grams)}g`).join(" + ") || "sin ingredientes"}</div></div>
        <div class="kcal-tag">${r0(p.totals.kcal)} kcal</div></div>
      <div class="row between" style="margin-top:8px">${macroLine(p.totals)}
        <div class="row"><button class="btn small" onclick="editPreset(${p.id})">Editar</button>
        <button class="btn small primary" onclick='state.tab="today";go("today");setTimeout(()=>addPresetById(${p.id}),50)'>Añadir hoy</button></div></div></div>`).join("") || '<div class="empty">Sin presets todavía.</div>'}`;
}
async function addPresetById(id) { const p = (await api("GET", "/api/presets")).find((x) => x.id === id); pickPreset(p); }

async function editPreset(id) {
  const foods = await api("GET", "/api/foods");
  const p = id ? (await api("GET", "/api/presets")).find((x) => x.id === id) : { name: "", meal: "", items: [{ food_id: foods[0]?.id, grams: 100 }] };
  const row = (it) => `<div class="preset-ing"><select>${foods.map((f) => `<option value="${f.id}" ${f.id == it.food_id ? "selected" : ""}>${esc(f.name)}${f.brand ? " – " + esc(f.brand) : ""}</option>`).join("")}</select>
    <input inputmode="decimal" value="${it.grams}" placeholder="g"><button type="button">✕</button></div>`;
  openSheet(`${sheetHead(id ? "Editar preset" : "Nuevo preset")}
    <label>Nombre</label><input id="pn" value="${esc(p.name)}" placeholder="Batido de proteína">
    <label>Comida habitual (opcional)</label>${mealChips(p.meal || "")}
    <label>Ingredientes</label><div id="ings">${p.items.map(row).join("")}</div>
    <button class="btn small" id="addIng">＋ Ingrediente</button>
    <button class="btn primary" style="width:100%;margin-top:16px" id="ok">Guardar</button>
    ${id ? '<button class="btn danger" style="width:100%;margin-top:8px" id="del">Eliminar preset</button>' : ""}`);
  bindMealChips();
  const bindRemove = () => $$("#ings .preset-ing button").forEach((b) => b.onclick = () => b.parentElement.remove());
  bindRemove();
  $("#addIng").onclick = () => { $("#ings").insertAdjacentHTML("beforeend", row({ food_id: foods[0]?.id, grams: 100 })); bindRemove(); };
  $("#ok").onclick = async () => {
    const items = $$("#ings .preset-ing").map((r) => ({ food_id: +$("select", r).value, grams: toNum($("input", r).value) }));
    const body = { name: $("#pn").value, meal: $("#mealChips .chip.on")?.dataset.meal || "", items };
    await (id ? api("PUT", `/api/presets/${id}`, body) : api("POST", "/api/presets", body));
    closeSheet(); renderPresets();
  };
  if (id) $("#del").onclick = async () => { if (confirm("¿Eliminar preset?")) { await api("DELETE", `/api/presets/${id}`); closeSheet(); renderPresets(); } };
}

// ------------------------------------------------------------------ ALIMENTOS
async function renderFoods() {
  $("#view").innerHTML = `<h1>Alimentos</h1>
    <button class="btn primary" style="width:100%;margin-bottom:10px" onclick="editFood()">＋ Nuevo alimento</button>
    <input id="fq" placeholder="Buscar…" value="${esc(state.foodQuery)}"><div id="fl" style="margin-top:10px"></div>`;
  const foods = await api("GET", "/api/foods");
  const draw = () => {
    const q = $("#fq").value.trim().toLowerCase(); state.foodQuery = $("#fq").value;
    $("#fl").innerHTML = foods.filter((f) => !q || (f.name + " " + f.brand).toLowerCase().includes(q)).map((f) => `<div class="item" data-id="${f.id}">${thumb(f)}
      <div class="grow"><div class="title">${esc(f.name)}${f.brand ? ` <span class="muted">${esc(f.brand)}</span>` : ""}</div>
      <span class="macros">por 100 g · P ${r1(f.protein)} · C ${r1(f.carbs)} · G ${r1(f.fat)}</span></div><div class="kcal-tag">${r0(f.kcal)}</div></div>`).join("") || '<div class="empty">Nada por aquí.</div>';
    $$("#fl .item").forEach((el) => el.onclick = () => editFood(+el.dataset.id, foods));
  };
  $("#fq").oninput = draw; draw();
}

function editFood(id, foods) {
  const f = (foods || []).find((x) => x.id === id) || { name: "", brand: "", kcal: "", protein: "", carbs: "", fat: "", unit_g: "", unit_name: "", photo: "" };
  const num = (k, label) => `<div><label>${label}</label><input id="f_${k}" inputmode="decimal" value="${f[k] ?? ""}"></div>`;
  openSheet(`${sheetHead(id ? "Editar alimento" : "Nuevo alimento")}
    <label>Nombre</label><input id="f_name" value="${esc(f.name)}"><label>Marca (opcional)</label><input id="f_brand" value="${esc(f.brand)}">
    <h2>Por cada 100 g / ml</h2>
    <div class="grid2">${num("kcal", "Kcal")}${num("protein", "Proteína (g)")}${num("carbs", "Hidratos (g)")}${num("fat", "Grasa (g)")}</div>
    <h2>Unidad (opcional)</h2>
    <div class="grid2"><div><label>Nombre (huevo, scoop…)</label><input id="f_unit_name" value="${esc(f.unit_name)}"></div>${num("unit_g", "Gramos por unidad")}</div>
    <label>Foto</label><input id="f_photo" type="file" accept="image/*">
    <button class="btn primary" style="width:100%;margin-top:16px" id="ok">Guardar</button>
    ${id ? '<button class="btn danger" style="width:100%;margin-top:8px" id="del">Eliminar</button>' : ""}`);
  $("#ok").onclick = async () => {
    const body = {};
    ["name", "brand", "kcal", "protein", "carbs", "fat", "unit_g", "unit_name"].forEach((k) => body[k] = $("#f_" + k).value);
    const res = await (id ? api("PUT", `/api/foods/${id}`, body) : api("POST", "/api/foods", body));
    const file = $("#f_photo").files[0];
    if (file) { const fd = new FormData(); fd.append("photo", file); await api("POST", `/api/foods/${id || res.id}/photo`, fd); }
    closeSheet(); renderFoods();
  };
  if (id) $("#del").onclick = async () => { if (confirm("¿Eliminar alimento? El histórico se conserva.")) { await api("DELETE", `/api/foods/${id}`); closeSheet(); renderFoods(); } };
}

// ------------------------------------------------------------------ HISTÓRICO
async function renderHistory() {
  const h = await api("GET", `/api/history?days=${state.histDays}`);
  const g = h.goals, a = h.average;
  const maxK = Math.max(g.kcal, ...h.days.map((d) => d.kcal), 1);
  $("#view").innerHTML = `<h1>Histórico</h1>
    <div class="chips">${[7, 30, 90].map((n) => `<button class="chip ${n === state.histDays ? "on" : ""}" onclick="state.histDays=${n};renderHistory()">${n} días</button>`).join("")}</div>
    <div class="card"><div class="muted">Promedio diario · ${h.logged_days} día(s) con registros</div>
      <div class="big" style="margin:6px 0">${r0(a.kcal)} <span class="muted">kcal</span></div>
      <div class="macros"><b class="mp">P ${r0(a.protein)} g</b> · <b class="mc">C ${r0(a.carbs)} g</b> · <b class="mf">G ${r0(a.fat)} g</b></div></div>
    ${h.days.map((d) => `<div class="item day-row" onclick="state.date='${d.date}';go('today')"><div class="grow">
      <div class="row between"><div class="title" style="text-transform:capitalize">${parseISO(d.date).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" })}</div><div class="kcal-tag">${r0(d.kcal)} kcal</div></div>
      ${macroLine(d)}<div class="bar ${d.kcal > g.kcal ? "over" : ""}"><i style="width:${(d.kcal / maxK) * 100}%;background:var(--kcal)"></i></div></div></div>`).join("") || '<div class="empty">Sin registros en este periodo.</div>'}
    <h2>Mis objetivos diarios</h2>
    <div class="card"><div class="grid2">
      <div><label>Kcal</label><input id="g_kcal" inputmode="decimal" value="${g.kcal}"></div><div><label>Proteína (g)</label><input id="g_protein" inputmode="decimal" value="${g.protein}"></div>
      <div><label>Hidratos (g)</label><input id="g_carbs" inputmode="decimal" value="${g.carbs}"></div><div><label>Grasa (g)</label><input id="g_fat" inputmode="decimal" value="${g.fat}"></div></div>
      <button class="btn primary" style="width:100%;margin-top:12px" id="saveGoals">Guardar objetivos</button></div>`;
  $("#saveGoals").onclick = async () => {
    await api("PUT", "/api/settings", Object.fromEntries(["kcal", "protein", "carbs", "fat"].map((k) => [k, toNum($("#g_" + k).value)])));
    toast("Objetivos guardados ✓"); renderHistory();
  };
}

render();
