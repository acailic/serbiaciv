// A small synthetic Serbia for the advisors' tests (see core/data.test.js): two okruzi (one with a null population,
// as Južnobački) and a Kosovo okrug with null statistics; two cities; four opštine (one off the map, one Novi-Sad-like,
// one Kosovo). Only test files import this module.
import { NACE_KEYS } from "../data.js";

export const JOBS = Object.fromEntries(NACE_KEYS.map((k, i) => [k, 100 * (i + 1)])); // sums to 19 000

export const world = {
  owner: [0, 0, 0, 1, 1, 2, 2, -1, -1, -1, -1, -1],
  county: [0, 0, 0, 2, 2, 3, 3, -1, -1, -1, -1, -1],
  // Per-cell WorldCover shares in percent (a city's land cover is the mean over its hexes).
  pct: { forest: [10, 20, 30, null, null, null, null, null, null, null, null, null], developed: [90, 80, 70, null, null, null, null, null, null, null, null, null] },
  elev: [100, 90, 80, 75, 70, 500, 600, null, null, null, null, null],
  cover: [9, 9, 1, 1, 7, 1, 2, null, null, null, null, null],
  states: [{ fips: "RS110", name: "Beogradski okrug" }, { fips: "RS123", name: "Južnobački okrug" }, { fips: "RS231", name: "Kosovski okrug" }],
  counties: [{ geoid: "70001", name: "Beograd" }, { geoid: "70002", name: "Vračar" }, { geoid: "80284", name: "Novi Sad" }, { geoid: "90001", name: "Kosovska Mitrovica" }],
};
export const states = [
  { fips: "RS110", name: "Beogradski okrug", population: 1681470, employed: 713556, unemployment: 0.0911, wage_net: 151304.62, age65: 0.2063, gdp: 32418650000, growth: -0.0043, growth_years: [2021, 2025],
    land: { forest: 0.378, crop: 0.333, pasture: 0.192, grass: 0.01, shrub: 0.01, wetland: 0.0, developed: 0.066 }, jobs: JOBS,
    yields: { food: 5665, production: 107383, gold: 32418650000, science: 119470, culture: 18125 } },
  { fips: "RS123", name: "Južnobački okrug", population: null, employed: 243503, unemployment: null, wage_net: null, age65: null, gdp: 8065190000, growth: null, growth_years: null,
    land: { forest: 0.2, crop: 0.5, pasture: 0.1, grass: 0.02, shrub: 0.02, wetland: 0.01, developed: 0.07 }, jobs: null, yields: null },
  { fips: "RS231", name: "Kosovski okrug", population: null, employed: null, unemployment: null, wage_net: null, age65: null, gdp: null, growth: null, growth_years: null,
    land: { forest: 0.493, crop: 0.227, pasture: 0.231, grass: 0.0, shrub: 0.0, wetland: 0.0, developed: 0.0 }, jobs: null, yields: null },
];
export const cities = [
  { id: "79014", name: "Beograd", full: "Beograd (Beogradski okrug)", states: ["RS110"], counties: ["70001", "70002"], footprint: [0, 1], cell: 0, capital: true,
    population: 1681470, employed: 713556, growth: -0.0043, growth_years: [2021, 2025], gdp: 32418650000, unemployment: null, wage_net: null, age65: null, land: null,
    yields: { food: 5665, production: 107383, gold: 32418650000, science: 119470, culture: 18125 }, jobs: JOBS, settlement_population: 209763,
    education: { total15: 1500000, none: 30000, incomplete_primary: 70000, primary: 300000, secondary: 750000, higher: 350000, unknown: 0 },
    religion: { total: 1681470, orthodox: 1550000, catholic: 20000, muslim: 15000, nonbeliever: 20000 },
    ethnicity: { total: 1681470, srbi: 1550000, madjari: 5000, romi: 20000 },
    commute: { total: 700000, same_unit: 600000, other_unit: 40000, other_oblast: 50000, abroad: 10000 } },
  { id: "89010", name: "Novi Sad", states: ["RS123"], counties: ["80284"], footprint: [], cell: 3,
    population: 320000, employed: 158315, growth: 0.01, growth_years: [2011, 2025], gdp: null, unemployment: 0.08, wage_net: 126469, age65: 0.18, land: null,
    yields: { food: 100, production: 2000, gold: null, science: 5000, culture: 900 }, jobs: { ...JOBS, agriculture: null }, settlement_population: 250000,
    education: { total15: 310136, none: 1000, incomplete_primary: 5000, primary: 50000, secondary: 150000, higher: 104136, unknown: 0 },
    religion: null, ethnicity: null, commute: { total: 150000, same_unit: 120000, other_unit: 10000, other_oblast: 20000, abroad: 0 } },
];
export const COLUMNS = ["geoid", "name", "state", "population", "land_km2", "density", "age65", "education", "wage_net", "unemployment", "manufacturing", "commute", "orthodox", "serbs", "life_expectancy", "natural_increase", "forest", "crop", "pasture", "developed", "city", "cell"];
export const counties = { vintage: "Procene RZS 2025 · Popis 2022", fields: COLUMNS, columns: COLUMNS, rows: [
  ["70001", "Beograd", "RS110", 1500000, 3600, 416.7, 0.2, 0.3, 151304.62, 0.09, 0.12, 0.25, 0.9, 0.9, 76.5, -4.2, 0.3, 0.3, 0.1, 0.2, "79014", 0],
  ["70002", "Vračar", "RS110", 50000, 12, 4166.7, 0.22, 0.4, 160000, 0.08, 0.1, 0.3, 0.88, 0.88, 77.0, -3.0, 0.1, 0.0, 0.0, 0.9, "79014", null],
  ["80284", "Novi Sad", "RS123", null, 697.9, null, 0.1799, 0.3546, 126469, 0.0964, 0.1236, 0.2753, 0.7665, 0.7836, null, 0, 0.1, 0.6, 0.05, 0.2, "89010", 3],
  ["90001", "Kosovska Mitrovica", "RS231", null, 350, null, null, null, null, null, null, null, null, null, null, null, 0.4, 0.3, 0.2, 0.0, null, 5],
] };
export const lensValues = { version: 2, municipality_ids: ["70001", "70002", "80284", "90001"], values: {
  pop_change: [0.01, 0.02, -0.03, null], wages: [151304.62, 160000, 126469, null], education: [0.3, 0.4, 0.3546, null], unemployment: [0.09, 0.08, 0.0964, null] } };
export const lenses = { version: 2, lenses: [
  { id: "pop_change", name: "Promena broja stanovnika", group: "people", format: "pct", source: "rzs_db", description: "Promena procenjenog broja stanovnika.", note: "Za Novi Sad nema procene.", value_source: { kind: "municipality", file: "lens-values.json", key: "pop_change" } },
  { id: "wages", name: "Prosečna neto zarada", group: "work", format: "rsd", value_source: { kind: "municipality", file: "lens-values.json", key: "wages" } },
  { id: "elevation", name: "Nadmorska visina", format: "int", value_source: { kind: "world", field: "elev" } },
] };
export const nation = { year: 2025, vintage: "Procene RZS 2025 · Popis 2022", nation: { name: "Republika Srbija", population: null, employed: 2401690, gdp: 75180030000, gdp_pc: null, unemployment: 0.1436, wage_net: 117104.44, age65: 0.2319 },
  yields: [{ key: "science", label: "Nauka", description: "Zaposleni u nauci." }], industries: { agriculture: "Poljoprivreda, šumarstvo i ribarstvo" } };
export const sources = [
  { id: "census", title: "Popis stanovništva, domaćinstava i stanova 2022.", publisher: "RZS", vintage: "Popis 2022." },
  { id: "rzs_db", title: "Diseminaciona baza podataka", publisher: "RZS", vintage: { pop_estimate: "Procene 1991–2025", births: "Rođeni 2025" } },
];

/** A minimal app with the shape buildData() and the lenses read. */
export function makeApp({ withCounties = true, withLensValues = true, extra = {} } = {}) {
  const d = { world, cities, states, nation, lenses, sources, resources: null, counties: withCounties ? counties : null, "lens-values": withLensValues ? lensValues : null, ...extra };
  return {
    data: d,
    w: { raw: world, grid: { R: 5, size: world.owner.length } },
    lensById: new Map(lenses.lenses.map((l) => [l.id, l])),
    cityById: new Map(cities.map((c) => [c.id, c])),
    selected: [],
    state: { lens: null },
    cam: { scale: 1.7 },
    loadData: async (name) => d[name] ?? null,
    selectCity(id) { this.selected.push(["city", id]); },
    selectState(id) { this.selected.push(["state", id]); },
    highlightBounds: () => null,
  };
}
