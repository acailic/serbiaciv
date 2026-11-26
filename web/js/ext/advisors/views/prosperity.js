// Prosperitet: neto zarade, nezaposlenost, starost i trajanje života po opštinama, okruzima i gradovima.
import { fin, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { pct, int, signedPct, count3, fmtShort, fmtValue, fmtCell } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createScatter } from "../core/scatter.js";
import { createTable } from "../core/table.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight, BIG_METRO_MIN } from "../core/data.js";
import { NULL_NOTE, KIM_NOTE, BEOGRAD_NOTE, NOVI_SAD_OPSTINA_NOTE, offMapNote } from "../core/notes.js";

const WAGE_COLOR = "#3f9c82";
const UN_COLOR = "#c2463d";

export function mount(ctx) {
  const { data, el, link } = ctx;
  const n = data.nation;
  const { states, metros, counties } = data.levels;
  const cRows = counties.rows;
  const uLabel = counties.field("unemployment").label;

  const best = topBy(states.rows, (r) => r.v.unemployment, { n: 1, asc: true })[0]?.r ?? null;
  el.insertAdjacentHTML("beforeend", tiles([
    { label: counties.field("wage_net").label, value: fmtValue("rsd", n.v.wage_net), sub: "dinarski mesečno, 2025.", color: WAGE_COLOR },
    { label: uLabel, value: pct(n.v.unemployment), sub: "Popis 2022.", color: UN_COLOR },
    { label: "Stariji od 65 godina", value: pct(n.v.age65), sub: "procena 2025." },
    { label: "Najniža nezaposlenost", value: best ? best.name : "–", sub: best ? `${pct(best.v.unemployment)} · ${best.sub}` : "", color: "#3f9c82" },
  ]));

  // --- map ---------------------------------------------------------------------------------------------------------
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "wages",
    options: [
      { value: "wages", label: "Zarade", lens: () => "wages" },
      { value: "unemployment", label: "Nezaposlenost", lens: () => "unemployment" },
      { value: "age65", label: "Stariji od 65", lens: () => "age65" },
      { value: "life_expectancy", label: "Trajanje života", lens: () => "life_expectancy" },
    ],
  });

  // --- wages -------------------------------------------------------------------------------------------------------
  const lvl = (v) => (v === "counties" ? counties : v === "states" ? states : metros);
  let wLevel = "counties";
  const wBody = section(el, { title: "Gde su zarade više, a gde niže", note: `Prosečna neto zarada u dinarima mesečno (2025): osam jedinica sa najvišom i osam sa najnižom zaradom. ${BEOGRAD_NOTE}` });
  const wHost = document.createElement("div");
  segmented(wBody, { label: "Podela", value: wLevel, options: [{ value: "counties", label: "Opština" }, { value: "states", label: "Okrug" }, { value: "metros", label: "Grad" }], onChange: (v) => { wLevel = v; drawWages(); } });
  wBody.appendChild(wHost);
  function drawWages() {
    wHost.innerHTML = "";
    const lv = lvl(wLevel);
    const rows = lv.rows.filter((r) => fin(r.v.wage_net));
    const hi = topBy(rows, (r) => r.v.wage_net, { n: 8 });
    const lo = topBy(rows, (r) => r.v.wage_net, { n: 8, asc: true });
    const max = Math.max(...hi.map((x) => x.v), n.v.wage_net ?? 0, 1);
    const ref = fin(n.v.wage_net) && n.v.wage_net > 0 ? n.v.wage_net : null;
    const mk = (x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", value: x.v, text: `${fmtValue("rsd", x.v)}${ref ? ` · ${fmtShort("float", x.v / ref)}× prosek` : ""}`, color: WAGE_COLOR, row: x.r });
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null), onClick: (r) => lv.focus(r.row) };
    wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najviše</h4>`);
    barList(wHost, { ...o, rows: hi.map(mk), ariaLabel: "Najviše prosečne neto zarade" });
    wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najniže</h4>`);
    barList(wHost, { ...o, rows: lo.map(mk), ariaLabel: "Najniže prosečne neto zarade" });
  }
  drawWages();

  // --- unemployment ------------------------------------------------------------------------------------------------
  let uLevel = "states";
  const uBody = section(el, { title: "Nezaposlenost", note: `Udeo nezaposlenih u aktivnom stanovništvu (Popis 2022.): okruzi sa najvišom i najnižom stopom, i gradovi od ${count3(BIG_METRO_MIN)} stanovnika.` });
  const uHost = document.createElement("div");
  segmented(uBody, { label: "Podela", value: uLevel, options: [{ value: "states", label: "Okrug" }, { value: "metros", label: "Grad" }], onChange: (v) => { uLevel = v; drawUnemp(); } });
  uBody.appendChild(uHost);
  function drawUnemp() {
    uHost.innerHTML = "";
    const lv = lvl(uLevel);
    const rows = uLevel === "metros" ? topBy(metros.rows, (r) => r.v.unemployment, { n: 12, min: BIG_METRO_MIN }).map((x) => x.r) : states.rows.filter((r) => fin(r.v.unemployment));
    const list = topBy(rows, (r) => r.v.unemployment, { n: uLevel === "metros" ? 12 : 8 });
    const max = Math.max(1e-9, ...list.map((x) => x.v));
    const ref = fin(n.v.unemployment) ? n.v.unemployment : null;
    const lo = uLevel === "metros" ? [] : topBy(rows, (r) => r.v.unemployment, { n: 8, asc: true });
    const mk = (x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", value: x.v, text: `${pct(x.v)}${ref ? ` · ${fmtShort("float", x.v / ref)}× prosek` : ""}`, color: UN_COLOR, row: x.r });
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null), onClick: (r) => lv.focus(r.row) };
    uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${uLevel === "metros" ? "Gradovi od 200 hilj. stanovnika" : "Najviša stopa"}</h4>`);
    barList(uHost, { ...o, rows: list.map(mk), ariaLabel: "Najviša stopa nezaposlenosti" });
    if (lo.length) {
      uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najniža stopa</h4>`);
      barList(uHost, { ...o, rows: lo.map(mk), ariaLabel: "Najniža stopa nezaposlenosti" });
    }
  }
  drawUnemp();

  // --- age and unemployment ----------------------------------------------------------------------------------------
  const aBody = section(el, { title: "Starost i nezaposlenost", note: "Svaka tačka je opština: udeo starijih od 65 godina horizontalno, stopa nezaposlenosti uspravno, veličina = stanovništvo, boja = prosečna neto zarada. Prevucite pravougaonik da izaberete opštine; one se osvetle na karti." });
  const wDom = robustDomain(cRows.map((r) => r.v.wage_net), 0.05) || [60000, 160000];
  const wColor = colorScale({ type: "seq", domain: wDom, ramp: ["#e6f2ee", "#bfe0d6", "#8fcbb8", "#5fb39e", "#2f8f7a", "#186352"] });
  const aPts = cRows.filter((r) => fin(r.v.age65) && fin(r.v.unemployment));
  const scatter = createScatter(aBody, {
    height: 310,
    points: aPts.map((r) => ({ key: r.key, x: r.v.age65, y: r.v.unemployment, s: r.v.population, c: r.v.wage_net, label: r.name, sub: r.sub, row: r })),
    x: { label: "Stariji od 65 godina", fmt: (v) => fmtShort("pct", v) },
    y: { label: uLabel, fmt: (v) => fmtShort("pct", v) },
    size: { label: "Stanovništvo", fmt: count3, max: 13, min: 2 },
    color: (c) => (fin(c) ? wColor(c) : "#8a8378"),
    labels: topBy(aPts, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    onHover: (p) => link.hover(p ? rowsHighlight(counties, [p.row]) : null),
    onClick: (p) => counties.focus(p.row),
    onBrush: (set) => {
      const sel = set ? aPts.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(counties, sel, { dim: true }) : null, { frame: sel.length > 1 });
      selInfo.innerHTML = sel.length ? `<b>${int(sel.length)}</b> opština · ${count3(sel.reduce((a, r) => a + (fin(r.v.population) ? r.v.population : 0), 0))} stanovnika${fin(n.v.population) && n.v.population > 0 ? ` (${pct(sel.reduce((a, r) => a + (fin(r.v.population) ? r.v.population : 0), 0) / n.v.population)} Srbije)` : ""} ${frameBtn()}<button type="button" class="adv-mini" data-clear>Očisti</button>` : "";
    },
  });
  aBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: ["#e6f2ee", "#bfe0d6", "#8fcbb8", "#5fb39e", "#2f8f7a", "#186352"], domain: wDom, fmt: (v) => fmtShort("rsd", v), label: "Prosečna neto zarada" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  aBody.appendChild(selInfo);
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; } });

  // --- wage distribution -------------------------------------------------------------------------------------------
  const hBody = section(el, { title: "Koliko opština ima koju zaradu", note: "Opštine po prosečnoj neto zaradi; postavite kursor na stubić da vidite koje su to opštine." });
  const hHost = document.createElement("div");
  hBody.appendChild(hHost);
  const hInfo = document.createElement("div");
  hInfo.className = "adv-brushinfo";
  hBody.appendChild(hInfo);
  const wDomH = robustDomain(cRows.map((r) => r.v.wage_net), 0.02) || [60000, 160000];
  const hist = histogram(hHost, {
    values: cRows.map((r) => ({ key: r.key, v: r.v.wage_net })), bins: 26, domain: wDomH, height: 120, color: WAGE_COLOR,
    fmt: (v) => fmtShort("rsd", v), unitLabel: "opština", label: "Histogram prosečne neto zarade po opštinama",
    markers: fin(n.v.wage_net) ? [{ v: n.v.wage_net, label: "prosek Srbije" }] : [],
    onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
    onClick: (bin) => {
      const rows = bin.keys.map((k) => counties.byKey.get(k));
      link.base(rowsHighlight(counties, rows, { dim: true }), { frame: rows.length > 1 });
      hInfo.innerHTML = `<b>${int(rows.length)}</b> opština · ${count3(rows.reduce((a, r) => a + (fin(r.v.population) ? r.v.population : 0), 0))} stanovnika ${frameBtn()}<button type="button" class="adv-mini" data-clear>Očisti</button>`;
    },
  });
  hInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { link.base(null); hInfo.innerHTML = ""; } });

  // --- table -------------------------------------------------------------------------------------------------------
  const tBody = section(el, { title: "Sve opštine", note: "Kliknite na zaglavlje da sortirate, na red da vidite opštinu na karti. Pretraga filtrira po imenu.", open: false });
  const col = (key, short, fmt, title) => ({ key, label: short, value: (r) => r.v[key], text: (r) => (fin(r.v[key]) ? fmt(r.v[key]) : "–"), align: "r", title });
  const table = createTable(tBody, {
    rows: cRows, rank: true, sort: { key: "population", dir: "desc" }, maxHeight: 360, search: "Pretraži opštinu", caption: "Opštine po zaradi, nezaposlenosti i starosti",
    columns: [
      { key: "name", label: "Opština", align: "l", value: (r) => r.name, text: (r) => r.name },
      col("population", "Stanovništvo", (v) => fmtCell("int", v), "Procenjeni broj stanovnika, 2025."),
      col("wage_net", "Neto zarada", (v) => fmtCell("rsd", v), "Prosečna neto zarada u RSD mesečno, 2025."),
      col("unemployment", "Nezaposlenost", (v) => fmtCell("pct", v), "Stopa nezaposlenosti, Popis 2022."),
      col("age65", "Stariji od 65", (v) => fmtCell("pct", v), "Udeo stanovništva starog 65 i više godina, 2025."),
      col("life_expectancy", "Trajanje života", (v) => fmtCell("float", v), "Očekivano trajanje života pri rođenju, 2025."),
    ],
    onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
    onClick: (r) => counties.focus(r),
  });

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["rzs_db", "census", "boundaries"], [
    NULL_NOTE,
    KIM_NOTE,
    BEOGRAD_NOTE,
    NOVI_SAD_OPSTINA_NOTE,
    "Tabla o stanovanju (deo troškova stanovanja u prihodima domaćinstava, vrednost stanova, pregrejavanje) izostavljena je: za Srbiju ti podaci po opštinama nisu javno objavljeni.",
    "Vrednosti na vrhu table su vrednosti za Republiku Srbiju iz nacionalnog bloka podataka (bez Kosova i Metohije); „× prosek“ je odnos jedinice prema toj vrednosti.",
    ...(data.countiesOffMap ? [offMapNote(data)] : []),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      table.setHot(r ? r.key : null, false);
      hist.setHot(r ? hist.binOf(r.v.wage_net)?.i ?? null : null);
    },
    onEscape() {
      if (scatter.selected || hInfo.childNodes.length) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; hInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
