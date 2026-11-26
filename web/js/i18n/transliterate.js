// Serbian script helpers for the web app: the mirror of pipeline/core/srtext.py, function for function. Serbian is
// written in both scripts with one letter for each sound, so the conversion is mechanical. Everything in the app and
// in web/data is authored in Serbian Latin; Cyrillic is generated from it at display time (i18n/index.js).
// tests/test_srtext.py checks that the two PROTECTED lists agree.
//
// Run the tests: node --test "web/js/i18n/**/*.test.js"

// --- Latin → Cyrillic ------------------------------------------------------------------------------------------

// Digraphs first, so "lj", "nj" and "dž" never split into two letters.
const L2C_DIGRAPHS = [
  [/DŽ/g, "Џ"], [/Dž/g, "Џ"], [/dž/g, "џ"],
  [/LJ/g, "Љ"], [/Lj/g, "Љ"], [/lj/g, "љ"],
  [/NJ/g, "Њ"], [/Nj/g, "Њ"], [/nj/g, "њ"],
];
const L2C = {
  a: "а", b: "б", c: "ц", č: "ч", ć: "ћ", d: "д", đ: "ђ", e: "е", f: "ф", g: "г", h: "х",
  i: "и", j: "ј", k: "к", l: "л", m: "м", n: "н", o: "о", p: "п", r: "р", s: "с", š: "ш",
  t: "т", u: "у", v: "в", z: "з", ž: "ж",
  A: "А", B: "Б", C: "Ц", Č: "Ч", Ć: "Ћ", D: "Д", Đ: "Ђ", E: "Е", F: "Ф", G: "Г", H: "Х",
  I: "И", J: "Ј", K: "К", L: "Л", M: "М", N: "Н", O: "О", P: "П", R: "Р", S: "С", Š: "Ш",
  T: "Т", U: "У", V: "В", Z: "З", Ž: "Ж",
};
const L2C_RE = new RegExp(`[${Object.keys(L2C).join("")}]`, "g");

// Names written in Latin in both scripts: foreign publishers, products and acronyms. Matched as whole words.
export const PROTECTED = [
  "AWS", "COG", "Copernicus", "ESA", "ESA WorldCover", "Eurostat", "GISCO", "GLO-30", "GeoJSON", "GitHub", "NACE",
  "Natural Earth", "OpenStreetMap", "OurAirports", "Overpass", "UNESCO", "USGS", "Wikidata", "WRI", "geoBoundaries",
];
// Longest name first, so "ESA WorldCover" is never cut short by "ESA". The character before a name is part of the
// match (and is transliterated with the text around it): that states "not preceded by a letter" without a lookbehind,
// which browsers older than Safari 16.4 cannot parse.
const PROTECT_RE = new RegExp(
  `(^|[^A-Za-z])(${[...PROTECTED].sort((a, b) => b.length - a.length).map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(?![A-Za-z])`,
  "g",
);

/** The Latin letters of one unprotected stretch of text, as Cyrillic. */
function latinChunk(part) {
  for (const [re, cyrillic] of L2C_DIGRAPHS) part = part.replace(re, cyrillic);
  return part.replace(L2C_RE, (ch) => L2C[ch]);
}

/** Serbian Latin → Cyrillic. Protected names stay Latin. Other scripts pass through untouched. */
export function toCyrillic(text) {
  if (!text) return text;
  const s = String(text);
  let out = "", last = 0;
  for (const m of s.matchAll(PROTECT_RE)) {
    out += latinChunk(s.slice(last, m.index + m[1].length)) + m[2];
    last = m.index + m[0].length;
  }
  return out + latinChunk(s.slice(last));
}

// --- Cyrillic → Latin ------------------------------------------------------------------------------------------

// One letter at a time. The three Cyrillic digraph letters are handled per word (see toLatin).
const C2L = {
  "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e", "ж": "ž", "з": "z", "и": "i", "ј": "j",
  "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "ć", "у": "u",
  "ф": "f", "х": "h", "ц": "c", "ч": "č", "ш": "š",
  "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I", "Ј": "J",
  "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "Ћ": "Ć", "У": "U",
  "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Ш": "Š",
};
// lower-case letter → Latin digraph; upper-case letter → [mixed-case, all-caps] digraph
const C2L_DIGRAPHS = { "љ": "lj", "њ": "nj", "џ": "dž", "Љ": ["Lj", "LJ"], "Њ": ["Nj", "NJ"], "Џ": ["Dž", "DŽ"] };

// A run of letters, any script: what the pipeline's [^\W\d_] matches (letters, and the letter-like numerals).
const WORD = /[\p{L}\p{Nl}\p{No}]+/gu;
// "Set entirely in capitals", as Python's str.isupper(): at least one letter is cased and every cased one is a
// capital. (A lower-case letter that has no capital form, such as ƫ, is still not a capital.)
const ALL_CAPS = /^(?:\p{Uppercase}|[^\p{Cased}])*\p{Uppercase}(?:\p{Uppercase}|[^\p{Cased}])*$/u;

/** Serbian Cyrillic → Latin. A word of at least two letters set entirely in capitals gets capital digraphs (ЉУБАВ → LJUBAV). */
export function toLatin(text) {
  if (!text) return text;
  const s = String(text);
  let out = "", last = 0;
  for (const m of s.matchAll(WORD)) {
    out += s.slice(last, m.index);
    const chars = [...m[0]];
    const caps = chars.length > 1 && ALL_CAPS.test(m[0]);
    out += chars.map((ch) => {
      const d = C2L_DIGRAPHS[ch];
      return Array.isArray(d) ? d[caps ? 1 : 0] : d ?? C2L[ch] ?? ch;
    }).join("");
    last = m.index + m[0].length;
  }
  return out + s.slice(last);
}

// --- search key ------------------------------------------------------------------------------------------------

/** One search key for both scripts and for typed text without diacritics: lowercase ASCII letters and digits.
 *  The one departure from the pipeline: a combining mark of class 0 (never used in Serbian) is dropped here where
 *  srtext.fold_key keeps it as a separator, since JavaScript has no combining-class data. */
export function fold(text) {
  if (text == null) return "";
  // đ has no accented decomposition, so it is unfolded by hand before the diacritics are stripped.
  const latin = toLatin(String(text)).replace(/đ/g, "dj").replace(/Đ/g, "Dj");
  return latin.normalize("NFD").replace(/\p{M}+/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}
