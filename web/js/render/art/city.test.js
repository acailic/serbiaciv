import { test } from "node:test";
import assert from "node:assert/strict";
import { CITY_CLASSES, cityClass } from "./city.js";

// The populations are those of web/data/cities.json (Popis 2022).
test("the class floors follow Serbia's distribution: Niš is a city, Kragujevac a town, Beograd the metropolis", () => {
  assert.deepEqual(CITY_CLASSES.map((c) => c.id), ["village", "town", "city", "metropolis", "megalopolis"]);
  assert.equal(cityClass(5).id, "village");
  assert.equal(cityClass(60000).id, "town");
  assert.equal(cityClass(169495).id, "town"); // Kragujevac
  assert.equal(cityClass(248079).id, "city"); // Niš: the comment names it a city, so the floor must let it in
  assert.equal(cityClass(373652).id, "city"); // Novi Sad
  assert.equal(cityClass(1681470).id, "metropolis"); // Beograd
});
