// City View "Kvartovi": the city's real industry specialisation (districts.json: Popis 2022, employed residents by
// NACE section) as strategy-game districts, plus the Encampment tier from military.json (installations + armed-forces
// residents). Names, descriptions and caveats come from the file's catalog; only the short plaque labels and the
// wording are here.
//
//   cityDistricts(ddata, mil, id) → [district]   the city's districts, strongest first, each with what the dock and
//                                                the map plaques need ({id, name, short, color, icon, lq, emp, …})
//   badgeOf(ddata, id) → {label, text, color, icon, district} | null | undefined   the city-type badge
//   districtsHtml(m, ddata, mil) → HTML          the section body
//   badgeHtml(m, ddata) → HTML                   the header badge
import { esc, int, pct } from "../../format.js";
import { compact, money } from "./fmt.js";
import { icon } from "../../ui/icon.js";
import { hasIcon } from "../../icons.js";

// Icons the district catalog names (d-*) are not drawn yet; until they are, a near icon from the set stands in,
// and canvas plaques without any icon get the letter in `mark`.
const FALLBACK = {
  campus: ["y-science", "🎓"], commercial_hub: ["i-finance", "💰"], industrial_zone: ["i-manufacturing", "🏭"],
  harbor: ["i-transportation", "🚚"], theater_square: ["i-arts", "🎭"], entertainment_complex: ["i-accommodation", "🎡"],
  aerodrome: ["i-transportation", "✈️"], government_plaza: ["i-public_admin", "🏛"], encampment: [null, "⛺"],
  aqueduct: ["i-utilities", "💧"], agriculture: ["y-food", "🌾"], construction: ["y-production", "🔨"],
};
// Short plaque labels (the map plaques clip to 18 characters); a district without one shows the catalog's name.
const SHORT = {
  campus: "Kampus", commercial_hub: "Poslovni centar", industrial_zone: "Industrija", harbor: "Logistika", theater_square: "Kultura",
  entertainment_complex: "Turizam", aerodrome: "Aerodrom", government_plaza: "Uprava", encampment: "Logor",
  aqueduct: "Komunalije", agriculture: "Poljoprivreda", construction: "Gradnja",
};
const TIER = { garrison: "Garnizon", fortress: "Tvrđava" };
/** "1,25" — the Serbian decimal comma, as format.js writes percentages. */
const dec = (x, d = 1) => (x == null ? "–" : x.toFixed(d).replace(".", ","));

const catCache = new WeakMap();
function catalog(ddata) {
  let m = catCache.get(ddata);
  if (!m) catCache.set(ddata, (m = new Map((ddata?.catalog || []).map((c) => [c.id, c]))));
  return m;
}

export function iconFor(id, cat) {
  if (cat?.icon && hasIcon(cat.icon)) return cat.icon;
  const f = FALLBACK[id]?.[0];
  return f && hasIcon(f) ? f : null;
}

const instCache = new WeakMap();
function installationsById(mil) {
  let m = instCache.get(mil);
  if (!m) instCache.set(mil, (m = new Map((mil?.installations || []).map((i) => [i.id, i]))));
  return m;
}

/**
 * The city's districts: districts.json entries (strongest first), with military.json's Encampment merged in (its
 * tier label; added at the end when only military.json has one).
 */
export function cityDistricts(ddata, mil, id) {
  const cat = catalog(ddata);
  const row = ddata?.cities?.[id] || null;
  const mc = mil?.cities?.[id] || null;
  const out = [];
  for (const d of row?.districts || []) {
    const c = cat.get(d.id) || {};
    const spec = d.via === "specialty" && d.sub;
    out.push({
      ...d, name: c.name || d.id, color: c.color || "#5a6a7a", icon: iconFor(d.id, c), emoji: FALLBACK[d.id]?.[1] || "◆",
      cat: c, subName: d.sub ? c.sub?.[d.sub] || ddata.industries?.[d.sub]?.title || d.sub : null,
      // The map plaque: a speciality-qualified district is labelled by that speciality (its own LQ is the reason).
      short: spec ? c.sub?.[d.sub] || SHORT[d.id] : SHORT[d.id] || c.name || d.id,
      mapLq: spec ? d.sub_lq : d.lq,
      military: d.id === "encampment" ? mc : null,
    });
  }
  if (mc && !out.some((d) => d.id === "encampment")) {
    const c = cat.get("encampment") || {};
    out.push({
      id: "encampment", name: c.name || "Vojni logor", color: c.color || "#8a4a3a", icon: iconFor("encampment", c), emoji: "⛺",
      cat: c, lq: null, emp: null, short: TIER[mc.tier] || "Logor", mapLq: null, military: mc, militaryOnly: true,
    });
  }
  for (const d of out) {
    if (d.military) d.tierLabel = TIER[d.military.tier] || d.military.tier;
  }
  return out;
}

/** The city-type badge; undefined while districts.json is loading, null when there is none (no census row). */
export function badgeOf(ddata, id) {
  if (!ddata) return ddata; // undefined (loading) or null (missing)
  const row = ddata.cities?.[id];
  if (!row) return null;
  if (!row.badge) return { label: "Raznovrsna privreda", text: "Nijedan kvart ne ispunjava pravilo: nijedna grana privrede se ne ističe.", color: "#6a7484", icon: null, district: null };
  const c = catalog(ddata).get(row.badge.district) || {};
  return { ...row.badge, color: c.color || "#6a7484", icon: iconFor(row.badge.district, c), emoji: FALLBACK[row.badge.district]?.[1] };
}

export function badgeHtml(m, ddata) {
  const b = badgeOf(ddata, m.city.id);
  if (!b) return "";
  return `<span class="cv-type${b.district ? "" : " plain"}" style="--tc:${esc(b.color)}" title="Tip grada: ${esc(b.text || b.label)} (Popis ${esc(String(ddata.year || ""))}.)">
    <span class="cv-type-ic">${icon(b.icon, b.emoji || "◆", { size: 13 })}</span>${esc(b.label)}</span>`;
}

const ge = (lb) => (lb ? "≥" : "");
const signed = (x) => (x == null ? "–" : `${x >= 0 ? "+" : "−"}${dec(Math.abs(x * 100))} %`);

function lqTag(lq, lb, tip) {
  if (lq == null) return "";
  const cls = lq >= 1.25 ? "hi" : lq <= 0.75 ? "lo" : "mid";
  return `<span class="cv-lq ${cls}" title="${esc(tip || `Lokacioni količnik: ${dec(lq, 2)}× nacionalnog udela zaposlenih`)}">×${ge(lb)}${dec(lq)}</span>`;
}

function districtCard(d, row, ddata, mil) {
  const nat = ddata?.national || {};
  const c = d.cat || {};
  const lb = !!d.lower_bound;
  const supTip = lb && d.suppressed != null ? ` Deo je RZS zadržao u ${int(d.suppressed)} opštin${d.suppressed === 1 ? "i" : "a"}, pa je ovo donja granica.` : "";
  const facts = [];
  if (d.emp != null) {
    facts.push(`<div><span>Zaposleni</span><b>${ge(lb)}${compact(d.emp)}</b><small>${d.share != null ? `${pct(d.share, 1)} grada` : ""}</small></div>`);
  }
  if (d.avg_pay != null) {
    facts.push(`<div><span>Prosečna zarada</span><b>${money(d.avg_pay)}</b><small>${row?.avg_pay != null ? `grad ${money(row.avg_pay)}` : ""}</small></div>`);
  }
  if (d.strength != null) {
    facts.push(`<div title="Zaposleni iznad nacionalnog proseka: zaposleni − zaposleni ÷ količnik (tako se kvartovi ređaju)"><span>Iznad proseka</span><b>${ge(lb)}${compact(Math.max(0, d.strength))}</b><small>zaposlenih</small></div>`);
  }
  let spec = "";
  if (d.sub && d.subName) {
    // the speciality's own withheld flag (districts.json sub_lower_bound; older files: the top-industries row)
    const slb = d.sub_lower_bound ?? !!(row?.top || []).find((t) => t.naics === d.sub)?.lower_bound;
    spec = `<p class="cv-dc-sub">${d.via === "specialty" ? "Ispunjava pravilo kroz" : "Najjača specijalnost"}: <b>${esc(d.subName)}</b> ${lqTag(d.sub_lq, slb, slb ? `Lokacioni količnik: najmanje ${dec(d.sub_lq, 2)}× nacionalni udeo (deo je zadržan, pa je ovo donja granica)` : undefined)}${
      d.sub_emp != null ? ` <small>${ge(slb)}${compact(d.sub_emp)} zaposlenih</small>` : ""}${
      d.via === "specialty" && d.lq != null ? `<br><small>Delatnosti kvarta u celini imaju ${dec(d.lq, 2)}× nacionalni udeo; ova specijalnost jedina ispunjava pravilo.</small>` : ""}</p>`;
  }
  let milHtml = "";
  if (d.military) {
    const mc = d.military;
    const inst = installationsById(mil);
    const names = (mc.installations || []).map((i) => inst.get(i)?.name).filter(Boolean);
    milHtml = `<div class="cv-dc-mil">
      <p><b>${esc(d.tierLabel)}</b>${mc.naval ? " (pomorski)" : ""}: ${int(mc.armed_forces)} stanovnika u oružanim snagama, ${pct(mc.share, mc.share < 0.01 ? 2 : 1)} stanovništva sa 16 i više godina.</p>
      ${names.length ? `<p class="cv-dc-inst">${names.slice(0, 5).map((n) => `<span>${esc(n)}</span>`).join("")}${
        mc.installation_count > Math.min(5, names.length) ? `<small>+${mc.installation_count - Math.min(5, names.length)} još</small>` : ""}</p>` : ""}
    </div>`;
  }
  const caveat = c.caveat ? `<p class="cv-dc-cav">${esc(c.caveat)}</p>` : "";
  const title = d.militaryOnly ? `${esc(d.name)} · ${esc(d.tierLabel)}` : d.military ? `${esc(d.name)} · ${esc(d.tierLabel)}` : esc(d.name);
  return `<div class="cv-dc" style="--dc:${esc(d.color)}" title="${esc(c.description || "")}${esc(supTip)}">
    <div class="cv-dc-h"><span class="cv-dc-hex">${icon(d.icon, d.emoji, { size: 18 })}</span>
      <div class="cv-dc-t"><b>${title}</b><small>${esc(c.description || "")}</small></div>
      ${d.lq != null ? lqTag(d.lq, lb, `Lokacioni količnik: udeo ovih delatnosti u zaposlenima grada je ${dec(d.lq, 2)}× nacionalni udeo.${supTip}`) : ""}</div>
    ${facts.length ? `<div class="cv-dc-f">${facts.join("")}</div>` : ""}
    ${spec}${milHtml}${caveat}
  </div>`;
}

function topTable(row, ddata) {
  const top = row?.top || [];
  if (!top.length) return "";
  const max = Math.max(...top.map((t) => t.lq || 0), 1);
  return `<h4 class="cv-h4">Najspecijalizovanije delatnosti <span class="muted">po lokacionom količniku</span></h4>
  <div class="cv-top" role="table" aria-label="Najspecijalizovanije delatnosti">
    <div class="cv-top-r cv-top-hd" role="row"><span role="columnheader">Delatnost</span><span role="columnheader">Zaposleni</span><span role="columnheader">×RS</span><span role="columnheader">Zarada</span><span role="columnheader">1 god.</span></div>
    ${top.map((t) => {
      const title = ddata.industries?.[t.naics]?.title || `NACE ${t.naics}`;
      const lb = !!t.lower_bound;
      return `<div class="cv-top-r" role="row" title="${esc(title)} (NACE odeljak ${esc(t.naics)})${lb && t.suppressed != null ? ` Donja granica: podatak je zadržan u ${int(t.suppressed)} opštin${t.suppressed === 1 ? "i" : "a"}.` : ""}">
        <span role="cell" class="cv-top-n">${esc(title)}<i style="width:${((Math.log(1 + (t.lq || 0)) / Math.log(1 + max)) * 100).toFixed(1)}%"></i></span>
        <span role="cell">${ge(lb)}${compact(t.emp)}</span>
        <span role="cell"><b>${t.lq != null ? `${ge(lb)}${dec(t.lq)}` : "–"}</b></span>
        <span role="cell">${money(t.avg_pay)}</span>
        <span role="cell" class="${t.oty_pct == null ? "" : t.oty_pct >= 0 ? "good" : "bad"}">${signed(t.oty_pct)}</span></div>`;
    }).join("")}
  </div>`;
}

/** The Districts section body. ddata: districts.json (undefined while loading, null when missing). */
export function districtsHtml(m, ddata, mil) {
  if (ddata === undefined) return `<p class="muted cv-note">Učitavamo kvartove…</p>`;
  if (!ddata) return `<p class="muted cv-note">Podaci o kvartovima nisu dostupni.</p>`;
  const id = m.city.id;
  const row = ddata.cities?.[id] || null;
  const list = cityDistricts(ddata, mil, id);
  const b = badgeOf(ddata, id);
  let lead;
  if (!row) {
    lead = `<p class="cv-lead">Popis 2022. nije sproveden za ${esc(m.city.name)}, pa grad nema privredne kvartove.</p>`;
  } else {
    const cnt = row.counties ? ` u ${row.counties[0]} od ${row.counties[1]} opštin${row.counties[1] === 1 ? "i" : "a"} grada` : "";
    lead = `<p class="cv-lead">${b?.district ? `<b class="cv-type-l" style="--tc:${esc(b.color)}">${esc(b.label)}</b> · ${esc(b.text || "")}. ` : ""}${
      int(row.emp)} zaposlenih po prebivalištu${esc(cnt)}; prosečna zarada se po opštinama ne objavljuje (Popis 2022).</p>`;
  }
  const cards = list.length
    ? `<div class="cv-dcs">${list.map((d) => districtCard(d, row, ddata, mil)).join("")}</div>`
    : row ? `<p class="muted cv-note">Nijedan kvart ne ispunjava pravilo: zaposleni su raspoređeni kao u celoj Srbiji.</p>` : "";
  const milRule = mil?.rule && list.some((d) => d.military) ? `<p><b>Nivo garnizona</b> (military.json): ${esc(mil.rule)}</p>` : "";
  return `${lead}
    ${cards}
    ${topTable(row, ddata)}
    <div class="cv-schematic">
      <p><b>◆ Na karti</b> svaki kvart stoji kao pločica na heksu grada pored naselja. Položaji su šematski: pokazuju u čemu se grad specijalizuje, ne gde su radna mesta.</p>
    </div>
    <details class="cv-more cv-rule"><summary>Kako se biraju kvartovi</summary>
      <p>${esc(ddata.rule?.text || "")}</p>${milRule}
      <p>Popis broji zaposlene po prebivalištu, a ne tamo gde je poslodavac; obuhvata samozaposlene i poljoprivrednike, a zarade po opštinama ne objavljuje.</p>
    </details>
    <p class="cv-note">${esc(ddata.vintage || "Popis 2022")}. ×N = lokacioni količnik prema nacionalnom udelu zaposlenih (Republika Srbija bez Kosova i Metohije).${
      mil && list.some((d) => d.military) ? ` Nivo garnizona: ${esc(typeof mil.vintage === "object" ? [mil.vintage.installations, mil.vintage.acs].filter(Boolean).join("; ") : mil.vintage || "")}.` : ""}</p>`;
}
