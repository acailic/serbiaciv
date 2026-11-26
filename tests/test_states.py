"""The okruzi, the nation and their labels on a hand-made world.

The interims are small and made here (the real ones come from Tasks 1–5); the ids are the committed territory's. Every
okrug but the last two has three rows of hexes, so that each centroid is a round number. Nothing is written outside
a temporary store: the tests patch store.INTERIM and store.WEB_DATA.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.build import states
from pipeline.core import geo, srb, store, territory
from pipeline.core.hexgrid import HexGrid

YEARS = [2021, 2022, 2023, 2024, 2025]
COLS = 36
GRAD_NOVI_SAD = "89010"
STARI_GRAD, NOVI_BEOGRAD, VRAČAR = "70246", "70181", "70114"
NOVI_SAD, PETROVARADIN, TEMERIN = "80284", "80519", "80446"
ALEKSANDROVAC, BRUS, VARVARIN = "70017", "70343", "70378"
ARILJE, PRIŠTINA = "70041", "90263"

# One row of hexes per entry: (okrug, the municipality on the map); (None, None) is foreign ground.
BANDS = [
    ("RS110", STARI_GRAD), ("RS110", NOVI_BEOGRAD), ("RS110", VRAČAR),  # rows 0–2
    ("RS123", NOVI_SAD), ("RS123", PETROVARADIN), ("RS123", TEMERIN),  # rows 3–5
    ("RS216", ALEKSANDROVAC), ("RS216", BRUS), ("RS216", VARVARIN),  # rows 6–8
    ("RS211", ARILJE),  # row 9
    ("RS231", PRIŠTINA),  # row 10: Kosovo
    (None, None),  # row 11
]

# unit → latest RZS population, registered employment, net wage, share aged 65+, census employed, census unemployed,
#          jobs by NACE section. Vračar, Petrovaradin, Temerin and Varvarin have no row anywhere; Priština, in
# Kosovo, has null ones.
ROWS = {
    STARI_GRAD: (48000, 5000.0, 120000.0, 0.24, 16000, 1000, {"A": 100, "C": 2000, "F": 500, "J": 2000, "M": 6000, "R": 1000}),
    NOVI_BEOGRAD: (210000, 20000.0, 130000.0, 0.17, 90000, 6000, {"B": 100, "C": 12000, "F": 4000, "J": 18000, "M": 30000, "R": 2500}),
    # The sources' own rows for the two grade. Belgrade's is the total of its opštine, which have rows of their own;
    # Novi Sad's is the only row there is for the grad.
    srb.GRAD_BEOGRAD: (1137000, 25000.0, None, None, 106000, 7000,
                       {"A": 100, "B": 100, "C": 14000, "F": 4500, "J": 20000, "M": 36000, "R": 3500}),
    GRAD_NOVI_SAD: (368000, 90000.0, 105000.0, 0.19, 90000, 9000, {"A": 1000, "C": 15000, "F": 6000, "J": 8000, "M": 20000, "R": 2500}),
    ALEKSANDROVAC: (39000, 4000.0, 104512.0, 0.213, 16800, 2200, {"A": 3100, "B": 80, "C": 3900, "F": 1200, "J": 300, "M": 1100, "R": 200}),
    BRUS: (27000, 1000.0, 80000.0, 0.25, 900, 300, {"A": 400, "C": 200, "F": 100, "G": 100, "J": 20, "M": 50, "R": 30}),
    ARILJE: (28000, 2000.0, 80000.0, 0.25, 6000, 800, {"A": 900, "C": 3500, "F": 400, "J": 200, "M": 400, "R": 150}),
    PRIŠTINA: (None, None, None, None, None, None, {}),
}

# okrug → population, employed, unemployment, net wage, share 65+, GDP, growth, yields
EXPECTED = {
    "RS110": (258000, 106000, 0.0619, 128000.0, 0.183, 1000000000, -0.0301,
              {"food": 100, "production": 18600, "gold": 1000000000, "science": 56000, "culture": 3500}),
    "RS123": (368000, 90000, 0.0909, 105000.0, 0.19, 2000000000, -0.0108,
              {"food": 1000, "production": 21000, "gold": 2000000000, "science": 28000, "culture": 2500}),
    "RS216": (66000, 17700, 0.1238, 99609.6, 0.2281, 500000000, -0.1081,
              {"food": 3500, "production": 5480, "gold": 500000000, "science": 1470, "culture": 230}),
    "RS211": (28000, 6000, 0.1176, 80000.0, 0.25, 300000000, -0.125,
              {"food": 900, "production": 3900, "gold": 300000000, "science": 600, "culture": 150}),
}
NATION = (720000, 219700, 0.0808, 109082.36, 0.1933, 3800000000, -0.0323,
          {"food": 5500, "production": 48980, "gold": 3800000000, "science": 86070, "culture": 6380})
NATION_JOBS = {"agriculture": 5500, "mining": 180, "manufacturing": 36600, "trade": 100, "construction": 12200,
               "information": 28520, "professional": 57550, "arts": 6380}

STATE_KEYS = ["fips", "abbr", "name", "population", "employed", "yields", "jobs", "median_income", "median_rent",
              "home_value", "rent_burden", "unemployment", "wage_net", "age65", "gdp", "gdp_year", "gdp_by_industry",
              "gdp_undisclosed", "gdp_estimated", "growth", "growth_years", "ranks", "label", "land", "energy"]
LAND = {"forest": 0.4, "crop": 0.3, "pasture": 0.0, "grass": 0.0, "shrub": 0.0, "wetland": 0.0, "developed": 0.2}


def make_world(bands):
    """The _world interim of a grid with one row per band, and the grid. Every hex has land-cover samples except the
    last of each six, whose figures are wild and must be ignored."""
    grid = HexGrid(srb.HEX_RADIUS_KM, COLS, len(bands))
    proj = geo.MapProjection(min_x=0.0, max_y=0.0, margin=200.0)
    okruzi = sorted({s for s, _ in bands if s})
    counties = sorted({c for _, c in bands if c})
    owner, county, cover = [], [], []
    for state, unit in bands:
        for col in range(COLS):
            if state is None:
                owner.append(srb.FOREIGN)
                county.append(-1)
                cover.append(0)
            else:
                owner.append(okruzi.index(state))
                county.append(counties.index(unit))
                cover.append(0 if col % 6 == 5 else 1)
    pct = {"forest": [40.0 if c else 90.0 for c in cover], "crop": [30.0 if c else 0.0 for c in cover]}
    pct.update({key: [0.0] * grid.size for key in ("pasture", "grass", "shrub", "wetland")})
    pct["developed"] = [20.0 if c else 0.0 for c in cover]
    world = {
        "grid": grid.to_dict(), "projection": proj.to_dict(), "owner": owner, "county": county,
        "water": [srb.LAND] * grid.size, "cover": cover, "pct": pct, "states": okruzi, "counties": counties,
        "cells_of_county": [[c for c, k in enumerate(county) if k == i] for i in range(len(counties))],
    }
    return world, grid


def nace(**sections):
    return {section: float(sections.get(section, 0)) for _, section, _ in srb.INDUSTRIES} | {"total": 0.0, "unknown": 0.0}


def make_interims():
    def series(latest):
        return None if latest is None else [latest + 4000, latest + 3000, latest + 2000, latest + 1000, latest]

    census = {"settlements": [], "units": {
        unit: {"activity": {"employed": row[4], "unemployed": row[5], "inactive": 0, "total15": row[4] + row[5]},
               "industry": nace(**row[6])}
        for unit, row in ROWS.items() if row[4] is not None}}
    rzs = {
        "pop_years": YEARS,
        "pop": {unit: series(row[0]) for unit, row in ROWS.items()},
        "pop_65": {"year": 2025, "by_unit": {unit: row[3] for unit, row in ROWS.items()}},
        "wages": {"year": 2025, "net": {unit: row[2] for unit, row in ROWS.items()}},
        "employment": {"year": 2025, "by_unit": {unit: {"total": row[1]} for unit, row in ROWS.items()}},
    }
    gdp = {"vintage": "Eurostat, BDP po oblastima (nama_10r_3gdp), 2023 — privremeni podaci", "year": 2023, "unit": "MIO_EUR",
           "nuts3": {"RS110": 1000.0, "RS123": 2000.0, "RS211": 300.0, "RS216": 500.0}, "provisional": ["RS110"]}
    return census, rzs, gdp


class StatesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for patched in (mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", root / "web")):
            patched.start()
            self.addCleanup(patched.stop)
        self.world, self.grid = make_world(BANDS)
        self.census, self.rzs, self.gdp = make_interims()

    def build(self):
        """Write the interims as they stand, run the builder, and return (states.json, nation.json, what it printed)."""
        store.save_interim("census", self.census, vintage="Popis 2022")
        store.save_interim("rzs_db", self.rzs, vintage="Procene RZS 2025")
        store.save_interim("gdp", self.gdp, vintage=self.gdp["vintage"])
        store.save_interim("_world", self.world)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            states.build()
        web = store.WEB_DATA
        return (json.loads((web / "states.json").read_text(encoding="utf-8")),
                json.loads((web / "nation.json").read_text(encoding="utf-8")), printed.getvalue())

    @staticmethod
    def okrug(states_json, fips):
        return next(s for s in states_json if s["fips"] == fips)

    def test_requires_and_produces(self):
        self.assertEqual(states.REQUIRES, ["census", "rzs_db", "gdp", "_world"])
        self.assertEqual(states.PRODUCES, ["states.json", "nation.json"])

    def test_one_row_per_okrug_of_the_world_in_its_order_with_the_documented_keys(self):
        states_json, _, _ = self.build()
        self.assertEqual([s["fips"] for s in states_json], ["RS110", "RS123", "RS211", "RS216", "RS231"])
        self.assertEqual([s["name"] for s in states_json],
                         ["Beogradski okrug", "Južnobački okrug", "Zlatiborski okrug", "Rasinski okrug", "Kosovski okrug"])
        for s in states_json:
            self.assertEqual(list(s), STATE_KEYS, s["fips"])
            self.assertIsNone(s["abbr"])
            self.assertIsNone(s["energy"])

    def test_sums_are_over_the_okrugs_units_on_the_map(self):
        states_json, _, _ = self.build()
        for fips, (population, employed, unemployment, wage, age65, gdp, growth, yields) in EXPECTED.items():
            with self.subTest(fips):
                s = self.okrug(states_json, fips)
                self.assertEqual((s["population"], s["employed"], s["unemployment"]), (population, employed, unemployment))
                self.assertEqual((s["wage_net"], s["age65"]), (wage, age65))
                self.assertEqual((s["gdp"], s["gdp_year"], s["gdp_estimated"]), (gdp, 2023, None))
                self.assertEqual((s["growth"], s["growth_years"]), (growth, [2021, 2025]))
                self.assertEqual(s["yields"], yields)
                for field in ("median_income", "median_rent", "home_value", "rent_burden", "gdp_by_industry", "gdp_undisclosed"):
                    self.assertIsNone(s[field], (fips, field))
        rasinski = self.okrug(states_json, "RS216")
        self.assertEqual({k: v for k, v in rasinski["jobs"].items() if v},
                         {"agriculture": 3500, "mining": 80, "manufacturing": 4100, "trade": 100, "construction": 1300,
                          "information": 320, "professional": 1150, "arts": 230})

    def test_age65_is_population_weighted_and_never_averaged(self):
        """(39,000 × 0.213 + 27,000 × 0.25) ÷ 66,000 = 0.2281, where the plain mean of the two shares is 0.2315."""
        states_json, _, _ = self.build()
        self.assertEqual(self.okrug(states_json, "RS216")["age65"], 0.2281)
        self.rzs["pop_65"]["by_unit"][ALEKSANDROVAC] = None  # a unit without the share is in neither sum
        states_json, _, _ = self.build()
        self.assertEqual(self.okrug(states_json, "RS216")["age65"], 0.25)

    def test_wage_net_is_employment_weighted(self):
        """(104,512 × 4,000 + 80,000 × 1,000) ÷ 5,000 = 99,609.6, where the plain mean of the two wages is 92,256."""
        states_json, _, _ = self.build()
        self.assertEqual(self.okrug(states_json, "RS216")["wage_net"], 99609.6)
        self.assertEqual(self.okrug(states_json, "RS110")["wage_net"], 128000.0)

    def test_an_aggregate_the_sources_publish_by_itself_is_counted_once(self):
        """Novi Sad: rows for the grad, none for its two city municipalities, which are the units on the map."""
        states_json, nation, _ = self.build()
        južnobački = self.okrug(states_json, "RS123")
        self.assertEqual((južnobački["population"], južnobački["employed"], južnobački["wage_net"]), (368000, 90000, 105000.0))
        self.assertEqual(južnobački["yields"]["science"], 28000)
        self.assertEqual(nation["nation"]["population"], NATION[0])  # 368,000 once, not twice

    def test_the_aggregates_own_row_is_not_added_to_its_parts(self):
        """Belgrade: the opštine have rows, so the grad's own row (their total) is not added on top of them."""
        states_json, _, _ = self.build()
        beogradski = self.okrug(states_json, "RS110")
        self.assertEqual((beogradski["population"], beogradski["employed"]), (258000, 106000))
        self.assertEqual(beogradski["wage_net"], 128000.0)  # the grad's own row has no wage to inherit

    def test_a_unit_without_a_figure_leaves_the_sum_unknown(self):
        self.rzs["pop"][BRUS][4] = None  # Brus has no estimate for the latest year
        states_json, nation, _ = self.build()
        rasinski = self.okrug(states_json, "RS216")
        self.assertIsNone(rasinski["population"])
        self.assertIsNone(rasinski["growth"])
        self.assertEqual(rasinski["age65"], 0.213)  # over the units with both figures: Aleksandrovac alone
        self.assertIsNone(nation["nation"]["population"])

    def test_a_missing_gdp_leaves_the_okrug_and_the_nation_without_one(self):
        del self.gdp["nuts3"]["RS211"]
        states_json, nation, _ = self.build()
        zlatiborski = self.okrug(states_json, "RS211")
        self.assertIsNone(zlatiborski["gdp"])
        self.assertEqual(zlatiborski["gdp_year"], 2023)
        self.assertIsNone(zlatiborski["yields"]["gold"])
        self.assertIsNone(nation["nation"]["gdp"])
        self.assertIsNone(nation["nation"]["yields"]["gold"])

    def test_a_kosovo_okrug_is_null_everywhere_but_for_its_name_label_and_land(self):
        states_json, _, _ = self.build()
        kosovska = self.okrug(states_json, "RS231")
        for field in STATE_KEYS:
            if field not in ("fips", "abbr", "name", "label", "land"):
                self.assertIsNone(kosovska[field], field)
        self.assertEqual((kosovska["fips"], kosovska["abbr"], kosovska["name"]), ("RS231", None, "Kosovski okrug"))
        self.assertEqual(kosovska["label"], {"x": 151.6, "y": 75.0, "angle": 0, "size": 19.2})
        self.assertEqual(kosovska["land"], LAND)

    def test_the_label_is_the_centroid_of_the_okrugs_hexes(self):
        states_json, nation, _ = self.build()
        # 108 hexes: 3.2 × √108 is clamped to 22; 36 hexes: 3.2 × √36 = 19.2
        self.assertEqual(self.okrug(states_json, "RS110")["label"], {"x": 153.0, "y": 7.5, "angle": 0, "size": 22.0})
        self.assertEqual(self.okrug(states_json, "RS123")["label"], {"x": 154.4, "y": 30.0, "angle": 0, "size": 22.0})
        self.assertEqual(self.okrug(states_json, "RS216")["label"], {"x": 153.0, "y": 52.5, "angle": 0, "size": 22.0})
        self.assertEqual(self.okrug(states_json, "RS211")["label"], {"x": 155.9, "y": 67.5, "angle": 0, "size": 19.2})
        self.assertEqual(nation["nation"]["label"], {"x": 153.7, "y": 33.8, "angle": 0, "size": 22.0})  # rows 0–9

    def test_land_is_the_mean_cover_of_the_okrugs_sampled_hexes_or_null(self):
        states_json, _, _ = self.build()
        for s in states_json:
            self.assertEqual(s["land"], LAND, s["fips"])
        for cell, owner in enumerate(self.world["owner"]):
            if owner >= 0 and self.world["states"][owner] == "RS211":
                self.world["cover"][cell] = 0  # no samples at all
        states_json, _, _ = self.build()
        self.assertIsNone(self.okrug(states_json, "RS211")["land"])

    def test_ranks_are_among_the_okruzi_with_data(self):
        states_json, _, _ = self.build()
        for fips, place in {"RS123": 1, "RS110": 2, "RS216": 3, "RS211": 4}.items():
            ranks = self.okrug(states_json, fips)["ranks"]
            self.assertEqual([ranks[k] for k in ("population", "gdp", "growth")], [place] * 3, fips)
            self.assertEqual(list(ranks), ["population", "gdp", "gdp_per_capita", "growth", "food", "production", "gold", "science", "culture"])
        # GDP per resident: the small okrug with the big figure comes first
        self.assertEqual([self.okrug(states_json, f)["ranks"]["gdp_per_capita"] for f in ("RS211", "RS216", "RS123", "RS110")], [1, 2, 3, 4])
        self.assertIsNone(self.okrug(states_json, "RS231")["ranks"])

    def test_the_nation_is_the_sum_over_the_okruzi_with_data(self):
        states_json, nation, _ = self.build()
        n = nation["nation"]
        population, employed, unemployment, wage, age65, gdp, growth, yields = NATION
        self.assertEqual((n["population"], n["employed"], n["unemployment"]), (population, employed, unemployment))
        self.assertEqual((n["wage_net"], n["age65"], n["gdp"]), (wage, age65, gdp))
        self.assertEqual((n["growth"], n["growth_years"]), (growth, [2021, 2025]))
        self.assertEqual(n["yields"], yields)
        self.assertEqual({k: v for k, v in n["jobs"].items() if v}, NATION_JOBS)
        with_data = [s for s in states_json if s["population"] is not None]
        self.assertEqual(len(with_data), 4)  # Kosovo's okrug is not among them
        for key in ("population", "employed", "gdp"):
            self.assertEqual(n[key], sum(s[key] for s in with_data), key)
        for key in srb.YIELD_KEYS:
            self.assertEqual(n["yields"][key], sum(s["yields"][key] for s in with_data), key)
        for key in srb.INDUSTRY_KEYS:
            self.assertEqual(n["jobs"][key], sum(s["jobs"][key] for s in with_data), key)

    def test_the_nation_row_has_the_okrugs_keys(self):
        _, nation, _ = self.build()
        n = nation["nation"]
        self.assertEqual(list(n), STATE_KEYS)
        self.assertEqual((n["fips"], n["abbr"], n["gdp_year"]), ("RS", None, 2023))
        self.assertEqual(n["name"], territory.name("RS"))  # the country's node, as the tree names it
        self.assertEqual(n["land"], LAND)
        for field in ("median_income", "median_rent", "home_value", "rent_burden", "gdp_by_industry", "gdp_undisclosed",
                      "gdp_estimated", "ranks", "energy"):
            self.assertIsNone(n[field], field)

    def test_nation_json(self):
        _, nation, _ = self.build()
        self.assertEqual(list(nation), ["vintage", "year", "gdp_vintage", "nation", "yields", "industries"])
        self.assertEqual(nation["vintage"], "Procene RZS 2025 · Popis 2022")  # the latest year of the RZS estimates
        self.assertEqual((nation["year"], nation["gdp_vintage"]), (2025, self.gdp["vintage"]))
        self.assertEqual(nation["yields"], srb.YIELDS)
        self.assertEqual(nation["industries"], srb.INDUSTRY_NAMES)


if __name__ == "__main__":
    unittest.main()
