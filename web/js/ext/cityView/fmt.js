// Number formatting for the City View: format.js's compact helpers with a roll-over fix, so a value that rounds up
// to the next unit reads "1 mil." rather than "1000 hilj." (e.g. 999 960 people). format.js is shared with the rest
// of the app; this wrapper keeps the same output for every other value.
import { compact as baseCompact, money as baseMoney, popShort as basePopShort } from "../../format.js";

const UNITS = [[1e12, "bil."], [1e9, "mlrd"], [1e6, "mil."], [1e3, "hilj."]];

/** Rounds n up to the next unit when its compact form would print 1000 of the current one. */
function rollover(n, fmt) {
  if (n == null || Number.isNaN(n)) return fmt(n);
  const s = fmt(n);
  const m = /^-?1000 (hilj\.|mil\.|mlrd)$/.exec(s);
  if (!m) return s;
  const i = UNITS.findIndex(([, u]) => u === m[1]);
  return fmt(Math.sign(n) * UNITS[i - 1][0]);
}

export const compact = (n) => rollover(n, baseCompact);
export const money = baseMoney; // format.js's: the currency of the map's data (euros for Serbia)
export const yieldValue = (y, v) => (y.unit === "eur" ? money(v) : compact(v));
export const popShort = (n) => rollover(n, basePopShort);
