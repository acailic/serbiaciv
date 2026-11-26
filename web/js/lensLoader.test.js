import { test } from "node:test";
import assert from "node:assert/strict";
import { createLensLoader } from "./lensLoader.js";

const world = { owner: [0, 0, -1], county: [0, 1, -1], counties: [{ geoid: "70001" }, { geoid: "70002" }],
  elev: [0, 20, null] };
const indexed = { version: 2, municipality_ids: ["70001", "70002"], values: { x: [0, 8], y: [1, null] } };
const municipal = (key) => ({ value_source: { kind: "municipality", file: "lens-values.json", key } });

test("physical lenses need no fetch; concurrent municipality lenses share a request", async () => {
  let calls = 0;
  const load = createLensLoader(world, async () => { calls++; return indexed; });
  assert.deepEqual(await load({ value_source: { kind: "world", field: "elev" } }), [0, 20, null]);
  assert.equal(calls, 0);
  const [x, y] = await Promise.all([load(municipal("x")), load(municipal("y"))]);
  assert.deepEqual(x, [0, 8, null]);
  assert.deepEqual(y, [1, null, null]);
  assert.equal(calls, 1);
});

test("a failed download can be retried", async () => {
  let calls = 0;
  const load = createLensLoader(world, async () => { if (++calls === 1) throw new Error("offline"); return indexed; });
  await assert.rejects(load(municipal("x")), /offline/);
  assert.deepEqual(await load(municipal("x")), [0, 8, null]);
  assert.equal(calls, 2);
});

test("invalid cached values can be fetched again after correction", async () => {
  let calls = 0;
  const load = createLensLoader(world, async () => ++calls === 1
    ? { ...indexed, municipality_ids: ["wrong", "order"] } : indexed);
  await assert.rejects(load(municipal("x")), /IDs/);
  assert.deepEqual(await load(municipal("x")), [0, 8, null]);
  assert.equal(calls, 2);
});
