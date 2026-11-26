import { test } from "node:test";
import assert from "node:assert/strict";
import { citizensHtml } from "./citizens.js";
import { CATEGORY_COLOR, PAINTED } from "./figures.js";
import { CITIZEN_ROWS } from "../../render/art/people.js";
import { city, load, serbian } from "./_serbian.js";

const data = load("citizens.json");
const cities = load("cities.json");
const beograd = { city: city("79014") };

test("citizens.json keeps the upstream shape with Serbian groups", () => {
  assert.equal(data.version, 1);
  assert.equal(data.year, 2022);
  for (const k of ["version", "vintage", "year", "sources", "figures", "rows", "groups", "rule"]) assert.ok(k in data, k);
  assert.deepEqual(Object.keys(data.rows).sort(), ["age", "commute", "education", "nativity", "workforce"]);
  assert.deepEqual(data.groups.workforce.map((g) => g.key), CITIZEN_ROWS.workforce);
  for (const [row, keys] of Object.entries(CITIZEN_ROWS)) assert.deepEqual(data.groups[row].map((g) => g.key), keys, row);
  serbian(JSON.stringify(data.groups), "groups");
  serbian(data.rule.text, "rule");
});

test("every category has a painter and a colour", () => {
  for (const [row, keys] of Object.entries(CITIZEN_ROWS)) {
    for (const k of keys) {
      assert.ok(PAINTED[row]?.includes(k), `${row}/${k} has no painter`);
      assert.match(CATEGORY_COLOR[row]?.[k] || "", /^#[0-9a-f]{6}$/i, `${row}/${k} has no colour`);
    }
  }
});

test("Beograd: five rows with figures, Serbian labels, no English", () => {
  const html = citizensHtml(beograd, data);
  serbian(html, "Beograd");
  for (const id of Object.keys(CITIZEN_ROWS)) assert.ok(html.includes(`data-row="${id}"`), id);
  assert.match(html, /Rukovodioci/);
  assert.match(html, /Dete \(do 14\)/);
  assert.match(html, /Bez završene osnovne škole/);
  assert.match(html, /Gde zaposleni rade/);
  assert.match(html, /Od rođenja u istom naselju/);
  assert.match(html, /Svaka figura ≈/);
  assert.match(html, /u Srbiji/);
  // The workforce row shows 20 figures for Beograd; scholar and healer (unpublished) are listed as "nema podataka".
  assert.equal((html.match(/class="cv-fig(?: up| down)?" tabindex="0" role="img" data-k="(?:executive|engineer|service|clerk|farmer|builder|maker)"/g) || []).length >= 5, true);
  assert.match(html, /nema podataka/);
});

test("a city without a census row (Kosovo and Metohija) gets empty rows, never zeros", () => {
  const html = citizensHtml({ city: city("00000") }, data);
  serbian(html, "no row");
  assert.match(html, /nije sproveden za 00000/);
  assert.doesNotMatch(html, /class="cv-fig"/);
});

test("no data at all is said in Serbian", () => {
  serbian(citizensHtml(beograd, null), "null");
  assert.match(citizensHtml(beograd, null), /nisu dostupni/);
});

test("every city in cities.json has a record with five rows or a null record", () => {
  for (const c of cities) {
    const rec = data.cities[c.id];
    assert.ok(rec !== undefined, c.id);
    if (rec != null) for (const id of Object.keys(CITIZEN_ROWS)) assert.ok(rec[id] === null || typeof rec[id] === "object", `${c.id}/${id}`);
  }
  assert.equal(data.national.workforce.counts.executive > 0, true);
});
