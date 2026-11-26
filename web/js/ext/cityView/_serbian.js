import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const load = (name) => JSON.parse(readFileSync(new URL(`../../../data/${name}`, import.meta.url), "utf8"));
const CYRILLIC = /[\u0400-\u04ff]/;
// US wording of the ported screen: none of it may reach the page.
const US_TEXT = /U\.S\.|\bUS\b|\bACS\b|\bBEA\b|\bBLS\b|\bQCEW\b|\bNAICS\b|\bCensus\b|metro|Micro|Drove alone|Diversified|Harbor|County|\bTurn\b/;

export const serbian = (html, where = "") => {
  assert.ok(!CYRILLIC.test(html), `${where}: Cyrillic in ${html.slice(0, 200)}`);
  const visible = html.replace(/<!--[\s\S]*?-->/g, "");
  assert.ok(!US_TEXT.test(visible), `${where}: US wording in ${visible.match(/.{0,60}(U\.S\.|\bUS\b|\bACS\b|\bBEA\b|\bBLS\b|\bQCEW\b|\bNAICS\b|\bCensus\b|metro|Diversified|Harbor|County|\bTurn\b).{0,60}/)?.[0]}`);
};

export const city = (id) => ({ id, name: id === "79014" ? "Beograd" : id === "89010" ? "Novi Sad" : id, population: 1681470, states: [], stateName: () => "Beogradski okrug" });
export { load };
