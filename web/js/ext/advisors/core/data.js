// The advisors' view of Serbia: three levels built from the app's data files.
//   states   = okruzi  (states.json, one row per okrug; the five okruzi of Kosovo and Metohija carry null statistics)
//   metros   = gradovi (cities.json, the "metros" level)
//   counties = opštine (counties.json rows joined with lens-values.json by geoid)
// A row keeps the raw record in `ref`; `v` holds the typed values the dashboards read. Null means "no data"
// (never 0, never invented): the views print "—" or "Nema podataka" and explain why in a note.
import { fin } from "./util.js";

// Serbia's city classes for rankings; mirrors METRO_MIN / BIG_METRO_MIN in web/js/ui/yieldReport.js.
export const METRO_MIN = 50000; // cities of 50 000 and more rank in the share tables
export const BIG_METRO_MIN = 200000; // cities of 200 000 and more rank by unemployment

export const LAND_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"];
export const LAND_LABEL = {
  forest: "Šuma", crop: "Njive", pasture: "Livade i pašnjaci", grass: "Travnjaci", shrub: "Žbunje",
  wetland: "Močvare", developed: "Gradsko zemljište",
};
export const LAND_COLOR = {
  forest: "#3f7a3a", crop: "#d2c457", pasture: "#93b852", grass: "#b9b06a", shrub: "#c9a874", wetland: "#4f9a86",
  developed: "#9a8f9e",
};

// NACE sections (the jobs blocks of cities.json / states.json). nation.industries carries the Serbian names;
// these are the fallback.
export const NACE_KEYS = [
  "agriculture", "mining", "manufacturing", "energy", "water_waste", "construction", "trade", "transport",
  "accommodation", "information", "finance", "real_estate", "professional", "admin", "public_admin", "education",
  "health", "arts", "other",
];
export const NACE_LABEL = {
  agriculture: "Poljoprivreda, šumarstvo i ribarstvo", mining: "Rudarstvo i vađenje",
  manufacturing: "Prerađivačka industrija", energy: "Snabdevanje električnom energijom, gasom i parom",
  water_waste: "Snabdevanje vodom; uklanjanje i obrada otpada", construction: "Građevinarstvo",
  trade: "Trgovina na veliko i na malo", transport: "Saobraćaj i skladištenje", accommodation: "Ugostiteljstvo",
  information: "Informisanje i komunikacije", finance: "Finansijske delatnosti",
  real_estate: "Poslovanje nekretninama", professional: "Stručne, naučne i tehničke delatnosti",
  admin: "Administrativne i pomoćne uslužne delatnosti",
  public_admin: "Državna uprava i odbrana; obavezno socijalno osiguranje", education: "Obrazovanje",
  health: "Zdravstvena zaštita i socijalna pomoć", arts: "Umetnost, zabava i rekreacija",
  other: "Ostale uslužne delatnosti",
};
export const YIELD_KEYS = ["food", "production", "gold", "science", "culture"];
// The Science yield (nation.yields.science.industries): NACE sections M and J.
export const SCIENCE_KEYS = ["professional", "information"];
// Kosovo and Metohija: on the map and in the tables, with null statistics.
export const KIM_FIPS = new Set(["RS231", "RS232", "RS233", "RS234", "RS235"]);
export const KIM_NOTE = "Za Kosovo i Metohiju nema podataka: Republički zavod za statistiku ne objavljuje statistiku za te okruge i opštine, pa su njihova polja prazna.";
export const NO_DATA = "Nema podataka.";

// The 12 statistical sočiva (lenses.json) → the counties.json column each reads.
export const COUNTY_LENS = {
  density: "density", pop_change: null, natural_increase: "natural_increase", age65: "age65", education: "education",
  wages: "wage_net", unemployment: "unemployment", manufacturing: "manufacturing", commute: "commute",
  orthodox: "orthodox", serbs: "serbs", life_expectancy: "life_expectancy",
};

const num = (v) => (Number.isFinite(v) ? v : null); // null unless a finite number
const nonNeg = (v) => (Number.isFinite(v) && v >= 0 ? v : null);
const share = (a, b) => (Number.isFinite(a) && Number.isFinite(b) && b > 0 && a >= 0 ? a / b : null);

export const isKim = (rec) => !!(rec && (KIM_FIPS.has(rec.fips) || KIM_FIPS.has(rec.state)));

/** Field catalog entry. `format` is one of core/fmt.js's formats (text, int, pct, signed, float, rsd, eur, km2). */
export function field(key, label, format, o = {}) {
  return {
    key, label, format, unit: o.unit ?? "", higher_is: o.higher_is ?? "neutral", source: o.source ?? "",
    description: o.description ?? "", lens: o.lens ?? null, group: o.group ?? "", derived: !!o.derived,
  };
}

const byKey = (fields) => new Map(fields.map((f) => [f.key, f]));
const gdpNote = "Bruto domaći proizvod u tekućim evrima, tamo gde se obavlja rad (Eurostat, BDP po oblastima, 2023). Za grad je to procena: BDP okruga podeljen prema udelu grada u zaposlenima okruga.";

/** Fields shared by the three levels. */
function commonFields(level) {
  const counties = level === "counties";
  return [
    field("population", "Stanovništvo", "int", { source: "rzs_db", group: "Stanovništvo",
      description: counties ? "Procenjeni broj stanovnika opštine za 2025. godinu." : "Procenjeni broj stanovnika (Republički zavod za statistiku, 2025)." }),
    field("employed", "Zaposleni", "int", { source: "census", group: "Rad", description: "Zaposleni prema prebivalištu, Popis 2022." }),
    field("land_km2", "Površina", "km2", { unit: "km²", source: "boundaries", group: "Zemljište", derived: !counties,
      description: counties ? "Površina opštine po granicama izvora (Eurostat GISCO, LAU)." : "Zbir površina opština koje okrug obuhvata (Eurostat GISCO, LAU)." }),
    field("density", "Gustina naseljenosti", "int", { unit: "stanovnika / km²", lens: "density", source: "rzs_db", group: "Stanovništvo", derived: true,
      description: "Procenjeni broj stanovnika podeljen površinom: stanovnika po km²." }),
    field("growth", "Promena broja stanovnika", "signed", { unit: "%", lens: "pop_change", source: "rzs_db", group: "Stanovništvo",
      description: counties ? "Koliko se procenjeni broj stanovnika opštine promenio od 2015. do 2025. godine, u odnosu na 2015. godinu." : "Koliko se procenjeni broj stanovnika promenio između dve godine procene (godine su u polju growth_years)." }),
    field("age65", "Stariji od 65 godina", "pct", { unit: "%", lens: "age65", source: "rzs_db", group: "Stanovništvo",
      description: "Udeo stanovništva starog 65 i više godina u proceni za 2025. godinu." }),
    field("natural_increase", "Prirodni priraštaj", "float", { unit: "na 1.000 stanovnika", lens: "natural_increase", source: "rzs_db", group: "Stanovništvo",
      description: "Prirodni priraštaj na 1.000 stanovnika (živorođeni minus umrli) za 2025. godinu." }),
    field("life_expectancy", "Očekivano trajanje života", "float", { unit: "godine", lens: "life_expectancy", higher_is: "good", source: "rzs_db", group: "Kvalitet života",
      description: "Očekivano trajanje života pri rođenju za 2025. godinu: sredina vrednosti za muškarce i za žene." }),
    field("education", "Visoko obrazovanje", "pct", { unit: "%", lens: "education", higher_is: "good", source: "census", group: "Obrazovanje",
      description: "Udeo stanovništva starog 15 i više godina sa završenim visokim obrazovanjem, Popis 2022." }),
    field("wage_net", "Prosečna neto zarada", "rsd", { unit: "RSD", lens: "wages", higher_is: "good", source: "rzs_db", group: "Rad",
      description: "Prosečna neto zarada u dinarima mesečno, 2025. godina." }),
    field("unemployment", "Stopa nezaposlenosti", "pct", { unit: "%", lens: "unemployment", higher_is: "bad", source: "census", group: "Rad",
      description: "Udeo nezaposlenih u aktivnom stanovništvu (zaposleni i nezaposleni), Popis 2022." }),
    field("manufacturing", "Prerađivačka industrija", "pct", { unit: "%", lens: "manufacturing", source: "census", group: "Rad",
      description: "Udeo zaposlenih u prerađivačkoj industriji (NACE odeljak C) u svim zaposlenima, Popis 2022." }),
    field("commute", "Rad u drugoj opštini", "pct", { unit: "%", lens: "commute", source: "census", group: "Rad",
      description: "Udeo zaposlenih koji rade u drugoj opštini ili u drugom okrugu, u svim zaposlenima, Popis 2022." }),
    field("orthodox", "Pravoslavni", "pct", { unit: "%", lens: "orthodox", source: "census", group: "Identitet",
      description: "Udeo pravoslavnih u ukupnom stanovništvu, Popis 2022." }),
    field("serbs", "Srbi", "pct", { unit: "%", lens: "serbs", source: "census", group: "Identitet",
      description: "Udeo Srba u ukupnom stanovništvu, Popis 2022." }),
    field("gdp", "Bruto domaći proizvod", "eur", { unit: "€", higher_is: "good", source: "gdp", group: "Ekonomija", description: gdpNote }),
    field("gdp_pc", "BDP po stanovniku", "eur", { unit: "€", higher_is: "good", source: "gdp", group: "Ekonomija", derived: true,
      description: "Bruto domaći proizvod podeljen procenjenim brojem stanovnika." }),
  ];
}

function yieldFields(yields) {
  const y = (k) => (Array.isArray(yields) ? yields.find((x) => x.key === k) : null);
  return YIELD_KEYS.map((k) => field(`yield_${k}`, y(k)?.label ?? k, k === "gold" ? "eur" : "int",
    { unit: k === "gold" ? "€" : "zaposlenih", higher_is: "good", source: k === "gold" ? "gdp" : "census", group: "Prinosi",
      description: y(k)?.description ?? "" }));
}

function landFields(keys) {
  return keys.map((k) => field(`land_${k}`, LAND_LABEL[k], "pct", { unit: "%", source: "landcover", group: "Zemljište",
    description: "Udeo površine pod zemljišnim pokrivačem (ESA WorldCover 2021)." }));
}

function jobFields(industries) {
  return NACE_KEYS.map((k) => field(`jobs_${k}`, industries?.[k] ?? NACE_LABEL[k], "int", { source: "census", group: "Zaposleni po delatnostima",
    description: "Zaposleni u delatnosti prema prebivalištu, Popis 2022 (NACE odeljak)." }));
}

/** Cities only: the Popis 2022 blocks as shares. */
function cityExtraFields() {
  return [
    field("settlement_population", "Stanovništvo naselja", "int", { source: "census", group: "Stanovništvo",
      description: "Stanovnici gradskog naselja u užem smislu (Popis 2022); grad obuhvata i okolna naselja." }),
    field("edu_none", "Bez škole", "pct", { unit: "%", source: "census", group: "Obrazovanje", description: "Udeo stanovništva starog 15 i više godina bez škole ili bez završene osnovne škole, Popis 2022." }),
    field("edu_primary", "Osnovno obrazovanje", "pct", { unit: "%", source: "census", group: "Obrazovanje", description: "Udeo stanovništva starog 15 i više godina sa završenom osnovnom školom, Popis 2022." }),
    field("edu_secondary", "Srednje obrazovanje", "pct", { unit: "%", source: "census", group: "Obrazovanje", description: "Udeo stanovništva starog 15 i više godina sa završenom srednjom školom, Popis 2022." }),
    field("edu_higher", "Visoko obrazovanje (15+)", "pct", { unit: "%", higher_is: "good", source: "census", group: "Obrazovanje", description: "Udeo stanovništva starog 15 i više godina sa završenim visokim obrazovanjem, Popis 2022." }),
    field("commute_same", "Rad u mestu stanovanja", "pct", { unit: "%", source: "census", group: "Rad", description: "Udeo zaposlenih koji rade u istoj jedinici u kojoj stanuju, Popis 2022." }),
    field("commute_other_oblast", "Rad u drugom okrugu", "pct", { unit: "%", source: "census", group: "Rad", description: "Udeo zaposlenih koji rade u drugom okrugu, Popis 2022." }),
    field("commute_abroad", "Rad u inostranstvu", "pct", { unit: "%", source: "census", group: "Rad", description: "Udeo zaposlenih koji rade u inostranstvu, Popis 2022." }),
    field("rel_orthodox", "Pravoslavni", "pct", { unit: "%", source: "census", group: "Veroispovest", description: "Udeo pravoslavnih u ukupnom stanovništvu, Popis 2022." }),
    field("rel_catholic", "Katolici", "pct", { unit: "%", source: "census", group: "Veroispovest", description: "Udeo katolika u ukupnom stanovništvu, Popis 2022." }),
    field("rel_muslim", "Muslimani", "pct", { unit: "%", source: "census", group: "Veroispovest", description: "Udeo muslimana u ukupnom stanovništvu, Popis 2022." }),
    field("rel_protestant", "Protestanti", "pct", { unit: "%", source: "census", group: "Veroispovest", description: "Udeo protestanata u ukupnom stanovništvu, Popis 2022." }),
    field("rel_nonbeliever", "Nevernici", "pct", { unit: "%", source: "census", group: "Veroispovest", description: "Udeo onih koji su se izjasnili kao nevernici, Popis 2022." }),
    field("eth_srbi", "Srbi", "pct", { unit: "%", source: "census", group: "Narodnost", description: "Udeo Srba u ukupnom stanovništvu, Popis 2022." }),
    field("eth_madjari", "Mađari", "pct", { unit: "%", source: "census", group: "Narodnost", description: "Udeo Mađara u ukupnom stanovništvu, Popis 2022." }),
    field("eth_bosnjaci", "Bošnjaci", "pct", { unit: "%", source: "census", group: "Narodnost", description: "Udeo Bošnjaka u ukupnom stanovništvu, Popis 2022." }),
    field("eth_romi", "Romi", "pct", { unit: "%", source: "census", group: "Narodnost", description: "Udeo Roma u ukupnom stanovništvu, Popis 2022." }),
  ];
}

/** The growth label carries the two years of the estimate when the records have them. */
export function growthLabel(rec, fallback = "Promena broja stanovnika") {
  const y = rec?.growth_years;
  return Array.isArray(y) && y.length === 2 && fin(y[0]) && fin(y[1]) ? `Promena broja stanovnika ${y[0]}–${y[1]}` : fallback;
}

/** Population, jobs, yields and land of a cities.json / states.json / nation.json record. */
export function blockValues(rec, landKeys = LAND_KEYS) {
  const v = {
    population: num(rec.population), employed: num(rec.employed), growth: num(rec.growth), age65: num(rec.age65),
    unemployment: num(rec.unemployment), wage_net: num(rec.wage_net), gdp: num(rec.gdp),
    gdp_pc: share(num(rec.gdp), num(rec.population)),
  };
  // Every field key is always present: a missing block yields explicit nulls (never 0, never undefined).
  const y = rec.yields && typeof rec.yields === "object" ? rec.yields : null;
  for (const k of YIELD_KEYS) v[`yield_${k}`] = y ? num(y[k]) : null;
  for (const k of landKeys) v[`land_${k}`] = rec.land && typeof rec.land === "object" ? nonNeg(rec.land[k]) : null;
  let total = null;
  if (rec.jobs && typeof rec.jobs === "object") {
    let t = 0, complete = true, any = false;
    for (const k of NACE_KEYS) {
      const j = nonNeg(rec.jobs[k]);
      v[`jobs_${k}`] = j;
      if (j == null) complete = false; else { t += j; any = true; }
    }
    total = complete && any ? t : null; // only a full block adds up; Kosovo's null block stays null
  } else {
    for (const k of NACE_KEYS) v[`jobs_${k}`] = null;
  }
  v.jobs_total = total;
  v.jobs_science = fin(v.jobs_professional) && fin(v.jobs_information) ? v.jobs_professional + v.jobs_information : null;
  for (const k of LAND_KEYS) if (!fin(v[`land_${k}`])) v[`land_${k}`] = null;
  return v;
}

const EDU_KEYS = ["none", "incomplete_primary", "primary", "secondary", "higher", "unknown"];
const REL_KEYS = ["orthodox", "catholic", "protestant", "other_christian", "muslim", "jewish", "eastern", "other", "agnostic", "nonbeliever", "undeclared", "unknown", "no_answer"];
const ETH_KEYS = ["srbi", "albanci", "bosnjaci", "bugari", "bunjevci", "vlasi", "goranci", "jugosloveni", "madjari", "makedonci", "muslimani", "nemci", "romi", "rumuni", "rusini", "slovaci", "ukrajinci", "crnogorci", "cehani", "jegrci", "ostali", "nije_izjasnio", "regionalno", "nepoznato"];

/** Cities only: the Popis 2022 blocks (education, religion, ethnicity, commute) as shares of their totals. */
export function censusShares(city) {
  const v = { education: null, commute: null, orthodox: null, serbs: null, settlement_population: num(city?.settlement_population) };
  const c = city ?? {};
  const block = (b, keys, prefix) => {
    if (!b || !fin(b.total) || b.total <= 0) return;
    v[`${prefix}_total`] = b.total;
    for (const k of Object.keys(b)) if (k !== "total") v[`${prefix}_${k}`] = share(b[k], b.total);
    void keys;
  };
  block(c.education && { ...c.education, total: c.education.total15 }, EDU_KEYS, "edu");
  block(c.religion, REL_KEYS, "rel");
  block(c.ethnicity, ETH_KEYS, "eth");
  if (c.commute && fin(c.commute.total) && c.commute.total > 0) {
    const other = (fin(c.commute.other_unit) ? c.commute.other_unit : 0) + (fin(c.commute.other_oblast) ? c.commute.other_oblast : 0);
    v.commute = share(other, c.commute.total);
    v.commute_same = share(c.commute.same_unit, c.commute.total);
    v.commute_other_oblast = share(c.commute.other_oblast, c.commute.total);
    v.commute_abroad = share(c.commute.abroad, c.commute.total);
  }
  v.education = v.edu_higher ?? null;
  v.orthodox = v.rel_orthodox ?? null;
  v.serbs = v.eth_srbi ?? null;
  return v;
}

// --- level construction ------------------------------------------------------------------------------------------

const MANY = { okrug: "okruga", grad: "gradova", opština: "opština" }; // genitive plural for counts: "52 grada" → "52 gradova"
function makeLevel(id, label, noun, rows, fields, o) {
  const fmap = byKey(fields);
  return {
    id, label, noun, many: MANY[noun] || noun, rows, fields,
    byKey: new Map(rows.map((r) => [r.key, r])),
    field: (key) => fmap.get(key) ?? null,
    value: (row, key) => (row && row.v ? row.v[key] ?? null : null),
    highlight(rowsIn, opts = {}) {
      return o.highlight(rowsIn, opts);
    },
    rowAtCell: o.rowAtCell,
    focus: o.focus,
    cellsOf: (row) => row?.cells ?? [],
  };
}

const frameCells = (app, cells) => {
  const b = app.highlightBounds?.({ cells: new Set(cells) });
  if (b) app.fitBounds?.(b.x0, b.y0, b.x1, b.y1, { padLeft: 36, padRight: 36, padTop: 36, padBottom: 36 });
};

/** Build the three levels from the app (web/js/main.js `app`). Safe to call before counties.json has loaded. */
export function buildData(app) {
  const d = app.data;
  const raw = app.w?.raw ?? {};
  const owner = raw.owner ?? [];
  const countyOf = raw.county ?? [];
  const rawStates = raw.states ?? [];
  const rawCounties = raw.counties ?? [];
  const nationFile = d.nation ?? {};
  const nation = nationFile.nation ?? nationFile;
  const industries = nationFile.industries ?? null;
  const yields = Array.isArray(nationFile.yields) ? nationFile.yields : null;
  const lensById = app.lensById ?? new Map();
  const hexArea = app.w?.grid ? (3 * Math.sqrt(3) / 2) * app.w.grid.R * app.w.grid.R : null;
  const stateIdx = new Map(rawStates.map((s, i) => [s.fips, i]));
  const stateName = (fips) => rawStates[stateIdx.get(fips)]?.name ?? "";

  // counties.json: rows are arrays in `columns` order; the same order as world.counties (lens-values.json relies on it).
  const countyFile = Array.isArray(d.counties?.rows) ? d.counties : null;
  const countyRec = (r) => Object.fromEntries(countyFile.columns.map((c, i) => [c, r[i]]));
  const countyByKey = new Map();
  if (countyFile) for (const r of countyFile.rows) { const rec = countyRec(r); countyByKey.set(rec.geoid, rec); }

  // Cells per okrug / per opština; the city owning a cell (smallest footprint first, the city's own hex last).
  const stateCells = rawStates.map(() => []);
  const countyCells = new Map();
  for (let i = 0; i < owner.length; i++) {
    const o = owner[i];
    if (o == null || o < 0) continue;
    (stateCells[o] ??= []).push(i);
    const c = countyOf[i];
    const g = c != null && c >= 0 ? rawCounties[c]?.geoid : null;
    if (g) { if (!countyCells.has(g)) countyCells.set(g, []); countyCells.get(g).push(i); }
  }
  const cityCells = new Map();
  const citiesSorted = [...(d.cities ?? [])].sort((a, b) => (a.footprint?.length ?? 0) - (b.footprint?.length ?? 0));
  for (const c of citiesSorted) for (const cell of c.footprint ?? []) if (!cityCells.has(cell)) cityCells.set(cell, c);
  for (const c of citiesSorted) if (c.cell != null) cityCells.set(c.cell, c);

  // --- okruzi -----------------------------------------------------------------------------------------------------
  const states = (d.states ?? []).map((s) => {
    const idx = rawStates.findIndex((x) => x.fips === s.fips);
    const cells = idx >= 0 ? stateCells[idx] : [];
    const v = blockValues(s);
    v.land_km2 = null;
    return { key: s.fips, name: s.name, full: s.name, sub: "Okrug", level: "states", ref: s, idx, cells, v, kim: isKim(s) };
  });
  for (const rec of countyByKey.values()) if (fin(rec.land_km2)) { const r = states.find((x) => x.key === rec.state); if (r) r.v.land_km2 = (r.v.land_km2 ?? 0) + rec.land_km2; }
  for (const r of states) r.v.density = share(r.v.population, r.v.land_km2);
  const growthRec = (d.states ?? []).find((s) => Array.isArray(s.growth_years)) ?? {};
  const statesLevel = makeLevel("states", "Okrug", "okrug", states, [
    field("name", "Okrug", "text"),
    ...commonFields("states").map((f) => (f.key === "growth" ? { ...f, label: growthLabel(growthRec) } : f)),
    ...yieldFields(yields), ...landFields(LAND_KEYS), ...jobFields(industries),
  ], {
    highlight: (rows, opts) => {
      const idx = rows.map((r) => r.idx).filter((i) => i >= 0);
      return idx.length ? { states: new Set(idx), dimOthers: !!opts.dim } : null;
    },
    rowAtCell: (cell) => { const o = owner[cell]; return o == null || o < 0 ? null : states[o] ?? null; },
    focus: (row) => { if (row) app.selectState?.(row.key); },
  });

  // --- gradovi ----------------------------------------------------------------------------------------------------
  // Land cover of a city = the mean WorldCover share over its hexes (cities.json carries no land block).
  const pct = raw.pct && typeof raw.pct === "object" ? raw.pct : null;
  const landFromCells = (cells) => {
    if (!pct || !cells.length) return null;
    const out = Object.fromEntries(LAND_KEYS.map((k) => [k, 0]));
    let n = 0;
    for (const cell of cells) {
      let any = false;
      for (const k of LAND_KEYS) { const x = pct[k]?.[cell]; if (fin(x)) { out[k] += x; any = true; } }
      if (any) n++;
    }
    return n ? Object.fromEntries(LAND_KEYS.map((k) => [k, out[k] / (n * 100)])) : null;
  };
  const metroByKey = new Map();
  const metrosLevel = makeLevel("metros", "Grad", "grad", (d.cities ?? []).map((c, i) => {
    const cells = [...new Set([...(c.footprint ?? []), ...(c.cell != null ? [c.cell] : [])])];
    // A city's area on the map is its hexes: cities.json lists census units that need not match the map's
    // opštine, so the county land areas are not comparable for cities. Density uses the hex area.
    const v = blockValues(c);
    v.land_km2 = hexArea ? cells.length * hexArea : null;
    v.density = share(v.population, v.land_km2);
    let landFromHexes = false;
    if (!c.land || typeof c.land !== "object") {
      const l = landFromCells(cells);
      if (l) { for (const k of LAND_KEYS) v[`land_${k}`] = l[k]; landFromHexes = true; }
    }
    Object.assign(v, censusShares(c));
    const okrug = (c.states ?? []).map(stateName).filter(Boolean).join(", ") || "Grad";
    v.okrug = okrug;
    const row = { key: c.id, name: c.name, full: c.full ?? c.name, sub: okrug,
      level: "metros", ref: c, idx: i, cells, v, kim: isKim({ fips: c.states?.[0] }), landFromHexes };
    metroByKey.set(row.key, row);
    return row;
  }), [
    field("name", "Grad", "text"), field("okrug", "Okrug", "text", { group: "Opšte", description: "Okrug ili okruzi u kojima grad leži (prema granicama opština iz Popisa 2022.).", source: "boundaries" }),
    ...commonFields("metros").map((f) => (f.key === "growth" ? { ...f, label: growthLabel((d.cities ?? []).find((c) => Array.isArray(c.growth_years)) ?? {}) } : f)),
    ...yieldFields(yields), ...landFields(LAND_KEYS), ...jobFields(industries), ...cityExtraFields(),
  ], {
    highlight: (rows, opts) => (rows.length ? { cells: new Set(rows.flatMap((r) => r.cells)), cities: new Set(rows.map((r) => r.key)), dimOthers: !!opts.dim } : null),
    rowAtCell: (cell) => { const c = cityCells.get(cell); return c ? metroByKey.get(c.id) ?? null : null; },
    focus: (row) => { if (row) app.selectCity?.(row.key); },
  });

  // --- opštine ----------------------------------------------------------------------------------------------------
  const lensFile = d["lens-values"]?.version === 2 ? d["lens-values"] : null;
  const lensIndex = lensFile ? new Map(lensFile.municipality_ids.map((g, i) => [g, i])) : null;
  const lensValue = (lens, geoid) => {
    const i = lensIndex?.get(geoid);
    const arr = lensFile?.values?.[lens];
    const x = i == null || !arr ? undefined : arr[i];
    return Number.isFinite(x) ? x : undefined;
  };
  const countyRows = countyFile ? countyFile.rows.map((r) => {
    const rec = countyRec(r);
    const col = (c) => (Number.isFinite(rec[c]) ? rec[c] : null);
    const lv = (lens) => lensValue(lens, rec.geoid) ?? null;
    const v = {
      population: col("population"), land_km2: col("land_km2"), density: col("density") ?? lv("density"),
      growth: lv("pop_change"), age65: col("age65") ?? lv("age65"), natural_increase: col("natural_increase") ?? lv("natural_increase"),
      education: col("education") ?? lv("education"), wage_net: col("wage_net") ?? lv("wages"), unemployment: col("unemployment") ?? lv("unemployment"),
      manufacturing: col("manufacturing") ?? lv("manufacturing"), commute: col("commute") ?? lv("commute"), orthodox: col("orthodox") ?? lv("orthodox"),
      serbs: col("serbs") ?? lv("serbs"), life_expectancy: col("life_expectancy") ?? lv("life_expectancy"),
      employed: null, gdp: null, gdp_pc: null,
    };
    for (const k of LAND_KEYS) v[`land_${k}`] = k === "grass" || k === "shrub" || k === "wetland" ? null : nonNeg(rec[k]);
    const okrug = stateName(rec.state) || rec.state || "Okrug";
    v.okrug = okrug;
    return { key: rec.geoid, name: rec.name, full: rec.name, sub: okrug, level: "counties", ref: rec,
      cells: countyCells.get(rec.geoid) ?? [], v, kim: isKim(rec), city: rec.city ?? null };
  }) : null;
  const countyByKey2 = new Map((countyRows ?? []).map((r) => [r.key, r]));
  const countiesLevel = countyRows ? makeLevel("counties", "Opština", "opština", countyRows, [
    field("name", "Opština", "text"), field("okrug", "Okrug", "text", { group: "Opšte", description: "Okrug kome opština pripada.", source: "boundaries" }),
    ...commonFields("counties"), ...landFields(["forest", "crop", "pasture", "developed"]),
  ], {
    highlight: (rows, opts) => { const cells = rows.flatMap((r) => r.cells); return cells.length ? { cells: new Set(cells), dimOthers: !!opts.dim } : null; },
    rowAtCell: (cell) => { const c = countyOf[cell]; const g = c != null && c >= 0 ? rawCounties[c]?.geoid : null; return g ? countyByKey2.get(g) ?? null : null; },
    focus: (row) => {
      if (!row) return;
      if (row.city && app.cityById?.has(row.city)) app.selectCity?.(row.city);
      else if (row.cells.length) frameCells(app, row.cells);
    },
  }) : null;

  // --- nation row (the tiles at the top of a dashboard) ----------------------------------------------------------
  const nv = blockValues(nation);
  nv.land_km2 = null;
  nv.density = null;
  nv.growth = fin(nation.growth) ? nation.growth : null;
  let popSum = null;
  if (countyByKey.size) { popSum = 0; for (const rec of countyByKey.values()) if (fin(rec.population)) popSum += rec.population; }
  if (nv.population == null && popSum != null) nv.population = popSum; // zbir opština, bez Kosova i Metohije
  if (nv.gdp_pc == null && fin(nv.gdp) && fin(nv.population)) nv.gdp_pc = nv.gdp / nv.population;
  const nationRow = { key: "RS", name: nation.name ?? "Republika Srbija", full: "Republika Srbija", sub: "Država", level: "nation", ref: nation, v: nv, kim: false,
    populationIsSum: popSum != null && !fin(nation.population) };

  return {
    app,
    levels: { states: statesLevel, metros: metrosLevel, counties: countiesLevel },
    order: ["states", "metros", "counties"],
    nation: nationRow,
    nationFields: [...commonFields("states"), ...yieldFields(yields), ...landFields(LAND_KEYS), ...jobFields(industries)],
    yields, industries,
    vintage: nationFile.vintage ?? "",
    gdpVintage: nationFile.gdp_vintage ?? "",
    countyVintage: countyFile?.vintage ?? "",
    countyFields: countyFile?.fields ?? [],
    sources: d.sources ?? [],
    lensById, hexArea, year: nationFile.year ?? null,
    raw: { states: rawStates, counties: rawCounties },
    stateIdx, countyCells, cityCells, stateCells,
    countiesOffMap: countiesLevel ? countiesLevel.rows.filter((r) => !r.cells.length).length : 0,
    kimNote: KIM_NOTE,
    extra: {},
    /** One sources.json record by id, with `vintage` flattened to a line (the file may carry one vintage per table). */
    source: (id) => {
      const s = (Array.isArray(d.sources) ? d.sources : []).find((x) => x && x.id === id);
      if (!s) return null;
      const v = s.vintage;
      const vintage = typeof v === "string" ? v : v && typeof v === "object" ? Object.values(v).join("; ") : "";
      return { ...s, vintage };
    },
  };
}

/** Highlight for a row selection: the level's geometry, the advisors' hover colour and an optional label. */
export function rowsHighlight(level, rows, opts = {}) {
  if (!level) return null;
  const list = (Array.isArray(rows) ? rows : rows ? [rows] : []).filter(Boolean);
  const h = level.highlight(list, opts);
  if (!h) return null;
  return { ...h, dimOthers: !!opts.dim, ...(opts.color ? { color: opts.color } : {}), ...(opts.label ? { label: opts.label } : {}) };
}

/**
 * Lazily load the optional files a view needs (lens-values, infrastructure, resources, wonders…) and attach
 * them to `data.extra`. Builds the opštine level if counties.json arrived after buildData(). Never rejects.
 */
export async function extendData(data, names = []) {
  const app = data.app;
  await Promise.all([...new Set(["counties", "lens-values", ...names])].map((name) => app.loadData(name).catch(() => null)));
  if (!data.levels.counties && Array.isArray(app.data.counties?.rows)) {
    const fresh = buildData(app);
    Object.assign(data.levels, fresh.levels);
    for (const k of ["countyVintage", "countyFields", "countiesOffMap", "countyCells", "cityCells", "stateCells"]) data[k] = fresh[k];
    data.nation.v.population = fresh.nation.v.population;
    data.nation.populationIsSum = fresh.nation.populationIsSum;
  }
  for (const name of names) data.extra[name] = app.data[name] ?? null;
  return data;
}
