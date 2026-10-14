/* Gráficas SVG sin librerías. Los colores vienen de variables CSS (valen para tema claro y oscuro). */

/** Anillo de progreso. value/goal -> arco. */
function ringChart(value, goal, { size = 132, stroke = 12, color = "var(--kcal)" } = {}) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const pct = goal > 0 ? Math.min(value / goal, 1) : 0;
  const over = goal > 0 && value > goal;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" class="ring">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--track)" stroke-width="${stroke}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${over ? "var(--danger)" : color}" stroke-width="${stroke}"
      stroke-linecap="round" stroke-dasharray="${c * pct} ${c}" transform="rotate(-90 ${size / 2} ${size / 2})" style="transition:stroke-dasharray .5s"/></svg>`;
}

/** Reparto de calorías por macro (proteína/hidratos/grasa) como anillo. */
function donutChart(p, c, f, size = 110) {
  const parts = [[p * 4, "var(--p)"], [c * 4, "var(--c)"], [f * 9, "var(--f)"]];
  const total = parts.reduce((a, x) => a + x[0], 0);
  const r = 40, circ = 2 * Math.PI * r;
  if (!total) return `<svg width="${size}" height="${size}" viewBox="0 0 100 100"><circle cx="50" cy="50" r="${r}" fill="none" stroke="var(--track)" stroke-width="14"/></svg>`;
  let off = 0;
  const arcs = parts.map(([v, col]) => {
    const len = (v / total) * circ;
    const s = `<circle cx="50" cy="50" r="${r}" fill="none" stroke="${col}" stroke-width="14" stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="${-off}" transform="rotate(-90 50 50)"/>`;
    off += len; return s;
  }).join("");
  return `<svg width="${size}" height="${size}" viewBox="0 0 100 100">${arcs}</svg>`;
}

/** Barras de kcal por día con línea de objetivo. days: [{date,kcal}] ascendente. */
function barChart(days, goal) {
  const W = 340, H = 150, padL = 4, padB = 18, padT = 8, n = days.length || 1;
  const max = Math.max(goal * 1.15, ...days.map((d) => d.kcal), 1);
  const bw = (W - padL) / n, gap = Math.min(4, bw * 0.25);
  const y = (v) => padT + (H - padT - padB) * (1 - v / max);
  const bars = days.map((d, i) => {
    const h = Math.max(0, (H - padT - padB) * (d.kcal / max));
    const cls = d.kcal > goal ? "over" : d.kcal > 0 ? "ok" : "";
    return `<rect class="bar-r ${cls}" x="${padL + i * bw + gap / 2}" y="${H - padB - h}" width="${Math.max(1, bw - gap)}" height="${h}" rx="${Math.min(4, bw / 3)}"><title>${d.date}: ${Math.round(d.kcal)} kcal</title></rect>`;
  }).join("");
  const step = Math.ceil(n / 6);
  const labels = days.map((d, i) => (i % step === 0 || i === n - 1) ? `<text x="${padL + i * bw + bw / 2}" y="${H - 4}" text-anchor="middle">${d.date.slice(8)}/${d.date.slice(5, 7)}</text>` : "").join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart">${bars}
    <line x1="0" x2="${W}" y1="${y(goal)}" y2="${y(goal)}" stroke="var(--muted)" stroke-dasharray="4 4" stroke-width="1"/>
    <text x="${W - 2}" y="${y(goal) - 3}" text-anchor="end" class="goal-l">objetivo ${Math.round(goal)}</text>${labels}</svg>`;
}

/** Línea de peso. points: [{date,kg}] ascendente. */
function lineChart(points) {
  const W = 340, H = 140, padL = 30, padR = 10, padT = 12, padB = 18;
  if (points.length < 2) return `<div class="empty small">Apunta al menos 2 pesos para ver la gráfica</div>`;
  const ts = points.map((p) => new Date(p.date).getTime());
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  const ks = points.map((p) => p.kg);
  let lo = Math.min(...ks), hi = Math.max(...ks);
  const pad = Math.max(0.5, (hi - lo) * 0.2); lo -= pad; hi += pad;
  const x = (t) => padL + ((t - t0) / (t1 - t0 || 1)) * (W - padL - padR);
  const y = (k) => padT + (1 - (k - lo) / (hi - lo)) * (H - padT - padB);
  const pts = points.map((p, i) => [x(ts[i]), y(p.kg)]);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const area = `${path} L${pts[pts.length - 1][0]} ${H - padB} L${pts[0][0]} ${H - padB} Z`;
  const ticks = [hi - pad, (hi + lo) / 2, lo + pad].map((k) => `<line x1="${padL}" x2="${W - padR}" y1="${y(k)}" y2="${y(k)}" stroke="var(--line)" stroke-width="1"/><text x="${padL - 4}" y="${y(k) + 3}" text-anchor="end">${k.toFixed(1)}</text>`).join("");
  const dots = pts.length <= 40 ? pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="var(--accent)"><title>${points[i].date}: ${points[i].kg} kg</title></circle>`).join("") : "";
  const d0 = points[0].date, d1 = points[points.length - 1].date;
  return `<svg viewBox="0 0 ${W} ${H}" class="chart"><defs><linearGradient id="wg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--accent)" stop-opacity=".3"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>
    ${ticks}<path d="${area}" fill="url(#wg)"/><path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>${dots}
    <text x="${padL}" y="${H - 3}">${d0.slice(8)}/${d0.slice(5, 7)}</text><text x="${W - padR}" y="${H - 3}" text-anchor="end">${d1.slice(8)}/${d1.slice(5, 7)}</text></svg>`;
}

