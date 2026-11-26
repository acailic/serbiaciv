// Caveats the Serbian dashboards share. Every null in the data is explained by one of these; nothing is filled in.
import { int } from "./fmt.js";
import { KIM_NOTE } from "./data.js";

export { KIM_NOTE };

/** Why a cell is "–": the source publishes nothing for that unit. */
export const NULL_NOTE = "„–“ znači da izvor ne objavljuje podatak za tu jedinicu; nijedna vrednost nije procenjena niti dopunjena.";

/** counties.json (opštine) and lens-values.json vintage, e.g. "Procene RZS 2025 · Popis 2022". */
export const vintageNote = (data) => `Podaci za opštine su ${data.countyVintage ? `iz izdanja „${data.countyVintage}“` : "iz poslednjeg izdanja"}; podaci za okruge i gradove ${data.vintage ? `iz izdanja „${data.vintage}“` : "iz istog izvora"}.`;

/** Opštine smaller than one hex cannot be outlined on the map. */
export const offMapNote = (data) => {
  const names = (data.levels?.counties?.rows ?? []).filter((r) => !r.cells.length).map((r) => r.name);
  const n = names.length;
  if (!n) return "";
  const list = `(${names.join(", ")})`;
  if (n === 1) return `1 opština je manja od jednog heksa ${list}, pa se na karti ne može označiti; u tabelama i grafikonima je.`;
  return `${int(n)} ${n < 5 ? "opštine su" : "opština je"} manje od jednog heksa ${list}, pa se na karti ne mogu označiti; u tabelama i grafikonima su.`;
};

export const NOVI_SAD_OPSTINA_NOTE = "Za opštinu Novi Sad izvor ne objavljuje procenu broja stanovnika ni očekivano trajanje života, pa su te dve vrednosti prazne; ostale mere opštine postoje.";
export const BEOGRAD_NOTE = "Za Beograd kao grad nema prosečne neto zarade ni udela starijih od 65 godina: izvor te podatke vodi po gradskim opštinama, pa grad kao celina nema svoju vrednost. Beogradski okrug je ima.";
export const JUZNOBACKI_NOTE = "Za Južnobački okrug izvor ne objavljuje procenu broja stanovnika ni promenu stanovništva, pa su te vrednosti i gustina naseljenosti okruga prazne; zbir njegovih opština je u tabelama opština.";
export const JUZNOBACKI_GDP_NOTE = "Za pet gradova Južnobačkog okruga (Novi Sad, Bačka Palanka, Vrbas, Bečej i Temerin) procena BDP grada nije izračunata; BDP celog okruga je poznat.";
export const GROWTH_PERIOD_NOTE = "Promena broja stanovnika meri se za različite periode: po opštinama od 2015. do 2025. godine, po okruzima i gradovima od 2021. do 2025. godine (dve procene istog izvora). Zato se te brojke ne mogu sabrati ni porediti red po red.";

/** The population-related caveats, in the order the views list them. */
export const peopleCaveats = (data) => [
  NULL_NOTE,
  KIM_NOTE,
  NOVI_SAD_OPSTINA_NOTE,
  BEOGRAD_NOTE,
  JUZNOBACKI_NOTE,
  GROWTH_PERIOD_NOTE,
  ...(data.countiesOffMap ? [offMapNote(data)] : []),
];
