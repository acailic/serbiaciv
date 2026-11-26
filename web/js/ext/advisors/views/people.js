// Stanovništvo: population, change, density, age, natural increase and life expectancy of Serbia's opštine, okruzi and gradovi.
import { esc, fin, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { pct, int, signedPct, count3, fmtShort } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight, METRO_MIN } from "../core/data.js";
import { growthLens } from "../core/lenses.js";
import { peopleCaveats } from "../core/notes.js";

const medianOf = (rows, k) => {
  const s = rows.map((r) => r.v[k]).filter(fin).sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : null;
};

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nation;
  const { states, metros, counties } = data.levels;

  const cRows = counties.rows;
  const withGrowth = cRows.filter((r) => fin(r.v.growth));
  const growing = withGrowth.filter((r) => r.v.growth > 0).length;
  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Stanovništvo", value: count3(n.v.population), sub: n.populationIsSum ? "zbir opština, bez Kosova i Metohije" : data.vintage },
    { label: "Opštine koje rastu", value: `${int(growing)} od ${int(withGrowth.length)}`, sub: "procena 2025. prema 2015." },
    { label: "Gradovi", value: int(metros.rows.length), sub: `${int(states.rows.length)} okruga · ${int(cRows.length)} opština` },
  ]));

  // --- the map: change by default, so the map tells the same story as the first chart --------------------------------
  let gLevel = "metros";
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "growth",
    options: [
      { value: "growth", label: "Promena", lens: () => growthLens(data, gLevel) },
      { value: "density", label: "Gustina", lens: () => "density" },
      { value: "age65", label: "Stariji od 65", lens: () => "age65" },
      { value: "natural_increase", label: "Prirodni priraštaj", lens: () => "natural_increase" },
      { value: "life_expectancy", label: "Trajanje života", lens: () => "life_expectancy" },
      { value: "terrain", label: "Teren", lens: () => null },
    ],
  });

  // --- change ------------------------------------------------------------------------------------------------------
  const gLabel = metros.field("growth").label;
  const gBody = section(el, { title: "Ko raste, a ko se smanjuje", note: `${gLabel}: gradovi od ${count3(METRO_MIN)} stanovnika ili okruzi. Po opštinama se promena meri za drugi period (od 2015. do 2025. godine), pa opštine nisu u ovom poretku.` });
  const gHost = document.createElement("div");
  segmented(gBody, { label: "Podela", value: gLevel, options: [{ value: "metros", label: "Gradovi" }, { value: "states", label: "Okrug" }], onChange: (v) => { gLevel = v; drawGrowth(); if (picker.value === "growth") picker.refresh(); } });
  gBody.appendChild(gHost);
  function drawGrowth() {
    gHost.innerHTML = "";
    const lv = gLevel === "metros" ? metros : states;
    const min = gLevel === "metros" ? METRO_MIN : 0;
    const fast = topBy(lv.rows, (r) => r.v.growth, { n: 8, min });
    const slow = topBy(lv.rows, (r) => r.v.growth, { n: 8, min, asc: true });
    const max = Math.max(...[...fast, ...slow].map((x) => Math.abs(x.v)));
    const mk = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: gLevel === "metros" ? x.r.sub : "", value: x.v, text: signedPct(x.v), tone: x.v >= 0 ? "good" : "bad", row: x.r }));
    const opts = {
      diverging: true, max,
      onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null),
      onClick: (r) => lv.focus(r.row),
    };
    gHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najbrže rastu</h4>`);
    barList(gHost, { ...opts, rows: mk(fast), ariaLabel: "Najbrže rastući" });
    gHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${slow.every((x) => x.v < 0) ? "Najviše se smanjuju" : "Najsporije rastu"}</h4>`);
    barList(gHost, { ...opts, rows: mk(slow), ariaLabel: "Najsporije rastući" });
  }
  drawGrowth();

  // --- density -----------------------------------------------------------------------------------------------------
  const dBody = section(el, { title: "Koliko je gusto", note: "Opštine po broju stanovnika na km² (logaritamska skala). Prebacite na <i>stanovnike</i> da svaka opština teži koliko ljudi ima: većina stanovništva živi u gusto naseljenim opštinama. Postavite kursor na stubić da vidite te opštine; kliknite da ostanu označene." });
  const dCtl = document.createElement("div");
  dCtl.className = "adv-row";
  dBody.appendChild(dCtl);
  let weighted = false, pinnedBin = null;
  segmented(dCtl, { label: "Brojanje", value: "counties", options: [{ value: "counties", label: "Opštine" }, { value: "people", label: "Stanovnici" }], onChange: (v) => { weighted = v === "people"; drawHist(); } });
  const dLens = document.createElement("button");
  dLens.type = "button";
  dLens.className = "adv-mini";
  dLens.textContent = "Oboji kartu po gustini";
  dLens.addEventListener("click", () => picker.set("density"));
  dCtl.appendChild(dLens);
  const histHost = document.createElement("div");
  dBody.appendChild(histHost);
  const binInfo = document.createElement("div");
  binInfo.className = "adv-brushinfo";
  dBody.appendChild(binInfo);
  let hist = null;
  const rsPop = cRows.reduce((a, r) => a + (fin(r.v.population) ? r.v.population : 0), 0);
  const rsLand = cRows.reduce((a, r) => a + (fin(r.v.population) && fin(r.v.land_km2) ? r.v.land_km2 : 0), 0);
  const rsDensity = rsLand > 0 ? rsPop / rsLand : null;
  const cByKey = counties.byKey;
  const densRamp = RAMPS.heat;
  const densDom = robustDomain(cRows.map((r) => r.v.density), 0.02, true) || [10, 5000];
  function drawHist() {
    histHost.innerHTML = "";
    const vals = cRows.map((r) => ({ key: r.key, v: r.v.density, w: r.v.population }));
    hist = histogram(histHost, {
      values: vals, log: true, bins: 30, domain: densDom, weighted, height: 130,
      fmt: (v) => fmtShort("float", v), unitLabel: "opština", weightFmt: (w) => `${count3(w)} stanovnika`,
      label: "Histogram gustine naseljenosti opština",
      colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: densRamp })(t),
      markers: fin(rsDensity) ? [{ v: rsDensity, label: "prosek Srbije" }] : [],
      onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => cByKey.get(k)), { dim: true }) : null),
      onClick: (bin) => {
        pinnedBin = pinnedBin === bin.i ? null : bin.i;
        const rows = pinnedBin != null ? bin.keys.map((k) => cByKey.get(k)) : [];
        link.base(rows.length ? rowsHighlight(counties, rows, { dim: true }) : null, { frame: rows.length > 1 });
        binInfo.innerHTML = rows.length ? `<b>${int(rows.length)}</b> opština sa ${fmtShort("float", bin.x0)}–${fmtShort("float", bin.x1)} stanovnika/km² · ${count3(rows.reduce((a, r) => a + (fin(r.v.population) ? r.v.population : 0), 0))} stanovnika ${frameBtn()}<button type="button" class="adv-mini" data-clear>Očisti</button>` : "";
      },
    });
  }
  binInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { pinnedBin = null; link.base(null); binInfo.innerHTML = ""; } });
  drawHist();

  // --- age and natural increase ------------------------------------------------------------------------------------
  const aBody = section(el, { title: "Starost i prirodni priraštaj", note: "Svaka tačka je opština: udeo starijih od 65 godina horizontalno, prirodni priraštaj na 1.000 stanovnika uspravno, veličina = stanovništvo, boja = očekivano trajanje života. Prevucite pravougaonik da izaberete opštine; one se osvetle na karti. Pređite kursorom preko karte da nađete opštinu ovde." });
  const aCtl = document.createElement("div");
  aCtl.className = "adv-row";
  aBody.appendChild(aCtl);
  aCtl.innerHTML = `<span class="adv-note">Oboji kartu po</span><button type="button" class="adv-mini" data-map="age65">starima od 65</button><button type="button" class="adv-mini" data-map="natural_increase">prirodnom priraštaju</button><button type="button" class="adv-mini" data-map="life_expectancy">trajanju života</button>`;
  aCtl.addEventListener("click", (e) => { const v = e.target.closest("[data-map]")?.dataset.map; if (v) picker.set(v); });
  const leDom = robustDomain(cRows.map((r) => r.v.life_expectancy), 0.02) || [70, 80];
  const leColor = colorScale({ type: "seq", domain: leDom, ramp: RAMPS.gold });
  const big = topBy(cRows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key);
  const scatter = createScatter(aBody, {
    height: 310,
    points: cRows.map((r) => ({ key: r.key, x: r.v.age65, y: r.v.natural_increase, s: r.v.population, c: r.v.life_expectancy, label: r.name, sub: r.sub, row: r })),
    x: { label: "Stariji od 65 godina", fmt: (v) => fmtShort("pct", v) },
    y: { label: "Prirodni priraštaj na 1.000", fmt: (v) => fmtShort("float", v) },
    size: { label: "Stanovništvo", fmt: count3, max: 14, min: 1.4 },
    color: (c) => leColor(c), colorLabel: "Očekivano trajanje života", colorFmt: (v) => `${fmtShort("float", v)} god.`,
    labels: big,
    refX: fin(medianOf(cRows, "age65")) ? [{ v: medianOf(cRows, "age65"), label: "medijana opština" }] : [],
    refY: [{ v: 0, label: "nula" }],
    onHover: (p) => link.hover(p ? rowsHighlight(counties, [p.row]) : null),
    onClick: (p) => counties.focus(p.row),
    onBrush: (set) => {
      const sel = set ? cRows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(counties, sel, { dim: true }) : null, { frame: sel.length > 1 });
      selInfo.innerHTML = sel.length ? selSummary(sel) : "";
    },
  });
  aBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.gold, domain: leDom, fmt: (v) => `${fmtShort("float", v)} god.`, label: "Očekivano trajanje života" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  aBody.appendChild(selInfo);
  function selSummary(sel) {
    const pop = sel.reduce((a, r) => a + (fin(r.v.population) ? r.v.population : 0), 0);
    const top = [...sel].sort((a, b) => (b.v.population || 0) - (a.v.population || 0)).slice(0, 5);
    return `<b>${int(sel.length)}</b> opština · ${count3(pop)} stanovnika${fin(n.v.population) && n.v.population > 0 ? ` (${pct(pop / n.v.population)} Srbije)` : ""}<br><span class="sub">Najveće: ${top.map((r) => `${esc(r.name)}, ${esc(r.sub)}`).join(" · ")}</span> ${frameBtn()}<button type="button" class="adv-mini" data-clear>Očisti</button>`;
  }
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; } });

  // --- life expectancy ---------------------------------------------------------------------------------------------
  const lBody = section(el, { title: "Očekivano trajanje života", note: "Opštine sa najdužim i najkraćim očekivanim trajanjem života pri rođenju (sredina za muškarce i žene, 2025).", open: false });
  const lHost = document.createElement("div");
  lBody.appendChild(lHost);
  const lRows = cRows.filter((r) => fin(r.v.life_expectancy));
  const lTop = topBy(lRows, (r) => r.v.life_expectancy, { n: 8 });
  const lLow = topBy(lRows, (r) => r.v.life_expectancy, { n: 8, asc: true });
  const leRange = [Math.min(...lLow.map((x) => x.v)), Math.max(...lTop.map((x) => x.v))];
  const mkLe = (x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub, value: x.v, text: fmtShort("float", x.v), color: leColor(x.v), row: x.r });
  lHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najduže</h4>`);
  barList(lHost, { rows: lTop.map(mkLe), max: leRange[1], ariaLabel: "Najduže očekivano trajanje života", onHover: (r) => link.hover(r ? rowsHighlight(counties, [r.row]) : null), onClick: (r) => counties.focus(r.row) });
  lHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najkraće</h4>`);
  barList(lHost, { rows: lLow.map(mkLe), max: leRange[1], ariaLabel: "Najkraće očekivano trajanje života", onHover: (r) => link.hover(r ? rowsHighlight(counties, [r.row]) : null), onClick: (r) => counties.focus(r.row) });

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["rzs_db", "census", "boundaries"], [
    ...peopleCaveats(data),
    "Zbir stanovništva na vrhu je zbir opština za koje postoji procena (bez Kosova i Metohije); nacionalni zbir zavod ne objavljuje u ovoj izradi.",
    "Gustina po opštinama je procena podeljena površinom opštine; za okruge i gradove površina je zbir opština, odnosno površina hekseva koje jedinica zauzima na karti.",
    "Boja tačke je očekivano trajanje života opštine; sredina vrednosti za grupu opština nije prosek njihovih sredina.",
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      hist?.setHot(r ? hist.binOf(r.v.density)?.i ?? null : null);
    },
    onEscape() {
      if (scatter.selected || pinnedBin != null) {
        scatter.setSelected(null); pinnedBin = null; link.base(null); selInfo.innerHTML = ""; binInfo.innerHTML = "";
        return true;
      }
      return false;
    },
  };
}
