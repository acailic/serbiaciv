// Znanje: obrazovanje stanovništva (Popis 2022), zarade i zaposleni u nauci (NACE M i J) po opštinama i gradovima.
import { fin, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { pct, int, count3, fmtShort, fmtValue } from "../core/fmt.js";
import { barList, stackedBars, rampLegend } from "../core/charts.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { scienceLens, scienceShare } from "../core/lenses.js";
import { NULL_NOTE, KIM_NOTE, offMapNote } from "../core/notes.js";

// The Popis 2022 schooling ladder of the cities' education block, as shares of the population aged 15+.
export const EDU_LEVELS = [
  { key: "edu_none", label: "Bez škole", color: "#8a6a4a" },
  { key: "edu_primary", label: "Osnovna škola", color: "#c9a45c" },
  { key: "edu_secondary", label: "Srednja škola", color: "#4a86d6" },
  { key: "edu_higher", label: "Visoka škola ili fakultet", color: "#1d4e8f" },
  { key: "edu_unknown", label: "Nepoznato", color: "#c8c2b8" },
];

/** Population-weighted mean of a share over the rows that have both the share and the population. */
export function weightedShare(rows, key) {
  let s = 0, w = 0;
  for (const r of rows) {
    const v = r?.v?.[key], p = r?.v?.population;
    if (fin(v) && fin(p) && p > 0) { s += v * p; w += p; }
  }
  return w > 0 ? s / w : null;
}

const EDU_RAMP = ["#eef3f8", "#cfe0ee", "#a9c6e2", "#7fa9d0", "#5588ba", "#2f5f96", "#183a66"];

export function mount(ctx) {
  const { data, el, link } = ctx;
  const n = data.nation;
  const { states, metros, counties } = data.levels;
  const cRows = counties.rows;
  const eduLabel = counties.field("education").label;

  const eduNat = weightedShare(cRows, "education");
  const sci = data.yields?.find((y) => y.key === "science");
  el.insertAdjacentHTML("beforeend", tiles([
    { label: eduLabel, value: pct(eduNat), sub: "stanovništvo 15+, Popis 2022.", color: "#4a86d6" },
    { label: "Sa srednjom školom", value: pct(weightedShare(metros.rows, "edu_secondary")), sub: "stanovništvo 15+ u 52 grada, Popis 2022." },
    { label: sci?.label ?? "Nauka", value: fmtValue("int", n.v.yield_science), sub: "zaposlenih, NACE M i J", color: "#4a86d6" },
    { label: counties.field("wage_net").label, value: fmtValue("rsd", n.v.wage_net), sub: "dinarski mesečno, 2025." },
  ]));

  // --- map ---------------------------------------------------------------------------------------------------------
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "education",
    options: [
      { value: "education", label: "Visoko obrazovanje", lens: () => "education" },
      { value: "wages", label: "Zarade", lens: () => "wages" },
      { value: "science", label: "Nauka", lens: () => scienceLens(data) },
      { value: "unemployment", label: "Nezaposlenost", lens: () => "unemployment" },
    ],
  });

  // --- most educated -----------------------------------------------------------------------------------------------
  let eLevel = "counties";
  const eBody = section(el, { title: "Gde ima najviše obrazovanih", note: `Udeo stanovništva starog 15 i više godina sa završenom visokom školom ili fakultetom (Popis 2022.): osam jedinica sa najvišim i osam sa najnižim udelom. ${KIM_NOTE}` });
  const eHost = document.createElement("div");
  segmented(eBody, { label: "Podela", value: eLevel, options: [{ value: "counties", label: "Opština" }, { value: "metros", label: "Grad" }], onChange: (v) => { eLevel = v; drawEdu(); } });
  eBody.appendChild(eHost);
  const eduColor = colorScale({ type: "seq", domain: robustDomain(cRows.map((r) => r.v.education), 0.02) || [0.07, 0.5], ramp: EDU_RAMP });
  function drawEdu() {
    eHost.innerHTML = "";
    const lv = eLevel === "counties" ? counties : metros;
    const rows = lv.rows.filter((r) => fin(r.v.education));
    const hi = topBy(rows, (r) => r.v.education, { n: 8 });
    const lo = topBy(rows, (r) => r.v.education, { n: 8, asc: true });
    const max = Math.max(1e-9, ...hi.map((x) => x.v));
    const mk = (x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", value: x.v, text: pct(x.v), color: eduColor(x.v), row: x.r });
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null), onClick: (r) => lv.focus(r.row) };
    eHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najviši udeo</h4>`);
    barList(eHost, { ...o, rows: hi.map(mk), ariaLabel: "Najviši udeo visoko obrazovanih" });
    eHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najniži udeo</h4>`);
    barList(eHost, { ...o, rows: lo.map(mk), ariaLabel: "Najniži udeo visoko obrazovanih" });
  }
  drawEdu();

  // --- education vs. wages -----------------------------------------------------------------------------------------
  const sBody = section(el, { title: "Obrazovanje i zarade", note: "Svaka tačka je opština: udeo visoko obrazovanih horizontalno, prosečna neto zarada uspravno, veličina = stanovništvo, boja = stopa nezaposlenosti. Prevucite pravougaonik da izaberete opštine; one se osvetle na karti." });
  const unDom = robustDomain(cRows.map((r) => r.v.unemployment), 0.05) || [0.05, 0.3];
  const unColor = colorScale({ type: "seq", domain: unDom, ramp: RAMPS.heat });
  const pts = cRows.filter((r) => fin(r.v.education) && fin(r.v.wage_net));
  const scatter = createScatter(sBody, {
    height: 310,
    points: pts.map((r) => ({ key: r.key, x: r.v.education, y: r.v.wage_net, s: r.v.population, c: r.v.unemployment, label: r.name, sub: r.sub, row: r })),
    x: { label: "Visoko obrazovanje", fmt: (v) => fmtShort("pct", v) },
    y: { label: "Prosečna neto zarada", fmt: (v) => fmtShort("rsd", v) },
    size: { label: "Stanovništvo", fmt: count3, max: 13, min: 2 },
    color: (c) => (fin(c) ? unColor(c) : "#8a8378"),
    labels: topBy(pts, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    onHover: (p) => link.hover(p ? rowsHighlight(counties, [p.row]) : null),
    onClick: (p) => counties.focus(p.row),
    onBrush: (set) => {
      const sel = set ? pts.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(counties, sel, { dim: true }) : null, { frame: sel.length > 1 });
      selInfo.innerHTML = sel.length ? `<b>${int(sel.length)}</b> opština · ${count3(sel.reduce((a, r) => a + (fin(r.v.population) ? r.v.population : 0), 0))} stanovnika ${frameBtn()}<button type="button" class="adv-mini" data-clear>Očisti</button>` : "";
    },
  });
  sBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.heat, domain: unDom, fmt: (v) => fmtShort("pct", v), label: "Stopa nezaposlenosti" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  sBody.appendChild(selInfo);
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; } });

  // --- science workers ---------------------------------------------------------------------------------------------
  const wBody = section(el, { title: "Zaposleni u nauci", note: `${sci?.description ?? "Zaposleni u stručnim, naučnim i tehničkim delatnostima i u informisanju (NACE M i J)"} Kao udeo zaposlenih stanovnika grada, prema prebivalištu (Popis 2022.): gradovi od 20 hiljada stanovnika.` });
  const wCtl = document.createElement("div");
  wCtl.className = "adv-row";
  wBody.appendChild(wCtl);
  const wBtn = document.createElement("button");
  wBtn.type = "button";
  wBtn.className = "adv-mini";
  wBtn.textContent = "Oboji kartu po nauci";
  wBtn.addEventListener("click", () => picker.set("science"));
  wCtl.appendChild(wBtn);
  const wHost = document.createElement("div");
  wBody.appendChild(wHost);
  const sciRows = metros.rows.filter((r) => fin(scienceShare(r)) && (r.v.population ?? 0) >= 20000);
  const sciTop = topBy(sciRows, scienceShare, { n: 10 });
  const sciLo = topBy(sciRows, scienceShare, { n: 10, asc: true });
  const sciDom = robustDomain(sciRows.map(scienceShare), 0.02) || [0.02, 0.12];
  const sciColor = colorScale({ type: "seq", domain: sciDom, ramp: ["#e4f3ff", "#8cc2ee", "#4f93d6", "#2f63a8", "#173a6b", "#0a1a33"] });
  const mkSci = (x) => ({ key: x.r.key, label: x.r.name, sub: `${count3(x.r.v.jobs_science)} zaposlenih`, value: x.v, text: pct(x.v), color: sciColor(x.v), row: x.r });
  const sciOpts = { max: sciTop[0]?.v ?? 1, onHover: (r) => link.hover(r ? rowsHighlight(metros, [r.row]) : null), onClick: (r) => metros.focus(r.row) };
  wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najviši udeo</h4>`);
  barList(wHost, { ...sciOpts, rows: sciTop.map(mkSci), ariaLabel: "Najviši udeo zaposlenih u nauci" });
  wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najniži udeo</h4>`);
  barList(wHost, { ...sciOpts, rows: sciLo.map(mkSci), ariaLabel: "Najniži udeo zaposlenih u nauci" });

  // --- schooling ladder of the cities ------------------------------------------------------------------------------
  const lBody = section(el, { title: "Obrazovanje gradova po stepenu", note: "Stanovništvo staro 15 i više godina po najvišoj završenoj školi (Popis 2022.), za šesnaest gradova sa najviše stanovnika. Popisni blok obrazovanja postoji samo za gradove, ne i za opštine i okruge.", open: false });
  const lHost = document.createElement("div");
  lBody.appendChild(lHost);
  lHost.insertAdjacentHTML("beforeend", `<div class="adv-legend sw">${EDU_LEVELS.map((g) => `<span class="it"><i style="background:${g.color}"></i>${g.label}</span>`).join("")}</div>`);
  stackedBars(lHost, {
    keys: EDU_LEVELS.map((g) => ({ key: g.key, label: g.label, color: g.color })), normalize: true, ariaLabel: "Obrazovanje stanovništva gradova",
    fmt: (v) => pct(v),
    rows: topBy(metros.rows, (r) => r.v.population, { n: 16 }).map((x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", parts: Object.fromEntries(EDU_LEVELS.map((g) => [g.key, x.r.v[g.key]])), text: `${pct(x.r.v.edu_higher)} visoko obrazovanih`, row: x.r })),
    onHover: (x) => link.hover(x?.row ? rowsHighlight(metros, [x.row]) : null),
    onClick: (x) => x?.row && metros.focus(x.row),
  });

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["census", "rzs_db"], [
    NULL_NOTE,
    KIM_NOTE,
    "Udeo visoko obrazovanih po opštinama je udeo među stanovništvom starim 15 i više godina (Popis 2022.); nacionalni udeo na vrhu težinska je sredina opština po broju stanovnika.",
    "Zaposleni u nauci broje se prema prebivalištu: NACE odeljak M (stručne, naučne i tehničke delatnosti) i J (informisanje i komunikacije). To je merilo „Nauka“ iz gornje trake.",
    "Tabla o univerzitetima, studentima i istraživanju i razvoju, i tabla o širokopojasnom internetu, izostavljene su: za Srbiju ti podaci nisu javno objavljeni po opštinama u obliku koji ova karta može da cita.",
    ...(data.countiesOffMap ? [offMapNote(data)] : []),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
    },
    onEscape() {
      if (scatter.selected) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
