import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CITIZEN_KINDS, CITIZEN_ROWS, citizenKind, citizenSVG } from "./people.js";

const CYRILLIC = /[\u0400-\u04ff]/;
// Words of the US vocabulary the kinds were ported from: none may survive in a label.
const US_WORDS = /\b(drove|carpool|transit|walk|home|born|state|abroad|foreign|college|school|high|degree|child|under)\b/i;
const rows = Object.values(CITIZEN_ROWS).flat();

test("every row kind exists and every kind belongs to a row", () => {
  for (const k of rows) assert.ok(CITIZEN_KINDS[k], `missing kind ${k}`);
  assert.deepEqual(Object.keys(CITIZEN_KINDS).sort(), [...rows].sort());
});

test("workforce and age keep the upstream keys the figures are drawn with", () => {
  assert.deepEqual(CITIZEN_ROWS.workforce, ["executive", "engineer", "scholar", "healer", "service", "clerk", "farmer", "builder", "maker"]);
  assert.deepEqual(CITIZEN_ROWS.age, ["child", "young", "midlife", "elder"]);
});

test("commute, education and nativity use the Serbian census categories", () => {
  assert.deepEqual(CITIZEN_ROWS.commute, ["home_settlement", "same_municipality", "other_municipality", "other_area", "abroad"]);
  assert.deepEqual(CITIZEN_ROWS.education, ["less_than_hs", "primary", "high_school", "bachelors", "graduate"]);
  assert.deepEqual(CITIZEN_ROWS.nativity, ["same_settlement", "elsewhere_serbia", "former_yugoslavia", "other_country"]);
});

test("labels are Serbian Latin: no Cyrillic, no English wording", () => {
  for (const [k, d] of Object.entries(CITIZEN_KINDS)) {
    assert.ok(!CYRILLIC.test(d.label), `${k}: Cyrillic in "${d.label}"`);
    assert.ok(!US_WORDS.test(d.label), `${k}: English wording in "${d.label}"`);
    assert.ok(d.row in CITIZEN_ROWS, `${k}: row ${d.row}`);
  }
  assert.equal(CITIZEN_KINDS.child.label, "Dete (do 14)");
  assert.equal(CITIZEN_KINDS.less_than_hs.label, "Bez završene osnovne škole");
});

test("citizenKind accepts the data keys and the icon aliases, and refuses the US keys", () => {
  assert.equal(citizenKind("executive"), "executive");
  assert.equal(citizenKind("home_settlement"), "home_settlement");
  assert.equal(citizenKind("c-work_okrug"), "other_area");
  assert.equal(citizenKind("c-edu0"), "less_than_hs");
  assert.equal(citizenKind("car"), "same_municipality");
  for (const us of ["drove_alone", "carpool", "some_college", "born_in_state", "foreign_born", "native_abroad", "other_state"]) {
    assert.equal(citizenKind(us), null, us);
  }
  assert.equal(citizenKind(null), null);
});

test("every kind draws as an SVG with a Serbian title", () => {
  for (const k of rows) {
    const svg = citizenSVG(k, { size: 20, title: CITIZEN_KINDS[k].label });
    assert.match(svg, /^<svg class="citizen" /);
    assert.match(svg, /viewBox="-0\.6 -0\.6 25\.2 25\.2"/);
    assert.ok(svg.includes(`<title>${CITIZEN_KINDS[k].label.replace(/&/g, "&amp;")}</title>`), k);
    assert.ok(!svg.includes("null"), k);
  }
  assert.equal(citizenSVG("drove_alone"), "");
});
