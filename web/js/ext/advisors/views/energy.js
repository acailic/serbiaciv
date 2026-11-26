// Energija i resursi: elektrane i rudnici sa karte (resources.json), po vrsti i po okrugu.
import { esc, fin } from "../core/util.js";
import { fmtValue, mw, int, count3 } from "../core/fmt.js";
import { barList, shareBar, stackedBars, sizeLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, chips, sourcesHtml } from "../core/view.js";
import { frameBox, focusPoint } from "../core/frame.js";
import { glyph } from "../../../ui/icon.js";
import { NULL_NOTE, KIM_NOTE } from "../core/notes.js";

// Vrste resursa (ids as in resources.json / upstream), grouped for the chips; types the groups do not list go to "other".
export const GROUPS = [
  { id: "thermal", label: "Termoenergetika i nuklearna", types: ["nuclear", "coal_plant", "gas_plant", "geothermal"] },
  { id: "water", label: "Hidroelektrane", types: ["hydro", "pumped_storage"] },
  { id: "renew", label: "Vetar, sunce i baterije", types: ["wind", "solar", "battery"] },
  { id: "mines", label: "Rudnici", types: ["coal_mine", "gold", "copper", "iron", "silver", "platinum", "molybdenum", "lead_zinc", "rare_earths", "uranium", "lithium", "bauxite", "salt", "quartz", "clay", "gravel", "stone"] },
  { id: "plays", label: "Nafta i gas", types: ["oil", "gas"] },
];

/** Text for a site's size in the type's own unit; "–" when the file carries none. */
export function sizeText(r, typeById) {
  const t = typeById.get(r.type);
  if (!fin(r.value)) return "–";
  if (t?.unit === "MW") return mw(r.value);
  if (t?.unit === "employees") return `${int(r.value)} zaposlenih`;
  if (/^(tons|t\/)/.test(t?.unit || "")) return `${count3(r.value)} t godišnje`;
  if (/km/.test(t?.unit || "")) return `${count3(r.value)} km²`;
  return fmtValue("float", r.value);
}

/** Mapped capacity (MW) per okrug from the items; null for okruzi without a mapped MW site. */
export function powerByState(items, stateIndexOf, mwTypes) {
  const by = new Map();
  for (const it of items) {
    const t = mwTypes.has(it.type);
    if (!t || !fin(it.value)) continue;
    const si = stateIndexOf(it);
    if (si == null) continue;
    const cur = by.get(si) || { total: 0, by_type: {}, n: 0 };
    cur.total += it.value;
    cur.by_type[it.type] = (cur.by_type[it.type] || 0) + it.value;
    cur.n += 1;
    by.set(si, cur);
  }
  return by;
}

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const res = app.data.resources;
  if (!res) {
    el.innerHTML = `<p class="adv-empty pad">Datoteka resources.json još nije uključena: elektrane i rudnici biće prikazani iz nje, po vrsti i po okrugu.</p>${sourcesHtml(data, [], ["Elektrane i rudnici na karti dolaze iz datoteke resources.json; dok ona nije uključena, ovaj savetnik nema šta da prikaže. Za Kosovo i Metohiju statistika ne postoji."])}`;
    return {};
  }
  const types = res.types;
  const typeById = new Map(types.map((t) => [t.id, t]));
  const items = res.items.map((it, i) => ({ ...it, idx: i, key: String(i) }));
  const nat = res.summary?.national || {};
  const isMW = (t) => typeById.get(t)?.unit === "MW";
  const mwTypes = types.filter((t) => t.unit === "MW");
  const mwSet = new Set(mwTypes.map((t) => t.id));
  const states = data.levels.states.rows;
  const owner = app.w?.raw?.owner || app.w?.owner || null;
  // An item's okrug: its hex's owner when the file gives a cell, else the okrug named like the item's state field.
  const stateIdx = new Map(states.map((s, i) => [s.name, i]));
  const stateIndexOf = (it) => {
    if (fin(it.cell) && owner && owner[it.cell] >= 0) return owner[it.cell];
    if (it.state != null) {
      if (stateIdx.has(it.state)) return stateIdx.get(it.state);
      const s = states.find((r) => r.key === it.state || r.v.abbr === it.state);
      if (s) return states.indexOf(s);
    }
    return null;
  };
  // Draw groups in GROUPS order, plus any type the groups do not list.
  const listed = new Set(GROUPS.flatMap((g) => g.types));
  const groups = GROUPS.map((g) => ({ ...g, types: g.types.filter((t) => typeById.has(t)) })).filter((g) => g.types.length);
  const extra = types.filter((t) => !listed.has(t.id)).map((t) => t.id);
  if (extra.length) groups.push({ id: "other", label: "Ostalo", types: extra });

  const st = { on: new Set(types.map((t) => t.id)), min: 0, state: null };
  ctx.setShowResources(true);

  // --- headline -------------------------------------------------------------------------------------------------
  const totalMW = mwTypes.reduce((a, t) => a + (nat[t.id]?.value || 0), 0);
  const sites = mwTypes.reduce((a, t) => a + (nat[t.id]?.count || 0), 0);
  const mines = groups.find((g) => g.id === "mines");
  const top = el.appendChild(document.createElement("div"));
  top.innerHTML = tiles([
    { label: "Snaga na karti", value: mw(totalMW), sub: `${int(sites)} lokacija` },
    { label: "Rudnici", value: int(mines?.types.reduce((a, t) => a + (nat[t]?.count || 0), 0) || 0), sub: "iznad praga za prikaz" },
    { label: "Nafta i gas", value: int((nat.oil?.count || 0) + (nat.gas?.count || 0)), sub: "heksovi sa ležištima" },
  ]) + `<p class="adv-callout">${esc(res.summary?.note || "Zbirovi obuhvataju samo lokacije prikazane na karti.")}</p>`;

  // --- national mix ---------------------------------------------------------------------------------------------
  const mixBody = section(el, { title: "Energetski miks Srbije", kicker: "Lokacije sa karte iznad praga", note: "Snaga elektrana prikazanih na karti, po vrsti. Male elektrane nisu na karti, pa ovo <b>nije</b> ukupna proizvodna snaga zemlje: pokazuje gde su velika postrojenja i na čemu rade." });
  const mixParts = mwTypes.map((t) => ({ key: t.id, label: t.name, value: nat[t.id]?.value || 0, color: t.color, text: mw(nat[t.id]?.value), icon: glyph(t, 14) })).sort((a, b) => b.value - a.value);
  const mixHover = (p) => {
    if (!p) { link.hover(null); bubbles.setSelected(null); return; }
    const set = new Set(visible().filter((it) => it.type === p.key).map((it) => it.idx));
    link.hover({ resources: set, dimOthers: true });
    bubbles.setSelected(new Set(visible().filter((it) => it.type === p.key).map((it) => it.key)));
  };
  const solo = (typeId) => {
    const only = st.on.size === 1 && st.on.has(typeId);
    st.on = only ? new Set(types.map((t) => t.id)) : new Set([typeId]);
    typeChips.set(st.on);
    apply();
  };
  shareBar(mixBody, { parts: mixParts, legend: false, onHover: mixHover, onClick: (p) => solo(p.key) });
  const mixBars = barList(mixBody, {
    rows: mixParts.map((p) => ({ ...p, sub: `${int(nat[p.key]?.count || 0)} lokacija` })),
    onHover: mixHover, onClick: (p) => solo(p.key), ariaLabel: "Snaga na karti po vrsti",
  });

  // --- filters --------------------------------------------------------------------------------------------------
  const fBody = section(el, { title: "Filtrirajte kartu", note: "Uključite vrste (Alt-klik prikazuje samo jednu). Karta zatamnjuje teren i crta svaku elektranu kao krug čija površina odgovara snazi." });
  const typeChips = chips(fBody, {
    label: "Vrste resursa",
    items: groups.flatMap((g) => g.types.map((t) => {
      const ty = typeById.get(t);
      return { key: t, label: ty.name, color: ty.color, icon: glyph(ty, 13), count: nat[t]?.count ?? null };
    })),
    onChange: (on) => { st.on = on; apply(); },
  });
  const quick = document.createElement("div");
  quick.className = "adv-row";
  quick.innerHTML = groups.map((g) => `<button type="button" class="adv-mini" data-g="${g.id}">${esc(g.label)}</button>`).join("") +
    `<button type="button" class="adv-mini" data-g="all">Sve</button><button type="button" class="adv-mini" data-g="none">Ništa</button>`;
  fBody.appendChild(quick);
  quick.addEventListener("click", (e) => {
    const g = e.target.closest("[data-g]")?.dataset.g;
    if (!g) return;
    st.on = g === "all" ? new Set(types.map((t) => t.id)) : g === "none" ? new Set() : new Set(groups.find((x) => x.id === g).types);
    typeChips.set(st.on);
    apply();
  });
  const maxMW = Math.max(0, ...items.filter((it) => isMW(it.type) && fin(it.value)).map((it) => it.value));
  const step = maxMW > 0 ? Math.max(10, 10 ** Math.floor(Math.log10(maxMW / 30))) : 100;
  const slider = document.createElement("div");
  slider.className = "adv-slider";
  slider.innerHTML = `<label><span>Najmanja snaga</span><input type="range" min="0" max="${Math.ceil(maxMW / step) * step}" step="${step}" value="0" aria-label="Najmanja snaga elektrane u megavatima"><b>Bilo koja snaga</b></label>
    <p class="adv-note adv-min-note" hidden>Rudnici i ležišta nafte i gasa sakriveni su dok je postavljen minimum: njihova veličina ne meri se u megavatima.</p>`;
  fBody.appendChild(slider);
  const range = slider.querySelector("input");
  range.addEventListener("input", () => {
    st.min = +range.value;
    slider.querySelector("b").textContent = st.min ? `≥ ${int(st.min)} MW` : "Bilo koja snaga";
    slider.querySelector(".adv-min-note").hidden = !st.min;
    apply();
  });
  const stateChip = document.createElement("div");
  stateChip.className = "adv-row adv-filterbar";
  fBody.appendChild(stateChip);
  stateChip.addEventListener("click", (e) => { if (e.target.closest("[data-clear-state]")) setState(null); });
  const legendBox = document.createElement("div");
  fBody.appendChild(legendBox);

  // --- top sites ------------------------------------------------------------------------------------------------
  const tBody = section(el, { title: "Lokacije", note: "Svaka lokacija sa karte koja prolazi filtere. Postavite kursor da je nađete na karti; kliknite da preletite do nje." });
  const sizeSort = (r) => (isMW(r.type) && fin(r.value) ? r.value : null);
  const table = createTable(tBody, {
    caption: "Lokacije resursa na karti",
    search: "Pretražite lokacije, okruge i operatere",
    searchText: (r) => `${r.name} ${r.state || ""} ${r.detail || ""} ${typeById.get(r.type)?.name || ""}`,
    rank: true,
    columns: [
      { key: "name", label: "Lokacija", align: "l", width: "minmax(0,1.7fr)", value: (r) => r.name, html: (r) => `<span class="ic">${glyph(typeById.get(r.type), 13)}</span>${esc(r.name)}` },
      { key: "type", label: "Vrsta", align: "l", width: "minmax(0,1fr)", value: (r) => typeById.get(r.type)?.name, text: (r) => typeById.get(r.type)?.name || r.type },
      { key: "state", label: "Okrug", align: "l", width: "minmax(0,.9fr)", value: (r) => r.state, text: (r) => r.state || "–" },
      { key: "value", label: "Veličina", width: "minmax(0,.95fr)", value: sizeSort, text: (r) => sizeText(r, typeById), title: "Poređaj po snazi (MW; druge jedinice idu na kraju)" },
    ],
    rows: [],
    sort: { key: "value", dir: "desc" },
    maxHeight: 300,
    onHover: (r) => {
      link.hover(r ? { resources: new Set([r.idx]), dimOthers: true, label: r.name } : null);
      bubbles.setHot(r ? r.key : null);
    },
    onClick: (r) => flyTo(r),
  });
  function flyTo(r) {
    if (!fin(r.x) || !fin(r.y)) return;
    focusPoint(app, r.x, r.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3.2)));
  }

  // --- per okrug -------------------------------------------------------------------------------------------------
  const byState = powerByState(items, stateIndexOf, mwSet);
  const sBody = section(el, { title: "Snaga po okrugu", note: "Snaga prikazanih elektrana po okrugu, po vrsti. Kliknite na okrug da filtrirate sve na njega; ponovnim klikom skidate filter." });
  const stateRows = [...byState.entries()]
    .map(([i, s]) => ({ key: states[i].key, label: states[i].name, idx: i, parts: s.by_type, total: s.total, n: s.n, text: mw(s.total) }))
    .filter((r) => fin(r.total) && r.total > 0)
    .sort((a, b) => b.total - a.total);
  const stacks = stackedBars(sBody, {
    rows: stateRows, keys: mwTypes.map((t) => ({ key: t.id, label: t.name, color: t.color })), fmt: (v) => mw(v),
    ariaLabel: "Snaga elektrana na karti po okrugu",
    onHover: (x) => {
      if (!x) return link.hover(null);
      const sIdx = x.row.idx;
      const set = x.part ? new Set(items.filter((it) => stateIndexOf(it) === sIdx && it.type === x.part).map((it) => it.idx)) : undefined;
      link.hover({ states: new Set([sIdx]), resources: set, dimOthers: true, label: x.part ? `${x.row.label}: ${typeById.get(x.part)?.name || x.part}` : x.row.label });
    },
    onClick: (x) => setState(st.state === x.row.key ? null : x.row.key, true),
  });
  const noPower = states.filter((r, i) => !(byState.get(i)?.total > 0)).map((r) => r.name);
  if (noPower.length) sBody.insertAdjacentHTML("beforeend", `<p class="adv-note">Bez prikazane elektrane: ${esc(noPower.join(", "))}. Za pet okruga na Kosovu i Metohiji statistika ne postoji.</p>`);

  // --- explainer ------------------------------------------------------------------------------------------------
  const eBody = section(el, { title: "Šta simboli znače", note: "Svaka vrsta resursa, prag koji lokacija mora da pređe da bi bila na karti i odakle podaci dolaze.", open: false });
  eBody.innerHTML = groups.map((g) => `<h4 class="adv-h4">${esc(g.label)}</h4>${g.types.map((t) => {
    const ty = typeById.get(t);
    const s = nat[t] || {};
    const src = data.source(ty.source);
    const total = fin(s.value) ? (ty.unit === "MW" ? mw(s.value) : `${count3(s.value)} ${ty.unit}`) : "";
    return `<div class="adv-explain" style="--cc:${esc(ty.color)}"><span class="ic">${glyph(ty, 22)}</span><div>
      <b>${esc(ty.name)}</b> <span class="sub">${int(s.count || 0)} na karti${total ? ` · ${esc(total)}` : ""} · meri se u ${esc(ty.unit)}</span>
      <p>${esc(ty.description || "")}</p><span class="src">Izvor: ${esc(src ? `${src.title} (${src.vintage || src.publisher})` : ty.source || "nije naveden")}</span></div></div>`;
  }).join("")}`).join("");

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, [...new Set(types.map((t) => t.source).filter((s) => data.source(s)))], [
    NULL_NOTE,
    "Na karti su samo lokacije iznad praga za svoju vrstu, pa zbiroi <b>nisu</b> ukupna snaga okruga ni zemlje.",
    "Snaga je nazivna (instalisana) snaga u megavatima, a ne količina struje koju elektrana proizvede: solarna elektrana od 1.000 MW godišnje proizvede daleko manje od termoelektrane iste snage.",
    "Rudnici se mere brojem zaposlenih ili godišnjom proizvodnjom, a ležišta nafte i gasa površinom. Te jedinice ne mogu da se saberu s megavatima.",
    KIM_NOTE,
  ]));

  // --- map ------------------------------------------------------------------------------------------------------
  const bubbles = ctx.bubbles("sites", {
    rMax: 24,
    tip: (b) => {
      const it = b.it, t = typeById.get(it.type);
      return `<b>${esc(it.name)}</b><br>${esc(t.name)} · <b>${esc(sizeText(it, typeById))}</b>${it.state ? ` · ${esc(it.state)}` : ""}${it.detail ? `<br><span class="sub">${esc(it.detail)}</span>` : ""}`;
    },
    onHover: (b) => table.setHot(b ? b.key : null),
    onClick: (b) => { table.setHot(b.key); flyTo(b.it); },
  });

  function visible() {
    return items.filter((it) => st.on.has(it.type) && (!st.min || (isMW(it.type) && fin(it.value) && it.value >= st.min)) && (!st.state || stateIndexOf(it) === st.state));
  }

  function setState(idx, fly = false) {
    st.state = idx;
    stacks.setSelected(idx == null ? null : states[idx].key);
    apply();
    if (idx != null && fly) {
      const b = app.highlightBounds({ states: new Set([idx]) });
      if (b) frameBox(app, b, { pad: 30, maxScale: 13 });
    }
  }

  function apply() {
    const typesOn = st.min ? new Set([...st.on].filter(isMW)) : st.on;
    const all = typesOn.size === types.length && !st.min && st.state == null;
    ctx.setResourceFilter(all ? null : { types: new Set(typesOn), minValue: st.min || undefined });
    const vis = visible();
    table.setRows(vis.map((it) => ({ ...it, state: it.state || states[stateIndexOf(it)]?.name || null })));
    const mwVis = vis.filter((it) => isMW(it.type) && fin(it.value));
    const vMax = Math.max(1, ...items.filter((it) => isMW(it.type) && fin(it.value)).map((it) => it.value));
    bubbles.set(mwVis.map((it) => ({ key: it.key, x: it.x, y: it.y, value: it.value, color: typeById.get(it.type).color, it })), { vMax });
    const sIdx = st.state;
    link.base({ dimOthers: true, states: sIdx != null ? new Set([sIdx]) : undefined });
    stateChip.innerHTML = st.state != null
      ? `<span class="adv-fchip">Okrug: <b>${esc(states[sIdx]?.name || "")}</b> · ${int(vis.length)} lokacija<button type="button" data-clear-state aria-label="Ukloni filter okruga">✕</button></span>`
      : "";
    const r = (v) => 24 * Math.sqrt(v / vMax);
    const stops = [250, 1000, 4000].filter((v) => v <= vMax * 1.2);
    legendBox.innerHTML = stops.length ? sizeLegend(stops, r, (v) => `${int(v)} MW`, "Površina kruga = snaga") : "";
    mixBars.setSelected(st.on.size === 1 ? [...st.on][0] : null);
  }
  apply();

  return {
    onMapHover(h) {
      if (h.resource) {
        const it = items[res.items.indexOf(h.resource)];
        if (it) table.setHot(it.key);
      }
    },
    onEscape() {
      if (st.state != null) { setState(null); return true; }
      return false;
    },
    destroy() {},
  };
}
