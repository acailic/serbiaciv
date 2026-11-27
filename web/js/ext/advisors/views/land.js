// Zemljište: what covers Serbia (WorldCover shares by okrug, opština and grad), who works the land, the terrain,
// and the forest–field split of the opštine.
import { fin, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { pct, int, count3, fmtShort, fmtValue } from "../core/fmt.js";
import { barList, stackedBars, swatchLegend, rampLegend } from "../core/charts.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight, LAND_KEYS, LAND_LABEL, LAND_COLOR } from "../core/data.js";
import { countyLens, stateLens } from "../core/lenses.js";
import { NULL_NOTE, KIM_NOTE, offMapNote } from "../core/notes.js";

// The four covers that make up almost all of Serbia's land (grass, scrub and wetland are under 0.5 % together).
const BARS = ["forest", "crop", "pasture", "developed"];
const RELIEF = [
  { key: 0, label: "Ravnica", color: "#6f9e4a" },
  { key: 1, label: "Brdovit teren", color: "#c2a24f" },
  { key: 2, label: "Planine", color: "#8d6e63" },
  { key: 3, label: "Vrhovi", color: "#efe9df" },
];
const GREEN = ["#e9f1dc", "#cfe0ad", "#a9c77a", "#7fae52", "#558a3a", "#2f5f2a", "#16381a"];

/** Area-weighted national cover shares from the okruzi with a complete land block. */
export function nationalLand(states) {
  const out = Object.fromEntries(LAND_KEYS.map((k) => [k, null]));
  let w = 0;
  for (const r of states.rows) {
    if (!fin(r.v.land_km2) || !LAND_KEYS.every((k) => fin(r.v[`land_${k}`]))) continue;
    w += r.v.land_km2;
    for (const k of LAND_KEYS) out[k] = (out[k] ?? 0) + r.v[`land_${k}`] * r.v.land_km2;
  }
  if (w > 0) for (const k of LAND_KEYS) out[k] /= w;
  return out;
}

/** Share of each relief class among a unit's hexes. */
export function reliefShares(cells, relief) {
  const n = [0, 0, 0, 0];
  let t = 0;
  for (const c of cells) { const k = relief[c]; if (k != null && k >= 0 && k < 4) { n[k]++; t++; } }
  return n.map((x) => (t ? x / t : null));
}

/** Share of employed residents working in agriculture, forestry and fishing (NACE A). */
export const farmShare = (r) => (fin(r?.v?.jobs_agriculture) && fin(r?.v?.jobs_total) && r.v.jobs_total > 0 ? r.v.jobs_agriculture / r.v.jobs_total : null);

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const { states, metros, counties } = data.levels;
  const cRows = counties.rows;
  const raw = app.w.raw;
  const relief = raw.relief ?? [];
  const landCells = (raw.owner ?? []).filter((o) => o != null && o >= 0).length;
  const nat = nationalLand(states);

  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Površina Srbije", value: fmtValue("km2", data.hexArea ? landCells * data.hexArea : null), sub: `${int(landCells)} hekseva od 5 km` },
    { label: "Pod šumom", value: pct(nat.forest), sub: "površine okruga", color: LAND_COLOR.forest },
    { label: "Pod njivama", value: pct(nat.crop), sub: "površine okruga", color: LAND_COLOR.crop },
    { label: "Na pašnjacima i livadama", value: pct(nat.pasture), sub: "površine okruga", color: LAND_COLOR.pasture },
  ]));

  // --- map ---------------------------------------------------------------------------------------------------------
  const forestLens = () => countyLens(data, "land_forest", { name: "Šuma po opštinama", unit: "%", format: "pct", ramp: GREEN, group: "land", icon: "l-land_cover", emoji: "🌲",
    description: "Udeo površine opštine pod šumom (ESA WorldCover 2021). Svaki heks nosi vrednost svoje opštine.", source: "landcover", note: "Za Kosovo i Metohiju pokrivač zemljišta postoji (satelitski podatak), statistika ne." });
  const cropLens = () => countyLens(data, "land_crop", { name: "Njive po opštinama", unit: "%", format: "pct", ramp: ["#f3efd8", "#e6dca0", "#d6c45e", "#c2ad3c", "#9c8526", "#6e5a16"], group: "land", icon: "l-land_cover", emoji: "🌾",
    description: "Udeo površine opštine pod njivama (ESA WorldCover 2021). Svaki heks nosi vrednost svoje opštine.", source: "landcover", note: "Za Kosovo i Metohiju pokrivač zemljišta postoji (satelitski podatak), statistika ne." });
  let cLevel = "states";
  const farmLens = () => stateLens(data, "farm", farmShare, { name: "Zaposleni u poljoprivredi po okruzima", unit: "od zaposlenih", format: "pct", ramp: RAMPS.seq, group: "land", icon: "l-manufacturing", emoji: "🚜",
    description: "Zaposleni u poljoprivredi, šumarstvu i ribarstvu (NACE odeljak A) kao udeo zaposlenih stanovnika okruga, prema prebivalištu (Popis 2022).", source: "census", note: KIM_NOTE });
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "cover",
    options: [
      { value: "cover", label: "Pokrivač", lens: () => "land_cover" },
      { value: "forest", label: "Šuma", lens: forestLens },
      { value: "crop", label: "Njive", lens: cropLens },
      { value: "farm", label: "Poljoprivreda", lens: farmLens },
      { value: "relief", label: "Reljef", lens: () => "relief" },
    ],
  });

  // --- what covers the land ----------------------------------------------------------------------------------------
  const cBody = section(el, { title: "Šta pokriva zemlju", note: "Udeo površine pod svakim pokrivačem: 20 najvećih jedinica. Postavite kursor na traku da vidite jedinicu na karti; kliknite da je otvorite." });
  const keys = BARS.map((k) => ({ key: k, label: LAND_LABEL[k], color: LAND_COLOR[k] }));
  const cHost = document.createElement("div");
  segmented(cBody, { label: "Podela", value: cLevel, options: [{ value: "states", label: "Okrug" }, { value: "counties", label: "Opština" }, { value: "metros", label: "Grad" }], onChange: (v) => { cLevel = v; drawCover(); } });
  cBody.appendChild(cHost);
  cBody.insertAdjacentHTML("beforeend", swatchLegend(keys));
  let cover = null;
  function drawCover() {
    cover?.el.remove();
    const lv = data.levels[cLevel];
    const rows = lv.rows.filter((r) => fin(r.v.land_km2) && BARS.some((k) => fin(r.v[`land_${k}`])))
      .sort((a, b) => b.v.land_km2 - a.v.land_km2).slice(0, 20);
    cover = stackedBars(cHost, {
      keys, normalize: true, ariaLabel: "Pokrivač zemljišta po jedinicama",
      fmt: (v) => pct(v),
      rows: rows.map((r) => ({ key: r.key, label: r.name, sub: r.sub !== r.name ? r.sub : "", parts: Object.fromEntries(BARS.map((k) => [k, r.v[`land_${k}`]])), text: `${pct(r.v.land_forest)} šume · ${fmtValue("km2", r.v.land_km2)}` })),
      onHover: (x) => link.hover(x?.row ? rowsHighlight(lv, [x.row]) : null),
      onClick: (x) => x?.row && lv.focus(x.row),
    });
  }
  drawCover();

  // --- forest vs. field --------------------------------------------------------------------------------------------
  const sBody = section(el, { title: "Šuma i njive", note: "Svaka tačka je opština: udeo pod šumom horizontalno, pod njivama uspravno, veličina = površina, boja = gradsko zemljište. Prevucite pravougaonik da izaberete opštine; one se osvetle na karti." });
  const devDom = robustDomain(cRows.map((r) => r.v.land_developed), 0.02) || [0, 0.2];
  const devColor = colorScale({ type: "seq", domain: devDom, ramp: ["#f1ece2", "#d9cfd6", "#b9a9b8", "#9a8f9e", "#5f5463"] });
  const scatter = createScatter(sBody, {
    height: 310,
    points: cRows.map((r) => ({ key: r.key, x: r.v.land_forest, y: r.v.land_crop, s: r.v.land_km2, c: r.v.land_developed, label: r.name, sub: r.sub, row: r })),
    x: { label: "Šuma", fmt: (v) => fmtShort("pct", v) },
    y: { label: "Njive", fmt: (v) => fmtShort("pct", v) },
    size: { label: "Površina", fmt: (v) => fmtValue("km2", v), max: 14, min: 1.4 },
    color: (c) => (fin(c) ? devColor(c) : "#8a8378"),
    labels: topBy(cRows, (r) => r.v.land_km2, { n: 6 }).map((x) => x.r.key),
    refX: [{ v: nat.forest, label: "Srbija" }], refY: [{ v: nat.crop, label: "Srbija" }],
    onHover: (p) => link.hover(p ? rowsHighlight(counties, [p.row]) : null),
    onClick: (p) => counties.focus(p.row),
    onBrush: (set) => {
      const sel = set ? cRows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(counties, sel, { dim: true }) : null, { frame: sel.length > 1 });
      selInfo.innerHTML = sel.length ? selSummary(sel) : "";
    },
  });
  sBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: ["#f1ece2", "#d9cfd6", "#b9a9b8", "#9a8f9e", "#5f5463"], domain: devDom, fmt: (v) => fmtShort("pct", v), label: "Gradsko zemljište" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  sBody.appendChild(selInfo);
  function selSummary(sel) {
    const km2 = sel.reduce((a, r) => a + (fin(r.v.land_km2) ? r.v.land_km2 : 0), 0);
    const top = [...sel].sort((a, b) => (b.v.land_km2 ?? 0) - (a.v.land_km2 ?? 0)).slice(0, 5);
    return `<b>${int(sel.length)}</b> opština · ${fmtValue("km2", km2)}${frameBtn()}<button type="button" class="adv-mini" data-clear>Očisti</button><br><span class="sub">Najveće: ${top.map((r) => `${r.name}, ${r.sub}`).join(" · ")}</span>`;
  }
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; } });

  // --- who works the land ------------------------------------------------------------------------------------------
  let fRow = "states";
  const fBody = section(el, { title: "Ko radi na zemlji", note: "Udeo zaposlenih stanovnika koji rade u poljoprivredi, šumarstvu i ribarstvu (NACE odeljak A), prema prebivalištu (Popis 2022): osam okruga ili gradova sa najvećim i osam sa najmanjim udelom." });
  const fHost = document.createElement("div");
  segmented(fBody, { label: "Podela", value: "states", options: [{ value: "states", label: "Okrug" }, { value: "metros", label: "Grad" }], onChange: (v) => { fRow = v; drawFarm(); } });
  fBody.appendChild(fHost);
  function drawFarm() {
    fHost.innerHTML = "";
    const lv = fRow === "states" ? states : metros;
    const hi = topBy(lv.rows, farmShare, { n: 8 });
    const lo = topBy(lv.rows, farmShare, { n: 8, asc: true });
    const max = Math.max(1e-9, ...hi.map((x) => x.v));
    const mk = (x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", value: x.v, text: pct(x.v), color: LAND_COLOR.pasture, row: x.r });
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null), onClick: (r) => lv.focus(r.row) };
    fHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najviše</h4>`);
    barList(fHost, { ...o, rows: hi.map(mk), ariaLabel: "Najveći udeo zaposlenih u poljoprivredi" });
    fHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najmanje</h4>`);
    barList(fHost, { ...o, rows: lo.map(mk), ariaLabel: "Najmanji udeo zaposlenih u poljoprivredi" });
  }
  drawFarm();

  // --- terrain -----------------------------------------------------------------------------------------------------
  const rBody = section(el, { title: "Teren", note: "Koliko hekseva svakog okruga je ravnica, koliko brdovit teren, koliko planine i vrhovi (Copernicus GLO-10). Kliknite na red da otvorite okrug.", open: false });
  const rHost = document.createElement("div");
  rBody.appendChild(rHost);
  rHost.insertAdjacentHTML("beforeend", swatchLegend(RELIEF));
  const reliefLens = data.lensById?.get("relief");
  const reliefNames = reliefLens?.categories ?? [];
  const rKeys = RELIEF.map((x, i) => ({ key: String(x.key), label: reliefNames[i]?.name ?? x.label, color: reliefNames[i]?.color ?? x.color }));
  stackedBars(rHost, {
    keys: rKeys, normalize: true, ariaLabel: "Reljef po okruzima",
    fmt: (v) => pct(v),
    rows: states.rows.map((r) => { const s = reliefShares(r.cells, relief); return { key: r.key, label: r.name, sub: "", parts: Object.fromEntries(RELIEF.map((x, i) => [String(x.key), s[i]])), text: `${pct(s[2])} planina` }; })
      .sort((a, b) => (b.parts["2"] ?? 0) - (a.parts["2"] ?? 0)),
    onHover: (x) => link.hover(x?.row ? rowsHighlight(states, [x.row]) : null),
    onClick: (x) => x?.row && states.focus(x.row),
  });

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["landcover", "dem", "boundaries", "census"], [
    NULL_NOTE,
    KIM_NOTE,
    "Pokrivač zemljišta je ESA WorldCover 2021 (10 m): udeo površine jedinice pod svakim tipom. Travnjaci, žbunje i močvare zajedno pokrivaju manje od pola procenta Srbije, pa nisu u traci; u Istraživaču su.",
    "Za gradove je pokrivač izračunat po heksima koje grad zauzima na karti (podaci o gradovima nemaju površinu po granicama), a gustoća koristi površinu tih hekseva.",
    "Zaposleni u poljoprivredi broje se prema prebivalištu, ne prema mestu rada: okrug sa mnogo poljoprivrednog stanovništva može imati velik udeo iako se deo njih radi drugde.",
    ...(data.countiesOffMap ? [offMapNote(data)] : []),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      if (r) cover?.setHot(r.key); else cover?.setHot(null);
    },
    onEscape() {
      if (scatter.selected) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
