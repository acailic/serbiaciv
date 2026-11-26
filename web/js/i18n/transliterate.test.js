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
  assert.equal(PROTECTED.length, 20);
  assert.equal(toCyrillic("Podaci ESA WorldCover 2021"), "Подаци ESA WorldCover 2021");
  // every protected name survives a sentence on its own
  for (const name of PROTECTED) assert.equal(toCyrillic(`izvor ${name} i BDP`), `извор ${name} и БДП`, name);
});

test("PROTECTED lists the twenty names the pipeline protects", () => {
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
