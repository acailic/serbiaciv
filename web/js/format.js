const missing = (n) => n == null || Number.isNaN(n);
const decimal = (n, digits = 1) => n.toFixed(digits).replace(/\.0+$/, "").replace(".", ",");

export function compact(n) {
  if (missing(n)) return "–";
  const a = Math.abs(n);
  for (const [unit, label] of [[1e12, "bil."], [1e9, "mlrd"], [1e6, "mil."], [1e3, "hilj."]]) {
    if (a >= unit) return `${decimal(n / unit, unit !== 1e3 && a / unit >= 100 ? 0 : 1)} ${label}`;
  }
  return String(Math.round(n));
}

export const int = (n) => missing(n) ? "–" : Math.round(n).toLocaleString("sr-RS");
export const eur = (n) => missing(n) ? "–" : `${compact(n)} €`;
export const rsd = (n) => missing(n) ? "–" : `${int(n)} RSD`;
export const money = eur;
export const dollars = rsd;
export const pct = (x, d = 1) => missing(x) ? "–" : `${(x * 100).toFixed(d).replace(".", ",")} %`;

export function yieldValue(y, v) {
  return y.unit === "eur" ? eur(v) : compact(v);
}

export function popShort(n) {
  if (missing(n)) return "–";
  return Math.abs(n) < 1e6 ? `${decimal(n / 1e3, 0)} hilj.` : compact(n);
}

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
