/* Calculadora de macros - frontend sin dependencias. Iconos: icons.js · Gráficas: charts.js */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const MEALS = ["desayuno", "comida", "merienda", "cena", "otro"];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const r0 = (n) => Math.round(n);
const r1 = (n) => Math.round(n * 10) / 10;
const toNum = (v) => parseFloat(String(v).replace(",", ".")) || 0;

// La fecha se detecta en el navegador (hora local), así no depende de la zona horaria del servidor.
const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseISO = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const shiftDay = (s, n) => { const d = parseISO(s); d.setDate(d.getDate() + n); return isoDate(d); };
const guessMeal = () => { const h = new Date().getHours(); return h < 11 ? "desayuno" : h < 16 ? "comida" : h < 19 ? "merienda" : "cena"; };

const CATEGORIES = [
  ["todos", "Todos"],
  ["desayuno", "Desayunos"],
  ["lacteos", "Lácteos / Boles"],
  ["carnes_pescados", "Carnes / Pescados"],
  ["hidratos_panes", "Hidratos / Panes"],
  ["combos", "Combos"],
  ["otros", "Otros"]
];

const categoryChips = (sel, idPrefix = "catFilter") => `
  <div class="cat-scroll" id="${idPrefix}">
    ${CATEGORIES.map(([k, label]) => `<button type="button" class="cat-chip ${k === sel ? "on" : ""}" data-cat="${k}">${label}</button>`).join("")}
  </div>
`;

// Caching local en localStorage para carga instantánea y persistencia offline
function getLocalCache(key, fallback = null) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
function setLocalCache(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}

let lastToday = isoDate(new Date());
const state = { tab: "today", date: lastToday, foodQuery: "", histDays: 7, foodCat: "todos", presetCat: "todos" };

// ---------------------------------------------------------------------- red
async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(url, opt); }
  catch {
    // Si estamos sin conexión, intentar devolver caché de localStorage para peticiones GET
    if (method === "GET") {
      const cached = getLocalCache("api_cache:" + url);
      if (cached) return cached;
    }
    toast("Sin conexión con el servidor"); throw new Error("offline");
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !url.startsWith("/api/auth/")) { closeSheet(); renderLogin(); throw new Error("auth"); }
  if (!res.ok) { toast(data.error || "Error"); throw new Error(data.error || res.statusText); }
  if (method === "GET") setLocalCache("api_cache:" + url, data);
  return data;
}

let toastTimer;
function toast(msg, ok = false) {
  const t = $("#toast"); t.innerHTML = (ok ? icon("check", 16) : "") + esc(msg); t.classList.remove("hidden");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), 2400);
}

// ------------------------------------------------------------------ hojas modales
let sheetCleanup = null;
function openSheet(html, { onClose } = {}) { sheetCleanup = onClose || null; $("#sheet").innerHTML = html; $("#modal").classList.remove("hidden"); $("#sheet").scrollTop = 0; }
function closeSheet() { sheetCleanup?.(); sheetCleanup = null; $("#modal").classList.add("hidden"); $("#sheet").innerHTML = ""; }
$("#modal").addEventListener("mousedown", (e) => { if (e.target.id === "modal") closeSheet(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").classList.contains("hidden")) closeSheet(); });
$("#sheet").addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT" && e.target.type !== "file" && $("#ok")) { e.preventDefault(); $("#ok").click(); } });
const sheetHead = (title) => `<div class="head"><h1>${esc(title)}</h1><button class="icon-btn ghost" onclick="closeSheet()" aria-label="Cerrar">${icon("x", 22)}</button></div>`;

// ---------------------------------------------------------------- piezas de UI
const macroLine = (m) => `<span class="macros"><b class="mp">P ${r1(m.protein)}</b> · <b class="mc">C ${r1(m.carbs)}</b> · <b class="mf">G ${r1(m.fat)}</b></span>`;
const thumb = (f, fallback = "apple") => f.photo ? `<img class="thumb" loading="lazy" src="/uploads/${esc(f.photo)}" alt="">` : `<div class="thumb">${icon(fallback, 22)}</div>`;
const scaleFood = (f, g) => ({ kcal: f.kcal * g / 100, protein: f.protein * g / 100, carbs: f.carbs * g / 100, fat: f.fat * g / 100 });
const mealChips = (sel) => `<div class="chips" id="mealChips">${MEALS.map((m) => `<button type="button" class="chip ${m === sel ? "on" : ""}" data-meal="${m}">${icon(MEAL_ICON[m], 15)} ${m}</button>`).join("")}</div>`;
function bindMealChips() { $$("#mealChips .chip").forEach((b) => b.onclick = () => { $$("#mealChips .chip").forEach((x) => x.classList.remove("on")); b.classList.add("on"); }); }
const selectedMeal = () => $("#mealChips .chip.on")?.dataset.meal || "otro";
const foodRow = (f, extra = "", fallback = "apple") => `<div class="item" data-id="${f.id ?? ""}">${thumb(f, fallback)}
  <div class="grow"><div class="title">${esc(f.name)}${f.brand ? ` <span class="muted">${esc(f.brand)}</span>` : ""}</div>
  <span class="macros">100 g · <b class="mp">P ${r1(f.protein)}</b> · <b class="mc">C ${r1(f.carbs)}</b> · <b class="mf">G ${r1(f.fat)}</b></span></div>
  <div class="kcal-tag">${r0(f.kcal)}<small>kcal</small></div>${extra}</div>`;
const emptyBox = (ic, text) => `<div class="empty">${icon(ic, 40)}<div>${text}</div></div>`;

// ----------------------------------------------------------------- navegación
const TABS = [["today", "home", "Hoy"], ["presets", "zap", "Presets"], ["foods", "apple", "Alimentos"], ["progress", "chart", "Progreso"], ["settings", "sliders", "Ajustes"]];
function buildNav() {
  $("#tabs").innerHTML = `<div class="brand">${icon("flame", 30)}</div>` + TABS.map(([id, ic, label]) =>
    `<button data-tab="${id}" class="${id === state.tab ? "active" : ""}">${icon(ic, 23)}${label}</button>`).join("");
  $$("#tabs button").forEach((b) => b.onclick = () => go(b.dataset.tab));
}
function go(tab) { state.tab = tab; buildNav(); render(); }
function render() {
  document.body.classList.remove("locked");
  ({ today: renderToday, presets: renderPresets, foods: renderFoods, progress: renderProgress, settings: renderSettings })[state.tab]();
  window.scrollTo(0, 0);
}
// Si la app se queda abierta toda la noche, al volver pasa a "hoy" sola
document.addEventListener("visibilitychange", () => {
  const now = isoDate(new Date());
  if (!document.hidden && now !== lastToday) { if (state.date === lastToday) state.date = now; lastToday = now; if (state.tab === "today") renderToday(); }
});

// ============================================================================ HOY
async function renderToday() {
  let d = await api("GET", `/api/day/${state.date}`);
  if (d.entries && d.entries.length > 0) {
    setLocalCache("journal_day:" + state.date, d.entries);
  } else {
    const saved = getLocalCache("journal_day:" + state.date, []);
    if (Array.isArray(saved) && saved.length > 0) {
      try {
        const byM = {};
        saved.forEach((e) => (byM[e.meal || "otro"] ||= []).push({
          name: e.name,
          grams: e.grams,
          kcal: e.kcal,
          protein: e.protein,
          carbs: e.carbs,
          fat: e.fat,
          matched_food_id: e.food_id || null,
        }));
        for (const [m, items] of Object.entries(byM)) {
          await api("POST", "/api/ai/apply", { date: state.date, meal: m, items });
        }
        d = await api("GET", `/api/day/${state.date}`);
        toast("Registros recuperados automáticamente", true);
      } catch {}
    }
  }
  const isToday = state.date === isoDate(new Date());
  const label = parseISO(state.date).toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
  const g = d.goals, t = d.totals, remaining = g.kcal - t.kcal;
  const pct = (v, goal) => Math.min(100, goal ? (v / goal) * 100 : 0);
  const macro = (key, name, ic, cls, color) => `<div class="macro"><div class="top"><span class="${cls}">${icon(ic, 14)}</span>${name}</div>
      <div class="val">${r0(t[key])}<small> / ${r0(g[key])} g</small></div>
      <div class="bar ${t[key] > g[key] ? "over" : ""}"><i style="width:${pct(t[key], g[key])}%;background:${color}"></i></div></div>`;

  const byMeal = {};
  d.entries.forEach((e) => (byMeal[e.meal] ||= []).push(e));
  const meals = MEALS.filter((m) => byMeal[m]).map((m) => {
    const list = byMeal[m], sum = list.reduce((a, e) => a + e.kcal, 0);
    const canPreset = list.filter((e) => e.kind === "food" && e.food_id).length > 0;
    return `<div class="meal-head"><h2>${icon(MEAL_ICON[m], 16)} ${m} · ${r0(sum)} kcal</h2>
      ${canPreset ? `<button class="icon-btn ghost" title="Guardar como preset" onclick="saveMealAsPreset('${m}')">${icon("bookmark", 18)}</button>` : ""}</div>` +
      list.map((e) => `<div class="item" onclick="editEntry(${e.id})">
        <div class="thumb ${e.kind === "quick" ? "accent" : ""}">${icon(e.kind === "quick" ? "flame" : "utensils", 21)}</div>
        <div class="grow"><div class="title">${esc(e.name)}${e.grams ? ` <span class="muted">${r0(e.grams)} g</span>` : ""}</div>
          ${e.protein || e.carbs || e.fat ? macroLine(e) : '<span class="macros">solo calorías</span>'}</div>
        <div class="kcal-tag">${r0(e.kcal)}<small>kcal</small></div></div>`).join("");
  }).join("");

  $("#view").innerHTML = `
    <div class="datebar">
      <button class="icon-btn" onclick="changeDay(-1)" aria-label="Día anterior">${icon("left", 22)}</button>
      <div class="date" onclick="pickDate()"><strong>${isToday ? "Hoy" : label}</strong><span class="muted">${isToday ? label : "Toca para cambiar de día"}</span></div>
      ${isToday ? "" : `<button class="chip on" onclick="state.date=isoDate(new Date());renderToday()">Hoy</button>`}
      <a class="icon-btn" href="/report?date=${state.date}" target="_blank" title="Ver / Descargar informe PDF" aria-label="Informe PDF">${icon("download", 20)}</a>
      <button class="icon-btn" onclick="changeDay(1)" aria-label="Día siguiente">${icon("right", 22)}</button>
    </div>
    <div class="card">
      <div class="summary">
        <div class="ring-wrap">${ringChart(t.kcal, g.kcal)}
          <div class="center"><div class="big">${r0(t.kcal)}</div><div class="muted">kcal</div></div></div>
        <div class="stats">
          <div class="stat">
            <div class="lbl">${
              remaining >= 0
                ? "Te quedan"
                : t.kcal <= g.kcal * 1.10
                ? "En rango (±10%)"
                : "Te has pasado"
            }</div>
            <div class="val" style="color:${
              remaining >= 0
                ? "var(--accent)"
                : t.kcal <= g.kcal * 1.10
                ? "var(--accent)"
                : "var(--danger)"
            }">${remaining < 0 && t.kcal <= g.kcal * 1.10 ? "+" : ""}${r0(Math.abs(remaining))} kcal</div>
          </div>
          <div class="stat"><div class="lbl">Déficit vs TDEE (3350)</div>
            <div class="val" style="color:var(--accent)">-${r0(3350 - t.kcal)} kcal</div></div>
          <div class="stat"><div class="lbl">Objetivo</div><div class="val">${r0(g.kcal)} kcal</div></div>
        </div>
      </div>
      <div class="macro-grid">${macro("protein", "Proteína", "beef", "mp", "var(--p)")}${macro("carbs", "Hidratos", "wheat", "mc", "var(--c)")}${macro("fat", "Grasa", "droplet", "mf", "var(--f)")}</div>
    </div>
    <div class="tiles">
      <button class="tile primary" onclick="addFood()"><span class="ic">${icon("plus", 22)}</span>Alimento</button>
      <button class="tile" onclick="addPreset()"><span class="ic">${icon("zap", 20)}</span>Preset</button>
      <button class="tile" onclick="addQuick()"><span class="ic">${icon("flame", 20)}</span>Solo kcal</button>
      <button class="tile ai" onclick="openAiSheet()"><span class="ic">${icon("sparkles", 20)}</span>IA / Voz</button>
      <button class="tile" onclick="repeatDay()"><span class="ic">${icon("repeat", 20)}</span>Repetir</button>
    </div>
    ${meals || emptyBox("utensils", "Nada apuntado este día.<br>Pulsa <b>Alimento</b> para empezar.")}`;
}
function changeDay(n) { state.date = shiftDay(state.date, n); renderToday(); }
function pickDate() {
  openSheet(`${sheetHead("Ir a un día")}<input id="pd" type="date" value="${state.date}">
    <button class="btn primary block" style="margin-top:14px" id="ok">Ir</button>`);
  $("#ok").onclick = () => { if ($("#pd").value) { state.date = $("#pd").value; closeSheet(); renderToday(); } };
}

// --- repetir un día
function repeatDay() {
  openSheet(`${sheetHead("Repetir comidas")}
    <p class="muted">Copia lo que comiste otro día a <b>${esc(state.date)}</b>.</p>
    <label>Copiar desde</label><input id="rd" type="date" value="${shiftDay(state.date, -1)}">
    <label>Qué copiar</label><select id="rm"><option value="">Todo el día</option>${MEALS.map((m) => `<option value="${m}">Solo ${m}</option>`).join("")}</select>
    <button class="btn primary block" style="margin-top:14px" id="ok">${icon("copy", 18)} Copiar</button>`);
  $("#ok").onclick = async () => {
    const r = await api("POST", "/api/entries/copy", { from_date: $("#rd").value, to_date: state.date, meal: $("#rm").value || undefined });
    closeSheet(); toast(r.copied ? `${r.copied} entrada(s) copiadas` : "Ese día no tenía nada", !!r.copied); renderToday();
  };
}

// --- guardar una comida como preset
async function saveMealAsPreset(meal) {
  const d = await api("GET", `/api/day/${state.date}`);
  const ids = d.entries.filter((e) => e.meal === meal && e.kind === "food" && e.food_id).map((e) => e.id);
  openSheet(`${sheetHead("Guardar como preset")}<p class="muted">Se guardarán los ${ids.length} alimentos de ${esc(meal)} con sus cantidades.</p>
    <label>Nombre del preset</label><input id="pn" placeholder="Mi desayuno de siempre">
    <button class="btn primary block" style="margin-top:14px" id="ok">${icon("bookmark", 18)} Guardar</button>`);
  $("#pn").focus();
  $("#ok").onclick = async () => {
    if (!$("#pn").value.trim()) return toast("Ponle un nombre");
    await api("POST", "/api/presets/from-entries", { name: $("#pn").value, meal, entry_ids: ids });
    closeSheet(); toast("Preset guardado", true);
  };
}

// --- añadir alimento (mis alimentos / online) con categorías
async function addFood() {
  const foods = await api("GET", "/api/foods");
  openSheet(`${sheetHead("Añadir alimento")}${mealChips(guessMeal())}
    ${categoryChips(state.foodCat, "foodCatChips")}
    <div class="search"><span>${icon("search", 18)}</span><input id="q" placeholder="Buscar en mis alimentos…" autocomplete="off">
      <button class="icon-btn ghost scan" onclick="scanBarcode(selectedMeal())" title="Escanear código de barras">${icon("barcode", 22)}</button></div>
    <div id="foodList" style="margin-top:12px"></div>`);
  bindMealChips();

  const bindCat = () => {
    $$("#foodCatChips .cat-chip").forEach((b) => b.onclick = () => {
      $$("#foodCatChips .cat-chip").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      state.foodCat = b.dataset.cat;
      draw();
    });
  };
  bindCat();

  const draw = () => {
    const q = $("#q").value.trim().toLowerCase();
    const cat = state.foodCat;
    const list = foods.filter((f) => {
      const matchCat = !cat || cat === "todos" || (f.category || "otros") === cat;
      const matchQ = !q || (f.name + " " + (f.brand || "")).toLowerCase().includes(q);
      return matchCat && matchQ;
    });
    $("#foodList").innerHTML = list.map((f) => foodRow(f)).join("") + (q.length > 1 ? `<button class="btn block" id="goOnline">${icon("globe", 18)} Buscar «${esc($("#q").value.trim())}» online</button>` : "")
      || emptyBox("apple", "No hay alimentos en esta categoría.");
    $$("#foodList .item").forEach((el) => el.onclick = () => pickFood(foods.find((f) => f.id == el.dataset.id), selectedMeal()));
    $("#goOnline")?.addEventListener("click", () => onlineSearch($("#q").value.trim(), selectedMeal()));
  };
  $("#q").oninput = draw; draw(); $("#q").focus();
}

function pickFood(f, meal) {
  const hasUnit = f.unit_g > 0;
  openSheet(`${sheetHead(f.name)}${mealChips(meal)}
    <div class="grid2">
      <div><label>Gramos directos</label><input id="grams" inputmode="decimal" value="${hasUnit ? f.unit_g : 100}"></div>
      ${hasUnit ? `<div><label>${esc(f.unit_name || "Unidad")} (1 ud = ${r0(f.unit_g)}g)</label><input id="units" inputmode="decimal" value="1"></div>` : ""}
    </div>
    <div class="preview"><div class="big" id="pk"></div><div id="pm"></div></div>
    <button class="btn primary block" id="ok">${icon("plus", 18)} Añadir</button>`);
  bindMealChips();
  const upd = () => { const m = scaleFood(f, toNum($("#grams").value)); $("#pk").textContent = `${r0(m.kcal)} kcal`; $("#pm").innerHTML = macroLine(m); };
  $("#grams").oninput = () => { if (hasUnit) $("#units").value = r1(toNum($("#grams").value) / f.unit_g); upd(); };
  if (hasUnit) $("#units").oninput = () => { $("#grams").value = r1(toNum($("#units").value) * f.unit_g); upd(); };
  $("#ok").onclick = async () => {
    await api("POST", "/api/entries", { date: state.date, meal: selectedMeal(), food_id: f.id, grams: toNum($("#grams").value) });
    closeSheet(); toast("Añadido", true); renderToday();
  };
  upd(); ($("#units") || $("#grams")).select();
}

// --- buscar online (Open Food Facts) y guardar en mis alimentos
async function saveOnline(item) {
  const r = await api("POST", "/api/foods", item);
  return { ...item, id: r.id, photo: r.photo, unit_g: null, unit_name: "" };
}
function onlineSearch(query = "", meal = null, importOnly = false) {
  openSheet(`${sheetHead("Buscar online")}<p class="muted">Base de datos abierta Open Food Facts. Al elegir un producto se guarda en tus alimentos.</p>
    <div class="search"><span>${icon("search", 18)}</span><input id="oq" placeholder="Ej. yogur proteínas Hacendado" value="${esc(query)}" autocomplete="off">
      <button class="icon-btn ghost scan" onclick="scanBarcode(${meal ? `'${meal}'` : "null"})" title="Escanear código">${icon("barcode", 22)}</button></div>
    <div id="ores" style="margin-top:12px"></div>`);
  let last = 0;
  const run = async () => {
    const q = $("#oq").value.trim(); if (q.length < 2) return;
    const id = ++last; $("#ores").innerHTML = `<div class="empty small">${icon("search", 26, "spin")}Buscando…</div>`;
    let list; try { list = await api("GET", `/api/off/search?q=${encodeURIComponent(q)}`); } catch { if (id === last) $("#ores").innerHTML = emptyBox("globe", "No se pudo buscar online. ¿Tienes internet?"); return; }
    if (id !== last) return;
    $("#ores").innerHTML = list.length ? list.map((f, i) => foodRow({ ...f, id: i, photo: "" }, "", "globe")).join("") : emptyBox("search", "Sin resultados");
    $$("#ores .item").forEach((el) => el.onclick = async () => {
      const f = await saveOnline(list[el.dataset.id]);
      if (importOnly || !meal) { closeSheet(); toast("Guardado en tus alimentos", true); if (state.tab === "foods") renderFoods(); } else pickFood(f, meal);
    });
  };
  $("#oq").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  if (query.length > 1) run(); else $("#oq").focus();
}

// --- escáner de código de barras
function scanBarcode(meal) {
  let stream = null, stopped = false;
  const canCam = "BarcodeDetector" in window && navigator.mediaDevices?.getUserMedia && window.isSecureContext;
  openSheet(`${sheetHead("Código de barras")}
    ${canCam ? '<video class="scan" id="vid" playsinline muted></video>' : `<div class="note">${icon("info", 18)}<div>La cámara solo funciona en este navegador si abres la app con <b>https</b> o desde el propio PC (<b>localhost</b>). Escribe el código a mano.</div></div>`}
    <label>Código (EAN)</label><input id="bc" inputmode="numeric" placeholder="8480000340420">
    <button class="btn primary block" style="margin-top:14px" id="ok">${icon("search", 18)} Buscar</button>`,
    { onClose: () => { stopped = true; stream?.getTracks().forEach((t) => t.stop()); } });
  const lookup = async (code) => {
    if (stopped) return; stopped = true; stream?.getTracks().forEach((t) => t.stop());
    const r = await api("GET", `/api/off/barcode/${encodeURIComponent(code)}`).catch(() => null);
    if (!r) return scanBarcode(meal);
    const food = r.local || await saveOnline(r.online);
    pickFood(food, meal || guessMeal());
  };
  $("#ok").onclick = () => { const c = $("#bc").value.trim(); if (c) lookup(c); };
  if (canCam) (async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      const v = $("#vid"); v.srcObject = stream; await v.play();
      const det = new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] });
      const tick = async () => { if (stopped) return; try { const c = await det.detect(v); if (c[0]) return lookup(c[0].rawValue); } catch {} requestAnimationFrame(tick); };
      tick();
    } catch { $("#vid")?.remove(); toast("No se pudo abrir la cámara"); }
  })();
}

// --- añadir preset con categorías
async function addPreset() {
  const presets = await api("GET", "/api/presets");
  openSheet(`${sheetHead("Añadir preset / combo")}${mealChips(guessMeal())}
    ${categoryChips(state.presetCat, "presetCatChips")}
    <div id="presetList" style="margin-top:12px"></div>`);
  bindMealChips();

  const bindCat = () => {
    $$("#presetCatChips .cat-chip").forEach((b) => b.onclick = () => {
      $$("#presetCatChips .cat-chip").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      state.presetCat = b.dataset.cat;
      draw();
    });
  };
  bindCat();

  const draw = () => {
    const cat = state.presetCat;
    const list = presets.filter((p) => !cat || cat === "todos" || (p.category || "combos") === cat);
    $("#presetList").innerHTML = list.length ? list.map((p) => `<div class="item" data-id="${p.id}">
      <div class="thumb accent">${icon("zap", 22)}</div>
      <div class="grow">
        <div class="title">${esc(p.name)}</div>
        <div class="muted" style="font-size:.78rem;white-space:normal">${p.items.map((i) => `${r0(i.grams)}g ${esc(i.name)}`).join(" · ")}</div>
        ${macroLine(p.totals)}
      </div>
      <div class="kcal-tag">${r0(p.totals.kcal)}<small>kcal</small></div></div>`).join("")
      : emptyBox("zap", "No hay presets en esta categoría.");
    $$("#presetList .item").forEach((el) => el.onclick = () => pickPreset(presets.find((p) => p.id == el.dataset.id)));
  };
  draw();
}

function pickPreset(p) {
  openSheet(`${sheetHead(p.name)}${mealChips(p.meal || guessMeal())}
    <label>Multiplicador de todo el plato/combo</label><input id="mult" inputmode="decimal" value="1">
    <label>Gramos por ingrediente (ajustables en tiempo real)</label>
    ${p.items.map((i, k) => `<div class="ing-name"><div class="title">${esc(i.name)}</div>
      <input data-k="${k}" data-base="${i.grams}" inputmode="decimal" value="${i.grams}"></div>`).join("")}
    <div class="preview"><div class="big" id="pk"></div><div id="pm"></div></div>
    <button class="btn primary block" id="addComboGrouped">${icon("zap", 18)} Añadir en 1 línea agrupada</button>
    <button class="btn block" style="margin-top:8px" id="addComboItems">${icon("list", 18)} Añadir alimentos desglosados</button>`);
  bindMealChips();
  const upd = () => {
    const tot = { kcal: 0, protein: 0, carbs: 0, fat: 0 };
    $$("#sheet input[data-k]").forEach((inp) => { const m = scaleFood(p.items[inp.dataset.k], toNum(inp.value)); for (const k in tot) tot[k] += m[k]; });
    $("#pk").textContent = `${r0(tot.kcal)} kcal`; $("#pm").innerHTML = macroLine(tot);
  };
  $("#mult").oninput = () => { const m = toNum($("#mult").value); $$("#sheet input[data-k]").forEach((i) => i.value = r1(i.dataset.base * m)); upd(); };
  $$("#sheet input[data-k]").forEach((i) => i.oninput = upd);

  const getItems = () => $$("#sheet input[data-k]").map((i) => ({ food_id: p.items[i.dataset.k].food_id, grams: toNum(i.value) }));

  $("#addComboGrouped").onclick = async () => {
    const items = getItems();
    await api("POST", "/api/entries/preset", { date: state.date, meal: selectedMeal(), name: p.name, grouped: true, items });
    closeSheet(); toast("Combo añadido agrupado", true); renderToday();
  };

  $("#addComboItems").onclick = async () => {
    const items = getItems();
    await api("POST", "/api/entries/preset", { date: state.date, meal: selectedMeal(), name: p.name, grouped: false, items });
    closeSheet(); toast("Alimentos añadidos por separado", true); renderToday();
  };
  upd();
}

// --- solo kcal (sin detallar)
function addQuick() {
  openSheet(`${sheetHead("Solo calorías")}<p class="muted">Para cuando no quieres detallar: «cumple ≈ 500 kcal».</p>${mealChips(guessMeal())}
    <label>¿Qué ha sido? (opcional)</label><input id="qn" placeholder="Cumple: papas, fuet, queso…">
    <label>Kcal aproximadas</label><input id="qk" inputmode="decimal" placeholder="500">
    <details><summary>Añadir macros (opcional)</summary>
      <div class="grid3"><div><label>Prot</label><input id="qp" inputmode="decimal"></div><div><label>Hidr</label><input id="qc" inputmode="decimal"></div><div><label>Grasa</label><input id="qf" inputmode="decimal"></div></div></details>
    <button class="btn primary block" style="margin-top:16px" id="ok">${icon("plus", 18)} Añadir</button>`);
  bindMealChips(); $("#qk").focus();
  $("#ok").onclick = async () => {
    if (!toNum($("#qk").value)) return toast("Pon las kcal");
    await api("POST", "/api/entries", { kind: "quick", date: state.date, meal: selectedMeal(), name: $("#qn").value, kcal: toNum($("#qk").value), protein: toNum($("#qp").value), carbs: toNum($("#qc").value), fat: toNum($("#qf").value) });
    closeSheet(); toast("Añadido", true); renderToday();
  };
}

// --- Asistente Gemini (texto, voz, foto)
// --- Asistente Gemini (audio de voz hasta 2 min, texto, foto)
function openAiSheet() {
  let attachedImage = null;
  let mediaStream = null;
  let mediaRecorder = null;
  let recordedChunks = [];
  let audioBlob = null;
  let audioBase64 = null;
  let audioMime = "audio/webm";
  let audioDurationSec = 0;
  let recordTimer = null;
  let recordSeconds = 0;
  let isRecording = false;
  const MAX_RECORD_SECONDS = 120; // 2 minutos máximo

  function formatTime(s) {
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m.toString().padStart(2, "0")}:${rem.toString().padStart(2, "0")}`;
  }

  function getBestAudioMimeType() {
    if (!window.MediaRecorder) return "";
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/aac",
      "audio/ogg;codecs=opus",
      "audio/wav",
    ];
    for (const c of candidates) {
      try {
        if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(c)) {
          return c;
        }
      } catch {}
    }
    return "";
  }

  openSheet(`
    ${sheetHead("Asistente Gemini")}
    <p class="muted" style="margin-top:0">Graba una nota de voz (hasta 2 min), escribe lo que has comido o sube una foto de tu plato o etiqueta.</p>
    ${mealChips(guessMeal())}

    <!-- Sección de Audio / Voz -->
    <div id="aiAudioSection" style="margin:10px 0"></div>

    <div style="margin:8px 0">
      <textarea id="aiInput" rows="2" style="width:100%;resize:vertical" placeholder="Detalles opcionales o escribe aquí si prefieres no usar voz (ej: ensalada con atún, huevo, tomate...)"></textarea>
    </div>

    <div id="aiAttachWrap" class="hidden"></div>

    <div class="row" style="gap:8px;margin-bottom:12px">
      <button type="button" class="btn small" id="aiPhotoBtn">${icon("camera", 16)} Adjuntar foto de comida</button>
      <input type="file" id="aiPhotoInput" accept="image/*" class="hidden">
    </div>

    <button class="btn primary block" id="aiSubmit" style="font-size:1.02rem;padding:13px">${icon("sparkles", 18)} Analizar con Gemini</button>
    <div id="aiResults"></div>
  `, {
    onClose: () => {
      cleanupRecording();
    }
  });

  bindMealChips();
  const inp = $("#aiInput");
  const audioSection = $("#aiAudioSection");

  function cleanupRecording() {
    if (recordTimer) {
      clearInterval(recordTimer);
      recordTimer = null;
    }
    if (mediaRecorder && isRecording) {
      try { mediaRecorder.stop(); } catch {}
    }
    if (mediaStream) {
      try { mediaStream.getTracks().forEach(t => t.stop()); } catch {}
      mediaStream = null;
    }
    isRecording = false;
  }

  function renderAudioState() {
    if (isRecording) {
      audioSection.innerHTML = `
        <div class="audio-recorder">
          <div class="rec-live">
            <div class="row" style="gap:8px">
              <div class="rec-dot"></div>
              <span class="rec-timer" id="recTimerText">${formatTime(recordSeconds)} / ${formatTime(MAX_RECORD_SECONDS)}</span>
            </div>
            <div class="rec-waves">
              <div class="rec-wave-bar"></div>
              <div class="rec-wave-bar"></div>
              <div class="rec-wave-bar"></div>
              <div class="rec-wave-bar"></div>
              <div class="rec-wave-bar"></div>
            </div>
          </div>
          <div class="grid2" style="margin-top:6px">
            <button type="button" class="btn primary small" id="stopRecBtn">${icon("check", 16)} Terminar y usar audio</button>
            <button type="button" class="btn danger small" id="cancelRecBtn">${icon("x", 16)} Cancelar</button>
          </div>
        </div>
      `;
      $("#stopRecBtn").onclick = () => stopRecording(true);
      $("#cancelRecBtn").onclick = () => stopRecording(false);
    } else if (audioBase64) {
      audioSection.innerHTML = `
        <div class="audio-card">
          <div class="row" style="gap:10px;flex:1;min-width:0">
            <div class="thumb accent" style="width:42px;height:42px;color:var(--accent);background:color-mix(in srgb, var(--accent) 15%, var(--card2))">
              ${icon("audioLines", 22)}
            </div>
            <div class="grow" style="min-width:0">
              <div class="title" style="font-size:.9rem;font-weight:700">Nota de voz lista (${formatTime(audioDurationSec)})</div>
              <div class="muted" style="font-size:.78rem;color:var(--accent)">Audio preparado para enviar a Gemini</div>
            </div>
          </div>
          <div class="row" style="gap:6px;flex:none">
            <button type="button" class="btn small" id="playAudioBtn" title="Reproducir">${icon("play", 15)} Escuchar</button>
            <button type="button" class="icon-btn ghost" id="discardAudioBtn" title="Borrar audio y volver a grabar">${icon("trash", 17)}</button>
          </div>
        </div>
        <audio id="audioPreviewPlayer" class="hidden" preload="auto"></audio>
      `;
      const player = $("#audioPreviewPlayer");
      if (player && audioBlob) {
        player.src = URL.createObjectURL(audioBlob);
      }
      let isPlaying = false;
      const playBtn = $("#playAudioBtn");
      playBtn.onclick = () => {
        if (!player) return;
        if (isPlaying) {
          player.pause();
          player.currentTime = 0;
          isPlaying = false;
          playBtn.innerHTML = `${icon("play", 15)} Escuchar`;
        } else {
          player.play();
          isPlaying = true;
          playBtn.innerHTML = `${icon("square", 15)} Parar`;
        }
      };
      if (player) {
        player.onended = () => {
          isPlaying = false;
          playBtn.innerHTML = `${icon("play", 15)} Escuchar`;
        };
      }
      $("#discardAudioBtn").onclick = () => {
        if (player) { try { player.pause(); } catch {} }
        audioBlob = null;
        audioBase64 = null;
        audioDurationSec = 0;
        renderAudioState();
      };
    } else {
      audioSection.innerHTML = `
        <button type="button" class="btn block" id="startRecBtn" style="background:color-mix(in srgb, #ef4444 8%, var(--card2));border-color:color-mix(in srgb, #ef4444 32%, var(--line));padding:13px 14px;display:flex;align-items:center;justify-content:center;gap:10px">
          ${icon("mic", 20, "pulsing-icon")}
          <div style="text-align:left">
            <div style="font-weight:700;font-size:.92rem;color:var(--text)">Grabar nota de voz (hasta 2 min)</div>
            <div class="muted" style="font-size:.76rem">Explica tu plato con tranquilidad (ensaladas, cantidades, aliño...)</div>
          </div>
        </button>
      `;
      $("#startRecBtn").onclick = startRecording;
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return toast("Tu navegador no soporta grabación directa de audio.");
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      return toast("No se pudo acceder al micrófono: " + (err.message || "Permiso denegado"));
    }

    recordedChunks = [];
    const bestMime = getBestAudioMimeType();
    const options = bestMime ? { mimeType: bestMime } : {};
    try {
      mediaRecorder = new MediaRecorder(mediaStream, options);
    } catch {
      // Fallback sin opciones si el mimeType falló en este navegador
      try {
        mediaRecorder = new MediaRecorder(mediaStream);
      } catch (err2) {
        return toast("Error al iniciar grabadora: " + err2.message);
      }
    }

    audioMime = mediaRecorder.mimeType || bestMime || "audio/webm";
    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        recordedChunks.push(e.data);
      }
    };

    mediaRecorder.onstop = () => {
      if (mediaStream) {
        try { mediaStream.getTracks().forEach(t => t.stop()); } catch {}
        mediaStream = null;
      }
      if (recordTimer) {
        clearInterval(recordTimer);
        recordTimer = null;
      }
      isRecording = false;

      if (recordedChunks.length > 0 && recordSeconds > 0) {
        audioDurationSec = recordSeconds;
        audioBlob = new Blob(recordedChunks, { type: audioMime });
        const reader = new FileReader();
        reader.onloadend = () => {
          const res = reader.result;
          audioBase64 = typeof res === "string" ? res.split(",")[1] : null;
          renderAudioState();
        };
        reader.readAsDataURL(audioBlob);
      } else {
        renderAudioState();
      }
    };

    recordSeconds = 0;
    isRecording = true;
    mediaRecorder.start(250); // trozos cada 250ms
    renderAudioState();

    recordTimer = setInterval(() => {
      recordSeconds++;
      const timerEl = $("#recTimerText");
      if (timerEl) {
        timerEl.textContent = `${formatTime(recordSeconds)} / ${formatTime(MAX_RECORD_SECONDS)}`;
      }
      if (recordSeconds >= MAX_RECORD_SECONDS) {
        toast("Límite de 2 minutos alcanzado");
        stopRecording(true);
      }
    }, 1000);
  }

  function stopRecording(save) {
    if (!isRecording) return;
    if (!save) {
      recordedChunks = [];
      recordSeconds = 0;
      audioBlob = null;
      audioBase64 = null;
    }
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try { mediaRecorder.stop(); } catch {}
    } else {
      cleanupRecording();
      renderAudioState();
    }
  }

  // Render inicial del estado de audio
  renderAudioState();

  // Adjuntar foto
  const photoBtn = $("#aiPhotoBtn");
  const photoInput = $("#aiPhotoInput");
  const attachWrap = $("#aiAttachWrap");

  photoBtn.onclick = () => photoInput.click();
  photoInput.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reduced = await shrinkImage(file, 1024);
    const reader = new FileReader();
    reader.onload = (evt) => {
      attachedImage = { dataUrl: evt.target.result, mime: reduced.type || "image/jpeg" };
      attachWrap.classList.remove("hidden");
      attachWrap.innerHTML = `
        <div class="attach-preview">
          <img src="${evt.target.result}" alt="Foto adjunta">
          <div class="grow"><div class="title">${esc(file.name)}</div><div class="muted">Foto lista para analizar</div></div>
          <button type="button" class="icon-btn ghost" id="rmAttach">${icon("x", 18)}</button>
        </div>`;
      $("#rmAttach").onclick = () => {
        attachedImage = null;
        attachWrap.classList.add("hidden");
        attachWrap.innerHTML = "";
        photoInput.value = "";
      };
    };
    reader.readAsDataURL(reduced);
  };

  // Llamada a Gemini
  const submitBtn = $("#aiSubmit");
  const resultsDiv = $("#aiResults");

  submitBtn.onclick = async () => {
    if (isRecording) {
      stopRecording(true);
      // Dar una pequeña fracción de segundo para que procese el blob
      await new Promise(r => setTimeout(r, 300));
    }

    const textVal = inp.value.trim();
    if (!audioBase64 && !textVal && !attachedImage) {
      return toast("Graba una nota de voz, escribe lo que has comido o añade una foto");
    }

    submitBtn.disabled = true;
    const loadingMsg = audioBase64
      ? "Escuchando audio y calculando macros con Gemini..."
      : "Analizando alimentos y calculando macros...";
    submitBtn.innerHTML = `${icon("sparkles", 18, "spin")} Consultando a Gemini...`;
    resultsDiv.innerHTML = `<div class="empty small">${icon("sparkles", 26, "spin")}${loadingMsg}</div>`;

    try {
      let image_b64 = null, image_mime = null;
      if (attachedImage && attachedImage.dataUrl) {
        image_b64 = attachedImage.dataUrl.split(",")[1];
        image_mime = attachedImage.mime;
      }

      const res = await api("POST", "/api/ai/parse", {
        text: textVal,
        audio_b64: audioBase64 || null,
        audio_mime: audioBase64 ? audioMime : null,
        image_b64,
        image_mime,
      });

      renderAiResults(res);
    } catch (err) {
      resultsDiv.innerHTML = `<div class="note">${icon("info", 18)}<div>${esc(err.message)}</div></div>`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `${icon("sparkles", 18)} Analizar con Gemini`;
    }
  };

  function renderAiResults(data) {
    if (!data.items || !data.items.length) {
      resultsDiv.innerHTML = `<div class="empty small">Gemini no ha detectado alimentos claros. Prueba a dar más detalles en tu audio o texto.</div>`;
      return;
    }

    let itemsHtml = data.items.map((it, idx) => `
      <div class="ai-item" data-idx="${idx}">
        <div class="row between">
          <div class="grow">
            <input class="ai-name" value="${esc(it.name)}" style="font-weight:700;padding:6px 8px;margin-bottom:4px">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <span class="ai-badge ${it.matched_food_id ? 'matched' : 'estimated'}">
                ${it.matched_food_id ? '✓ Coincide con tu base' : '★ Estimación IA'}
              </span>
              <button type="button" class="btn ghost small ai-save-food" style="padding:2px 8px;font-size:.76rem;border:1px dashed var(--line);border-radius:6px;gap:4px" title="Guardar a 'Mis Alimentos' calculado por cada 100g">
                ${icon("bookmark", 13)} Guardar (100g)
              </button>
            </div>
          </div>
          <button type="button" class="icon-btn ghost ai-del" title="Eliminar ítem">${icon("trash", 16)}</button>
        </div>
        <div class="grid2" style="margin-top:8px">
          <div><label style="margin:2px 0">Gramos / Cantidad</label><input class="ai-grams" inputmode="decimal" value="${it.grams || 100}"></div>
          <div><label style="margin:2px 0">Calorías (kcal)</label><input class="ai-kcal" inputmode="decimal" value="${r0(it.kcal)}"></div>
        </div>
        <div class="grid3" style="margin-top:6px">
          <div><label style="margin:2px 0">Prot (g)</label><input class="ai-p" inputmode="decimal" value="${r1(it.protein)}"></div>
          <div><label style="margin:2px 0">Hidr (g)</label><input class="ai-c" inputmode="decimal" value="${r1(it.carbs)}"></div>
          <div><label style="margin:2px 0">Grasa (g)</label><input class="ai-f" inputmode="decimal" value="${r1(it.fat)}"></div>
        </div>
      </div>
    `).join("");

    resultsDiv.innerHTML = `
      <div class="result" style="margin-top:14px">
        <div class="row between">
          <div>
            <strong>${esc(data.summary || "Alimentos detectados")}</strong>
            <div class="muted">${data.items.length} ingrediente(s) identificado(s)</div>
          </div>
          <div class="kcal-tag" style="font-size:1.25rem">${r0(data.total_kcal || 0)}<small>kcal</small></div>
        </div>

        ${data.transcription ? `
          <div class="ai-transcript">
            <strong>${icon("audioLines", 14)} Lo que he escuchado:</strong>
            ${esc(data.transcription)}
          </div>
        ` : ""}

        ${data.notes ? `<p class="muted" style="margin:6px 0;font-size:.82rem">${esc(data.notes)}</p>` : ""}

        <div id="aiItemsList" style="margin-top:10px">${itemsHtml}</div>
        <button class="btn primary block" style="margin-top:14px" id="aiApplyBtn">${icon("plus", 18)} Añadir alimentos a ${esc(state.date)}</button>
      </div>
    `;

    // Guardar ítem a base de datos calculado por 100g
    $$("#aiItemsList .ai-save-food").forEach(btn => {
      btn.onclick = async () => {
        const itemEl = btn.closest(".ai-item");
        const idx = +itemEl.dataset.idx;
        const name = itemEl.querySelector(".ai-name").value.trim();
        const grams = toNum(itemEl.querySelector(".ai-grams").value) || 100;
        const totalKcal = toNum(itemEl.querySelector(".ai-kcal").value);
        const totalP = toNum(itemEl.querySelector(".ai-p").value);
        const totalC = toNum(itemEl.querySelector(".ai-c").value);
        const totalF = toNum(itemEl.querySelector(".ai-f").value);

        if (!name) return toast("El alimento necesita un nombre");
        btn.disabled = true;
        btn.innerHTML = `${icon("sparkles", 13, "spin")} Guardando...`;

        try {
          const factor = grams > 0 ? 100 / grams : 1;
          const payload = {
            name,
            brand: "Guardado desde IA",
            kcal: Math.round(totalKcal * factor * 10) / 10,
            protein: Math.round(totalP * factor * 10) / 10,
            carbs: Math.round(totalC * factor * 10) / 10,
            fat: Math.round(totalF * factor * 10) / 10,
            category: "otros"
          };

          const saved = await api("POST", "/api/foods", payload);
          if (data.items[idx]) {
            data.items[idx].matched_food_id = saved.id;
          }
          itemEl.dataset.matchedFoodId = saved.id;

          const badge = itemEl.querySelector(".ai-badge");
          if (badge) {
            badge.className = "ai-badge matched";
            badge.textContent = "✓ Guardado en tu base";
          }
          btn.style.display = "none";
          toast(`«${name}» guardado por 100g en tu base`, true);
        } catch (err) {
          btn.disabled = false;
          btn.innerHTML = `${icon("bookmark", 13)} Guardar (100g)`;
          toast("Error al guardar: " + err.message);
        }
      };
    });

    // Borrar ítems
    $$("#aiItemsList .ai-del").forEach(btn => {
      btn.onclick = () => {
        btn.closest(".ai-item").remove();
        if (!$$("#aiItemsList .ai-item").length) {
          resultsDiv.innerHTML = emptyBox("utensils", "Todos los alimentos fueron descartados.");
        }
      };
    });

    // Añadir al día
    $("#aiApplyBtn").onclick = async () => {
      const itemsToSave = $$("#aiItemsList .ai-item").map(el => {
        const idx = +el.dataset.idx;
        const orig = data.items[idx] || {};
        return {
          name: el.querySelector(".ai-name").value.trim(),
          grams: toNum(el.querySelector(".ai-grams").value),
          kcal: toNum(el.querySelector(".ai-kcal").value),
          protein: toNum(el.querySelector(".ai-p").value),
          carbs: toNum(el.querySelector(".ai-c").value),
          fat: toNum(el.querySelector(".ai-f").value),
          matched_food_id: orig.matched_food_id || null
        };
      });

      if (!itemsToSave.length) return toast("No hay alimentos que guardar");

      await api("POST", "/api/ai/apply", {
        date: state.date,
        meal: selectedMeal(),
        items: itemsToSave
      });

      closeSheet();
      toast("Alimentos añadidos con Gemini", true);
      renderToday();
    };
  }
}

// --- editar / duplicar / borrar entrada
async function editEntry(id) {
  const d = await api("GET", `/api/day/${state.date}`);
  const e = d.entries.find((x) => x.id === id);
  if (!e) return;
  const isFood = e.kind === "food" && e.food_id;
  const isToday = state.date === isoDate(new Date());
  openSheet(`${sheetHead(e.name)}${mealChips(e.meal)}
    ${isFood ? `<label>Gramos</label><input id="eg" inputmode="decimal" value="${e.grams}"><p class="muted">Las macros se recalculan con los valores actuales del alimento.</p>` : `
    <label>Nombre</label><input id="en" value="${esc(e.name)}"><label>Kcal</label><input id="ek" inputmode="decimal" value="${e.kcal}">
    <div class="grid3"><div><label>Prot</label><input id="ep" inputmode="decimal" value="${e.protein}"></div><div><label>Hidr</label><input id="ec" inputmode="decimal" value="${e.carbs}"></div><div><label>Grasa</label><input id="ef" inputmode="decimal" value="${e.fat}"></div></div>`}
    <button class="btn primary block" style="margin-top:16px" id="ok">${icon("check", 18)} Guardar</button>
    <div class="grid2" style="margin-top:8px">
      <button class="btn" id="dup">${icon("copy", 17)} ${isToday ? "Duplicar" : "Copiar a hoy"}</button>
      <button class="btn danger" id="del">${icon("trash", 17)} Eliminar</button></div>`);
  bindMealChips();
  $("#ok").onclick = async () => {
    const body = isFood ? { grams: toNum($("#eg").value), meal: selectedMeal() }
      : { name: $("#en").value, kcal: toNum($("#ek").value), protein: toNum($("#ep").value), carbs: toNum($("#ec").value), fat: toNum($("#ef").value), meal: selectedMeal() };
    await api("PUT", `/api/entries/${id}`, body); closeSheet(); renderToday();
  };
  $("#dup").onclick = async () => { await api("POST", `/api/entries/${id}/copy`, { date: isoDate(new Date()), meal: selectedMeal() }); closeSheet(); toast(isToday ? "Duplicado" : "Copiado a hoy", true); renderToday(); };
  $("#del").onclick = async () => {
    const cur = getLocalCache("journal_day:" + state.date, []);
    setLocalCache("journal_day:" + state.date, cur.filter((x) => x.id !== id));
    await api("DELETE", `/api/entries/${id}`);
    closeSheet();
    toast("Eliminado");
    renderToday();
  };
}

// ======================================================================= PRESETS & COMBOS
async function renderPresets() {
  const presets = await api("GET", "/api/presets");
  const cat = state.presetCat;

  // Separar los combos predefinidos de otros presets
  const combos = presets.filter((p) => (p.category || "combos") === "combos" || p.name.toLowerCase().startsWith("combo"));
  const others = presets.filter((p) => !combos.includes(p));

  const filteredCombos = cat === "todos" || cat === "combos" ? combos
    : combos.filter(p => (p.meal || "").includes(cat) || p.name.toLowerCase().includes(cat));

  const filteredOthers = cat === "todos" ? others
    : others.filter(p => (p.category || "otros") === cat || (p.meal || "").includes(cat));

  const comboCardHtml = (p) => `
    <div class="combo-card">
      <div class="row between">
        <div class="grow">
          <div class="row" style="gap:6px;margin-bottom:4px">
            <span class="combo-badge">${icon("zap", 12)} Combo 1-Clic</span>
            <span class="muted" style="font-size:.78rem;text-transform:capitalize">· ${esc(p.meal || "comida")}</span>
          </div>
          <div class="title" style="font-size:1.05rem;font-weight:700">${esc(p.name)}</div>
        </div>
        <div class="kcal-tag" style="font-size:1.15rem">${r0(p.totals.kcal)}<small>kcal</small></div>
      </div>
      <div class="combo-items-preview">
        ${p.items.map((i) => `<b>${r0(i.grams)}g</b> ${esc(i.name)}`).join(" · ")}
      </div>
      <div class="row between" style="margin-top:10px">
        <div>${macroLine(p.totals)}</div>
        <div class="row" style="gap:6px">
          <button class="btn small" onclick="customizeCombo(${p.id})">${icon("pencil", 14)} Desglosar</button>
          <button class="btn small primary" onclick="quickAddCombo(${p.id})">${icon("zap", 14)} 1-Clic hoy</button>
        </div>
      </div>
    </div>`;

  const presetRowHtml = (p) => `
    <div class="card">
      <div class="row between">
        <div class="row grow">
          <div class="thumb accent">${icon("zap", 22)}</div>
          <div class="grow">
            <div class="title" style="font-size:1.05rem">${esc(p.name)}</div>
            <div class="muted" style="white-space:normal">${p.items.map((i) => `${esc(i.name)} ${r0(i.grams)} g`).join(" · ") || "sin ingredientes"}</div>
          </div>
        </div>
        <div class="kcal-tag" style="font-size:1.1rem">${r0(p.totals.kcal)}<small>kcal</small></div>
      </div>
      <div class="row between" style="margin-top:12px">
        ${macroLine(p.totals)}
        <div class="row" style="gap:6px">
          <button class="btn small" onclick="editPreset(${p.id})">${icon("pencil", 14)} Editar</button>
          <button class="btn small primary" onclick="addPresetToToday(${p.id})">${icon("plus", 14)} Añadir hoy</button>
        </div>
      </div>
    </div>`;

  $("#view").innerHTML = `
    <h1>Platos Típicos & Presets</h1>
    <p class="muted" style="margin-bottom:12px">Añade comidas compuestas habituales en 1 solo clic o desglosa sus ingredientes para ajustar los gramos.</p>
    ${categoryChips(state.presetCat, "presetCatFilter")}
    <button class="btn primary block" style="margin:10px 0 16px" onclick="editPreset()">${icon("plus", 18)} Crear nuevo preset</button>

    <h2>${icon("zap", 15)} Platos Típicos (Combos Frecuentes)</h2>
    <div id="combosList">
      ${filteredCombos.map(comboCardHtml).join("") || emptyBox("zap", "No hay combos en esta categoría.")}
    </div>

    ${filteredOthers.length ? `<h2>${icon("bookmark", 15)} Mis Otros Presets Personalizados</h2>
      <div id="customPresetsList">${filteredOthers.map(presetRowHtml).join("")}</div>` : ""}`;

  $$("#presetCatFilter .cat-chip").forEach((b) => b.onclick = () => {
    $$("#presetCatFilter .cat-chip").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    state.presetCat = b.dataset.cat;
    renderPresets();
  });
}

async function quickAddCombo(id) {
  const presets = await api("GET", "/api/presets");
  const p = presets.find((x) => x.id === id);
  if (!p) return;
  const items = p.items.map((i) => ({ food_id: i.food_id, grams: i.grams }));
  await api("POST", "/api/entries/preset", {
    date: state.date,
    meal: p.meal || guessMeal(),
    name: p.name,
    grouped: true,
    items,
  });
  toast(`«${p.name}» añadido a ${state.date} (${r0(p.totals.kcal)} kcal)`, true);
  if (state.tab === "today") renderToday();
}

async function customizeCombo(id) {
  const presets = await api("GET", "/api/presets");
  const p = presets.find((x) => x.id === id);
  if (p) pickPreset(p);
}

async function addPresetToToday(id) {
  state.date = isoDate(new Date());
  const p = (await api("GET", "/api/presets")).find((x) => x.id === id);
  if (p) pickPreset(p);
}

async function editPreset(id) {
  const foods = await api("GET", "/api/foods");
  const p = id ? (await api("GET", "/api/presets")).find((x) => x.id === id) : { name: "", meal: "", category: "combos", items: [{ food_id: foods[0]?.id, grams: 100 }] };
  const row = (it) => `<div class="preset-ing"><select>${foods.map((f) => `<option value="${f.id}" ${f.id == it.food_id ? "selected" : ""}>${esc(f.name)}${f.brand ? " – " + esc(f.brand) : ""}</option>`).join("")}</select>
    <input inputmode="decimal" value="${it.grams}" placeholder="g"><button type="button" class="icon-btn ghost" aria-label="Quitar">${icon("x", 18)}</button></div>`;
  openSheet(`${sheetHead(id ? "Editar preset / combo" : "Nuevo preset / combo")}
    <label>Nombre del plato o preset</label><input id="pn" value="${esc(p.name)}" placeholder="Batido Moca + Cereales">
    <label>Comida habitual</label>${mealChips(p.meal || "")}
    <label>Categoría</label>
    <select id="p_category">
      <option value="combos" ${p.category === "combos" ? "selected" : ""}>Combos / Platos Frecuentes</option>
      <option value="desayuno" ${p.category === "desayuno" ? "selected" : ""}>Desayunos</option>
      <option value="lacteos" ${p.category === "lacteos" ? "selected" : ""}>Lácteos / Boles</option>
      <option value="carnes_pescados" ${p.category === "carnes_pescados" ? "selected" : ""}>Carnes / Pescados</option>
      <option value="hidratos_panes" ${p.category === "hidratos_panes" ? "selected" : ""}>Hidratos / Panes</option>
      <option value="otros" ${p.category === "otros" ? "selected" : ""}>Otros</option>
    </select>
    <label>Ingredientes y cantidades (g)</label><div id="ings">${p.items.map(row).join("")}</div>
    <button class="btn small" id="addIng">${icon("plus", 14)} Añadir ingrediente</button>
    <button class="btn primary block" style="margin-top:16px" id="ok">${icon("check", 18)} Guardar preset</button>
    ${id ? `<button class="btn danger block" style="margin-top:8px" id="del">${icon("trash", 17)} Eliminar preset</button>` : ""}`);
  bindMealChips();
  const bindRemove = () => $$("#ings .preset-ing button").forEach((b) => b.onclick = () => b.parentElement.remove());
  bindRemove();
  $("#addIng").onclick = () => { $("#ings").insertAdjacentHTML("beforeend", row({ food_id: foods[0]?.id, grams: 100 })); bindRemove(); };
  $("#ok").onclick = async () => {
    const items = $$("#ings .preset-ing").map((r) => ({ food_id: +$("select", r).value, grams: toNum($("input", r).value) }));
    const body = { name: $("#pn").value, meal: $("#mealChips .chip.on")?.dataset.meal || "", category: $("#p_category").value, items };
    await (id ? api("PUT", `/api/presets/${id}`, body) : api("POST", "/api/presets", body));
    closeSheet(); renderPresets();
  };
  if (id) $("#del").onclick = async () => { if (confirm("¿Eliminar preset?")) { await api("DELETE", `/api/presets/${id}`); closeSheet(); renderPresets(); } };
}

// ===================================================================== ALIMENTOS
async function renderFoods() {
  const foods = await api("GET", "/api/foods");
  setLocalCache("cached_foods", foods);

  $("#view").innerHTML = `<h1>Alimentos Base</h1>
    <div class="grid2" style="margin-bottom:12px">
      <button class="btn primary" onclick="editFood()">${icon("plus", 18)} Nuevo alimento</button>
      <button class="btn" onclick="onlineSearch('', null, true)">${icon("globe", 18)} Buscar online</button>
    </div>
    ${categoryChips(state.foodCat, "foodCatFilter")}
    <div class="search"><span>${icon("search", 18)}</span><input id="fq" placeholder="Buscar en alimentos…" value="${esc(state.foodQuery)}"></div>
    <div id="fl" style="margin-top:12px"></div>`;

  const draw = () => {
    const q = $("#fq").value.trim().toLowerCase(); state.foodQuery = $("#fq").value;
    const cat = state.foodCat;
    const list = foods.filter((f) => {
      const matchCat = !cat || cat === "todos" || (f.category || "otros") === cat;
      const matchQ = !q || (f.name + " " + (f.brand || "")).toLowerCase().includes(q);
      return matchCat && matchQ;
    });
    $("#fl").innerHTML = list.map((f) => foodRow(f)).join("") || emptyBox("search", "No hay alimentos que coincidan.");
    $$("#fl .item").forEach((el) => el.onclick = () => editFood(+el.dataset.id, foods));
  };

  $$("#foodCatFilter .cat-chip").forEach((b) => b.onclick = () => {
    $$("#foodCatFilter .cat-chip").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    state.foodCat = b.dataset.cat;
    draw();
  });

  $("#fq").oninput = draw; draw();
}

/** Reduce la foto antes de subirla (los móviles hacen fotos de varios MB). */
async function shrinkImage(file, max = 800) {
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
    const cv = document.createElement("canvas"); cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
    cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
    const blob = await new Promise((r) => cv.toBlob(r, "image/jpeg", 0.85));
    return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
  } catch { return file; }
}

function editFood(id, foods) {
  const f = (foods || []).find((x) => x.id === id) || { name: "", brand: "", kcal: "", protein: "", carbs: "", fat: "", unit_g: "", unit_name: "", category: "otros", photo: "", barcode: "" };
  const num = (k, label) => `<div><label>${label}</label><input id="f_${k}" inputmode="decimal" value="${f[k] ?? ""}"></div>`;
  openSheet(`${sheetHead(id ? "Editar alimento" : "Nuevo alimento")}
    <div class="row" style="margin-bottom:4px">${thumb(f)}<div class="grow"><label style="margin-top:0">Foto</label><input id="f_photo" type="file" accept="image/*"></div></div>
    <label>Nombre</label><input id="f_name" value="${esc(f.name)}"><label>Marca (opcional)</label><input id="f_brand" value="${esc(f.brand)}">
    <label>Categoría</label>
    <select id="f_category">
      <option value="desayuno" ${f.category === "desayuno" ? "selected" : ""}>Desayuno / Cereales</option>
      <option value="lacteos" ${f.category === "lacteos" ? "selected" : ""}>Lácteos / Boles / Fruta</option>
      <option value="carnes_pescados" ${f.category === "carnes_pescados" ? "selected" : ""}>Carnes / Pescados / Proteínas</option>
      <option value="hidratos_panes" ${f.category === "hidratos_panes" ? "selected" : ""}>Hidratos / Panes</option>
      <option value="otros" ${!f.category || f.category === "otros" ? "selected" : ""}>Otros</option>
    </select>
    <h2>Por cada 100 g / ml</h2>
    <div class="grid2">${num("kcal", "Kcal")}${num("protein", "Proteína (g)")}${num("carbs", "Hidratos (g)")}${num("fat", "Grasa (g)")}</div>
    <h2>Unidad (opcional)</h2>
    <div class="grid2"><div><label>Nombre (cacito, huevo, envase…)</label><input id="f_unit_name" value="${esc(f.unit_name)}"></div>${num("unit_g", "Gramos por unidad")}</div>
    <label>Código de barras (opcional)</label><input id="f_barcode" inputmode="numeric" value="${esc(f.barcode || "")}">
    <button class="btn primary block" style="margin-top:16px" id="ok">${icon("check", 18)} Guardar alimento</button>
    ${id ? `<button class="btn danger block" style="margin-top:8px" id="del">${icon("trash", 17)} Eliminar</button>` : ""}`);
  $("#ok").onclick = async () => {
    const body = {};
    ["name", "brand", "kcal", "protein", "carbs", "fat", "unit_g", "unit_name", "barcode", "category"].forEach((k) => body[k] = $("#f_" + k).value);
    const res = await (id ? api("PUT", `/api/foods/${id}`, body) : api("POST", "/api/foods", body));
    const file = $("#f_photo").files[0];
    if (file) { const fd = new FormData(); fd.append("photo", await shrinkImage(file)); await api("POST", `/api/foods/${id || res.id}/photo`, fd); }
    closeSheet(); renderFoods();
  };
  if (id) $("#del").onclick = async () => { if (confirm("¿Eliminar alimento? El histórico se conserva.")) { await api("DELETE", `/api/foods/${id}`); closeSheet(); renderFoods(); } };
}

// ===================================================================== PROGRESO
async function renderProgress() {
  const n = state.histDays;
  const [h, weights, s] = await Promise.all([api("GET", `/api/history?days=${n}`), api("GET", "/api/weights"), api("GET", "/api/settings")]);
  const g = h.goals, a = h.average, p = s.profile || {};
  const tdee = toNum(p.tdee || 3350);
  const lbm = toNum(p.lbm || 85.5);
  const weight = toNum(p.weight || 119);
  const byDate = Object.fromEntries(h.days.map((d) => [d.date, d]));
  const series = []; for (let i = n - 1; i >= 0; i--) { const dt = shiftDay(isoDate(new Date()), -i); series.push({ date: dt, kcal: byDate[dt]?.kcal || 0 }); }
  const wFrom = shiftDay(isoDate(new Date()), -Math.max(n, 30));
  const wSel = weights.filter((w) => w.date >= wFrom);
  const lastW = weights[weights.length - 1];
  const diff = a.kcal - g.kcal;
  const kc = a.protein * 4 + a.carbs * 4 + a.fat * 9;
  const share = (v) => kc ? Math.round(v / kc * 100) : 0;

  $("#view").innerHTML = `<h1>Progreso & Déficit</h1>
    <div class="bio-card">
      <div class="row between">
        <strong>${icon("target", 16)} Objetivos & Parámetros Biométricos</strong>
        <span class="combo-badge" style="background:var(--accent);color:var(--accent-ink)">Déficit -${r0(tdee - g.kcal)} kcal/día</span>
      </div>
      <div class="bio-grid">
        <div class="bio-item"><div class="lbl">Gasto Diario (TDEE)</div><div class="val">${r0(tdee)} kcal</div></div>
        <div class="bio-item"><div class="lbl">Objetivo Diario</div><div class="val" style="color:var(--accent)">${r0(g.kcal)} kcal</div></div>
        <div class="bio-item"><div class="lbl">Peso / Masa Magra</div><div class="val">${weight} kg <small class="muted">/ ${lbm} kg</small></div></div>
        <div class="bio-item"><div class="lbl">Proteína por kg LBM</div><div class="val" style="color:var(--p)">${(g.protein / (lbm || 1)).toFixed(2)} g/kg</div></div>
      </div>
    </div>

    <div class="card" style="border-color:color-mix(in srgb, var(--accent) 35%, var(--line));background:color-mix(in srgb, var(--accent) 5%, var(--card))">
      <div class="row between" style="gap:12px;flex-wrap:wrap">
        <div>
          <div class="row" style="gap:6px;margin-bottom:2px">
            <span class="combo-badge" style="background:var(--accent);color:var(--accent-ink)">${icon("chart", 12)} Informe PDF del Proceso</span>
            <span class="muted" style="font-size:.78rem">· Periodo de ${n} días</span>
          </div>
          <strong style="font-size:1.05rem;display:block;margin:2px 0">Descargar resumen detallado en PDF</strong>
          <div class="muted" style="font-size:.84rem">Incluye gráfica de barritas de calorías día por día, déficit acumulado, macros y tabla completa.</div>
        </div>
        <div class="row" style="gap:8px">
          <a class="btn primary" href="/api/export/pdf?date=${state.date}&days=${n}" download style="padding:10px 14px;font-size:.9rem">
            ${icon("download", 16)} Descargar PDF (${n} días)
          </a>
          <a class="btn" href="/report?date=${state.date}&days=${n}" target="_blank" title="Ver en navegador" style="padding:10px 12px">
            ${icon("eye", 16)}
          </a>
        </div>
      </div>
    </div>

    <div class="seg" style="margin-bottom:14px">${[7, 30, 90].map((d) => `<button class="${d === n ? "on" : ""}" onclick="state.histDays=${d};renderProgress()">${d} días</button>`).join("")}</div>
    <div class="card">
      <div class="muted">Promedio diario · ${h.logged_days} día(s) con registros</div>
      <div class="row between" style="margin:8px 0 12px"><div><span class="big">${r0(a.kcal)}</span> <span class="muted">kcal</span></div>
        ${h.logged_days ? `<div class="chip" style="cursor:default;color:${diff > 0 ? "var(--danger)" : "var(--accent)"}">${diff > 0 ? "+" : ""}${r0(diff)} vs objetivo</div>` : ""}</div>
      ${barChart(series, g.kcal)}
    </div>
    <div class="card"><div class="donut-row">${donutChart(a.protein, a.carbs, a.fat)}
      <div class="legend">
        <div><i style="background:var(--p)"></i>Proteína · <b>${r0(a.protein)} g</b> · ${share(a.protein * 4)}%</div>
        <div><i style="background:var(--c)"></i>Hidratos · <b>${r0(a.carbs)} g</b> · ${share(a.carbs * 4)}%</div>
        <div><i style="background:var(--f)"></i>Grasa · <b>${r0(a.fat)} g</b> · ${share(a.fat * 9)}%</div></div></div></div>

    <h2>${icon("gauge", 15)} Peso</h2>
    <div class="card">
      <div class="row between"><div>${lastW ? `<span class="big">${lastW.kg}</span> <span class="muted">kg · ${lastW.date}</span>` : '<span class="muted">Sin pesos apuntados</span>'}</div></div>
      <div style="margin:10px 0">${lineChart(wSel)}</div>
      <div class="row"><input id="wk" inputmode="decimal" placeholder="Peso de hoy (kg)" value="${lastW?.date === isoDate(new Date()) ? lastW.kg : ""}">
        <button class="btn primary" id="saveW">${icon("check", 18)}</button></div>
    </div>

    <h2>${icon("home", 15)} Por días</h2>
    ${h.days.map((d) => `<div class="item" onclick="state.date='${d.date}';go('today')"><div class="grow">
      <div class="row between"><div class="title" style="text-transform:capitalize">${parseISO(d.date).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" })}</div><div class="kcal-tag">${r0(d.kcal)}<small>kcal</small></div></div>
      ${macroLine(d)}<div class="bar ${d.kcal > g.kcal ? "over" : ""}"><i style="width:${Math.min(100, d.kcal / g.kcal * 100)}%;background:var(--kcal)"></i></div></div></div>`).join("") || emptyBox("chart", "Sin registros en este periodo.")}`;
  $("#saveW").onclick = async () => { const kg = toNum($("#wk").value); if (!kg) return toast("Escribe tu peso"); await api("POST", "/api/weights", { date: isoDate(new Date()), kg }); toast("Peso guardado", true); renderProgress(); };
}

// ====================================================================== AJUSTES
const ACTIVITY = [["1.2", "Sedentario (poco o nada de ejercicio)"], ["1.375", "Ligero (1-3 días/semana)"], ["1.55", "Moderado (3-5 días/semana)"], ["1.725", "Alto (6-7 días/semana)"], ["1.9", "Muy alto (trabajo físico + entreno)"]];
const GOALS = [["-0.2", "Perder grasa (−20 %)"], ["-0.1", "Definición suave (−10 %)"], ["0", "Mantener"], ["0.1", "Ganar músculo (+10 %)"]];

function setTheme(t) {
  localStorage.setItem("theme", t);
  const dark = t === "dark" || (t === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]').content = dark ? "#0b0d12" : "#f3f5f9";
  $$("#themeSeg button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
}

async function renderSettings() {
  const [s, conn, auth, weights, ai, gh] = await Promise.all([
    api("GET", "/api/settings"),
    api("GET", "/api/connect"),
    api("GET", "/api/auth/status"),
    api("GET", "/api/weights"),
    api("GET", "/api/ai/status"),
    api("GET", "/api/github/status").catch(() => ({ configured: false, repo: "ivangarmir18/Calculadora_Macros" })),
  ]);
  const g = s.goals, p = s.profile, theme = localStorage.getItem("theme") || "dark";
  const lastW = weights[weights.length - 1]?.kg || "";
  const isLocalhost = ["localhost", "127.0.0.1"].includes(location.hostname);
  $("#view").innerHTML = `<h1>Ajustes</h1>

    <h2>${icon("sun", 15)} Apariencia</h2>
    <div class="seg" id="themeSeg">${[["dark", "moon", "Oscuro"], ["light", "sun", "Claro"], ["auto", "sliders", "Auto"]].map(([t, ic, l]) => `<button data-t="${t}" class="${t === theme ? "on" : ""}">${icon(ic, 16)} ${l}</button>`).join("")}</div>

    <h2>${icon("globe", 15)} Sincronización Automática con GitHub (Render / Nube)</h2>
    <div class="card">
      <div class="row between" style="margin-bottom:8px">
        <span class="muted">Auto-guardado en <code>data/macros.db</code></span>
        <span class="badge-status ${gh.configured ? "active" : "inactive"}">
          ${gh.configured ? "● Activo (" + (gh.source === "env" ? "variable GITHUB_TOKEN" : "guardado en app") + ")" : "○ Falta Token de GitHub"}
        </span>
      </div>
      <div class="muted" style="font-size:.82rem;margin-bottom:8px">
        Repositorio: <b>${esc(gh.repo || "ivangarmir18/Calculadora_Macros")}</b> ${gh.sha ? `· SHA: <code>${esc(gh.sha)}</code>` : ""}
        ${gh.last_push_at ? `<br>Última subida a GitHub: <b>${esc(gh.last_push_at.replace("T", " "))}</b>` : ""}
        ${gh.last_pull_at ? `<br>Última descarga desde GitHub: <b>${esc(gh.last_pull_at.replace("T", " "))}</b>` : ""}
      </div>
      ${gh.last_error ? `<div class="note" style="margin-bottom:10px;border-color:var(--danger)">${icon("info", 18)}<div style="color:var(--danger)">${esc(gh.last_error)}</div></div>` : ""}
      ${gh.configured ? `<div class="url" style="color:var(--muted)">Token: ${esc(gh.masked)}</div>` : ""}
      <label>${gh.configured ? "Cambiar Personal Access Token de GitHub" : "Token de GitHub (GITHUB_TOKEN)"}</label>
      <input id="gh_token" type="password" placeholder="Pega tu token ghp_... o github_pat_..." autocomplete="off">
      <div class="grid2" style="margin-top:10px">
        <button class="btn primary" id="saveGhToken">${icon("check", 17)} Guardar Token</button>
        ${gh.source === "db" ? `<button class="btn danger" id="deleteGhToken">Quitar Token</button>` : `<button class="btn" id="syncGhNow">${icon("repeat", 17)} Sincronizar ahora</button>`}
      </div>
      <div class="grid2" style="margin-top:8px">
        <button class="btn" id="pushGhNow">${icon("upload", 16)} Subir DB a GitHub</button>
        <button class="btn" id="pullGhNow">${icon("download", 16)} Bajar DB de GitHub</button>
      </div>
      <div class="note" style="margin-top:12px">
        ${icon("info", 18)}
        <div>
          <b>¿Cómo funciona en Render y en tu PC?</b><br>
          Cada vez que apuntas una comida, pesaje o alimento, la app sube automáticamente <code>data/macros.db</code> a tu GitHub (con <code>[skip render]</code> para no reiniciar el servidor) y sin exponer tus claves secretas.<br>
          • <b>Para que Render no olvide el token al apagarse:</b> ve a tu panel de Render → <i>Environment</i> → añade la variable <code>GITHUB_TOKEN</code> con tu token de GitHub (créalo en GitHub → <i>Settings → Developer settings → Personal access tokens</i> con permiso <b>repo / contents: write</b>).
        </div>
      </div>
    </div>

    <h2>${icon("sparkles", 15)} Asistente Gemini (IA y voz)</h2>
    <div class="card">
      <div class="row between" style="margin-bottom:8px">
        <span class="muted">Estado</span>
        <span class="badge-status ${ai.configured ? "active" : "inactive"}">
          ${ai.configured ? "● Activo (" + (ai.source === "env" ? "archivo .env" : "guardada en app") + ")" : "○ No configurada"}
        </span>
      </div>
      ${ai.configured ? `<div class="url" style="color:var(--muted)">Clave: ${esc(ai.masked)}</div>` : ""}
      <label>${ai.configured ? "Cambiar clave de API de Gemini" : "Clave de API de Gemini"}</label>
      <input id="gemini_key" type="password" placeholder="Pega tu clave AIzaSy..." autocomplete="off">
      <div class="grid2" style="margin-top:12px">
        <button class="btn primary" id="saveAiKey">${icon("check", 17)} Guardar clave</button>
        ${ai.source === "db" ? `<button class="btn danger" id="deleteAiKey">Eliminar clave</button>` : ""}
      </div>
      <label style="margin-top:14px">Modelo de Gemini</label>
      <div class="row" style="gap:8px">
        <select id="gemini_model" style="flex:1">
          ${(ai.available_models || ["gemini-3.8-flash", "gemini-3-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]).map(m => `
            <option value="${m}" ${m === ai.model ? "selected" : ""}>${esc(m)} ${m === "gemini-3.8-flash" ? "★ Recomendado" : ""}</option>
          `).join("")}
        </select>
        <button type="button" class="btn" id="saveAiModel" style="flex:none">${icon("check", 16)} Cambiar</button>
      </div>
      <div class="muted" style="font-size:.78rem;margin-top:4px">
        Modelo prioritario: <b>${esc(ai.model || "gemini-3.8-flash")}</b> (${ai.model_source === "env" ? "archivo .env" : ai.model_source === "db" ? "guardado" : "por defecto"}). Si no está activo en tu cuenta, salta automáticamente al siguiente modelo de respaldo.
      </div>
      <div class="note" style="margin-top:12px">
        ${icon("info", 18)}
        <div>
          <b>¿Prefieres no ponerla aquí?</b><br>
          Crea un archivo <code>.env</code> en la carpeta de la app con la línea:<br>
          <code>GEMINI_API_KEY=tu_clave_aqui</code><br>
          (Opcional: <code>GEMINI_MODEL=gemini-3.8-flash</code>)<br>
          Ese archivo está en <code>.gitignore</code> y nunca se subirá a GitHub.
        </div>
      </div>
    </div>

    <h2>${icon("target", 15)} Mis objetivos diarios & Biometría</h2>
    <div class="card">
      <div class="grid2">
        <div><label style="margin-top:0">Kcal Objetivo</label><input id="g_kcal" inputmode="decimal" value="${g.kcal}"></div>
        <div><label style="margin-top:0">Proteína (g)</label><input id="g_protein" inputmode="decimal" value="${g.protein}"></div>
        <div><label>Hidratos (g)</label><input id="g_carbs" inputmode="decimal" value="${g.carbs}"></div>
        <div><label>Grasa (g)</label><input id="g_fat" inputmode="decimal" value="${g.fat}"></div>
      </div>
      <h2 style="margin:16px 0 6px">${icon("gauge", 14)} Datos Biométricos</h2>
      <div class="grid3">
        <div><label style="margin-top:0">Gasto TDEE (kcal)</label><input id="p_tdee" inputmode="decimal" value="${p.tdee || 3350}"></div>
        <div><label style="margin-top:0">Peso actual (kg)</label><input id="p_weight" inputmode="decimal" value="${p.weight || lastW || 119}"></div>
        <div><label style="margin-top:0">Masa Magra LBM (kg)</label><input id="p_lbm" inputmode="decimal" value="${p.lbm || 85.5}"></div>
      </div>
      <button class="btn primary block" style="margin-top:14px" id="saveGoals">${icon("check", 18)} Guardar objetivos y perfil</button>
    </div>

    <h2>${icon("calc", 15)} Calculadora de macros</h2>
    <div class="card"><p class="muted" style="margin-top:0">Calcula tus calorías con la fórmula Mifflin-St Jeor y reparte macros. Es una estimación: ajústala según tu progreso.</p>
      <label>Sexo</label><div class="seg" id="c_sex">${[["m", "Hombre"], ["f", "Mujer"]].map(([v, l]) => `<button data-v="${v}" class="${(p.sex || "m") === v ? "on" : ""}">${l}</button>`).join("")}</div>
      <div class="grid3"><div><label>Edad</label><input id="c_age" inputmode="numeric" value="${esc(p.age)}"></div><div><label>Altura (cm)</label><input id="c_height" inputmode="decimal" value="${esc(p.height)}"></div><div><label>Peso (kg)</label><input id="c_weight" inputmode="decimal" value="${esc(p.weight || lastW)}"></div></div>
      <label>Actividad</label><select id="c_activity">${ACTIVITY.map(([v, l]) => `<option value="${v}" ${(p.activity || "1.55") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <label>Objetivo</label><select id="c_goal">${GOALS.map(([v, l]) => `<option value="${v}" ${(p.goal || "0") === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <button class="btn block" style="margin-top:14px" id="calc">${icon("calc", 18)} Calcular</button><div id="calcRes"></div></div>

    <h2>${icon("phone", 15)} Usar en el móvil</h2>
    <div class="card">${conn.local_only ? `<div class="note">${icon("info", 18)}<div>La app está arrancada en modo <b>solo este PC</b>. Para usarla desde el móvil, ciérrala y arráncala sin <code>--local</code>.</div></div>` : conn.urls.length ? `
      <p style="margin-top:0">Con el móvil en la <b>misma wifi</b>, escanea el código o escribe la dirección en el navegador:</p>
      ${conn.qr ? `<div class="qr">${conn.qr}</div>` : ""}${conn.urls.map((u) => `<div class="url">${esc(u)}</div>`).join("")}
      ${conn.pin_set ? "" : `<div class="note">${icon("lock", 18)}<div>Ahora mismo cualquiera conectado a tu wifi podría abrirla. Pon un <b>PIN</b> aquí abajo.</div></div>`}
      <details><summary>No me abre en el móvil</summary><div class="muted" style="padding:6px 0">
        • PC y móvil deben estar en la misma wifi (no datos móviles, ni wifi de invitados).<br>
        • En Windows, al arrancar por primera vez pulsa <b>«Permitir acceso»</b> en el aviso del firewall (redes privadas).<br>
        • Si el PC está en suspensión, no responde.</div></details>
      <details><summary>Instalarla como app en el móvil</summary><div class="muted" style="padding:6px 0">
        • <b>Android (Chrome):</b> menú ⋮ → «Añadir a pantalla de inicio».<br>
        • <b>iPhone (Safari):</b> Compartir → «Añadir a pantalla de inicio».<br>
        • La instalación completa como PWA (sin barra del navegador, escáner con cámara y uso offline) requiere <b>https</b>. Con <i>Tailscale</i> o <i>Cloudflare Tunnel</i> lo consigues y además la usas fuera de casa (mira el README).</div></details>`
      : `<div class="note">${icon("info", 18)}<div>No he detectado una red local. Conecta el PC a una wifi/cable.</div></div>`}
      ${isLocalhost ? "" : `<p class="muted">Estás conectado desde ${esc(location.host)}.</p>`}</div>

    <h2>${icon("lock", 15)} Seguridad</h2>
    <div class="card"><p class="muted" style="margin-top:0">${auth.pin_set ? "PIN activo: cada dispositivo lo pedirá una vez." : "Sin PIN. Recomendado si usas la app desde el móvil o fuera de casa."}</p>
      ${auth.pin_set ? `<label>PIN actual</label><input id="pin_cur" type="password" inputmode="numeric" autocomplete="off">` : ""}
      <label>${auth.pin_set ? "Nuevo PIN" : "PIN (mínimo 4)"}</label><input id="pin_new" type="password" inputmode="numeric" autocomplete="new-password">
      <div class="grid2" style="margin-top:12px"><button class="btn primary" id="pinSave">${icon("lock", 17)} ${auth.pin_set ? "Cambiar" : "Activar"}</button>
      ${auth.pin_set ? `<button class="btn danger" id="pinOff">Quitar PIN</button>` : ""}</div></div>

    <h2>${icon("download", 15)} Copia de seguridad & Exportar</h2>
    <div class="card"><p class="muted" style="margin-top:0">Exporta tu informe nutricional en PDF, descarga tus copias en JSON o historial en CSV para Excel.</p>
      <div class="grid2" style="margin-bottom:8px">
        <a class="btn primary" href="/report?date=${state.date}" target="_blank">${icon("download", 17)} Ver Informe PDF</a>
        <a class="btn" href="/api/export/pdf?date=${state.date}" download>${icon("download", 17)} Descargar PDF</a>
      </div>
      <div class="grid2"><a class="btn" href="/api/export" download>${icon("download", 17)} Copia (.json)</a><a class="btn" href="/api/export.csv" download>${icon("download", 17)} Historial (.csv)</a></div>
      <button class="btn block" style="margin-top:8px" id="restore">${icon("upload", 17)} Restaurar copia…</button><input id="restoreFile" type="file" accept=".json,application/json" class="hidden"></div>

    <p class="muted" style="text-align:center;margin-top:24px">Macros · tus datos viven en tu PC · <a style="color:var(--accent)" href="https://github.com/ivangarmir18/Calculadora_Macros" target="_blank" rel="noopener">GitHub</a></p>`;

  $$("#themeSeg button").forEach((b) => b.onclick = () => setTheme(b.dataset.t));
  $$("#c_sex button").forEach((b) => b.onclick = () => { $$("#c_sex button").forEach((x) => x.classList.remove("on")); b.classList.add("on"); });
  $("#saveGoals").onclick = async () => {
    const goals = Object.fromEntries(["kcal", "protein", "carbs", "fat"].map((k) => [k, toNum($("#g_" + k).value)]));
    const profile = {
      ...(p || {}),
      tdee: toNum($("#p_tdee")?.value || 3350),
      weight: toNum($("#p_weight")?.value || 119),
      lbm: toNum($("#p_lbm")?.value || 85.5),
    };
    await api("PUT", "/api/settings", { goals, profile });
    toast("Objetivos y perfil biométrico guardados", true);
  };
  $("#saveGhToken")?.addEventListener("click", async () => {
    const t = $("#gh_token").value.trim();
    if (!t) return toast("Pega un token de GitHub válido");
    await api("POST", "/api/github/token", { token: t });
    toast("Token de GitHub guardado y sincronizando...", true);
    setTimeout(renderSettings, 1200);
  });
  $("#deleteGhToken")?.addEventListener("click", async () => {
    await api("POST", "/api/github/token", { token: "" });
    toast("Token eliminado", true);
    renderSettings();
  });
  const doSync = async (mode, label) => {
    toast(label + "...");
    const r = await api("POST", "/api/github/sync", { mode });
    if (r.ok) {
      toast(r.pushed ? "DB subida a GitHub" : r.pulled ? "DB actualizada desde GitHub" : "Ya estaba al día", true);
    } else {
      toast(r.error || "No se pudo sincronizar");
    }
    renderSettings();
  };
  $("#syncGhNow")?.addEventListener("click", () => doSync("auto", "Sincronizando con GitHub"));
  $("#pushGhNow")?.addEventListener("click", () => doSync("push", "Subiendo DB a GitHub"));
  $("#pullGhNow")?.addEventListener("click", () => doSync("pull", "Descargando DB de GitHub"));
  $("#saveAiKey").onclick = async () => {
    const k = $("#gemini_key").value.trim();
    if (!k) return toast("Introduce una clave válida");
    await api("POST", "/api/ai/key", { key: k });
    toast("Clave de Gemini guardada", true);
    renderSettings();
  };
  $("#deleteAiKey")?.addEventListener("click", async () => {
    await api("POST", "/api/ai/key", { key: "" });
    toast("Clave eliminada", true);
    renderSettings();
  });
  $("#saveAiModel")?.addEventListener("click", async () => {
    const m = $("#gemini_model")?.value;
    if (m) {
      await api("POST", "/api/ai/model", { model: m });
      toast("Modelo preferido: " + m, true);
      renderSettings();
    }
  });
  $("#calc").onclick = () => {
    const sex = $("#c_sex .on").dataset.v, age = toNum($("#c_age").value), h = toNum($("#c_height").value), w = toNum($("#c_weight").value);
    if (!age || !h || !w) return toast("Rellena edad, altura y peso");
    const act = toNum($("#c_activity").value), adj = toNum($("#c_goal").value);
    const bmr = 10 * w + 6.25 * h - 5 * age + (sex === "m" ? 5 : -161);
    const kcal = Math.round(bmr * act * (1 + adj) / 10) * 10;
    const protein = Math.round(w * (adj < 0 ? 2.2 : 1.8)), fat = Math.round(kcal * 0.25 / 9);
    const carbs = Math.max(0, Math.round((kcal - protein * 4 - fat * 9) / 4));
    $("#calcRes").innerHTML = `<div class="result"><div class="muted">Metabolismo basal ${r0(bmr)} kcal · mantenimiento ${r0(bmr * act)} kcal</div>
      <div class="big" style="margin:6px 0;color:var(--kcal)">${kcal} <span class="muted">kcal/día</span></div>
      <div class="macros"><b class="mp">Proteína ${protein} g</b> · <b class="mc">Hidratos ${carbs} g</b> · <b class="mf">Grasa ${fat} g</b></div>
      <button class="btn primary block" style="margin-top:12px" id="useCalc">${icon("check", 18)} Usar como mis objetivos</button></div>`;
    $("#useCalc").onclick = async () => {
      await api("PUT", "/api/settings", { goals: { kcal, protein, carbs, fat }, profile: { sex, age, height: h, weight: w, activity: act, goal: adj } });
      toast("Objetivos actualizados", true); renderSettings();
    };
  };
  $("#pinSave").onclick = async () => {
    const r = await api("POST", "/api/auth/pin", { pin: $("#pin_new").value, current: $("#pin_cur")?.value || "" });
    toast(r.pin_set ? "PIN activado" : "PIN quitado", true); renderSettings();
  };
  $("#pinOff")?.addEventListener("click", async () => { await api("POST", "/api/auth/pin", { pin: "", current: $("#pin_cur").value }); toast("PIN quitado", true); renderSettings(); });
  $("#restore").onclick = () => $("#restoreFile").click();
  $("#restoreFile").onchange = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    if (!confirm("Restaurar REEMPLAZA todos los datos actuales por los de la copia. ¿Continuar?")) return;
    const fd = new FormData(); fd.append("file", file);
    await api("POST", "/api/import", fd); toast("Copia restaurada", true); renderSettings();
  };
}

// ======================================================================== LOGIN
function renderLogin() {
  document.body.classList.add("locked");
  $("#view").innerHTML = `<div class="login"><div class="logo">${icon("lock", 44)}</div><h1>Macros</h1><p class="muted">Introduce tu PIN</p>
    <input id="lp" type="password" inputmode="numeric" autocomplete="current-password" style="text-align:center;font-size:1.4rem;letter-spacing:.3em;margin:14px 0" autofocus>
    <button class="btn primary block" id="lg">Entrar</button></div>`;
  const go_ = async () => { try { await api("POST", "/api/auth/login", { pin: $("#lp").value }); buildNav(); render(); } catch { $("#lp").value = ""; $("#lp").focus(); } };
  $("#lg").onclick = go_; $("#lp").addEventListener("keydown", (e) => { if (e.key === "Enter") go_(); }); $("#lp").focus();
}

// ======================================================================== ARRANQUE
(async function boot() {
  buildNav();
  if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("/sw.js").catch(() => {});
  try { const a = await api("GET", "/api/auth/status"); if (a.pin_set && !a.authed) return renderLogin(); } catch { return; }
  render();
})();
