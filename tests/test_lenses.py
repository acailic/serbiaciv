"""The lenses builder on hand-made interims: the formulas per municipality, the spread to hexes and the domain.

The fixture is a 5×3 grid on the real nomenklatura. Aleksandrovac (a city) lies in the Rasinska oblast; Medijana (a
city municipality of Niš), Aleksinac and Gadžin Han in the Nišavska; Glogovac in Kosovo and Metohija; Novi Sad and
Petrovaradin (the two city municipalities of Grad Novi Sad) in the Južnobačka. Hex 7 is water, hex 8 is foreign land,
and Varvarin is smaller than a hex, so it holds none. tests/test_counties_table.py builds the municipalities table
on the same fixture.
"""

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.build import lenses
from pipeline.core import srb, store

HEX_AREA = 1.5 * math.sqrt(3) * 5.0 ** 2  # km²
CENSUS_VINTAGE = "Popis stanovništva, domaćinstava i stanova 2022. u Republici Srbiji"
POP_YEARS = [2015, 2024, 2025]
OKRUZI = ["RS216", "RS225", "RS231", "RS123"]  # Rasinska, Nišavska, Kosovska, Južnobačka oblast
OPSTINE = ["70017", "71331", "70025", "70467", "90034", "70378", "80284", "80519"]  # in _world.counties order
OPSTINE_NAMES = ["Aleksandrovac", "Medijana", "Aleksinac", "Gadžin Han", "Glogovac", "Varvarin", "Novi Sad", "Petrovaradin"]
# hex:            0    1    2    3    4    5    6     7     8    9   10   11   12   13   14
OWNER =          [0,   0,   1,   1,   1,   1,   2,   -1,   -2,   1,   1,   1,   3,   3,   3]
COUNTY =         [0,   0,   1,   1,   2,   2,   4,   -1,   -1,   3,   3,   3,   6,   6,   7]
WATER =          [0,   0,   0,   0,   0,   0,   0,    3,    0,   0,   0,   0,   0,   0,   0]
ELEV =           [200, 210, 150, 160, 300, 310, 600,   70,  200, 250, 260, 250,  80,  85,  90]
RELIEF =         [0,   0,   0,   0,   1,   1,   2,    0,    1,   1,   1,   1,   0,   0,   0]
COVER =          [1,   1,   9,   9,   7,   7,   1,    0,    0,   4,   6,   3,   9,   7,   7]
CELLS_OF_COUNTY = [[0, 1], [2, 3], [4, 5], [9, 10, 11], [6], [], [12, 13], [14]]
AREAS = [395.0, 30.0, 707.0, 325.0, 290.0, 249.0, 250.0, 85.0]  # km² of each polygon, as the world builder measures it
PCT = {
    "forest": [60, 60, 0, 0, 10, 10, 50, 0, 0, 70, 80, 90, 10, 10, 0],
    "crop": [30, 30, 0, 0, 80, 80, 10, 0, 0, 20, 10, 0, 60, 60, 70],
    "pasture": [10, 10, 30, 30, 10, 10, 30, 0, 0, 10, 10, 10, 30, 30, 30],
    "grass": [0] * 15,
    "shrub": [0] * 15,
    "wetland": [0] * 15,
    "developed": [0, 0, 70, 70, 0, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0],
}
COVER_TABLE = [  # upstream's ids and keys, as pipeline/build/world.py writes them into world.json
    {"id": 0, "key": "none", "name": "Nema podataka", "rule": ""},
    {"id": 1, "key": "forest_deciduous", "name": "Listopadna šuma", "color": "#4f7a35", "rule": ""},
    {"id": 2, "key": "forest_evergreen", "name": "Četinarska šuma", "color": "#2f5a3a", "rule": ""},
    {"id": 3, "key": "forest_mixed", "name": "Mešovita šuma", "color": "#43703f", "rule": ""},
    {"id": 4, "key": "scrub", "name": "Žbunje", "color": "#c9b07a", "rule": ""},
    {"id": 5, "key": "grassland", "name": "Travnjaci", "color": "#a9b35a", "rule": ""},
    {"id": 6, "key": "pasture", "name": "Livade i pašnjaci", "color": "#8fb04e", "rule": ""},
    {"id": 7, "key": "cropland", "name": "Njive", "color": "#c2b84e", "rule": ""},
    {"id": 8, "key": "wetland", "name": "Močvare", "color": "#4f8a6e", "rule": ""},
    {"id": 9, "key": "urban", "name": "Gradsko", "color": "#8a8378", "rule": ""},
    {"id": 10, "key": "barren", "name": "Golo tlo", "color": "#bfae95", "rule": ""},
    {"id": 11, "key": "ice", "name": "Led i sneg", "color": "#e8eef2", "rule": ""},
]
CENSUS_UNITS = {
    "70017": {
        "education": {"total15": 3300, "higher": 810},
        "activity": {"employed": 1680, "unemployed": 220, "inactive": 1400, "total15": 3300},
        "industry": {"total": 1680, "A": 310, "B": 8, "C": 390, "unknown": 4},
        "commute": {"total": 1680, "same_unit": 980, "other_unit": 520, "other_oblast": 140, "abroad": 40},
        "religion": {"total": 3945, "orthodox": 3700},
        "ethnicity": {"total": 3945, "srbi": 3790},
    },
    "71331": {
        "education": {"total15": 41000, "higher": 16400},
        "activity": {"employed": 18000, "unemployed": 2000, "inactive": 21000, "total15": 41000},
        "industry": {"total": 18000, "A": 90, "B": 180, "C": 3780, "unknown": 90},
        "commute": {"total": 18000, "same_unit": 10800, "other_unit": 5400, "other_oblast": 1260, "abroad": 540},
        "religion": {"total": 41000, "orthodox": 36490},
        "ethnicity": {"total": 41000, "srbi": 34030},
    },
    "79022": {  # Grad Niš: each of its city municipalities has its own row, so none of them may inherit this one
        "education": {"total15": 500000, "higher": 250000},
        "activity": {"employed": 160000, "unemployed": 14000, "inactive": 326000, "total15": 500000},
        "industry": {"total": 160000, "C": 32000, "unknown": 100},
        "commute": {"total": 160000, "same_unit": 130000, "other_unit": 25000, "other_oblast": 5000, "abroad": 0},
        "religion": {"total": 500000, "orthodox": 460000},
        "ethnicity": {"total": 500000, "srbi": 470000},
    },
    "70025": {  # the census prints nothing for several of its cells
        "education": {"total15": 0, "higher": 0},
        "activity": {"employed": 1000, "unemployed": None, "inactive": 500, "total15": 1500},
        "industry": {"total": 1000, "C": 100, "unknown": 0},
        "commute": None,
        "religion": {"total": 1600, "orthodox": 1500},
        "ethnicity": {"total": 1600, "srbi": 1590},
    },
    "70467": {
        "education": {"total15": 2000, "higher": 200},
        "activity": {"employed": 900, "unemployed": 300, "inactive": 800, "total15": 2000},
        "industry": {"total": 900, "C": 100, "unknown": 0},
        "commute": {"total": 900, "same_unit": 800, "other_unit": 0, "other_oblast": 100, "abroad": 0},
        "religion": {"total": 2200, "orthodox": 2100},
        "ethnicity": {"total": 2200, "srbi": 2200},
    },
    "89010": {  # Grad Novi Sad: the census has the grad, not its two city municipalities
        "education": {"total15": 200000, "higher": 60000},
        "activity": {"employed": 100000, "unemployed": 8000, "inactive": 92000, "total15": 200000},
        "industry": {"total": 100000, "C": 15000, "unknown": 100},
        "commute": {"total": 100000, "same_unit": 92000, "other_unit": 5000, "other_oblast": 3000, "abroad": 0},
        "religion": {"total": 250000, "orthodox": 200000},
        "ethnicity": {"total": 250000, "srbi": 190000},
    },
}
CITIES = {  # what Task 6's cities builder writes for the non-Kosovo units
    "cities": [{"id": "70017", "name": "Aleksandrovac", "population": 10000}, {"id": "89010", "name": "Novi Sad", "population": 350000}],
    "units": {
        "70017": {"is_city": True, "why": "", "city": "70017"},
        "71331": {"is_city": False, "why": "city municipality of an aggregate that is a city", "city": "79022"},
        "70025": {"is_city": False, "why": "largest urban settlement under the minimum", "city": None},
        "80284": {"is_city": False, "why": "city municipality of an aggregate that is a city", "city": "89010"},
        "80519": {"is_city": False, "why": "city municipality of an aggregate that is a city", "city": "89010"},
    },
}
# The land lenses take the edition they cite from these payload vintages.
EDITIONS = {"dem": "Copernicus GLO-30, 2021", "landcover": "ESA WorldCover v200, 2021"}


def fixture() -> dict:
    """{"interim": {name: payload}, "web": {file: document}}: everything the lenses and counties builders read."""
    grid = {"radius": 5.0, "cols": 5, "rows": 3}
    per_cell = {"owner": list(OWNER), "county": list(COUNTY), "cover": list(COVER), "pct": {k: list(v) for k, v in PCT.items()}}
    world = {
        "grid": dict(grid), "width": 600.0, "height": 300.0,
        "states": list(OKRUZI), "counties": list(OPSTINE), "cells_of_county": [list(c) for c in CELLS_OF_COUNTY],
        "county_area_km2": list(AREAS), **per_cell,
    }
    rzs = {
        "pop_years": list(POP_YEARS),
        "pop": {"70017": [8000, 9600, 10000], "71331": [40000, 38000, 37000], "79022": [500000, 490000, 480000],
                "70025": [12000, None, 14400], "70467": [None, 3000, 3025], "90034": None, "70378": [2000, 1900, 1800],
                "80284": [300000, 310000, 320000], "80519": [30000, 31000, 32000]},
        "pop_65": {"year": 2025, "by_unit": {"70017": 0.213, "71331": 0.19, "70025": 0.22, "70467": 0.3, "90034": None,
                                             "70378": 0.28, "89010": 0.19}},
        "wages": {"year": 2025, "net": {"70017": 104512.0, "71331": 73000.0, "79022": 66000.0, "70025": None, "70467": 68250.4,
                                        "90034": None, "70378": 60000.0, "89010": 90000.0}, "gross": {"70017": 145610.0}},
        "natural_increase": {"year": 2025, "by_unit": {"70017": -6.2, "71331": -4.1, "70025": -4.0, "70467": -9.1, "90034": None,
                                                      "70378": -15.0, "80284": -3.0, "80519": -2.0}},
        "life_expectancy": {"year": 2024, "by_unit": {"70017": {"m": 72.0, "f": 77.5}, "71331": {"m": 71.0, "f": 76.2}, "70025": None,
                                                      "70467": {"m": 70.5, "f": 75.5}, "90034": None, "70378": {"m": 70.0, "f": 75.0},
                                                      "89010": {"m": 72.0, "f": 77.0}}},
    }
    world_json = {
        "version": 2, "grid": dict(grid), "width": 600.0, "height": 300.0, "margin": 200.0,
        "projection": {"min_x": -200.0, "max_y": 400.0, "margin": 200.0},
        "elev": list(ELEV), "elev_max": [e + 20 for e in ELEV], "elev_range": [20] * 15, "water": list(WATER), "relief": list(RELIEF),
        "states": [{"fips": f, "abbr": None, "name": n} for f, n in zip(OKRUZI, ["Rasinski okrug", "Nišavski okrug", "Kosovski okrug", "Južnobački okrug"])],
        "counties": [{"geoid": g, "name": n} for g, n in zip(OPSTINE, OPSTINE_NAMES)],
        "rivers": [], "tables": {"cover": copy.deepcopy(COVER_TABLE)},
        **per_cell,
    }
    interim = {
        "_world": {"vintage": None, "data": world},
        "_cities": {"vintage": None, "data": copy.deepcopy(CITIES)},
        "census": {"vintage": CENSUS_VINTAGE, "data": {"vintage": CENSUS_VINTAGE, "settlements": [], "units": copy.deepcopy(CENSUS_UNITS)}},
        "rzs_db": {"vintage": None, "data": rzs},
        "dem": {"vintage": EDITIONS["dem"], "data": {}},
        "landcover": {"vintage": EDITIONS["landcover"], "data": {}},
    }
    return {"interim": interim, "web": {"world.json": world_json}}


def write_fixture(root: Path, fx: dict) -> None:
    """The fixture's interim payloads into root/interim and its documents into root/web."""
    for name, payload in fx["interim"].items():
        path = root / "interim" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    for name, doc in fx["web"].items():
        path = root / "web" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc))


def build(builder, fx: dict) -> dict:
    """Run `builder` on the fixture and return the document it wrote to web/data."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixture(root, fx)
        with mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", root / "web"), \
                mock.patch.object(lenses, "WEB_DATA", root / "web"), mock.patch("builtins.print"):
            builder.build()
        doc = json.loads((root / "web" / builder.PRODUCES[0]).read_text())
        if builder is lenses:
            # Materialize the v2 contract as the browser does, retaining the existing per-cell expectations below.
            indexed = json.loads((root / "web" / "lens-values.json").read_text())["values"]
            world = fx["web"]["world.json"]
            for lens in doc["lenses"]:
                source = lens["value_source"]
                if source["kind"] == "municipality":
                    values = indexed[source["key"]]
                    lens["values"] = [values[c] if o >= 0 and 0 <= c < len(values) else None
                                      for o, c in zip(world["owner"], world["county"])]
                else:
                    mapping = source.get("categoryValues")
                    lens["values"] = [None if o < 0 or v is None else mapping.get(str(v)) if mapping else v
                                      for o, v in zip(world["owner"], world[source["field"]])]
        return doc


class ChangeYearsTest(unittest.TestCase):
    def test_the_lens_measures_a_ten_year_change(self):
        """pop_change starts in 2015; the growth field of cities and okruzi (Task 6) starts in srb.GROWTH_YEARS."""
        self.assertEqual(srb.LENS_CHANGE_YEARS, (2015, None))
        self.assertNotEqual(srb.LENS_CHANGE_YEARS[0], srb.GROWTH_YEARS[0])


class UnitValuesTest(unittest.TestCase):
    def setUp(self):
        fx = fixture()
        self.world = fx["interim"]["_world"]["data"]
        self.census = fx["interim"]["census"]["data"]
        self.rzs = fx["interim"]["rzs_db"]["data"]

    def values(self, geoid):
        return lenses.unit_values(geoid, self.world, self.census, self.rzs)

    def test_two_municipalities_from_known_counts(self):
        a, b = self.values("70017"), self.values("71331")
        self.assertEqual(a["population"], 10000)
        self.assertEqual(b["population"], 37000)
        self.assertEqual(a["land_km2"], 395.0)  # the polygon's area, not a count of hexes
        self.assertAlmostEqual(a["density"], 10000 / 395)
        self.assertAlmostEqual(b["density"], 37000 / 30)
        self.assertEqual(a["pop_change"], 0.25)  # 10,000 in 2025 over 8,000 in 2015
        self.assertAlmostEqual(b["pop_change"], -0.075)
        self.assertEqual(a["age65"], 0.213)
        self.assertEqual(a["wage_net"], 104512.0)
        self.assertEqual(a["natural_increase"], -6.2)
        self.assertEqual(a["life_expectancy"], (72.0 + 77.5) / 2)
        self.assertAlmostEqual(a["education"], 810 / 3300)
        self.assertAlmostEqual(a["unemployment"], 220 / (1680 + 220))
        self.assertAlmostEqual(a["manufacturing"], 390 / 1680)
        self.assertAlmostEqual(a["commute"], (520 + 140) / 1680)
        self.assertAlmostEqual(a["orthodox"], 3700 / 3945)
        self.assertAlmostEqual(a["serbs"], 3790 / 3945)
        self.assertAlmostEqual(b["education"], 16400 / 41000)
        self.assertAlmostEqual(b["unemployment"], 2000 / 20000)
        self.assertAlmostEqual(b["manufacturing"], 3780 / 18000)
        self.assertAlmostEqual(b["commute"], (5400 + 1260) / 18000)
        self.assertAlmostEqual(b["orthodox"], 36490 / 41000)
        self.assertAlmostEqual(b["serbs"], 34030 / 41000)

    def test_a_missing_term_is_null_never_zero(self):
        c, d = self.values("70025"), self.values("70467")
        self.assertIsNone(c["commute"])  # the census prints no commute row
        self.assertIsNone(c["education"])  # nobody aged 15 and over: a zero denominator is no data, not 0 %
        self.assertIsNone(c["unemployment"])  # the unemployed are not published
        self.assertIsNone(c["wage_net"])  # the office withholds the wage
        self.assertIsNone(c["life_expectancy"])
        self.assertEqual(d["commute"], 100 / 900)  # a published 0 is a term like any other
        self.assertEqual(d["serbs"], 1.0)

    def test_commuting_is_a_share_of_all_employed_not_only_daily_migrants(self):
        record = {"activity": {"employed": 6311}, "commute": {"total": 3160, "other_unit": 661, "other_oblast": 227}}
        self.assertAlmostEqual(lenses.census_values(record)["commute"], 888 / 6311)
        record["activity"]["employed"] = None
        self.assertIsNone(lenses.census_values(record)["commute"])

    def test_change_needs_the_base_year(self):
        d = self.values("70467")  # no estimate for 2015
        self.assertEqual(d["population"], 3025)
        self.assertIsNone(d["pop_change"])

    def test_a_municipality_smaller_than_a_hex_keeps_its_own_area(self):
        v = self.values("70378")  # it holds no hex at all
        self.assertEqual(v["land_km2"], 249.0)
        self.assertAlmostEqual(v["density"], 1800 / 249)

    def test_without_a_positive_area_there_is_no_density(self):
        for area in (None, 0, -5.0):
            with self.subTest(area=area):
                self.world["county_area_km2"][0] = area
                v = self.values("70017")
                self.assertEqual(v["land_km2"], area)
                self.assertIsNone(v["density"])

    def test_an_interim_from_before_the_areas_falls_back_to_whole_hexes(self):
        del self.world["county_area_km2"]
        a = self.values("70017")
        self.assertEqual(a["land_km2"], 2 * HEX_AREA)
        self.assertAlmostEqual(a["density"], 10000 / (2 * HEX_AREA))
        self.assertEqual(self.values("70378")["land_km2"], 0)

    def test_kosovo_has_land_but_no_statistics(self):
        k = self.values("90034")
        self.assertEqual(k["land_km2"], 290.0)
        for key, value in k.items():
            if key != "land_km2":
                self.assertIsNone(value, key)

    def test_kosovo_is_null_even_where_a_source_has_a_number(self):
        """Kosovo and Metohija is on the map, but the site shows no statistics for it."""
        self.rzs["pop"]["90034"] = [1000, 1000, 1000]
        self.census["units"]["90034"] = copy.deepcopy(CENSUS_UNITS["70467"])
        k = self.values("90034")
        self.assertIsNone(k["population"])
        self.assertIsNone(k["education"])

    def test_the_first_part_of_an_aggregate_inherits_its_row_and_only_that_part(self):
        """Shaped like Novi Sad: the census of 2022 has Grad Novi Sad (89010), the map has its two city municipalities."""
        novi, petrovaradin = self.values("80284"), self.values("80519")
        self.assertEqual(novi["education"], 60000 / 200000)  # the aggregate's row
        self.assertEqual(novi["manufacturing"], 15000 / 100000)
        self.assertIsNone(petrovaradin["education"])  # the grad's figures are counted once, never twice
        self.assertIsNone(petrovaradin["manufacturing"])
        self.assertEqual(novi["population"], 320000)  # where the office has the parts' own rows, they are used
        self.assertEqual(petrovaradin["population"], 32000)
        self.assertEqual(novi["natural_increase"], -3.0)
        self.assertEqual(petrovaradin["natural_increase"], -2.0)

    def test_the_rule_holds_table_by_table(self):
        """The office, too, has the grad in some tables and the parts in others."""
        novi, petrovaradin = self.values("80284"), self.values("80519")
        self.assertEqual(novi["wage_net"], 90000.0)  # wages: only the grad's row
        self.assertEqual(novi["age65"], 0.19)
        self.assertEqual(novi["life_expectancy"], 74.5)
        self.assertIsNone(petrovaradin["wage_net"])
        self.assertIsNone(petrovaradin["age65"])

    def test_a_part_with_its_own_row_never_inherits(self):
        """Medijana has its own rows although Grad Niš (79022) has rows too, like every opština of Beograd."""
        m = self.values("71331")
        self.assertAlmostEqual(m["education"], 16400 / 41000)
        self.assertEqual(m["wage_net"], 73000.0)
        self.assertEqual(m["population"], 37000)


class SpreadTest(unittest.TestCase):
    def test_each_hex_takes_its_municipalitys_value_and_kosovo_water_and_foreign_land_stay_null(self):
        values = lenses.spread([10.0, 20.0, None, 30.0, None, 40.0], OWNER[:12], COUNTY[:12])
        self.assertEqual(values, [10.0, 10.0, 20.0, 20.0, None, None, None, None, None, 30.0, 30.0, 30.0])


class DomainTest(unittest.TestCase):
    def test_the_2nd_and_98th_percentile_of_the_values(self):
        self.assertEqual(lenses.percentile_domain(list(range(1, 101))), [2, 98])

    def test_nulls_are_skipped_and_a_log_scale_ignores_what_is_not_positive(self):
        self.assertEqual(lenses.percentile_domain([None] + list(range(1, 101))), [2, 98])
        self.assertEqual(lenses.percentile_domain([0, -5] + list(range(1, 101)), log=True), [2, 98])

    def test_without_usable_values_there_is_no_domain(self):
        self.assertIsNone(lenses.percentile_domain([None, None]))
        self.assertIsNone(lenses.percentile_domain([0, 0], log=True))


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = build(lenses, fixture())
        cls.lens = {lens["id"]: lens for lens in cls.doc["lenses"]}
        cls.unit_lenses = ["density", "pop_change", "natural_increase", "age65", "education", "wages", "unemployment",
                           "manufacturing", "commute", "orthodox", "serbs", "life_expectancy"]

    def test_the_fifteen_lenses_in_their_order(self):
        self.assertEqual([lens["id"] for lens in self.doc["lenses"]], self.unit_lenses + ["elevation", "relief", "land_cover"])

    def test_what_each_lens_declares(self):
        table = {
            "density": ("people", "Gustina naseljenosti", "stanovnika / km²", "int", "log", "neutral", "rzs_db"),
            "pop_change": ("people", "Promena broja stanovnika", "%", "pct", "linear", "neutral", "rzs_db"),
            "natural_increase": ("people", "Prirodni priraštaj", "na 1.000 stanovnika", "float", "linear", "neutral", "rzs_db"),
            "age65": ("people", "Stariji od 65 godina", "%", "pct", "linear", "neutral", "rzs_db"),
            "education": ("work", "Visoko obrazovanje", "%", "pct", "linear", "good", "census"),
            "wages": ("work", "Prosečna neto zarada", "RSD", "rsd", "log", "good", "rzs_db"),
            "unemployment": ("work", "Stopa nezaposlenosti", "%", "pct", "linear", "bad", "census"),
            "manufacturing": ("work", "Prerađivačka industrija", "%", "pct", "linear", "neutral", "census"),
            "commute": ("work", "Rad u drugoj opštini", "%", "pct", "linear", "neutral", "census"),
            "orthodox": ("identity", "Pravoslavni", "%", "pct", "linear", "neutral", "census"),
            "serbs": ("identity", "Srbi", "%", "pct", "linear", "neutral", "census"),
            "life_expectancy": ("life", "Očekivano trajanje života", "godine", "float", "linear", "good", "rzs_db"),
            "elevation": ("land", "Nadmorska visina", "m", "int", "linear", "neutral", "dem"),
            "relief": ("land", "Reljef", "", "category", "linear", "neutral", "dem"),
            "land_cover": ("land", "Zemljišni pokrivač", "", "category", "linear", "neutral", "landcover"),
        }
        self.assertEqual(sorted(table), sorted(self.lens))
        for lid, (group, name, unit, fmt, scale, higher_is, source) in table.items():
            with self.subTest(lid):
                lens = self.lens[lid]
                self.assertEqual((lens["group"], lens["name"], lens["unit"]), (group, name, unit))
                self.assertEqual((lens["format"], lens["scale"], lens["higher_is"], lens["source"]), (fmt, scale, higher_is, source))
                self.assertEqual(lens["icon"], f"l-{lid}")
                self.assertTrue(lens["emoji"] and lens["ramp"] and lens["description"] and lens["note"], lid)

    def test_the_groups_in_their_order(self):
        self.assertEqual(self.doc["groups"], [
            {"id": "people", "name": "Stanovništvo"}, {"id": "work", "name": "Rad i zarade"}, {"id": "identity", "name": "Identitet"},
            {"id": "life", "name": "Kvalitet života"}, {"id": "land", "name": "Zemljište"}])

    def test_a_unit_lens_gives_each_hex_its_municipalitys_value(self):
        self.assertEqual(self.lens["education"]["values"],
                         [0.2455, 0.2455, 0.4, 0.4, None, None, None, None, None, 0.1, 0.1, 0.1, 0.3, 0.3, None])
        self.assertEqual(self.lens["density"]["values"],
                         [25, 25, 1233, 1233, 20, 20, None, None, None, 9, 9, 9, 1280, 1280, 376])

    def test_values_are_rounded_to_their_format(self):
        self.assertEqual(self.lens["wages"]["values"],
                         [104512, 104512, 73000, 73000, None, None, None, None, None, 68250, 68250, 68250, 90000, 90000, None])
        self.assertEqual(self.lens["life_expectancy"]["values"],
                         [74.8, 74.8, 73.6, 73.6, None, None, None, None, None, 73.0, 73.0, 73.0, 74.5, 74.5, None])
        self.assertEqual(self.lens["pop_change"]["values"],
                         [0.25, 0.25, -0.075, -0.075, 0.2, 0.2, None, None, None, None, None, None, 0.0667, 0.0667, 0.0667])

    def test_kosovo_water_and_foreign_land_are_null_in_every_unit_lens(self):
        for lid in self.unit_lenses:
            with self.subTest(lid):
                self.assertEqual(self.lens[lid]["values"][6:9], [None, None, None])

    def test_the_land_lenses_show_kosovo(self):
        self.assertEqual(self.lens["elevation"]["values"], [200, 210, 150, 160, 300, 310, 600, None, None, 250, 260, 250, 80, 85, 90])
        self.assertEqual(self.lens["relief"]["values"], [0, 0, 0, 0, 1, 1, 2, None, None, 1, 1, 1, 0, 0, 0])

    def test_relief_categories(self):
        lens = self.lens["relief"]
        self.assertEqual([(c["id"], c["name"]) for c in lens["categories"]], [("flat", "Ravnica"), ("hills", "Brdovito"),
                                                                             ("mountains", "Planine"), ("peaks", "Vrhovi")])
        self.assertEqual(lens["domain"], [0, 3])
        self.assertEqual(lens["ramp"], [c["color"] for c in lens["categories"]])

    def test_land_cover_takes_its_categories_from_the_world_cover_table(self):
        lens = self.lens["land_cover"]
        shown = [1, 2, 4, 6, 7, 8, 9, 10]
        table = {e["id"]: e for e in COVER_TABLE}
        self.assertEqual([c["id"] for c in lens["categories"]], [table[i]["key"] for i in shown])
        self.assertEqual([c["name"] for c in lens["categories"]], [table[i]["name"] for i in shown])
        self.assertEqual([c["color"] for c in lens["categories"]], [table[i]["color"] for i in shown])
        self.assertEqual(lens["ramp"], [table[i]["color"] for i in shown])
        self.assertEqual(lens["domain"], [0, 7])
        # hex 11 is mixed forest (3), a class the lens does not show
        self.assertEqual(lens["values"], [0, 0, 6, 6, 4, 4, 0, None, None, 2, 3, None, 6, 4, 4])

    def test_domains_are_the_percentiles_of_the_municipalities(self):
        self.assertEqual(self.lens["density"]["domain"], [7, 1280])
        self.assertEqual(self.lens["education"]["domain"], [0.1, 0.4])  # Aleksinac and Petrovaradin have no value
        self.assertEqual(self.lens["pop_change"]["domain"], [-0.1, 0.25])  # Gadžin Han has no estimate for 2015
        self.assertEqual(self.lens["life_expectancy"]["domain"], [72.5, 74.8])

    def test_the_domain_of_a_land_lens_spans_the_hexes(self):
        self.assertEqual(self.lens["elevation"]["domain"], [80, 600])

    def test_every_note_names_its_year_and_its_source(self):
        for lid, lens in self.lens.items():
            with self.subTest(lid):
                self.assertTrue(lens["note"].strip(), lid)
        rzs = "Republičkog zavoda za statistiku"
        for lid, year in [("density", "2025"), ("pop_change", "2025"), ("natural_increase", "2025"), ("age65", "2025"), ("wages", "2025"),
                          ("life_expectancy", "2024")]:  # the life-expectancy table lags the estimate
            with self.subTest(lid):
                self.assertIn(year, self.lens[lid]["note"])
                self.assertIn(rzs, self.lens[lid]["note"])
        self.assertIn("2015", self.lens["pop_change"]["note"])
        for lid in ["education", "unemployment", "manufacturing", "commute", "orthodox", "serbs"]:
            with self.subTest(lid):
                self.assertIn("2022", self.lens[lid]["note"])
                self.assertIn("Popis", self.lens[lid]["note"])
        self.assertIn("Copernicus", self.lens["elevation"]["note"])
        self.assertIn("2021", self.lens["elevation"]["note"])
        self.assertIn("ESA WorldCover", self.lens["land_cover"]["note"])
        self.assertIn("2021", self.lens["land_cover"]["note"])

    def test_life_expectancy_says_it_is_the_mean_of_men_and_women(self):
        note = self.lens["life_expectancy"]["note"]
        for word in ("sredina", "muškar", "žen"):
            self.assertIn(word, note)

    def test_vintage_names_both_editions(self):
        self.assertEqual(self.doc["vintage"], "Procene RZS 2025 · Popis 2022")

    def test_the_builder_declares_what_it_reads_and_writes(self):
        self.assertEqual(lenses.REQUIRES, ["_world", "_cities", "census", "rzs_db", "world.json"])
        self.assertEqual(lenses.PRODUCES, ["lenses.json", "lens-values.json"])


if __name__ == "__main__":
    unittest.main()
