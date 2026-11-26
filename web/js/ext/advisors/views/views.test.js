// The views' pure helpers and the registry, plus a static pass over the advisors' sources (Serbian Latin only, no
// retired US data columns) and a check of the Explorer's presets against the real web/data files.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { ADVISORS } from "../index.js";
import { NACE_KEYS, LAND_KEYS, buildData } from "../core/data.js";
import { fmtValue, fmtCell, fmtShort, parseNum, signedPct, count3 } from "../core/fmt.js";
import { NULL_NOTE, vintageNote, offMapNote, peopleCaveats, KIM_NOTE } from "../core/notes.js";
import { JOB_GROUPS, jobShare, nationalShares, lq, groupShares } from "./economy.js";
import { weightedShare } from "./knowledge.js";
import { weightedShare as weightedShareCulture, ruleTitle, metricText, blockShares } from "./culture.js";
import { paxOf, paxPrevOf, cargoOf, linkCounts } from "./commerce.js";
import { GROUPS, sizeText, powerByState } from "./energy.js";
import { nationalLand, reliefShares, farmShare } from "./land.js";
import { SHORT, DEFAULT_COLS, DEFAULT_XY } from "./explorer.js";
import { JOBS, makeApp } from "../core/fixtures/synthetic.js";

const CYR = /[\u0400-\u04ff]/;
const sources = readdirSync(new URL("../", import.meta.url), { recursive: true })
  .map(String).filter((p) => p.endsWith(".js") && !p.endsWith(".test.js") && !p.includes("fixtures"))
  .map((p) => [p, readFileSync(new URL(`../${p}`, import.meta.url), "utf8")]);

test("the council lists the nine Serbian advisors; military is gone", () => {
  assert.deepEqual(ADVISORS.map((a) => a.id), ["economy", "prosperity", "commerce", "energy", "people", "knowledge", "culture", "land", "explorer"]);
  for (const a of ADVISORS) {
    for (const k of ["name", "role", "blurb"]) assert.ok(a[k] && !CYR.test(a[k]), `${a.id}.${k}`);
    assert.ok(a.blurb.endsWith("."), `${a.id} blurb is a sentence`);
    assert.match(a.color, /^#[0-9a-f]{6}$/);
  }
  assert.equal(ADVISORS.find((a) => a.id === "explorer").name, "Istraživač");
  assert.equal(ADVISORS.find((a) => a.id === "commerce").name, "Saobraćaj i veze");
});

test("sources: Serbian Latin only, no Cyrillic, no 'Turn', no retired US data columns", () => {
  const retired = /\b(median_income|rent_burden|home_value|veterans|armed_forces|installations|NAICS|FAF5|FEMA|IPEDs|MIRTA|qcew_|encampment|def_|mil_)\b/i;
  for (const [p, text] of sources) {
    assert.ok(!CYR.test(text), `${p} contains Cyrillic`);
    assert.ok(!/\bTurn\b/.test(text), `${p} says "Turn" (the word is "Potez")`);
    assert.ok(!retired.test(text), `${p} mentions a retired US column: ${text.match(retired)?.[0]}`);
    assert.ok(!/military/i.test(text.replace(/\/\/.*$/gm, "")), `${p} still refers to military`);
  }
  assert.ok(sources.some(([p]) => p.endsWith("views/explorer.js")));
  assert.ok(!sources.some(([p]) => /military/.test(p)));
});

test("economy: job groups cover the 19 NACE sections once; shares, national shares and location quotients stay null without a block", () => {
  const all = JOB_GROUPS.flatMap((g) => g.keys);
  assert.equal(all.length, 19);
  assert.deepEqual([...all].sort(), [...NACE_KEYS].sort());
  for (const g of JOB_GROUPS) assert.ok(g.label && !CYR.test(g.label) && /^#[0-9a-f]{6}$/.test(g.color));
  const d = buildData(makeApp());
  const bg = d.levels.states.byKey.get("RS110");
  assert.equal(jobShare(bg, "manufacturing"), 300 / 19000);
  assert.equal(jobShare(d.levels.states.byKey.get("RS123"), "manufacturing"), null);
  assert.equal(jobShare({ v: { jobs_manufacturing: 1, jobs_total: 0 } }, "manufacturing"), null);
  const nat = nationalShares(d.levels.states.rows);
  assert.equal(nat.manufacturing, 300 / 19000); // only Beogradski has a complete block
  assert.equal(nat.agriculture, 100 / 19000);
  assert.equal(lq(bg, "manufacturing", nat), 1);
  assert.equal(lq(bg, "manufacturing", { manufacturing: null }), null);
  const g = groupShares(bg);
  assert.ok(Math.abs(Object.values(g).reduce((a, b) => a + b, 0) - 1) < 1e-12);
  assert.equal(g.industry, (200 + 300 + 400 + 500) / 19000);
  assert.equal(groupShares(d.levels.states.byKey.get("RS231")).industry, null);
  assert.deepEqual(nationalShares([]), Object.fromEntries(NACE_KEYS.map((k) => [k, null])));
});

test("knowledge and culture: population-weighted shares skip rows without a value", () => {
  const d = buildData(makeApp());
  const rows = d.levels.metros.rows;
  assert.equal(weightedShare(rows, "edu_higher"), (350000 / 1500000 * 1681470 + 104136 / 310136 * 320000) / (1681470 + 320000));
  assert.equal(weightedShare(rows, "rel_orthodox"), 1550000 / 1681470); // Novi Sad has no religion block
  assert.equal(weightedShare(rows, "nope"), null);
  assert.equal(weightedShare([], "edu_higher"), null);
  assert.equal(weightedShareCulture(rows, "eth_madjari"), 5000 / 1681470);
  assert.equal(ruleTitle({ id: "national_park" }), "Nacionalni parkovi");
  assert.equal(ruleTitle({ id: "x", name: "Ime iz datoteke" }), "Ime iz datoteke");
  assert.equal(ruleTitle({ id: "custom" }), "custom");
  assert.equal(ruleTitle(null), "");
  assert.equal(metricText({ metrics: null }), "–");
  assert.equal(metricText({ metrics: { area_km2: 395.6 } }), "396 km²");
  assert.equal(metricText({ metrics: { visits: 1234567 } }), "1,23 mil. poseta");
  assert.equal(metricText({ metrics: { students: 42000 } }), "42,0 hilj. studenata");
  assert.equal(metricText({ metrics: { designated: 1979 } }), "spomenik od 1979.");
  const bg = rows[0];
  const b = blockShares(bg, "eth", ["srbi", "madjari", "bosnjaci", "romi"]);
  assert.equal(b.srbi, 1550000 / 1681470);
  assert.equal(b.bosnjaci, null);
  assert.ok(Math.abs(b.other - (1 - (1550000 + 5000 + 20000) / 1681470)) < 1e-12);
  assert.deepEqual(blockShares(rows[1], "rel", ["orthodox"]), { orthodox: null, other: null });
});

test("commerce: upstream airport fields, cargo units and link counts", () => {
  assert.equal(paxOf({ enplanements: 10, passengers: 20 }), 10);
  assert.equal(paxOf({ passengers: 20 }), 20);
  assert.equal(paxOf(null), null);
  assert.equal(paxPrevOf({ enplanements_prev: 9 }), 9);
  assert.deepEqual(cargoOf({ cargo_lbs: 1000 }), { v: 1000, unit: "lb" });
  assert.deepEqual(cargoOf({ cargo_t: 5 }), { v: 5, unit: "t" });
  assert.deepEqual(cargoOf({ cargo_kg: 5 }), { v: 5, unit: "kg" });
  assert.equal(cargoOf({}), null);
  assert.deepEqual(Array.from(linkCounts([[0, 1, 2], [1, 2, 2], [2, 3, 0]])), [1, undefined, 2]);
  assert.deepEqual(linkCounts(null), []);
});

test("energy: Serbian groups, size text per unit, capacity per okrug", () => {
  assert.deepEqual(GROUPS.map((g) => g.id), ["thermal", "water", "renew", "mines", "plays"]);
  for (const g of GROUPS) assert.ok(!CYR.test(g.label) && g.types.length);
  const types = new Map([["hydro", { unit: "MW" }], ["coal_mine", { unit: "employees" }], ["copper", { unit: "tons" }], ["gold", { unit: "kg" }]]);
  assert.equal(sizeText({ type: "hydro", value: 2100 }, types), "2.100 MW");
  assert.equal(sizeText({ type: "hydro", value: 21000 }, types), "21 GW");
  assert.equal(sizeText({ type: "hydro", value: 15400 }, types), "15,4 GW");
  assert.equal(sizeText({ type: "coal_mine", value: 1500 }, types), "1.500 zaposlenih");
  assert.equal(sizeText({ type: "copper", value: 25000000 }, types), "25,0 mil. t godišnje");
  assert.equal(sizeText({ type: "coal_mine", value: 22000000 }, new Map([["coal_mine", { unit: "t/god" }]])), "22,0 mil. t godišnje"); // Serbia's unit
  assert.equal(sizeText({ type: "gold", value: 12.5 }, types), "12,5");
  assert.equal(sizeText({ type: "gold", value: null }, types), "–");
  const items = [{ type: "hydro", value: 100, state: "RS110" }, { type: "hydro", value: 50, state: "RS110" }, { type: "coal_mine", value: 999, state: "RS110" }, { type: "wind", value: 30 }];
  const idx = new Map([["RS110", 0], ["RS123", 1]]);
  const by = powerByState(items, (it) => idx.get(it.state), new Set(["hydro", "wind"]));
  assert.deepEqual(by.get(0), { total: 150, by_type: { hydro: 150 }, n: 2 });
  assert.equal(by.has(1), false);
});

test("land: national cover weighted by area, relief shares, who works the land", () => {
  const d = buildData(makeApp());
  const nat = nationalLand(d.levels.states);
  assert.ok(Math.abs(nat.forest - (0.378 * 3612 + 0.2 * 697.9 + 0.493 * 350) / (3612 + 697.9 + 350)) < 1e-12);
  assert.deepEqual(nationalLand({ rows: [{ v: { land_km2: null } }] }), Object.fromEntries(LAND_KEYS.map((k) => [k, null])));
  assert.deepEqual(reliefShares([0, 1, 2, 5], [0, 1, null, 9, -1, 1]), [1 / 3, 2 / 3, 0, 0]);
  assert.deepEqual(reliefShares([7], [null]), [null, null, null, null]);
  assert.equal(farmShare(d.levels.states.byKey.get("RS110")), 100 / 19000);
  assert.equal(farmShare(d.levels.states.byKey.get("RS231")), null);
});

test("fmt: Serbian numbers, every null as an en dash, Serbian input parsing", () => {
  for (const f of ["text", "int", "pct", "signed", "float", "rsd", "eur", "km2", "mw", "lq"]) {
    assert.equal(fmtValue(f, null), "–", f);
    assert.equal(fmtCell(f, undefined), "–", f);
    assert.equal(fmtShort(f, NaN), "–", f);
  }
  assert.equal(fmtValue("pct", 0.1234), "12,3 %");
  assert.equal(fmtValue("signed", -0.0043), "−0,4 %");
  assert.equal(signedPct(0.0123), "+1,2 %");
  assert.equal(signedPct(0), "+0,0 %");
  assert.equal(fmtValue("rsd", 151304.62), "151.305 RSD");
  assert.equal(fmtCell("rsd", 151304.62), "151.305 RSD");
  assert.equal(fmtValue("eur", 75180030000), "75,2 mlrd €");
  assert.equal(fmtCell("eur", 75180030000), "75,2 mlrd €");
  assert.equal(fmtValue("eur", 12180), "12,2 hilj. €");
  assert.equal(fmtValue("int", 1681470), "1,68 mil.");
  assert.equal(fmtValue("int", 523), "523");
  assert.equal(fmtValue("float", 76.5), "76,5");
  assert.equal(fmtValue("float", -4.2), "-4,20"); // two decimals below 10, a plain minus sign as in format.js
  assert.equal(fmtValue("km2", 88657.4), "88.657 km²");
  assert.equal(fmtValue("lq", 1.2345), "×1,23");
  assert.equal(fmtShort("signed", -0.0043), "−0,4 %");
  assert.equal(fmtShort("eur", 75180030000), "75,2 mlrd €");
  assert.equal(count3(123456), "123 hilj.");
  assert.equal(count3(2401690), "2,40 mil.");
  assert.equal(parseNum("50.000", "int"), 50000);
  assert.equal(parseNum("1,5", "float"), 1.5);
  assert.equal(parseNum("1.234.567", "int"), 1234567);
  assert.equal(parseNum("0.123", "float"), 0.123);
  assert.equal(parseNum("1.234,5", "int"), 1234.5);
  assert.equal(parseNum("12,345.6", "int"), 12345.6);
  assert.equal(parseNum("25 %", "pct"), 0.25);
  assert.ok(Math.abs(parseNum("12,3 %", "signed") - 0.123) < 1e-12);
  assert.equal(parseNum("−3 %", "signed"), -0.03);
  assert.equal(parseNum("25", "pct"), 0.25); // a bare number above 1 is read as percent
  assert.equal(parseNum("0.25", "pct"), 0.25);
  assert.equal(parseNum("109.462 RSD", "rsd"), 109462);
  assert.equal(parseNum("50 hilj.", "int"), 50000);
  assert.equal(parseNum("1,5 mil.", "eur"), 1.5e6);
  assert.equal(parseNum("80K", "int"), 80000);
  assert.equal(parseNum("1.5M", "int"), 1.5e6);
  assert.equal(parseNum("abc", "int"), null);
  assert.equal(parseNum("", "int"), null);
  assert.equal(parseNum(null, "int"), null);
});

test("notes: every caveat is Serbian and explains the dash", () => {
  const d = buildData(makeApp());
  assert.match(NULL_NOTE, /^„–“ znači da izvor ne objavljuje/);
  assert.match(KIM_NOTE, /Za Kosovo i Metohiju nema podataka/);
  assert.equal(vintageNote(d), "Podaci za opštine su iz izdanja „Procene RZS 2025 · Popis 2022“; podaci za okruge i gradove iz izdanja „Procene RZS 2025 · Popis 2022“.");
  assert.equal(offMapNote(d), "1 opština je manja od jednog heksa (Vračar), pa se na karti ne može označiti; u tabelama i grafikonima je.");
  assert.equal(offMapNote({ levels: { counties: null } }), "");
  assert.match(offMapNote({ levels: { counties: { rows: [{ name: "A", cells: [] }, { name: "B", cells: [] }, { name: "C", cells: [] }, { name: "D", cells: [] }, { name: "E", cells: [] }] } } }), /^5 opština je manje od jednog heksa/);
  const caveats = peopleCaveats(d);
  assert.equal(caveats[0], NULL_NOTE);
  assert.equal(caveats[1], KIM_NOTE);
  for (const c of caveats) assert.ok(c.endsWith(".") && !CYR.test(c));
});

test("explorer: presets and short headers exist in the real Serbian data", async () => {
  const read = (f) => JSON.parse(readFileSync(new URL(`../../../../data/${f}`, import.meta.url), "utf8"));
  const app = makeApp({ extra: { world: read("world.json"), cities: read("cities.json"), states: read("states.json"), nation: read("nation.json"), lenses: read("lenses.json"), sources: read("sources.json"), counties: read("counties.json"), "lens-values": read("lens-values.json") } });
  app.w = { raw: app.data.world, grid: { R: 5, size: app.data.world.owner.length } };
  app.lensById = new Map(app.data.lenses.lenses.map((l) => [l.id, l]));
  app.cityById = new Map(app.data.cities.map((c) => [c.id, c]));
  const d = buildData(app);
  assert.equal(d.levels.states.rows.length, 30);
  assert.equal(d.levels.metros.rows.length, 52);
  assert.equal(d.levels.counties.rows.length, 197);
  for (const lv of ["states", "metros", "counties"]) {
    const keys = new Set(d.levels[lv].fields.map((f) => f.key));
    for (const k of DEFAULT_COLS[lv]) assert.ok(keys.has(k), `${lv} default column ${k}`);
    const xy = DEFAULT_XY[lv];
    for (const k of [xy.x, xy.y, xy.s, xy.c]) assert.ok(keys.has(k) && d.levels[lv].field(k).format !== "text", `${lv} axis ${k}`);
  }
  const all = new Set(Object.values(d.levels).flatMap((lv) => lv.fields.map((f) => f.key)));
  for (const k of Object.keys(SHORT)) assert.ok(all.has(k), `SHORT header for unknown column ${k}`);
  for (const [k, v] of Object.entries(SHORT)) assert.ok(!CYR.test(v), k);
  // The real data keeps Kosovo null and never zeroes it.
  const kim = d.levels.states.rows.filter((r) => r.kim);
  assert.equal(kim.length, 5);
  assert.ok(kim.every((r) => r.v.population === null && r.v.gdp === null && r.v.jobs_total === null));
  const kc = d.levels.counties.rows.filter((r) => r.kim);
  assert.equal(kc.length, 29);
  assert.ok(kc.every((r) => r.v.population === null && r.v.wage_net === null));
  assert.equal(d.levels.states.byKey.get("RS231").v.population, null); // Kosovski okrug
  assert.equal(d.levels.counties.byKey.get("90042").v.population, null); // Gnjilane
  assert.equal(d.countiesOffMap, 7);
  assert.ok(d.levels.counties.rows.filter((r) => !r.kim).every((r) => typeof r.v.okrug === "string" && r.v.okrug.length > 0)); // parent okrug column
  assert.ok(d.levels.metros.rows.every((r) => typeof r.v.okrug === "string" && r.v.okrug.length > 0));
});

test("fixture: JOBS is complete, as the test above assumes", () => {
  assert.equal(Object.values(JOBS).reduce((a, b) => a + b, 0), 19000);
});
