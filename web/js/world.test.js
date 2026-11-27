import { test } from "node:test";
import assert from "node:assert/strict";
import { isCapital, labelForms, prepareWorld } from "./world.js";
import { toCyrillic } from "./i18n/transliterate.js";

test("an okrug's short label drops the word okrug in both scripts", () => {
  assert.deepEqual(labelForms("BORSKI OKRUG", (t) => t), ["BORSKI OKRUG", "BORSKI"]);
  const [name, stem] = labelForms("BORSKI OKRUG", toCyrillic);
  assert.equal(stem, toCyrillic("BORSKI")); // cut in Latin, then transliterated
  assert.notEqual(stem, name);
  assert.deepEqual(labelForms("GRAD BEOGRAD", (t) => t), ["GRAD BEOGRAD", "GRAD BEOGRAD"]); // nothing to cut
});

test("missing elevation stays unknown and does not create false shading", () => {
  const raw = { grid: { radius: 5, cols: 2, rows: 1 }, owner: [0, 0], water: [0, 0], elev: [null, 100],
    relief: [null, 0], cover: [null, 1], states: [{ fips: "RS110", name: "Beograd" }], counties: [], tables: {} };
  const w = prepareWorld(raw, []);
  assert.equal(raw.elev[0], null);
  assert.equal(w.shadeK[0], 0);
  assert.equal(w.shadeK[1], 0);
  assert.ok(w.terrainColors[0].every(Number.isFinite));
});

test("Belgrade is the fallback capital when the flag is absent", () => {
  assert.equal(isCapital({ id: "79014" }), true);
  assert.equal(isCapital({ id: "47900" }), false);
});
