import { test } from "node:test";
import assert from "node:assert/strict";
import { compareTable, countiesTable } from "./screen.js";
import { sparkline, meter, bar } from "./charts.js";
import { LAND, INDUSTRY, jobIndustries, resourceValue } from "./model.js";
import { city, load, serbian } from "./_serbian.js";

test("the counties table reads the Serbian columns and says so in Serbian", () => {
  const data = load("counties.json");
  const m = { city: { ...city("79014"), counties: data.rows.slice(0, 3).map((r) => r[data.columns.indexOf("geoid")]) }, stateName: () => "Beogradski okrug" };
  const html = countiesTable(m, data);
  serbian(html, "counties");
  assert.match(html, /Opština/);
  assert.match(html, /Stanovnici/);
  assert.match(html, /Zarada/);
  assert.match(html, /Podaci RZS o opštinama/);
  assert.match(countiesTable(m, null), /Tabela opština nije dostupna/);
});

test("the compare table has Serbian metric sets", () => {
  const m = { city: city("79014"), peers: [city("89010")], stateName: () => "Južnobački okrug" };
  for (const set of ["size", "housing"]) serbian(compareTable(m, set), set);
  assert.match(compareTable(m, "size"), /BDP po stanovniku/);
  assert.match(compareTable(m, "housing"), /Teret kirbije/);
});

test("charts carry no U.S. wording", () => {
  serbian(sparkline([], {}), "sparkline");
  serbian(meter(0.1, 0.2, 0.3, "low"), "meter");
  serbian(bar(0.5, "#fff", 0.2), "bar");
  assert.match(sparkline([], {}), /Nema godišnjih procena/);
});

test("the model names land and industries in Serbian and reads the Serbian industry keys", () => {
  serbian(JSON.stringify(LAND), "LAND");
  serbian(JSON.stringify(INDUSTRY), "INDUSTRY");
  for (const k of Object.keys(load("nation.json").nation.jobs)) assert.ok(INDUSTRY[k]?.short, k);
  const nation = load("nation.json");
  const beograd = load("cities.json").find((c) => c.id === "79014");
  const inds = jobIndustries(beograd, nation);
  assert.ok(inds.length > 10);
  assert.ok(inds.every((d) => Number.isFinite(d.lq) && d.short && d.label));
  serbian(inds.map((d) => d.label + d.short).join(" "), "jobIndustries");
  assert.equal(resourceValue({ value: 1500 }, { unit: "MW" }), "1,5 GW");
  assert.equal(resourceValue({ value: 1200 }, { unit: "employees" }, (v) => String(v)), "1200 zaposlenih");
});
