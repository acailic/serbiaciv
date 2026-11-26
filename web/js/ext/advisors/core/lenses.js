// Map colourings the advisors add beside the built-in sočiva (lenses.json has population change only by opština,
// and nothing for science jobs). Each is an ordinary lens object ({id, name, ramp, domain, scale, format, values:
// per cell}) that app.setLens() accepts; they are built once per data model and cached, so the lens dock's
// histogram cache stays valid.
import { fin, quantile, robustDomain } from "./util.js";
import { resolveLensValues } from "../../../lensValues.js";

// Diverging: shrinking (brick) ← no change (parchment) → growing (teal). Dark ends so the extremes read on the map.
const GROWTH_RAMP = ["#7a1f2b", "#c2463d", "#e8a07a", "#efe6d2", "#8fcbb8", "#2e9c8a", "#0f5e57"];
const SCIENCE_RAMP = ["#0a1a33", "#173a6b", "#2f63a8", "#4f93d6", "#8cc2ee", "#e4f3ff"];

const cache = new WeakMap();
const builtinCache = new WeakMap(); // data model → (lenses.json sočivo → the same sočivo with its per-cell values)

/**
 * A lenses.json sočivo as app.setLens() needs it: with `values` per cell. Serbia's sočiva carry a value_source
 * (world field or a lens-values.json column) instead of inline values, so the advisor resolves it here, once.
 * null when the sočivo does not exist or its values cannot be resolved (the file has not arrived).
 */
export function builtInLens(data, id) {
  const lens = data?.lensById?.get(id);
  if (!lens) return null;
  if (Array.isArray(lens.values)) return lens;
  let m = builtinCache.get(data);
  if (!m) builtinCache.set(data, (m = new Map()));
  if (!m.has(lens)) {
    let out = null;
    try {
      const src = lens.value_source;
      const world = data.app?.w?.raw;
      if (src?.kind === "world" && world) out = { ...lens, values: resolveLensValues(lens, world) };
      else if (src?.kind === "municipality" && world && data.app?.data?.["lens-values"]) out = { ...lens, values: resolveLensValues(lens, world, data.app.data["lens-values"]) };
    } catch { out = null; }
    m.set(lens, out);
  }
  return m.get(lens);
}

function memo(data, key, make) {
  let m = cache.get(data);
  if (!m) cache.set(data, (m = new Map()));
  if (!m.has(key)) m.set(key, make());
  return m.get(key);
}

const symDomain = (vals, q = 0.03) => {
  const s = vals.filter(fin).map(Math.abs).sort((a, b) => a - b);
  const d = s.length ? quantile(s, 1 - q) : 0.05;
  const r = Math.max(0.005, Math.round(d * 200) / 200); // to half a percent
  return [-r, r];
};

/** The years of the growth estimate, "2021–2025", or "" when the records do not say. */
export function growthYears(rows) {
  const y = rows.map((r) => r.ref?.growth_years).find((a) => Array.isArray(a) && a.length === 2 && a.every(fin));
  return y ? `${y[0]}–${y[1]}.` : "";
}

/** Science-yield workers (NACE M + J) as a share of the employed residents of a row. */
export const scienceShare = (r) => (fin(r?.v?.jobs_science) && fin(r?.v?.employed) && r.v.employed > 0 ? r.v.jobs_science / r.v.employed : null);

/** Population change per hex, by okrug or by grad (hexes outside the cities stay grey). */
export function growthLens(data, by = "metros") {
  return memo(data, `growth-${by}`, () => {
    const n = data.app.w.grid.size, owner = data.app.w.raw.owner;
    const values = new Array(n).fill(null);
    const rows = data.levels[by].rows;
    const yrs = growthYears(rows);
    let vals;
    if (by === "states") {
      for (let i = 0; i < n; i++) if (owner[i] >= 0) values[i] = rows[owner[i]]?.v.growth ?? null;
      vals = rows.map((r) => r.v.growth);
    } else {
      const byKey = data.levels.metros.byKey;
      for (const [cell, city] of data.cityCells) if (owner[cell] >= 0) values[cell] = byKey.get(city.id)?.v.growth ?? null;
      vals = rows.map((r) => r.v.growth);
    }
    return {
      id: `adv-growth-${by}`, group: "people", name: by === "states" ? "Promena broja stanovnika po okruzima" : "Promena broja stanovnika po gradovima",
      icon: "l-pop_change", emoji: "📈", unit: "promena broja stanovnika", format: "pct", scale: "linear",
      domain: symDomain(vals), ramp: GROWTH_RAMP, higher_is: "neutral", source: "rzs_db",
      description: by === "states"
        ? `Procenjeni broj stanovnika okruga prema proceni za 2025. godinu u odnosu na raniju procenu, ${yrs} (Republički zavod za statistiku).`
        : `Procenjeni broj stanovnika grada prema proceni za 2025. godinu u odnosu na raniju procenu, ${yrs} (Republički zavod za statistiku). Sivi heksovi su van gradova.`,
      note: "Za Kosovo i Metohiju nema podataka.",
      values,
    };
  });
}

/** Science-yield workers as a share of employed residents, per grad (other hexes grey). */
export function scienceLens(data) {
  return memo(data, "science", () => {
    const n = data.app.w.grid.size, owner = data.app.w.raw.owner;
    const values = new Array(n).fill(null);
    const rows = data.levels.metros.rows;
    const byKey = data.levels.metros.byKey;
    for (const [cell, city] of data.cityCells) if (owner[cell] >= 0) values[cell] = scienceShare(byKey.get(city.id));
    const sci = data.yields?.find((y) => y.key === "science");
    return {
      id: "adv-science-share", group: "work", name: "Zaposleni u nauci",
      icon: "l-education", emoji: "🔬", unit: "od zaposlenih stanovnika", format: "pct", scale: "linear",
      domain: robustDomain(rows.map(scienceShare)), ramp: SCIENCE_RAMP, higher_is: "neutral", source: "census",
      description: `${sci?.label || "Nauka"}: zaposleni u stručnim, naučnim i tehničkim delatnostima i u informisanju (NACE M i J) kao udeo zaposlenih stanovnika grada, prema prebivalištu (Popis 2022). Sivi heksovi su van gradova.`,
      values,
    };
  });
}

/**
 * An opština column as a map lens (each hex takes the value of the opština at its centre). For counties.json
 * columns that have no lens in lenses.json. opts: {name, ramp, format, unit, description, source, emoji, icon,
 * group, domain?, note}
 */
export function countyLens(data, key, opts = {}) {
  return memo(data, `county-${key}`, () => {
    const lv = data.levels.counties;
    const n = data.app.w.grid.size;
    const values = new Array(n).fill(null);
    if (lv) for (let i = 0; i < n; i++) { const r = lv.rowAtCell(i); const v = r ? r.v[key] : null; if (fin(v)) values[i] = v; }
    const f = lv?.field(key);
    const built = data.lensById?.get(opts.lens ?? LENS_BY_KEY[key] ?? "");
    return {
      id: `adv-county-${key}`, group: opts.group || "people", name: opts.name || built?.name || f?.label || key,
      icon: opts.icon || built?.icon || "layers", emoji: opts.emoji || built?.emoji || "🗺️", unit: opts.unit || built?.unit || f?.unit || "",
      format: opts.format || f?.format || "float",
      scale: "linear", domain: opts.domain || built?.domain || robustDomain(lv ? lv.rows.map((r) => r.v[key]) : []),
      ramp: opts.ramp || built?.ramp || SCIENCE_RAMP,
      higher_is: f?.higher_is || "neutral", source: opts.source || f?.source || "", description: opts.description || built?.description || f?.description || "",
      note: opts.note || built?.note || "",
      values,
    };
  });
}

// counties.json column → the lenses.json lens that draws it (the lens has the map's own colours and domain).
export const LENS_BY_KEY = {
  density: "density", growth: "pop_change", natural_increase: "natural_increase", age65: "age65", education: "education",
  wage_net: "wages", unemployment: "unemployment", manufacturing: "manufacturing", commute: "commute", orthodox: "orthodox",
  serbs: "serbs", life_expectancy: "life_expectancy",
};

/** A per-okrug value as a map lens. valueOf(row) → number | null. opts as countyLens plus id. */
export function stateLens(data, id, valueOf, opts = {}) {
  return memo(data, `state-${id}`, () => {
    const n = data.app.w.grid.size, owner = data.app.w.raw.owner;
    const rows = data.levels.states.rows;
    const byIdx = rows.map((r) => valueOf(r));
    const values = new Array(n).fill(null);
    for (let i = 0; i < n; i++) if (owner[i] >= 0 && fin(byIdx[owner[i]])) values[i] = byIdx[owner[i]];
    return {
      id: `adv-state-${id}`, group: opts.group || "people", name: opts.name || id, icon: opts.icon || "layers", emoji: opts.emoji || "🗺️",
      unit: opts.unit || "", format: opts.format || "float", scale: "linear", domain: opts.domain || robustDomain(byIdx),
      ramp: opts.ramp || SCIENCE_RAMP, higher_is: opts.higher_is || "neutral", source: opts.source || "", description: opts.description || "",
      note: opts.note || "",
      values,
    };
  });
}

/** A per-city value as a map lens (each city's hexes take the city's value). valueOf(row) → number | null. */
export function metroLens(data, id, valueOf, opts = {}) {
  return memo(data, `metro-${id}`, () => {
    const n = data.app.w.grid.size, owner = data.app.w.raw.owner;
    const values = new Array(n).fill(null);
    const byKey = data.levels.metros.byKey;
    for (const [cell, city] of data.cityCells) {
      const v = valueOf(byKey.get(city.id));
      if (owner[cell] >= 0 && fin(v)) values[cell] = v;
    }
    return {
      id: `adv-metro-${id}`, group: opts.group || "people", name: opts.name || id, icon: opts.icon || "layers", emoji: opts.emoji || "🗺️",
      unit: opts.unit || "", format: opts.format || "float", scale: "linear", domain: opts.domain || robustDomain(data.levels.metros.rows.map(valueOf)),
      ramp: opts.ramp || SCIENCE_RAMP, higher_is: opts.higher_is || "neutral", source: opts.source || "", description: opts.description || "",
      note: opts.note || "",
      values,
    };
  });
}
