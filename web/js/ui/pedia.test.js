// The Almanah must never show "[object Object]" for a source whose vintage is one entry per dataset.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { vintageText } from "./pedia.js";

const sources = JSON.parse(readFileSync(new URL("../../data/sources.json", import.meta.url), "utf8"));

test("a per-dataset vintage is printed as its values, in the file's order, each once", () => {
  assert.equal(vintageText({ regions: "Eurostat GISCO, NUTS 2024", areas: "Eurostat GISCO, NUTS 2024", communes: "LAU 2024" }),
    "Eurostat GISCO, NUTS 2024; LAU 2024");
  assert.equal(vintageText({ pop_estimate: "Procene stanovništva, 1991–2025", births: "Živorođeni, 2025" }),
    "Procene stanovništva, 1991–2025; Živorođeni, 2025");
});

test("a plain vintage is passed through and a missing one is empty", () => {
  assert.equal(vintageText("Popis 2022"), "Popis 2022");
  assert.equal(vintageText(null), "");
  assert.equal(vintageText(undefined), "");
});

test("no source in the shipped catalog prints as [object Object]", () => {
  const many = sources.filter((s) => s.vintage && typeof s.vintage === "object");
  assert.ok(many.length >= 2, "the catalog is expected to carry per-dataset vintages (boundaries, rzs_db)");
  for (const s of sources) assert.ok(!/\[object /.test(vintageText(s.vintage)), s.id);
});
