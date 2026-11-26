// The advisors' data model on a small synthetic Serbia (core/fixtures/synthetic.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildData, extendData, blockValues, censusShares, growthLabel, isKim, rowsHighlight, NACE_KEYS, METRO_MIN, BIG_METRO_MIN } from "./data.js";
import { JOBS, counties, makeApp } from "./fixtures/synthetic.js";

test("three levels with the Serbian nouns and the upstream row/field API", () => {
  const data = buildData(makeApp());
  assert.deepEqual(data.order, ["states", "metros", "counties"]);
  assert.equal(data.levels.states.rows.length, 3);
  assert.equal(data.levels.metros.rows.length, 2);
  assert.equal(data.levels.counties.rows.length, 4);
  for (const [id, label, many] of [["states", "Okrug", "okruga"], ["metros", "Grad", "gradova"], ["counties", "Opština", "opština"]]) {
    const lv = data.levels[id];
    assert.equal(lv.label, label);
    assert.equal(lv.many, many);
    assert.equal(typeof lv.field, "function");
    assert.equal(typeof lv.rowAtCell, "function");
    assert.equal(typeof lv.focus, "function");
    assert.equal(typeof lv.value, "function");
    assert.ok(lv.byKey instanceof Map);
    for (const f of lv.fields) assert.ok(!/[\u0400-\u04ff]/.test(f.label), `${f.key} label must be Latin`);
    for (const r of lv.rows) assert.equal(lv.byKey.get(r.key), r);
  }
  assert.equal(data.levels.states.field("wage_net").format, "rsd");
  assert.equal(data.levels.states.field("gdp").format, "eur");
  assert.equal(data.levels.states.field("growth").label, "Promena broja stanovnika 2021–2025");
  assert.equal(data.levels.counties.field("okrug").format, "text");
  assert.equal(data.levels.metros.field("okrug").group, "Opšte");
  assert.equal(data.levels.states.field("nope"), null);
  assert.equal(data.levels.states.value(data.levels.states.rows[0], "gdp"), 32418650000);
  assert.equal(data.levels.states.value(data.levels.states.rows[2], "gdp"), null);
});

test("Kosovo rows exist with null statistics: never dropped, never zero", () => {
  const data = buildData(makeApp());
  const kim = data.levels.states.byKey.get("RS231");
  assert.ok(kim && kim.kim);
  assert.equal(kim.name, "Kosovski okrug");
  for (const k of ["population", "employed", "gdp", "gdp_pc", "unemployment", "wage_net", "age65", "growth", "density", "jobs_total", "jobs_agriculture", "yield_gold", ...NACE_KEYS.map((j) => `jobs_${j}`)]) assert.equal(kim.v[k], null, k);
  assert.equal(kim.v.land_forest, 0.493); // land cover exists for Kosovo
  const kc = data.levels.counties.byKey.get("90001");
  assert.ok(kc && kc.kim);
  for (const k of ["population", "education", "wage_net", "unemployment", "orthodox", "serbs", "life_expectancy", "natural_increase", "growth", "density"]) assert.equal(kc.v[k], null, k);
  assert.equal(kc.v.land_forest, 0.4);
  assert.equal(isKim({ state: "RS235" }), true);
  assert.equal(isKim({ fips: "RS110" }), false);
  assert.equal(data.kimNote, "Za Kosovo i Metohiju nema podataka: Republički zavod za statistiku ne objavljuje statistiku za te okruge i opštine, pa su njihova polja prazna.");
});

test("a null in the source stays null (Južnobački population, Novi Sad opština) and derived values follow", () => {
  const data = buildData(makeApp());
  const jb = data.levels.states.byKey.get("RS123");
  assert.equal(jb.v.population, null);
  assert.equal(jb.v.gdp, 8065190000);
  assert.equal(jb.v.gdp_pc, null); // no population → no per-capita
  assert.equal(jb.v.jobs_total, null);
  assert.equal(jb.v.jobs_science, null);
  assert.equal(jb.v.land_km2, 697.9); // summed from its opština
  assert.equal(jb.v.density, null);
  const ns = data.levels.counties.byKey.get("80284");
  assert.equal(ns.v.population, null);
  assert.equal(ns.v.density, null);
  assert.equal(ns.v.wage_net, 126469);
  assert.equal(ns.v.growth, -0.03); // lens-values.json pop_change
  assert.equal(ns.v.natural_increase, 0); // a real zero is kept
  assert.equal(ns.v.okrug, "Južnobački okrug");
  const bg = data.levels.states.byKey.get("RS110");
  assert.equal(bg.v.gdp_pc, 32418650000 / 1681470);
  assert.equal(bg.v.jobs_total, 19000);
  assert.equal(bg.v.jobs_science, 2300); // information (1 000) + professional (1 300)
  assert.equal(bg.v.land_km2, 3612); // summed from its two opštine
  const vb = data.levels.counties.byKey.get("70001");
  assert.equal(vb.v.growth, 0.01);
  assert.equal(vb.v.education, 0.3);
  assert.equal(vb.v.land_km2, 3600);
  assert.equal(vb.v.density, 416.7);
});

test("cities: census blocks become shares, land cover comes from the hexes, density from the hex area", () => {
  const data = buildData(makeApp());
  const bg = data.levels.metros.byKey.get("79014");
  assert.equal(bg.v.edu_higher, 350000 / 1500000);
  assert.equal(bg.v.education, 350000 / 1500000);
  assert.equal(bg.v.eth_srbi, 1550000 / 1681470);
  assert.equal(bg.v.serbs, 1550000 / 1681470);
  assert.equal(bg.v.rel_orthodox, 1550000 / 1681470);
  assert.equal(bg.v.commute, (40000 + 50000) / 700000);
  assert.equal(bg.v.commute_abroad, 10000 / 700000);
  assert.equal(bg.v.settlement_population, 209763);
  assert.equal(bg.landFromHexes, true);
  assert.ok(Math.abs(bg.v.land_developed - 0.85) < 1e-9); // mean of 90 % and 80 % over cells 0 and 1
  assert.ok(Math.abs(bg.v.land_forest - 0.15) < 1e-9);
  assert.equal(bg.v.land_km2, 2 * (3 * Math.sqrt(3) / 2) * 25);
  assert.ok(Math.abs(bg.v.density - 1681470 / (2 * (3 * Math.sqrt(3) / 2) * 25)) < 1e-9);
  assert.equal(bg.v.jobs_science, 2300);
  assert.equal(bg.sub, "Beogradski okrug");
  assert.equal(bg.v.okrug, "Beogradski okrug");
  assert.equal(bg.kim, false);
  const ns = data.levels.metros.byKey.get("89010");
  assert.equal(ns.v.jobs_total, null); // one NACE key missing → the block does not add up
  assert.equal(ns.v.jobs_science, 2300); // both science keys are present
  assert.equal(ns.v.gdp_pc, null);
  assert.equal(ns.v.education, 104136 / 310136);
  assert.equal(ns.v.orthodox, null); // no religion block → null, not 0
  assert.equal(ns.landFromHexes, false); // no WorldCover share on its hex
});

test("blockValues and censusShares helpers", () => {
  const v = blockValues({ population: 10, gdp: 1000, jobs: { agriculture: 1 }, land: { forest: -1, crop: 0.5 } });
  assert.deepEqual([v.population, v.gdp_pc, v.jobs_agriculture, v.jobs_total, v.land_forest, v.land_crop], [10, 100, 1, null, null, 0.5]);
  const none = blockValues({});
  assert.equal(none.yield_gold, null);
  assert.equal(none.jobs_manufacturing, null);
  assert.equal(none.land_developed, null);
  const c = censusShares(null);
  assert.deepEqual([c.education, c.orthodox, c.serbs, c.settlement_population], [null, null, null, null]);
  assert.equal(growthLabel({ growth_years: [2011, 2025] }), "Promena broja stanovnika 2011–2025");
  assert.equal(growthLabel({}), "Promena broja stanovnika");
});

test("map linking: rowAtCell, highlight, focus and cells", () => {
  const app = makeApp();
  const data = buildData(app);
  const { states, metros, counties } = data.levels;
  assert.equal(states.rowAtCell(0).key, "RS110");
  assert.equal(states.rowAtCell(5).key, "RS231");
  assert.equal(states.rowAtCell(7), null);
  assert.equal(counties.rowAtCell(0).key, "70001");
  assert.equal(counties.rowAtCell(3).key, "80284");
  assert.equal(metros.rowAtCell(0).key, "79014");
  assert.equal(metros.rowAtCell(1).key, "79014");
  assert.equal(metros.rowAtCell(3).key, "89010");
  const h = states.highlight([states.byKey.get("RS110")], { dim: true });
  assert.equal(h.states.size, 1);
  assert.equal(h.dimOthers, true);
  const hm = metros.highlight([metros.byKey.get("79014")]);
  assert.deepEqual([...hm.cells].sort(), [0, 1]);
  assert.deepEqual([...hm.cities], ["79014"]);
  assert.equal(counties.highlight([counties.byKey.get("70002")]), null); // off the map: nothing to light
  assert.equal(data.countiesOffMap, 1);
  assert.deepEqual(states.byKey.get("RS110").cells, [0, 1, 2]);
  states.focus(states.byKey.get("RS110"));
  metros.focus(metros.byKey.get("79014"));
  assert.deepEqual(app.selected, [["state", "RS110"], ["city", "79014"]]);
  const rows = [states.byKey.get("RS110")];
  assert.deepEqual([...rowsHighlight(states, rows).states], [0]); // exported helper: the same shape as level.highlight
  assert.equal(rowsHighlight(states, []), null);
});

test("nation row: population falls back to the sum of opštine, gdp per capita derived", () => {
  const data = buildData(makeApp());
  assert.equal(data.nation.v.population, 1550000);
  assert.equal(data.nation.populationIsSum, true);
  assert.equal(data.nation.v.gdp, 75180030000);
  assert.equal(data.nation.v.gdp_pc, 75180030000 / 1550000);
  assert.equal(data.nation.v.yield_science, null); // nation.json yields are labels here, not values
  assert.equal(data.nation.v.wage_net, 117104.44);
  assert.equal(data.vintage, "Procene RZS 2025 · Popis 2022");
  assert.equal(data.countyVintage, "Procene RZS 2025 · Popis 2022");
  assert.equal(data.hexArea, (3 * Math.sqrt(3) / 2) * 25);
  assert.deepEqual(data.yields.map((y) => y.key), ["science"]);
  assert.equal(data.industries.agriculture, "Poljoprivreda, šumarstvo i ribarstvo");
});

test("source(id) flattens a per-table vintage and returns null for unknown ids", () => {
  const data = buildData(makeApp());
  assert.equal(data.source("census").vintage, "Popis 2022.");
  assert.equal(data.source("rzs_db").vintage, "Procene 1991–2025; Rođeni 2025");
  assert.equal(data.source("nope"), null);
});

test("thresholds mirror yieldReport (50 000 / 200 000) and the fixture covers all 19 NACE keys", () => {
  assert.equal(METRO_MIN, 50000);
  assert.equal(BIG_METRO_MIN, 200000);
  assert.equal(NACE_KEYS.length, 19);
  assert.equal(Object.keys(JOBS).length, 19);
});

test("extendData builds the opštine level once counties.json arrives and loads nothing else by default", async () => {
  const app = makeApp({ withCounties: false });
  const loaded = [];
  app.loadData = async (name) => { loaded.push(name); return app.data[name] ?? null; };
  const data = buildData(app);
  assert.equal(data.levels.counties, null);
  assert.equal(data.nation.v.population, null);
  app.data.counties = counties;
  await extendData(data);
  assert.deepEqual([...new Set(loaded)].sort(), ["counties", "lens-values"]);
  assert.equal(data.levels.counties.rows.length, 4);
  assert.equal(data.levels.counties.byKey.get("70001").v.growth, 0.01);
  assert.equal(data.nation.v.population, 1550000);
  assert.equal(data.extra.military, undefined);
  assert.equal(data.extra.districts, undefined); // no view asks for districts/citizens
});
