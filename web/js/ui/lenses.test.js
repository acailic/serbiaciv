// The legend's source line must never show "[object Object]" for a source whose vintage is one entry per dataset.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { lensVintage } from "./lenses.js";

const sources = JSON.parse(readFileSync(new URL("../../data/sources.json", import.meta.url), "utf8"));
const lenses = JSON.parse(readFileSync(new URL("../../data/lenses.json", import.meta.url), "utf8"));

test("a per-dataset vintage gives the lens file's summary and a plain one is kept", () => {
  assert.equal(lensVintage({ pop_estimate: "Procene 1991–2025", wages: "Zarade 2025" }, "Procene RZS 2025 · Popis 2022"),
    "Procene RZS 2025 · Popis 2022");
  assert.equal(lensVintage("Popis stanovništva 2022", "Procene RZS 2025"), "Popis stanovništva 2022");
  assert.equal(lensVintage(null, "s"), "s");
  assert.equal(lensVintage(undefined, undefined), "");
});

test("no lens legend in the shipped catalog would print [object Object]", () => {
  const many = sources.filter((s) => s.vintage && typeof s.vintage === "object");
  assert.ok(many.length >= 2, "the catalog is expected to carry per-dataset vintages (boundaries, rzs_db)");
  assert.ok(lenses.vintage, "lenses.json names its own vintage");
  for (const l of lenses.lenses) {
    const src = sources.find((s) => s.id === l.source);
    assert.ok(src, `${l.id} names its source`);
    assert.ok(!/\[object /.test(lensVintage(src.vintage, lenses.vintage)), l.id);
  }
});
