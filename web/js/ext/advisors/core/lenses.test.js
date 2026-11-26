// The advisor sočiva (core/lenses.js) built per cell from the synthetic Serbian levels.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildData } from "./data.js";
import { growthLens, scienceLens, scienceShare, countyLens, stateLens, metroLens, builtInLens, growthYears, LENS_BY_KEY } from "./lenses.js";
import { makeApp } from "./fixtures/synthetic.js";

const cells = (values) => values.map((v) => (v == null ? null : +v.toFixed(6)));
const data = () => buildData(makeApp());

test("growth by okrug: every land hex takes its okrug's change; nulls stay null; the domain is symmetric", () => {
  const d = data();
  const lens = growthLens(d, "states");
  assert.equal(lens.id, "adv-growth-states");
  assert.equal(lens.name, "Promena broja stanovnika po okruzima");
  assert.equal(lens.format, "pct");
  assert.equal(lens.values.length, 12);
  assert.deepEqual(cells(lens.values.slice(0, 7)), [-0.0043, -0.0043, -0.0043, null, null, null, null]);
  assert.equal(lens.values[7], null); // sea / outside the frame
  assert.deepEqual(lens.domain, [-0.005, 0.005]); // to half a percent, at least ±0.5 %
  assert.equal(lens.higher_is, "neutral");
  assert.match(lens.description, /Republički zavod za statistiku/);
  assert.equal(growthLens(d, "states"), lens); // cached per data model
});

test("growth by grad: only the cities' hexes are coloured", () => {
  const lens = growthLens(data(), "metros");
  assert.equal(lens.id, "adv-growth-metros");
  assert.deepEqual(cells(lens.values.slice(0, 5)), [-0.0043, -0.0043, null, 0.01, null]); // Beograd's two hexes, then Novi Sad
  assert.ok(Math.abs(lens.domain[1] - 0.01) < 1e-9 && lens.domain[0] === -lens.domain[1]);
  assert.match(lens.description, /Sivi heksovi su van gradova\./);
});

test("science jobs as a share of the employed, per grad", () => {
  const d = data();
  const lens = scienceLens(d);
  assert.equal(lens.id, "adv-science-share");
  assert.equal(lens.name, "Zaposleni u nauci");
  const bg = d.levels.metros.byKey.get("79014"), ns = d.levels.metros.byKey.get("89010");
  assert.equal(scienceShare(bg), 2300 / 713556);
  assert.equal(scienceShare(ns), 2300 / 158315);
  assert.equal(scienceShare({ v: { jobs_science: null, employed: 10 } }), null);
  assert.equal(scienceShare({ v: { jobs_science: 5, employed: 0 } }), null);
  assert.equal(lens.values[0], 2300 / 713556);
  assert.equal(lens.values[3], 2300 / 158315);
  assert.equal(lens.values[2], null); // a hex outside both cities
  assert.match(lens.description, /NACE M i J/);
  assert.match(lens.description, /Nauka/);
});

test("countyLens: an opština column per hex, with the lenses.json sočivo's name, note and colours", () => {
  const d = data();
  const lens = countyLens(d, "wage_net");
  assert.equal(lens.id, "adv-county-wage_net");
  assert.equal(lens.name, "Prosečna neto zarada"); // from lenses.json via LENS_BY_KEY
  assert.equal(lens.format, "rsd");
  assert.deepEqual(cells(lens.values.slice(0, 7)), [151304.62, 151304.62, 151304.62, 126469, 126469, null, null]);
  assert.equal(lens.values[7], null);
  assert.ok(lens.domain[0] > 126469 && lens.domain[1] < 160000 && lens.domain[0] < lens.domain[1]); // robustDomain trims the extremes
  const inc = countyLens(d, "natural_increase", { name: "Prirodni priraštaj", ramp: ["#000", "#fff"], note: "Izvor: RZS." });
  assert.equal(inc.name, "Prirodni priraštaj");
  assert.deepEqual(inc.ramp, ["#000", "#fff"]);
  assert.equal(inc.note, "Izvor: RZS.");
  assert.deepEqual(cells(inc.values.slice(0, 5)), [-4.2, -4.2, -4.2, 0, 0]); // Novi Sad's real 0 is a value
  assert.ok(inc.domain[0] > -4.2 && inc.domain[0] < -4 && inc.domain[1] < 0); // robustDomain trims the extremes (-4,2 … -3,0 … 0)
  assert.equal(LENS_BY_KEY.growth, "pop_change");
  assert.equal(countyLens(d, "wage_net"), lens); // cached
});

test("stateLens and metroLens: a per-row value as a map lens; null rows stay grey", () => {
  const d = data();
  const gdp = stateLens(d, "gdp", (r) => r.v.gdp, { name: "BDP okruga", format: "eur" });
  assert.equal(gdp.id, "adv-state-gdp");
  assert.equal(gdp.format, "eur");
  assert.deepEqual(cells(gdp.values.slice(0, 7)), [32418650000, 32418650000, 32418650000, 8065190000, 8065190000, null, null]);
  assert.ok(gdp.domain[0] > 8065190000 && gdp.domain[1] < 32418650000);
  const edu = metroLens(d, "edu-higher", (r) => r.v.edu_higher, { name: "Visoko obrazovanje" });
  assert.equal(edu.id, "adv-metro-edu-higher");
  assert.deepEqual(cells(edu.values.slice(0, 5)), cells([350000 / 1500000, 350000 / 1500000, null, 104136 / 310136, null]));
  assert.equal(stateLens(d, "gdp", (r) => r.v.gdp, { name: "BDP okruga", format: "eur" }), gdp); // cached
});

test("builtInLens resolves a lenses.json sočivo's values (world field or lens-values.json column)", () => {
  const d = data();
  const pop = builtInLens(d, "pop_change");
  assert.equal(pop.name, "Promena broja stanovnika");
  assert.equal(pop.note, "Za Novi Sad nema procene.");
  assert.deepEqual(cells(pop.values.slice(0, 7)), [0.01, 0.01, 0.01, -0.03, -0.03, null, null]);
  const elev = builtInLens(d, "elevation");
  assert.deepEqual(elev.values.slice(0, 7), [100, 90, 80, 75, 70, 500, 600]);
  assert.equal(builtInLens(d, "nope"), null);
  const noFile = buildData(makeApp({ withLensValues: false }));
  assert.equal(builtInLens(noFile, "pop_change"), null); // lens-values.json has not arrived
  assert.equal(builtInLens(noFile, "elevation").values[0], 100);
  const inline = { lensById: new Map([["x", { id: "x", values: [1, 2] }]]) };
  assert.deepEqual(builtInLens(inline, "x").values, [1, 2]);
  assert.equal(builtInLens(null, "x"), null);
});

test("growthYears reads the period off the rows", () => {
  const d = data();
  assert.equal(growthYears(d.levels.states.rows), "2021–2025.");
  assert.equal(growthYears(d.levels.metros.rows), "2021–2025.");
  assert.equal(growthYears([{ ref: {} }]), "");
});
