// web/js/i18n/transliterate.js against the corpus of tests/test_srtext.py (which also checks that the two PROTECTED
// lists agree). Run: node --test web/js/i18n/
import { test } from "node:test";
import assert from "node:assert/strict";
import { toCyrillic, toLatin, fold, PROTECTED } from "./transliterate.js";

// The same corpus as the pipeline's tests.
const GLOSSARY = {
  prinos: "принос", sočivo: "сочиво", heks: "хекс", građani: "грађани", kvart: "кварт",
  čudo: "чудо", savetnik: "саветник", Almanah: "Алманах", resurs: "ресурс", poboljšanje: "побољшање",
  okrug: "округ", opština: "општина", naselje: "насеље", "nema podataka": "нема података",
  izvor: "извор", prestonica: "престоница", Proizvodnja: "Производња", Nauka: "Наука",
  Kultura: "Култура", Zlato: "Злато", Hrana: "Храна",
};
const HARD_CASES = {
  Ljubljana: "Љубљана", injekcija: "ињекција", Njujork: "Њујорк", gde: "где", đerdap: "ђердап",
  Đerdap: "Ђердап", džamija: "џамија", LJUBAV: "ЉУБАВ", "Novi Sad": "Нови Сад", Niš: "Ниш",
  Beograd: "Београд", Šumadija: "Шумадија", Vojvodina: "Војводина", Mađarska: "Мађарска",
  Hrvatska: "Хрватска", Zvečan: "Звечан", "Kosovsko-mitrovačka": "Косовско-митровачка", "Severna Makedonija": "Северна Македонија",
};
const TWENTY_NAMES = [
  "AWS", "COG", "Copernicus", "ESA", "ESA WorldCover", "Eurostat", "GISCO", "GLO-30", "GeoJSON", "GitHub", "NACE",
  "Natural Earth", "OpenStreetMap", "OurAirports", "Overpass", "UNESCO", "USGS", "Wikidata", "WRI", "geoBoundaries",
  // licenses, publishers and product names that web/data prints
  "CC BY 4.0", "CC BY-SA 4.0", "Copernicus DEM", "Geofabrik", "Minerals Yearbook", "MIT", "ODbL", "Open Database License",
  "OpenStreetMap contributors", "U.S. Geological Survey", "XKX", "public domain", "serbiaciv",
];

test("every glossary term and hard case becomes Cyrillic", () => {
  for (const [latin, cyrillic] of Object.entries({ ...GLOSSARY, ...HARD_CASES })) {
    assert.equal(toCyrillic(latin), cyrillic, latin);
  }
});

test("Serbian Latin becomes Cyrillic, digraphs and all", () => {
  assert.equal(toCyrillic("Ljubljana"), "Љубљана");
  assert.equal(toCyrillic("injekcija"), "ињекција");
  assert.equal(toCyrillic("Njujork"), "Њујорк");
  assert.equal(toCyrillic("Đerdap"), "Ђердап");
  assert.equal(toCyrillic("LJUBAV"), "ЉУБАВ");
  assert.equal(toCyrillic("123 € (5 km)"), "123 € (5 км)");
});

test("protected names stay Latin and Serbian acronyms do not", () => {
  assert.equal(toCyrillic("Izvor: Eurostat, NACE i OpenStreetMap."), "Извор: Eurostat, NACE и OpenStreetMap.");
  assert.equal(toCyrillic("RZS i BDP"), "РЗС и БДП");
  assert.equal(toCyrillic("MESA"), "МЕСА");
  assert.equal(PROTECTED.length, 33);
  assert.equal(toCyrillic("Podaci ESA WorldCover 2021"), "Подаци ESA WorldCover 2021");
  // every protected name survives a sentence on its own
  for (const name of PROTECTED) assert.equal(toCyrillic(`izvor ${name} i BDP`), `извор ${name} и БДП`, name);
});

test("licenses and foreign names stay Latin", () => {
  assert.equal(toCyrillic("Eurostat: CC BY 4.0; Wikidata: CC0 1.0"), "Eurostat: CC BY 4.0; Wikidata: CC0 1.0");
  assert.equal(toCyrillic("© Evropska unija, 1995–2026, CC BY-SA 4.0"), "© Европска унија, 1995–2026, CC BY-SA 4.0");
  assert.equal(toCyrillic("Open Database License (ODbL) 1.0"), "Open Database License (ODbL) 1.0");
  assert.equal(toCyrillic("Javno dobro (public domain); MIT (licenca projekta)"), "Јавно добро (public domain); MIT (лиценца пројекта)");
  assert.equal(toCyrillic("USGS Minerals Yearbook 2024: Srbija"), "USGS Minerals Yearbook 2024: Србија");
  assert.equal(toCyrillic("izdavač serbiaciv (Geofabrik, U.S. Geological Survey, Copernicus DEM)"),
    "издавач serbiaciv (Geofabrik, U.S. Geological Survey, Copernicus DEM)");
});

test("identifiers stay Latin, and they do not shield Serbian words", () => {
  // dataset codes, NUTS codes, file names, units with letters Serbian has no Cyrillic for, foreign names with them
  const cases = {
    "BDP po oblastima (nama_10r_3gdp), 2023": "БДП по областима (nama_10r_3gdp), 2023",
    "šifra RS110": "шифра RS110",
    "sočivo age65, izdanje v200": "сочиво age65, издање v200",
    "OurAirports: airports.csv": "OurAirports: airports.csv",
    "Natural Earth 1:10m (naciscdn.org)": "Natural Earth 1:10m (naciscdn.org)",
    "Iz pipeline/data/wonders_sites.csv.": "Из pipeline/data/wonders_sites.csv.",
    "serbiaciv-source.zip": "serbiaciv-source.zip",
    "Instalisana snaga 5 MW i 3,9 GW (GWh)": "Инсталисана снага 5 MW и 3,9 GW (GWh)",
    "New York i Wikipedia": "New York и Wikipedia",
    "auto-put E75, deo A3": "ауто-пут E75, део A3",
    // an abbreviation, a date and a unit keep the behaviour they always had
    "i dr. drugi": "и др. други", "npr. nešto": "нпр. нешто", "d.o.o. Beograd": "д.о.о. Београд",
    "(5 km)": "(5 км)", "RZS, SFRJ i BDP": "РЗС, СФРЈ и БДП", "29. 8. 2025": "29. 8. 2025", "MESA": "МЕСА",
  };
  for (const [latin, cyrillic] of Object.entries(cases)) assert.equal(toCyrillic(latin), cyrillic, latin);
});

test("PROTECTED lists the names the pipeline protects", () => {
  assert.deepEqual([...PROTECTED].sort(), [...TWENTY_NAMES].sort());
});

test("nothing is lost on empty and null input", () => {
  assert.equal(toCyrillic(""), "");
  assert.equal(toCyrillic(null), null);
  assert.equal(toLatin(""), "");
  assert.equal(toLatin(null), null);
});

test("Latin comes back exactly, including capital digraphs", () => {
  for (const latin of ["Ljubljana", "injekcija", "Njujork", "Đerdap", "LJUBAV", "Niš", "Kosovsko-mitrovačka"]) {
    assert.equal(toLatin(toCyrillic(latin)), latin);
  }
  assert.equal(toLatin("ЉУБАВ"), "LJUBAV");
  for (const latin of Object.keys({ ...GLOSSARY, ...HARD_CASES })) {
    assert.equal(toLatin(toCyrillic(latin)), latin, latin);
  }
  assert.equal(toLatin("ЊЕГОШ"), "NJEGOŠ");
  assert.equal(toLatin("ЏАЗ"), "DŽAZ");
  // census names as the office prints them
  assert.equal(toLatin("Нишавска област"), "Nišavska oblast");
  assert.equal(toLatin("Косовско-митровачка област"), "Kosovsko-mitrovačka oblast");
  assert.equal(toLatin("Вражегрбац"), "Vražegrbac");
});

test("other scripts pass through untouched", () => {
  assert.equal(toCyrillic("Δελφοί — 東京 — ירושלים"), "Δελφοί — 東京 — ירושלים");
  assert.equal(toCyrillic("Ниш 2021."), "Ниш 2021."); // already Cyrillic: nothing to change
});

test("both scripts fold to one search key", () => {
  assert.equal(fold("Niš"), "nis");
  assert.equal(fold("Ниш"), "nis");
  assert.equal(fold("Đerdap"), "djerdap");
  assert.equal(fold("Kosovsko-mitrovačka"), "kosovsko mitrovacka");
  assert.deepEqual(new Set(["Niš", "nis", "NIS", "Ниш", "НИШ", "  nis ", "nisch"].map(fold)), new Set(["nis", "nisch"]));
  assert.equal(fold("Nišavski okrug"), "nisavski okrug");
  assert.equal(fold(null), "");
});
