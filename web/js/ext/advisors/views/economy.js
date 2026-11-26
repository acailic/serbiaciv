// Ekonomija: BDP po okruzima i gradovima, BDP po stanovniku, rast prema proizvodnji, i specijalizacija:
// u kojim delatnostima (NACE odeljci, Popis 2022) je koji kraj natprosečno zastupljen.
import { fin, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { pct, int, signedPct, count3, fmtShort, fmtValue } from "../core/fmt.js";
import { barList, stackedBars, rampLegend } from "../core/charts.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, selectBox, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight, NACE_KEYS, NACE_LABEL, METRO_MIN } from "../core/data.js";
import { stateLens, growthLens } from "../core/lenses.js";
import { NULL_NOTE, KIM_NOTE, JUZNOBACKI_GDP_NOTE, JUZNOBACKI_NOTE, BEOGRAD_NOTE } from "../core/notes.js";

// The 19 NACE sections in nine groups the stacked bars can carry.
export const JOB_GROUPS = [
  { key: "agri", label: "Poljoprivreda", keys: ["agriculture"], color: "#8fb04e" },
  { key: "industry", label: "Industrija i energetika", keys: ["mining", "manufacturing", "energy", "water_waste"], color: "#d9823b" },
  { key: "construction", label: "Građevinarstvo", keys: ["construction"], color: "#c9a45c" },
  { key: "trade_transport", label: "Trgovina i saobraćaj", keys: ["trade", "transport"], color: "#4a86d6" },
  { key: "hospitality", label: "Ugostiteljstvo", keys: ["accommodation"], color: "#e0a0a8" },
  { key: "info_finance", label: "Informisanje i finansije", keys: ["information", "finance", "real_estate"], color: "#2fa4b8" },
  { key: "professional", label: "Stručne i administrativne delatnosti", keys: ["professional", "admin"], color: "#9a7bc9" },
  { key: "public", label: "Uprava, obrazovanje i zdravstvo", keys: ["public_admin", "education", "health"], color: "#c25b9a" },
  { key: "other", label: "Kultura i ostale usluge", keys: ["arts", "other"], color: "#9aa3ad" },
];

/** Share of a unit's employed residents working in one NACE section; null without a complete jobs block. */
export const jobShare = (r, k) => (fin(r?.v?.[`jobs_${k}`]) && fin(r?.v?.jobs_total) && r.v.jobs_total > 0 ? r.v[`jobs_${k}`] / r.v.jobs_total : null);

/** National share of each NACE section: the sum of the section over the sum of all jobs, over rows with complete blocks. */
export function nationalShares(rows) {
  const acc = {}, out = {};
  let tot = 0;
  for (const r of rows) {
    if (!fin(r?.v?.jobs_total)) continue;
    tot += r.v.jobs_total;
    for (const k of NACE_KEYS) acc[k] = (acc[k] ?? 0) + (fin(r.v[`jobs_${k}`]) ? r.v[`jobs_${k}`] : 0);
  }
  for (const k of NACE_KEYS) out[k] = tot > 0 ? acc[k] / tot : null;
  return out;
}

/** Location quotient: how many times more concentrated a section is in the unit than in the nation (1 = as average). */
export const lq = (r, k, nat) => {
  const a = jobShare(r, k), b = nat?.[k];
  return fin(a) && fin(b) && b > 0 ? a / b : null;
};

/** A row's jobs grouped for the stacked bars (shares of the unit's jobs; null without a complete block). */
export function groupShares(r) {
  const out = {};
  for (const g of JOB_GROUPS) {
    let s = null;
    for (const k of g.keys) { const x = jobShare(r, k); if (fin(x)) s = (s ?? 0) + x; }
    out[g.key] = s;
  }
  return out;
}

const GOLD_RAMP = ["#f3e9c6", "#e6cf85", "#d4b056", "#c09a3a", "#9a7524", "#6b4e12"];

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nation;
  const { states, metros } = data.levels;
  const nat = nationalShares(states.rows);
  const industryNames = data.industries ?? NACE_LABEL;

  const gdpRows = states.rows.filter((r) => fin(r.v.gdp));
  const top = topBy(gdpRows, (r) => r.v.gdp, { n: 1 })[0]?.r ?? null;
  el.insertAdjacentHTML("beforeend", tiles([
    { label: "BDP Srbije", value: fmtValue("eur", n.v.gdp), sub: fin(n.v.gdp) ? "zbir okruga, bez Kosova i Metohije" : "nema procene", color: "#c9a43a" },
    { label: "BDP po stanovniku", value: fmtValue("eur", n.v.gdp_pc), sub: fin(n.v.gdp_pc) ? "BDP ÷ procena stanovništva" : "nema procene" },
    { label: "Najveća ekonomija", value: top ? top.name : "–", sub: top && fin(n.v.gdp) ? `${pct(top.v.gdp / n.v.gdp)} BDP-a Srbije` : "", color: "#d9823b" },
    { label: "Zaposleni", value: fmtValue("int", n.v.employed), sub: "prema prebivalištu, Popis 2022." },
  ]));

  // --- map ---------------------------------------------------------------------------------------------------------
  let spec = NACE_KEYS.includes(ctx.params.industry) ? ctx.params.industry : "manufacturing";
  const specLens = () => stateLens(data, `lq-${spec}`, (r) => lq(r, spec, nat), { name: `Specijalizacija: ${industryNames[spec] ?? NACE_LABEL[spec]}`, unit: " puta više od proseka", format: "float", domain: [0, 3], ramp: RAMPS.seq, group: "work", icon: "l-manufacturing", emoji: "🏭",
    description: `Koliko je puta udeo zaposlenih u delatnosti „${industryNames[spec] ?? NACE_LABEL[spec]}“ među zaposlenim stanovnicima okruga veći od udela te delatnosti u celoj Srbiji (1 = kao prosek). Prema prebivalištu, Popis 2022.`, source: "census", note: KIM_NOTE });
  const gdpLens = () => stateLens(data, "gdp", (r) => r.v.gdp, { name: "BDP po okruzima", unit: "€", format: "eur", ramp: GOLD_RAMP, group: "work", icon: "l-wages", emoji: "💰",
    description: "Bruto domaći proizvod okruga u tekućim evrima, tamo gde se obavlja rad (Eurostat, BDP po oblastima, 2023).", source: "gdp", note: KIM_NOTE });
  const pcLens = () => stateLens(data, "gdp-pc", (r) => r.v.gdp_pc, { name: "BDP po stanovniku", unit: "€", format: "eur", ramp: GOLD_RAMP, group: "work", icon: "l-wages", emoji: "💰",
    description: "Bruto domaći proizvod okruga po stanovniku (Eurostat, BDP po oblastima, 2023; procena stanovništva 2025).", source: "gdp", note: `${KIM_NOTE} Za Južnobački okrug nema procene stanovništva, pa nema ni BDP-a po stanovniku.` });
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "gdp",
    options: [
      { value: "gdp", label: "BDP", lens: gdpLens },
      { value: "pc", label: "BDP po stanovniku", lens: pcLens },
      { value: "growth", label: "Promena", lens: () => growthLens(data, "states") },
      { value: "spec", label: "Specijalizacija", lens: specLens },
    ],
  });

  // --- largest economies -------------------------------------------------------------------------------------------
  let eLevel = "states";
  const eBody = section(el, { title: "Najveće ekonomije", note: `BDP u tekućim evrima, tamo gde se obavlja rad (Eurostat, 2023). Za grad je to procena: BDP okruga podeljen prema udelu grada u zaposlenima okruga. Gradovi od ${count3(METRO_MIN)} stanovnika.` });
  const eHost = document.createElement("div");
  segmented(eBody, { label: "Podela", value: eLevel, options: [{ value: "states", label: "Okrug" }, { value: "metros", label: "Grad" }], onChange: (v) => { eLevel = v; drawGdp(); } });
  eBody.appendChild(eHost);
  let gdp = null;
  function drawGdp() {
    gdp?.el.remove();
    const lv = eLevel === "states" ? states : metros;
    const rows = topBy(lv.rows, (r) => r.v.gdp, { n: eLevel === "states" ? 12 : 14, min: eLevel === "metros" ? METRO_MIN : 0 });
    const max = rows[0]?.v ?? 1;
    gdp = barList(eHost, {
      rows: rows.map((x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", value: x.v, text: `${fmtShort("eur", x.v)} · ${fin(n.v.gdp) && n.v.gdp > 0 ? pct(x.v / n.v.gdp, 0) : ""}`, color: "#c9a43a", row: x.r })),
      max, ariaLabel: "BDP po jedinicama",
      onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null),
      onClick: (r) => lv.focus(r.row),
    });
  }
  drawGdp();

  // --- GDP per capita ----------------------------------------------------------------------------------------------
  let pLevel = "states";
  const pBody = section(el, { title: "BDP po stanovniku", note: "BDP podeljen procenjenim brojem stanovnika: najbogatiji i najsiromašniji okruzi, odnosno gradovi, u evrima po stanovniku." });
  const pHost = document.createElement("div");
  segmented(pBody, { label: "Podela", value: pLevel, options: [{ value: "states", label: "Okrug" }, { value: "metros", label: "Grad" }], onChange: (v) => { pLevel = v; drawPc(); } });
  pBody.appendChild(pHost);
  const pcColor = colorScale({ type: "seq", domain: [0.5, 1.5], ramp: GOLD_RAMP });
  function drawPc() {
    pHost.innerHTML = "";
    const lv = pLevel === "states" ? states : metros;
    const rows = lv.rows.filter((r) => fin(r.v.gdp_pc) && (pLevel === "states" || (r.v.population ?? 0) >= METRO_MIN));
    const hi = topBy(rows, (r) => r.v.gdp_pc, { n: 8 });
    const lo = topBy(rows, (r) => r.v.gdp_pc, { n: 8, asc: true });
    const max = hi[0]?.v ?? 1;
    const ref = fin(n.v.gdp_pc) && n.v.gdp_pc > 0 ? n.v.gdp_pc : 1;
    const mk = (x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", value: x.v, text: `${fmtValue("eur", x.v)} · ${fmtShort("float", x.v / ref)}× prosek`, color: pcColor(x.v / ref), row: x.r });
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null), onClick: (r) => lv.focus(r.row) };
    pHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najviši</h4>`);
    barList(pHost, { ...o, rows: hi.map(mk), ariaLabel: "Najviši BDP po stanovniku" });
    pHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najniži</h4>`);
    barList(pHost, { ...o, rows: lo.map(mk), ariaLabel: "Najniži BDP po stanovniku" });
  }
  drawPc();

  // --- growth vs. output -------------------------------------------------------------------------------------------
  const gBody = section(el, { title: "Rast i proizvodnja", note: `Svaka tačka je grad od ${count3(METRO_MIN)} stanovnika: BDP po stanovniku horizontalno, ${metros.field("growth").label.toLowerCase()} uspravno, veličina = stanovništvo, boja = stopa nezaposlenosti. Prevucite pravougaonik da izaberete gradove.` });
  const unDom = robustDomain(metros.rows.map((r) => r.v.unemployment), 0.05) || [0.05, 0.3];
  const unColor = colorScale({ type: "seq", domain: unDom, ramp: RAMPS.heat });
  const mRows = metros.rows.filter((r) => (r.v.population ?? 0) >= METRO_MIN);
  const scatter = createScatter(gBody, {
    height: 300,
    points: mRows.map((r) => ({ key: r.key, x: r.v.gdp_pc, y: r.v.growth, s: r.v.population, c: r.v.unemployment, label: r.name, sub: r.sub, row: r })),
    x: { label: "BDP po stanovniku", fmt: (v) => fmtShort("eur", v) },
    y: { label: metros.field("growth").label, fmt: (v) => signedPct(v) },
    size: { label: "Stanovništvo", fmt: count3, max: 13, min: 2 },
    color: (c) => (fin(c) ? unColor(c) : "#8a8378"),
    refY: [{ v: 0, label: "bez promene" }],
    labels: topBy(mRows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    onHover: (p) => link.hover(p ? rowsHighlight(metros, [p.row]) : null),
    onClick: (p) => metros.focus(p.row),
    onBrush: (set) => {
      const sel = set ? mRows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(metros, sel, { dim: true }) : null, { frame: sel.length > 1 });
      selInfo.innerHTML = sel.length ? `<b>${int(sel.length)}</b> gradova · ${count3(sel.reduce((a, r) => a + (r.v.population ?? 0), 0))} stanovnika ${frameBtn()}<button type="button" class="adv-mini" data-clear>Očisti</button>` : "";
    },
  });
  gBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.heat, domain: unDom, fmt: (v) => fmtShort("pct", v), label: "Stopa nezaposlenosti" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  gBody.appendChild(selInfo);
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; } });

  // --- who works in what -------------------------------------------------------------------------------------------
  const jBody = section(el, { title: "Ko radi u čemu", note: "Zaposleni stanovnici po devet grupama delatnosti (NACE odeljci, Popis 2022.): šesnaest okruga sa najvećim BDP-om ili gradova sa najviše stanovnika." });
  let jLevel = "states";
  const jHost = document.createElement("div");
  segmented(jBody, { label: "Podela", value: jLevel, options: [{ value: "states", label: "Okrug" }, { value: "metros", label: "Grad" }], onChange: (v) => { jLevel = v; drawJobs(); } });
  jBody.appendChild(jHost);
  jBody.insertAdjacentHTML("beforeend", `<div class="adv-legend sw">${JOB_GROUPS.map((g) => `<span class="it"><i style="background:${g.color}"></i>${g.label}</span>`).join("")}</div>`);
  let jobs = null;
  function drawJobs() {
    jobs?.el.remove();
    const lv = jLevel === "states" ? states : metros;
    const rows = (jLevel === "states" ? topBy(lv.rows, (r) => r.v.gdp, { n: 16 }) : topBy(lv.rows, (r) => r.v.population, { n: 16 })).map((x) => x.r);
    jobs = stackedBars(jHost, {
      keys: JOB_GROUPS.map((g) => ({ key: g.key, label: g.label, color: g.color })), normalize: true, ariaLabel: "Zaposleni po grupama delatnosti",
      fmt: (v) => pct(v),
      rows: rows.map((r) => ({ key: r.key, label: r.name, sub: r.sub !== r.name ? r.sub : "", parts: groupShares(r), text: r.v.jobs_total != null ? `${count3(r.v.jobs_total)} zaposlenih` : "Nema podataka" })),
      onHover: (x) => link.hover(x?.row ? rowsHighlight(lv, [x.row]) : null),
      onClick: (x) => x?.row && lv.focus(x.row),
    });
  }
  drawJobs();

  // --- specialisation ----------------------------------------------------------------------------------------------
  const sBody = section(el, { title: "Specijalizacija", note: "Koliko je puta udeo jedne delatnosti među zaposlenim stanovnicima okruga veći od udela te delatnosti u celoj Srbiji (1 = kao prosek). Birajte delatnost; kliknite na red da otvorite okrug." });
  const sCtl = document.createElement("div");
  sCtl.className = "adv-row";
  sBody.appendChild(sCtl);
  selectBox(sCtl, { label: "Delatnost", value: spec, options: NACE_KEYS.map((k) => ({ value: k, label: industryNames[k] ?? NACE_LABEL[k] })), onChange: (v) => { spec = v; drawSpec(); if (picker.value === "spec") picker.refresh(); } });
  const mapBtn = document.createElement("button");
  mapBtn.type = "button";
  mapBtn.className = "adv-mini";
  mapBtn.textContent = "Oboji kartu po ovoj delatnosti";
  mapBtn.addEventListener("click", () => picker.set("spec"));
  sCtl.appendChild(mapBtn);
  const sHost = document.createElement("div");
  sBody.appendChild(sHost);
  function drawSpec() {
    sHost.innerHTML = "";
    const lv = states;
    const hi = topBy(lv.rows, (r) => lq(r, spec, nat), { n: 8 });
    const lo = topBy(lv.rows, (r) => lq(r, spec, nat), { n: 8, asc: true });
    const max = Math.max(1, ...hi.map((x) => x.v));
    const mk = (x) => ({ key: x.r.key, label: x.r.name, sub: `${pct(jobShare(x.r, spec))} zaposlenih`, value: x.v, text: `${fmtShort("float", x.v)}×`, color: "#c9a43a", row: x.r });
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null), onClick: (r) => lv.focus(r.row) };
    sHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najviše koncentrisano</h4>`);
    barList(sHost, { ...o, rows: hi.map(mk), ariaLabel: "Najveća specijalizacija" });
    sHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najmanje zastupljeno</h4>`);
    barList(sHost, { ...o, rows: lo.map(mk), ariaLabel: "Najmanja specijalizacija" });
  }
  drawSpec();

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["gdp", "census", "rzs_db", "boundaries"], [
    NULL_NOTE,
    KIM_NOTE,
    JUZNOBACKI_GDP_NOTE,
    JUZNOBACKI_NOTE,
    BEOGRAD_NOTE,
    "BDP se meri tamo gde se obavlja rad, a zaposleni prema prebivalištu: okrug u kom mnogo ljudi radi, a drugde stanuje, ima veći BDP nego što bi se videlo po broju stanovnika.",
    "BDP po stanovniku okruga koristi procenu stanovništva okruga za 2025. godinu; BDP grada je procena podeljena prema udelu grada u zaposlenima okruga, pa zbir gradova jednog okruga daje BDP okruga.",
    "Struktura zaposlenih i specijalizacija računaju se po prebivalištu zaposlenih (Popis 2022.), ne po mestu rada.",
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? metros.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
    },
    onEscape() {
      if (scatter.selected) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
