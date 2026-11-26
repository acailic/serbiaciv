// Kultura („Čuvar čuda“): čuda po objavljenim pravilima (wonders.json), veroispovest i narodnost po opštinama
// i gradovima (Popis 2022.) sa njihovim ogranicama iz lenses.json.
import { esc, fin, el as mk, colorScale, robustDomain } from "../core/util.js";
import { int, pct, count3 } from "../core/fmt.js";
import { barList, stackedBars, swatchLegend } from "../core/charts.js";
import { section, tiles, segmented, mapPicker, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { metroLens, builtInLens } from "../core/lenses.js";
import { NULL_NOTE, KIM_NOTE, offMapNote } from "../core/notes.js";
import { frameBox, focusPoint } from "../core/frame.js";

// wonders.json kinds (upstream contract): natural | university | landmark; Serbia's file keeps the same keys.
const KIND = {
  natural: { label: "Priroda", color: "#6aa84f" },
  university: { label: "Univerziteti", color: "#4a86d6" },
  landmark: { label: "Spomenici", color: "#e0b54c" },
};
const RULE_TITLE = { national_park: "Nacionalni parkovi", park_unit: "Ostala zaštićena područja", research_university: "Istraživački univerziteti", landmark: "Spomenici kulture", unesco: "Svetska baština UNESCO" };

/** The rule's heading: the file's own name when it has one, else the known id, else the id. */
export const ruleTitle = (rule) => rule?.name || rule?.label || RULE_TITLE[rule?.id] || rule?.id || "";

/** What a wonder is ranked by; "–" when the file carries no metric (nothing is invented). */
export function metricText(w) {
  const m = w?.metrics || {};
  if (fin(m.visits)) return `${count3(m.visits)} poseta`;
  if (fin(m.area_km2)) return `${count3(m.area_km2)} km²`;
  if (fin(m.students)) return `${count3(m.students)} studenata`;
  if (fin(m.designated)) return `spomenik od ${Math.round(m.designated)}.`; // a year: no thousands separator
  if (fin(m.rd_eur)) return `${count3(m.rd_eur)} € istraživanja`;
  return "–";
}

/** Shares of a block of a city (eth_* or rel_*): the named keys, then "ostalo" to 100 %. */
export function blockShares(r, prefix, keys) {
  const out = {};
  let s = 0;
  for (const k of keys) { const v = r?.v?.[`${prefix}_${k}`]; out[k] = fin(v) ? v : null; if (fin(v)) s += v; }
  out.other = s > 0 && s < 1 ? 1 - s : s > 0 ? 0 : null;
  return out;
}

const ETH = [
  { key: "srbi", label: "Srbi", color: "#c2463d" },
  { key: "madjari", label: "Mađari", color: "#4a86d6" },
  { key: "bosnjaci", label: "Bošnjaci", color: "#3f9c82" },
  { key: "romi", label: "Romi", color: "#d9823b" },
  { key: "other", label: "Ostali i neizjašnjeni", color: "#c8c2b8" },
];
const REL = [
  { key: "orthodox", label: "Pravoslavni", color: "#c2463d" },
  { key: "catholic", label: "Katolici", color: "#4a86d6" },
  { key: "muslim", label: "Muslimani", color: "#3f9c82" },
  { key: "protestant", label: "Protestanti", color: "#d9823b" },
  { key: "nonbeliever", label: "Nevernici", color: "#9aa3ad" },
  { key: "other", label: "Ostali i neizjašnjeni", color: "#e4dfd5" },
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

export async function mount(ctx) {
  const { app, data, el, link } = ctx;
  const won = await app.loadData?.("wonders").catch(() => null); // lazy: only this advisor needs it
  const { states: stLevel, metros, counties } = data.levels;
  const lensOrth = builtInLens(data, "orthodox"), lensSerbs = builtInLens(data, "serbs");

  // --- headline -------------------------------------------------------------------------------------------------
  const wonders = (won?.wonders || []).map((w) => ({ ...w, key: w.id }));
  const byKind = (k) => wonders.filter((w) => w.kind === k).length;
  const byRule = (...ids) => wonders.filter((w) => ids.includes(w.rule)).length;
  const rules = won?.rules || [];
  const cRows = counties.rows;
  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Pravoslavni", value: pct(weightedShare(cRows, "orthodox")), sub: "stanovništvo opština, Popis 2022.", color: "#c2463d" },
    { label: "Srbi", value: pct(weightedShare(cRows, "serbs")), sub: "stanovništvo opština, Popis 2022.", color: "#4a86d6" },
    { label: "Čuda", value: won ? int(wonders.length) : "–", sub: won ? `${byRule("national_park", "park_unit")} zaštićenih područja · ${byKind("landmark")} spomenika · ${byKind("university")} univerziteta` : "datoteka wonders.json nije učitana" },
    { label: "Mađari", value: pct(topBy(metros.rows, (r) => r.v.eth_madjari, { n: 1 })[0]?.v), sub: `najviši udeo među gradovima (${topBy(metros.rows, (r) => r.v.eth_madjari, { n: 1 })[0]?.r.name ?? "nema podataka"}), Popis 2022.`, color: "#4a86d6" },
  ]));

  // --- map colour -----------------------------------------------------------------------------------------------
  const mapRow = mk("div", "adv-sec adv-mapsec");
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "terrain",
    options: [
      { value: "terrain", label: "Teren", lens: () => null },
      { value: "orthodox", label: "Pravoslavni", lens: () => "orthodox" },
      { value: "serbs", label: "Srbi", lens: () => "serbs" },
      { value: "catholic", label: "Katolici (gradovi)", lens: () => metroLens(data, "rel-catholic", (r) => r.v.rel_catholic, { name: "Katolici po gradovima", unit: "%", format: "pct", group: "identity", icon: "l-orthodox", emoji: "⛪", description: "Udeo katolika u ukupnom stanovništvu grada, Popis 2022. Sivi heksovi su van gradova.", source: "census", note: "Za Kosovo i Metohiju nema podataka." }) },
    ],
  });

  // --- čuda -----------------------------------------------------------------------------------------------------
  let wonderBars = [];
  const bubbles = ctx.bubbles("wonders", {
    rMax: 9, minR: 9, alpha: 0.28,
    tip: (b) => `<b>${esc(b.it.name)}</b><br>${esc(ruleTitle(rules.find((r) => r.id === b.it.rule)))}${fin(b.it.rank) ? ` · ${int(b.it.rank)}. po pravilu` : ""}${b.it.curated ? " · izbor urednika, ne po podacima" : ""}`,
    onHover: (b) => { for (const w of wonderBars) w.setHot(b ? b.key : null); },
    onClick: (b) => flyTo(b.it),
  });
  function flyTo(w) {
    if (!w) return;
    if (w.cells && w.cells.length > 2) {
      const b = app.highlightBounds({ cells: new Set(w.cells) });
      if (b) return frameBox(app, b, { pad: 60, maxScale: 13 });
    }
    if (!fin(w.x) || !fin(w.y)) return;
    focusPoint(app, w.x, w.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3.2)));
  }
  if (won && wonders.length) {
    const wBody = section(el, { title: "Čuda", kicker: "Svako izabrano po objavljenom pravilu", note: "Postavite kursor na čudo da ga nađete na karti; kliknite da preletite do njega. Redosled unutar pravila prati merilo koje pravilo navodi; gde merila nema, čudo je izbor urednika i nema rang." });
    let kind = "all";
    segmented(wBody, {
      label: "Vrsta", value: kind,
      options: [{ value: "all", label: "Sva" }, ...Object.entries(KIND).filter(([k]) => byKind(k)).map(([k, v]) => ({ value: k, label: v.label }))],
      onChange: (v) => { kind = v; drawWonders(); },
    });
    const wHost = mk("div");
    wBody.appendChild(wHost);
    function drawWonders() {
      wHost.innerHTML = "";
      wonderBars = [];
      const vis = wonders.filter((w) => kind === "all" || w.kind === kind);
      for (const rule of rules) {
        const list = vis.filter((w) => w.rule === rule.id);
        if (!list.length) continue;
        wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${esc(ruleTitle(rule))}</h4>${rule.text ? `<p class="adv-note adv-rule">${esc(rule.text)}</p>` : ""}`);
        const host = mk("div");
        wHost.appendChild(host);
        wonderBars.push(barList(host, {
          rank: !rule.curated, compact: true, ariaLabel: ruleTitle(rule),
          rows: list.map((w) => ({ key: w.key, label: w.short || w.name, full: w.name, sub: w.state || "", value: fin(w.rank) ? -w.rank : null, text: metricText(w), color: KIND[w.kind]?.color })),
          onHover: (r) => {
            const w = r ? wonders.find((x) => x.key === r.key) : null;
            link.hover(w ? { cells: new Set(w.cells && w.cells.length ? w.cells : w.cell != null ? [w.cell] : []), label: w.short || w.name } : null);
            bubbles.setHot(w ? w.key : null);
          },
          onClick: (r) => flyTo(wonders.find((x) => x.key === r.key)),
        }));
      }
      bubbles.set(vis.filter((w) => fin(w.x) && fin(w.y)).map((w) => ({ key: w.key, x: w.x, y: w.y, value: 1, color: KIND[w.kind]?.color || "#ccc", it: w })), { vMax: 1 });
    }
    drawWonders();
    wBody.insertAdjacentHTML("beforeend", `<p class="adv-note">Oznake na karti: ${Object.entries(KIND).filter(([k]) => byKind(k)).map(([k, v]) => `<i class="dot" style="background:${v.color}"></i>${v.label.toLowerCase()}`).join(" · ")}</p>`);
  } else {
    el.insertAdjacentHTML("beforeend", `<section class="adv-sec"><h3>Čuda</h3><p class="adv-empty pad">Datoteka wonders.json još nije uključena: nacionalni parkovi, svetska baština i spomenici kulture biće dodati iz nje, po objavljenim pravilima.</p></section>`);
  }

  // --- vera i narodnost ------------------------------------------------------------------------------------------
  const orthLens = builtInLens(data, "orthodox");
  const serbsLens = builtInLens(data, "serbs");
  const idBody = section(el, { title: "Vera i narodnost", kicker: "Popis 2022.", note: "Udeo pravoslavnih, odnosno Srba, u ukupnom stanovništvu opštine (ili grada): osam jedinica sa najvišim i osam sa najnižim udelom. Kliknite na red da otvorite jedinicu." });
  for (const l of [orthLens, serbsLens]) if (l?.note) idBody.insertAdjacentHTML("beforeend", `<p class="adv-callout adv-caveat">${esc(l.name)}: ${esc(l.note)}</p>`);
  let idKey = "orthodox", idLevel = "counties", idBars = [];
  const idCtl = mk("div", "adv-row");
  idBody.appendChild(idCtl);
  segmented(idCtl, { label: "Mera", value: idKey, options: [{ value: "orthodox", label: "Pravoslavni" }, { value: "serbs", label: "Srbi" }], onChange: (v) => { idKey = v; drawIdentity(); } });
  segmented(idCtl, { label: "Podela", value: idLevel, options: [{ value: "counties", label: "Opština" }, { value: "metros", label: "Grad" }], onChange: (v) => { idLevel = v; drawIdentity(); } });
  const idHost = mk("div");
  idBody.appendChild(idHost);
  const idColor = (k, v) => colorScale({ type: "seq", domain: robustDomain(cRows.map((r) => r.v[k]), 0.02) || [0.5, 1], ramp: k === "orthodox" ? ["#f6e9e4", "#e8b8a8", "#d98872", "#c2463d", "#8a2a26"] : ["#e8eef7", "#b9cde8", "#7fa9d0", "#4a86d6", "#1d4e8f"] })(v);
  function drawIdentity() {
    idHost.innerHTML = "";
    const lv = idLevel === "counties" ? counties : metros;
    const key = idKey === "orthodox" && idLevel === "metros" ? "rel_orthodox" : idKey === "serbs" && idLevel === "metros" ? "eth_srbi" : idKey;
    const rows = lv.rows.filter((r) => fin(r.v[key]));
    const hi = topBy(rows, (r) => r.v[key], { n: 8 });
    const lo = topBy(rows, (r) => r.v[key], { n: 8, asc: true });
    const mkRow = (x) => ({ key: x.r.key, label: x.r.name, sub: x.r.sub !== x.r.name ? x.r.sub : "", value: x.v, text: pct(x.v), color: idColor(key, x.v), row: x.r });
    const o = { max: 1, onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null), onClick: (r) => lv.focus(r.row) };
    idHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najviši udeo</h4>`);
    idBars = [barList(idHost, { ...o, rows: hi.map(mkRow), ariaLabel: "Najviši udeo" })];
    idHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Najniži udeo</h4>`);
    idBars.push(barList(idHost, { ...o, rows: lo.map(mkRow), ariaLabel: "Najniži udeo" }));
  }
  drawIdentity();

  // --- composition of the cities ----------------------------------------------------------------------------------
  const big = topBy(metros.rows, (r) => r.v.population, { n: 16 }).map((x) => x.r);
  const stack = (title, note, parts, prefix, keys, colorOf) => {
    const body = section(el, { title, note, open: false });
    body.insertAdjacentHTML("beforeend", swatchLegend(keys));
    stackedBars(body, {
      keys: keys.map((g) => ({ key: g.key, label: g.label, color: g.color })), normalize: true, ariaLabel: title, fmt: (v) => pct(v),
      rows: big.map((r) => { const p = blockShares(r, prefix, keys.map((g) => g.key).filter((k) => k !== "other")); return { key: r.key, label: r.name, sub: r.sub !== r.name ? r.sub : "", parts: p, text: pct(p[colorOf]), row: r }; }),
      onHover: (x) => link.hover(x?.row ? rowsHighlight(metros, [x.row]) : null),
      onClick: (x) => x?.row && metros.focus(x.row),
    });
  };
  stack("Narodnost gradova", "Stanovništvo po narodnosti (Popis 2022.) za šesnaest gradova sa najviše stanovnika. Popisni blok narodnosti postoji samo za gradove.", ETH, "eth", ETH, "srbi");
  stack("Veroispovest gradova", "Stanovništvo po veroispovesti (Popis 2022.) za šesnaest gradova sa najviše stanovnika. Popisni blok veroispovesti postoji samo za gradove.", REL, "rel", REL, "orthodox");

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["census", "boundaries"], [
    NULL_NOTE,
    KIM_NOTE,
    "Veroispovest i narodnost su izjašnjavanje stanovništva na Popisu 2022.; „ostali i neizjašnjeni“ obuhvata sve ostale odgovore, nepoznate i one koji se nisu izjasnili.",
    "Tabla o nesrećama (proglašene elementarne nepogode, poplave, šteta) izostavljena je: za Srbiju nema javnih podataka o nesrećama po opštinama.",
    ...(won ? [] : ["Čuda (nacionalni parkovi, svetska baština, spomenici kulture) biće dodata iz datoteke wonders.json po objavljenim pravilima; gde pravilo nema merilo, čudo se ne rangira."]),
    ...(data.countiesOffMap ? [offMapNote(data)] : []),
  ]));

  return {
    onMapHover(h) {
      const c = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      for (const b of idBars) b.setHot(c ? c.key : null, false);
      if (h.item?.kind === "wonder") for (const w of wonderBars) w.setHot(h.item.data?.id ?? null);
    },
    onMapClick(ev) {
      if (ev.item?.kind !== "wonder") return false;
      flyTo(wonders.find((w) => w.id === ev.item.data?.id));
      return true;
    },
  };
}
