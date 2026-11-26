// Number formatting for the advisor kit, built on web/js/format.js.
// Formats follow lenses.json / counties.json: int | usd | rsd | eur | pct (0..1 fraction) | float | minutes | years | km2 | text,
// plus a few of our own: money, signed (signed %), lq (×1.23), mw, count, ratio (×4.2).
import { compact, dollars, eur, int, money, pct } from "../../../format.js";
import { fin } from "./util.js";

export { compact, dollars, eur, int, money, pct };

export const signedPct = (g, d = 1) => (fin(g) ? `${g >= 0 ? "+" : "−"}${pct(Math.abs(g), d)}` : "–");

/** The glossary's decimal comma. */
const comma = (s) => String(s).replace(".", ",");

// Counts to three significant figures (1,12 mil. vs 1,11 mil. rather than 1,1 mil. twice).
export function count3(n) {
  if (!fin(n)) return "–";
  const a = Math.abs(n);
  const sig = (d, unit) => `${comma((n / d).toFixed(a / d >= 100 ? 0 : a / d >= 10 ? 1 : 2))} ${unit}`;
  if (a >= 1e12) return sig(1e12, "bil.");
  if (a >= 1e9) return sig(1e9, "mlrd");
  if (a >= 1e6) return sig(1e6, "mil.");
  if (a >= 1e4) return sig(1e3, "hilj.");
  return int(n);
}

export const mw = (v) => {
  if (!fin(v)) return "–";
  if (Math.abs(v) < 10000) return `${int(v)} MW`;
  return `${comma(String(+(v / 1000).toFixed(1)))} GW`; // 2,1 GW, 21 GW
};

/** Full-ish text for a value in a given format (tables, tooltips). */
export function fmtValue(format, v, unit) {
  if (format === "text") return v == null || v === "" ? "–" : String(v);
  if (!fin(v)) return "–";
  switch (format) {
    case "int": case "count": return Math.abs(v) >= 1e6 ? count3(v) : int(v);
    case "usd": return Math.abs(v) >= 1e6 ? money(v) : dollars(v);
    case "eur": return eur(v);
    case "rsd": return dollars(v);
    case "money": return money(v);
    case "pct": return pct(v);
    case "signed": return signedPct(v);
    case "lq": return `×${comma(v.toFixed(2))}`;
    case "ratio": return `×${comma(v.toFixed(1))}`;
    case "minutes": return `${v.toFixed(1)} min`;
    case "years": return `${comma(v.toFixed(1))} god.`;
    case "km2": return `${int(v)} km²`;
    case "mw": return mw(v);
    case "float": return Math.abs(v) >= 100 ? int(v) : comma(Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));
    default:
      if (unit === "MW") return mw(v);
      return Math.abs(v) >= 1e4 ? count3(v) : Math.abs(v) >= 100 ? int(v) : comma(v.toFixed(2));
  }
}

/** Compact text for a table cell, so numbers fit narrow columns: $121K, 9,4 mil., +2,1 %, 12,3 %, 4.210 km². */
export function fmtCell(format, v, unit) {
  if (format === "text") return v == null || v === "" ? "–" : String(v);
  if (!fin(v)) return "–";
  const a = Math.abs(v);
  switch (format) {
    case "int": case "count": return a >= 1e4 ? count3(v) : int(v);
    case "usd": return a >= 1e4 ? `$${count3(v)}` : dollars(v);
    case "eur": return `${count3(v)} €`;
    case "rsd": return dollars(v);
    case "money": return money(v);
    case "km2": return a >= 1e5 ? `${count3(v)} km²` : `${int(v)} km²`;
    case "float": return a >= 1e4 ? count3(v) : fmtValue(format, v, unit);
    default: return fmtValue(format, v, unit);
  }
}

/** Short text for axis ticks and chips. */
export function fmtShort(format, v) {
  if (!fin(v)) return "–";
  const a = Math.abs(v);
  switch (format) {
    case "usd": case "money": case "eur": return a >= 1e4 ? `${count3(v)} €` : eur(v);
    case "rsd": return dollars(v);
    case "pct": return pct(v, Math.abs(v) < 0.1 && v !== 0 ? 1 : 0);
    case "signed": return `${v > 0 ? "+" : v < 0 ? "−" : ""}${pct(Math.abs(v), 1)}`;
    case "lq": case "ratio": return `×${comma(String(+v.toFixed(1)))}`;
    case "mw": return mw(v);
    case "minutes": case "years": return String(+v.toFixed(0));
    default: return Math.abs(v) >= 1000 ? compact(v) : comma(+v.toPrecision(3));
  }
}

/** Parse "1,5 mil.", "50.000", "12,3 %", "80K", "−3 %" into a number in the field's units (pct → fraction). Serbian
 * numbers: dot groups thousands, comma is the decimal mark; when both appear the last one is decimal. */
export function parseNum(text, format) {
  if (text == null) return null;
  let s = String(text).trim().replace(/^−/, "-")
    .replace(/\b(hilj|mil|mlrd)\.?/gi, (w) => ({ hilj: "k", mil: "m", mlrd: "b" })[w.toLowerCase().replace(".", "")])
    .replace(/RSD|€|\$/gi, "").replace(/\s+/g, "");
  if (!s) return null;
  let isPct = false;
  if (s.endsWith("%")) { isPct = true; s = s.slice(0, -1); }
  const lastDot = s.lastIndexOf("."), lastComma = s.lastIndexOf(",");
  if (lastDot >= 0 && lastComma >= 0) {
    s = lastDot > lastComma ? s.replace(/,/g, "") : s.replace(/\./g, "").replace(/,/g, ".");
  } else if (lastDot >= 0) {
    const groups = s.split(".");
    const thousands = groups.length > 1 && groups[0] !== "0" && groups.slice(1).every((g) => g.length === 3);
    if (thousands) s = groups.join("");
  } else if (lastComma >= 0) {
    s = s.replace(/,/g, ".");
  }
  const m = /^(-?\d*\.?\d+)([kmbt]?)$/i.exec(s);
  if (!m) return null;
  let v = parseFloat(m[1]) * ({ "": 1, k: 1e3, m: 1e6, b: 1e9, t: 1e12 })[m[2].toLowerCase()];
  if ((format === "pct" || format === "signed") && (isPct || Math.abs(v) > 1)) v /= 100;
  return v;
}
