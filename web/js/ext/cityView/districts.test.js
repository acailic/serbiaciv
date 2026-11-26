import { test } from "node:test";
import assert from "node:assert/strict";
import { badgeHtml, badgeOf, cityDistricts, districtsHtml, iconFor } from "./districts.js";
import { compact, popShort } from "./fmt.js";
import { hasIcon } from "../../icons.js";
import { city, load, serbian } from "./_serbian.js";

const dd = load("districts.json");
const citizens = load("citizens.json");

test("districts.json keeps the upstream shape with a Serbian catalog", () => {
  assert.equal(dd.version, 1);
  for (const k of ["version", "vintage", "year", "sources", "rule", "catalog", "industries", "national", "cities", "counties"]) assert.ok(k in dd, k);
  assert.equal(dd.rule.max_per_city, 5);
  assert.equal(dd.national.avg_pay, null);
  serbian(JSON.stringify(dd.catalog), "catalog");
  serbian(dd.rule.text, "rule");
  for (const c of dd.catalog) {
    assert.ok(c.id && c.name && c.badge?.label && c.description, c.id);
    assert.equal(c.sub, null, `${c.id}.sub`);
    if (c.icon) assert.ok(hasIcon(c.icon), `${c.id}: icon ${c.icon} missing`);
  }
  // The harbour of upstream is Serbia's logistics hub (NACE H) under the same id.
  const harbor = dd.catalog.find((c) => c.id === "harbor");
  assert.equal(harbor.name, "Logistički čvor");
});

test("Beograd and Novi Sad: Serbian badges, plaques and cards", () => {
  for (const id of ["79014", "89010"]) {
    const m = { city: city(id) };
    const b = badgeOf(dd, id);
    assert.ok(b?.label, id);
    assert.ok(b.district, id);
    const list = cityDistricts(dd, null, id);
    assert.ok(list.length >= 1 && list.length <= 5, id);
    for (const d of list) {
      assert.ok(d.name && d.short && d.icon, `${id}: ${d.id}`);
      assert.ok(typeof d.lq === "number" && d.lq >= 1.25, `${id}: ${d.id} lq ${d.lq}`);
      assert.equal(d.sub, null);
    }
    const html = districtsHtml(m, dd, null);
    serbian(html, id);
    assert.match(html, /Kako se biraju kvartovi/);
    assert.match(html, /Najspecijalizovanije delatnosti/);
    assert.match(html, /Popis 2022/);
    assert.doesNotMatch(html, /NAICS/);
    const badge = badgeHtml(m, dd);
    serbian(badge, `${id} badge`);
    assert.ok(badge.includes(b.label));
  }
  assert.equal(badgeOf(dd, "79014").label, "Grad znanja");
});

test("no census row: the KiM case is said in Serbian, without zeros", () => {
  serbian(districtsHtml({ city: city("00000") }, dd, null), "no row");
  assert.match(districtsHtml({ city: city("00000") }, dd, null), /nije sproveden/);
  assert.match(districtsHtml({ city: city("00000") }, null, null), /nisu dostupni/);
  assert.match(districtsHtml({ city: city("00000") }, undefined, null), /Učitavamo/);
  assert.equal(badgeOf(dd, "00000"), null);
  assert.deepEqual(cityDistricts(dd, null, "00000"), []);
});

test("icons fall back to the Serbian set and the plaque labels are short Serbian", () => {
  assert.equal(iconFor("agriculture", {}), "y-food");
  assert.equal(iconFor("construction", {}), "y-production");
  assert.equal(iconFor("harbor", {}), "i-transportation");
  assert.ok(hasIcon(iconFor("harbor", {})));
  for (const id of ["79014", "89010", "79022", "80438"]) {
    for (const d of cityDistricts(dd, null, id)) assert.ok(d.short.length <= 18, `${d.short}`);
  }
});

test("every city record holds only districts that pass the rule; nulls stay null", () => {
  let withDistrict = 0;
  for (const [id, row] of Object.entries(dd.cities)) {
    if (!row) continue;
    assert.ok(row.emp > 0, id);
    assert.equal(row.avg_pay, null);
    assert.ok(row.districts.length <= 5, id);
    for (const d of row.districts) {
      assert.ok(d.lq >= dd.rule.min_lq, `${id}: ${d.id} lq ${d.lq}`);
      assert.ok(d.emp >= dd.rule.min_jobs || d.share >= dd.rule.min_share, `${id}: ${d.id}`);
      for (const k of ["sub", "sub_lq", "sub_emp", "sub_lower_bound", "suppressed", "lower_bound"]) assert.equal(d[k], null, `${id}: ${d.id}.${k}`);
      assert.equal(d.avg_pay, null);
    }
    for (const t of row.top) assert.ok(/^[A-S]$/.test(t.naics), `${id}: naics ${t.naics}`);
    withDistrict += row.districts.length ? 1 : 0;
  }
  assert.ok(withDistrict >= 40, `cities with a district: ${withDistrict}`);
  assert.ok(Object.keys(dd.cities).every((id) => citizens.cities[id] !== undefined));
});

test("compact numbers roll over to the Serbian units", () => {
  assert.equal(compact(999950), "1 mil.");
  assert.equal(compact(999999), "1 mil.");
  assert.equal(compact(713556), "713,6 hilj.");
  assert.equal(compact(4194), "4,2 hilj.");
  assert.equal(compact(713556), "713,6 hilj.");
  assert.equal(popShort(999950), "1 mil.");
  assert.equal(compact(null), "–");
});
