"""The cities builder on a hand-made world: which units are cities, where each stands and what it yields.

The interims are small and made here (the real ones come from Tasks 1–5); the ids are the committed territory's, so
the rules about aggregates and city municipalities run against the real tree. Nothing is written outside a temporary
store: the tests patch store.INTERIM, store.WEB_DATA and the builder's override file.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.build import cities
from pipeline.core import geo, srb, store, territory
from pipeline.core.hexgrid import HexGrid
from pipeline.core.srtext import okrug_name

YEARS = [2021, 2022, 2023, 2024, 2025]
COLS = 36
GRAD_NIŠ = "79022"
STARI_GRAD, NOVI_BEOGRAD, VRAČAR = "70246", "70181", "70114"
ALEKSANDROVAC, BRUS, KRUŠEVAC, TRSTENIK, VARVARIN = "70017", "70343", "70670", "71170", "70378"
MEDIJANA, ALEKSINAC, DOLJEVAC, GADŽIN_HAN = "71331", "70025", "70513", "70467"
ARILJE, PRIŠTINA = "70041", "90263"
GRAD_NOVI_SAD, NOVI_SAD, PETROVARADIN = "89010", "80284", "80519"

# One row of hexes per entry: (okrug, municipality); (None, None) is foreign ground.
BANDS = [
    ("RS110", STARI_GRAD), ("RS110", STARI_GRAD), ("RS110", STARI_GRAD),  # rows 0–2
    ("RS110", NOVI_BEOGRAD), ("RS110", NOVI_BEOGRAD),  # rows 3–4
    (None, None),  # row 5
    ("RS216", ALEKSANDROVAC),  # row 6
    ("RS216", BRUS),  # row 7
    ("RS216", KRUŠEVAC), ("RS216", KRUŠEVAC),  # rows 8–9
    ("RS216", TRSTENIK),  # row 10
    ("RS225", MEDIJANA),  # row 11
    ("RS225", ALEKSINAC),  # row 12
    ("RS225", DOLJEVAC),  # row 13
    ("RS211", ARILJE),  # row 14
    ("RS231", PRIŠTINA),  # row 15: Kosovo
    (None, None),  # row 16
]
LAKE = (5, 6)  # a lake hex inside Aleksandrovac
CITIES = [srb.GRAD_BEOGRAD, KRUŠEVAC, TRSTENIK, ALEKSANDROVAC, ALEKSINAC, ARILJE, DOLJEVAC]  # most populous first

# The keys of a city row, in the order of the plan's example; the last four are the summed census counts.
CITY_KEYS = ["id", "name", "full", "states", "metro", "capital", "x", "y", "cell", "population", "employed",
             "yields", "jobs", "median_income", "median_rent", "home_value", "rent_burden", "unemployment",
             "wage_net", "age65", "gdp", "gdp_year", "gdp_by_industry", "gdp_undisclosed", "gdp_estimated",
             "growth", "growth_years", "counties", "footprint", "pop_series", "ranks", "peers", "settlement_population",
             "education", "religion", "ethnicity", "commute"]
RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth", "food", "production", "gold", "science", "culture"]


def make_world(bands, lakes=()):
    """The _world interim of a grid with one row per band, plus the grid and the projection it was made with."""
    grid = HexGrid(srb.HEX_RADIUS_KM, COLS, len(bands))
    proj = geo.MapProjection(min_x=0.0, max_y=0.0, margin=200.0)  # puts Serbia's longitudes and latitudes inside
    states = sorted({s for s, _ in bands if s})
    counties = sorted({c for _, c in bands if c})
    owner, county, water = [], [], []
    for row, (state, unit) in enumerate(bands):
        for col in range(COLS):
            if (col, row) in lakes:
                owner.append(srb.WATER)
                county.append(-1)
                water.append(srb.LAKE)
            elif state is None:
                owner.append(srb.FOREIGN)
                county.append(-1)
                water.append(srb.LAND)
            else:
                owner.append(states.index(state))
                county.append(counties.index(unit))
                water.append(srb.LAND)
    world = {
        "grid": grid.to_dict(), "projection": proj.to_dict(), "owner": owner, "county": county, "water": water,
        "states": states, "counties": counties,
        "cells_of_county": [[c for c, k in enumerate(county) if k == i] for i in range(len(counties))],
    }
    return world, grid, proj


def nace(**sections):
    """A census industry row: every NACE section is 0 unless named by its letter (nace(A=3100, C=3900)). The two
    sections outside the 19 (T and U) and some unknown jobs are there to be ignored."""
    row = {section: float(sections.get(section, 0)) for _, section, _ in srb.INDUSTRIES}
    row.update(total=float(sum(sections.values())), unknown=10.0, T=7.0, U=3.0)
    return row


def census_unit(population, employed, unemployed, letters, commute=None, education=None):
    return {
        "population": population,
        "activity": {"employed": employed, "unemployed": unemployed, "inactive": 0, "total15": employed + unemployed},
        "industry": nace(**letters), "commute": commute, "education": education,
        "religion": None, "ethnicity": None, "migration": None,
    }


def commute(total, same_unit, other_unit, other_oblast, abroad):
    return {"total": total, "same_unit": same_unit, "other_unit": other_unit, "other_oblast": other_oblast, "abroad": abroad}


def make_interims(grid, proj):
    """census, rzs_db, gdp and places as Tasks 1–4 write them, for the units of BANDS."""
    def at(col, row):
        return proj.inverse(*grid.center(col, row))  # the lon/lat of a hex's centre

    def place(name, col, row, fclass="city"):
        lon, lat = at(col, row)
        return {"name": name, "name_lat": name, "fclass": fclass, "population": None, "lon": lon, "lat": lat}

    def settlement(id_, name, unit, urban, population):
        return {"id": id_, "name": name, "unit": unit, "oblast": territory.oblast_of(unit), "urban": urban,
                "population": population, "age": None}

    def series(first, last):
        step = (last - first) / (len(YEARS) - 1)
        return [round(first + step * i) for i in range(len(YEARS))]

    census = {
        "settlements": [
            # Grad Beograd's urban settlement as the census lists it: one row per opština it spreads over
            settlement("000101", "Beograd (Novi Beograd)", NOVI_BEOGRAD, True, 190000),
            settlement("000102", "Beograd (Stari grad)", STARI_GRAD, True, 48000),
            settlement("700029", "Aleksandrovac", ALEKSANDROVAC, True, 12000),
            settlement("000201", "Brus", BRUS, True, 5120),  # below CITY_MIN_URBAN_POP
            settlement("000202", "Крушевац", KRUŠEVAC, True, 60000),  # Cyrillic, as in the file
            settlement("000203", "Trstenik", TRSTENIK, True, 15000),
            settlement("000204", "Varvarin", VARVARIN, True, 11000),
            settlement(None, "Doljevac", DOLJEVAC, True, 11000),  # no territory id: never a position
            settlement("000303", "Pukovac", DOLJEVAC, True, 10500),
            settlement("000301", "Niš (Medijana)", MEDIJANA, True, 40000),
            settlement("000302", "Aleksinac", ALEKSINAC, True, 16000),
            settlement("000401", "Arilje", ARILJE, True, 14000),
            settlement("000501", "Priština", PRIŠTINA, True, 100000),
            settlement("000601", "Gadžin Han", GADŽIN_HAN, False, 4000),  # rural only
        ],
        "units": {
            STARI_GRAD: census_unit(48000, 16000, 1000, {"A": 100, "C": 2000, "F": 500, "M": 6000, "J": 2000, "R": 1000},
                                    commute(16000, 10000, 4000, 1000, 1000), {"total15": 14000, "secondary": 6000, "higher": 7000}),
            NOVI_BEOGRAD: census_unit(190000, 90000, 6000, {"B": 100, "C": 12000, "F": 4000, "M": 30000, "J": 18000, "R": 2500},
                                      commute(90000, 60000, 22000, 5000, 3000), {"total15": 150000, "secondary": 70000, "higher": 70000}),
            ALEKSANDROVAC: census_unit(39451, 16800, 2200, {"A": 3100, "B": 80, "C": 3900, "F": 1200.4, "M": 1100.6, "J": 300, "R": 200}),
            BRUS: census_unit(12000, 900, 300, {"A": 400, "C": 200, "F": 100, "G": 100, "M": 50, "J": 20, "R": 30}),
            TRSTENIK: census_unit(40000, 15000, 1500, {"A": 800, "C": 6000, "F": 1500, "M": 1500, "J": 600, "R": 300}),
            MEDIJANA: census_unit(41000, 20000, 2000, {"A": 100, "C": 3000, "F": 800, "M": 5000, "J": 2000, "R": 800}),
            ALEKSINAC: census_unit(30000, 8000, 1200, {"A": 1200, "B": 300, "C": 2500, "F": 900, "M": 800, "J": 300, "R": 200}),
            DOLJEVAC: census_unit(24000, 5000, 900, {"A": 1500, "C": 900, "F": 500, "M": 300, "J": 150, "R": 80}),
            VARVARIN: census_unit(17000, 3000, 600, {"A": 900, "C": 700, "F": 200, "M": 200}),
            ARILJE: census_unit(28000, 6000, 800, {"A": 900, "C": 3500, "F": 400, "M": 400, "J": 200, "R": 150}),
            PRIŠTINA: census_unit(200000, 40000, 5000, {"A": 1000, "C": 3000, "F": 2000, "M": 4000, "J": 1500, "R": 500}),
            # Kruševac has a settlement but no unit row; Gadžin Han has neither
            # The census's own row for the aggregate: the total of its parts, as in the real file for Grad Beograd
            srb.GRAD_BEOGRAD: census_unit(238000, 106000, 7000, {"A": 100, "B": 100, "C": 14000, "F": 4500, "J": 20000, "M": 36000, "R": 3500}),
        },
    }

    rzs = {
        "pop_years": YEARS,
        "pop": {
            srb.GRAD_BEOGRAD: [1150000, 1145000, 1140000, 1138000, 1137000], NOVI_BEOGRAD: series(212000, 210000),
            ALEKSANDROVAC: series(40000, 39000), BRUS: series(28000, 27000), KRUŠEVAC: series(115000, 113000),
            TRSTENIK: [43000, None, 42500, 42300, 42000], MEDIJANA: series(46000, 45000), GRAD_NIŠ: series(265000, 260000),
            ALEKSINAC: series(31000, 30000), DOLJEVAC: series(26500, 26000), VARVARIN: series(17500, 17000),
            GADŽIN_HAN: series(8000, 7800), ARILJE: series(29000, 28000), PRIŠTINA: series(198000, 202000),
        },
        "pop_65": {"year": 2025, "by_unit": {ALEKSANDROVAC: 0.213, KRUŠEVAC: 0.2, TRSTENIK: 0.22, ALEKSINAC: 0.21,
                                              DOLJEVAC: 0.23, ARILJE: 0.25}},
        "wages": {"year": 2025, "net": {ALEKSANDROVAC: 104512.0, KRUŠEVAC: 98000.0, TRSTENIK: 90000.0,
                                        ALEKSINAC: 85000.0, DOLJEVAC: 83000.0, ARILJE: 80000.0}},
        "employment": {"year": 2025, "by_unit": {
            ALEKSANDROVAC: {"total": 4000.0}, BRUS: {"total": 1000.0}, KRUŠEVAC: {"total": 15000.0},
            TRSTENIK: {"total": 5000.0},  # Rasinski okrug on the map: 25,000
            MEDIJANA: {"total": 5000.0}, ALEKSINAC: {"total": 3000.0}, DOLJEVAC: {"total": 1500.0},  # Nišavski: 9,500
            ARILJE: {"total": 2000.0}, PRIŠTINA: None,
            # the seventeen opštine of Grad Beograd: 40,000, of which 25,000 are on the map
            **{part: {"total": {STARI_GRAD: 5000.0, NOVI_BEOGRAD: 20000.0}.get(part, 1000.0)}
               for part in territory.parts_of(srb.GRAD_BEOGRAD)},
        }},
    }

    gdp = {"vintage": "Eurostat, BDP po oblastima (nama_10r_3gdp), 2023 — privremeni podaci", "year": 2023, "unit": "MIO_EUR",
           "nuts3": {"RS110": 1000.0, "RS216": 500.0, "RS225": 800.0}, "provisional": []}

    places = {"places": [
        place("Aleksandrovac", 22, 6, "town"),
        place("Kruševac", 22, 7),  # the name, but in Brus: not this city's place
        place("Ražanj", 22, 10, "town"),  # a place no city's settlement is called
        place("Trstenik", 22, 10, "town"),
        place("Aleksinac", 22, 12, "town"),
        place("Pukovac", 22, 13, "town"),
        place("Arilje", 22, 14, "town"),
    ]}
    return {"census": census, "rzs_db": rzs, "gdp": gdp, "places": places}, at


class CitiesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for patched in (mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", root / "web")):
            patched.start()
            self.addCleanup(patched.stop)
        self.world, self.grid, self.proj = make_world(BANDS, lakes={LAKE})
        self.data, self.at = make_interims(self.grid, self.proj)
        self.census, self.rzs, self.gdp, self.places = (self.data[k] for k in ("census", "rzs_db", "gdp", "places"))
        # Kruševac's only place stands in another unit, so the reviewed file is what places it
        self.csv = root / "city_positions.csv"
        lon, lat = self.at(22, 8)
        self.csv.write_text(f"id,lon,lat\n{KRUŠEVAC},{lon},{lat}\n", encoding="utf-8")
        patched = mock.patch.object(cities, "POSITIONS_FILE", self.csv)
        patched.start()
        self.addCleanup(patched.stop)

    def build(self):
        """Write the interims as they stand, run the builder, and return (cities, the _cities interim, what it printed)."""
        store.save_interim("census", self.census, vintage="Popis 2022")
        store.save_interim("rzs_db", self.rzs)
        store.save_interim("gdp", self.gdp, vintage="Eurostat 2023")
        store.save_interim("places", self.places)
        store.save_interim("_world", self.world)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            cities.build()
        cities_json = json.loads((store.WEB_DATA / "cities.json").read_text(encoding="utf-8"))
        return cities_json, store.load_interim("_cities"), printed.getvalue()

    @staticmethod
    def city(cities_json, unit_id):
        return next(c for c in cities_json if c["id"] == unit_id)

    # --- what a builder it is -------------------------------------------------------------------------------------

    def test_requires_and_produces(self):
        self.assertEqual(cities.REQUIRES, ["census", "rzs_db", "gdp", "places", "_world"])
        self.assertEqual(cities.PRODUCES, ["cities.json", "_cities"])

    def test_the_committed_override_file_holds_only_reviewed_positions(self):
        """The override file starts empty; a row is a reviewed position (docs/CITY_POSITIONS.md), never a scratch pad."""
        path = Path(cities.__file__).resolve().parents[1] / "data" / "city_positions.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "id,lon,lat")
        for line in lines[1:]:
            self.assertRegex(line, r"^\d{5},-?\d+\.\d+,-?\d+\.\d+$")
        doc = path.parents[2] / "docs" / "CITY_POSITIONS.md"
        text = doc.read_text(encoding="utf-8")
        for unit_id in (line.split(",")[0] for line in lines[1:]):
            self.assertIn(f"| {unit_id} |", text)

    # --- the four conditions on a city ------------------------------------------------------------------------------

    def test_a_city_needs_an_urban_settlement_of_10000_and_a_population_of_25000(self):
        cities_json, units, _ = self.build()
        self.assertEqual(units["units"][BRUS], {"is_city": False, "city": None, "why": "no urban settlement of 10,000+"})
        self.assertEqual(units["units"][GADŽIN_HAN], {"is_city": False, "city": None, "why": "no urban settlement of 10,000+"})
        self.assertEqual(units["units"][VARVARIN], {"is_city": False, "city": None, "why": "population below 25,000"})
        self.assertNotIn(BRUS, [c["id"] for c in cities_json])

    def test_kosovo_is_never_a_city(self):
        """Priština has an urban settlement, a population and hexes here, and is still left out."""
        cities_json, units, _ = self.build()
        self.assertNotIn(PRIŠTINA, [c["id"] for c in cities_json])
        self.assertFalse({u for u in units["units"] if territory.in_kosovo(u)})

    def test_a_city_municipality_is_never_a_city_on_its_own(self):
        """Novi Beograd meets both thresholds and is still only a part of Grad Beograd, which is the city."""
        cities_json, units, _ = self.build()
        self.assertNotIn(NOVI_BEOGRAD, [c["id"] for c in cities_json])
        self.assertEqual(units["units"][NOVI_BEOGRAD], {"is_city": False, "city": srb.GRAD_BEOGRAD, "why": "city municipality of 79014"})
        self.assertEqual(units["units"][STARI_GRAD], {"is_city": False, "city": srb.GRAD_BEOGRAD, "why": "city municipality of 79014"})
        self.assertEqual(units["units"][srb.GRAD_BEOGRAD], {"is_city": True, "city": srb.GRAD_BEOGRAD, "why": None})

    def test_a_city_municipality_belongs_to_no_city_when_its_aggregate_is_not_one(self):
        """Medijana meets both thresholds too. Grad Niš passes them but has no position, so there is no such city."""
        cities_json, units, _ = self.build()
        self.assertNotIn(MEDIJANA, [c["id"] for c in cities_json])
        self.assertEqual(units["units"][MEDIJANA], {"is_city": False, "city": None, "why": "city municipality of 79022"})

    def test_units_covers_every_unit_outside_kosovo_with_is_city_city_and_why(self):
        cities_json, units, _ = self.build()
        ids = {c["id"] for c in cities_json}
        self.assertEqual(set(units), {"cities", "units"})
        self.assertEqual(set(units["units"]), {u for u in territory.units() if not territory.in_kosovo(u)})
        self.assertEqual(units["cities"], cities_json)
        for unit_id, record in units["units"].items():
            self.assertEqual(list(record), ["is_city", "city", "why"], unit_id)
            self.assertEqual(record["is_city"], unit_id in ids, unit_id)
            if record["is_city"]:
                self.assertEqual((record["city"], record["why"]), (unit_id, None), unit_id)
            elif record["city"] is not None:
                self.assertIn(unit_id, territory.parts_of(record["city"]), unit_id)  # a part of that city

    # --- the rows ---------------------------------------------------------------------------------------------------

    def test_cities_are_sorted_by_population_and_have_the_documented_keys(self):
        cities_json, _, _ = self.build()
        self.assertEqual([c["id"] for c in cities_json], CITIES)
        populations = [c["population"] for c in cities_json]
        self.assertEqual(populations, sorted(populations, reverse=True))
        for c in cities_json:
            self.assertEqual(list(c), CITY_KEYS, c["id"])
            self.assertIs(c["metro"], True)  # upstream's "not a micropolitan area": its leaderboards need it
            for field in ("median_income", "median_rent", "home_value", "rent_burden", "gdp_by_industry", "gdp_undisclosed"):
                self.assertIsNone(c[field], (c["id"], field))
            self.assertEqual((c["gdp_year"], c["growth_years"]), (2023, [2021, 2025]))
            self.assertEqual(c["states"], [territory.oblast_of(c["id"])])
            self.assertEqual(c["full"], f"{c['name']} ({okrug_name(territory.name(territory.oblast_of(c['id'])))})")

    def test_the_capital_is_grad_beograd_standing_on_stari_grad(self):
        cities_json, _, _ = self.build()
        beograd = cities_json[0]
        self.assertEqual((beograd["name"], beograd["capital"]), ("Beograd", True))
        self.assertTrue(all(c["capital"] is False for c in cities_json[1:]))
        self.assertEqual(beograd["full"], "Beograd (Beogradski okrug)")
        # Stari grad is rows 0–2, whose centre (153.0, 7.5) is nearest to the centre of hex (17, 1)
        self.assertEqual((beograd["x"], beograd["y"], beograd["cell"]),
                         (*[round(v, 1) for v in self.grid.center(17, 1)], self.grid.index(17, 1)))
        self.assertEqual(beograd["counties"], territory.parts_of(srb.GRAD_BEOGRAD))

    def test_the_aggregate_is_the_sum_of_its_parts(self):
        beograd = self.city(self.build()[0], srb.GRAD_BEOGRAD)
        self.assertEqual(beograd["population"], 1137000)
        self.assertEqual(beograd["employed"], 106000)
        self.assertEqual(beograd["unemployment"], 0.0619)  # 7000 / (106000 + 7000)
        self.assertEqual({k: v for k, v in beograd["jobs"].items() if v},
                         {"agriculture": 100, "mining": 100, "manufacturing": 14000, "construction": 4500,
                          "information": 20000, "professional": 36000, "arts": 3500})
        self.assertEqual(beograd["education"], {"total15": 164000, "secondary": 76000, "higher": 77000})
        self.assertEqual(beograd["commute"], {"total": 106000, "same_unit": 70000, "other_unit": 26000, "other_oblast": 6000, "abroad": 4000})
        self.assertEqual(beograd["yields"], {"food": 100, "production": 18600, "gold": 1600000000, "science": 56000, "culture": 3500})
        self.assertIsNone(beograd["religion"])  # no part has it
        # RZS has no row of its own for the grad, and here none for its parts on the map either
        self.assertIsNone(beograd["age65"])
        self.assertIsNone(beograd["wage_net"])
        self.assertEqual(beograd["settlement_population"], 190000)  # the largest urban settlement over the parts
        self.assertEqual(beograd["growth"], -0.0113)
        self.assertEqual(beograd["pop_series"], {"2021": 1150000, "2022": 1145000, "2023": 1140000, "2024": 1138000, "2025": 1137000})

    def test_a_part_without_a_field_leaves_the_aggregate_field_null(self):
        """Vračar has a row but no commute table: a sum over the other parts would pass for the whole city's."""
        self.census["units"][VRAČAR] = census_unit(5000, 500, 50, {"C": 300, "M": 150})
        cities_json, _, _ = self.build()
        beograd = self.city(cities_json, srb.GRAD_BEOGRAD)
        self.assertEqual(beograd["employed"], 106500)
        self.assertIsNone(beograd["commute"])

    def test_an_aggregate_without_a_row_of_its_own_takes_the_weighted_mean_of_its_parts(self):
        """Grad Beograd has no wage or 65+ row of its own: its figure is the weighted mean over its opštine, as an
        okrug's is (a wage by the registered employment, a share by the latest population estimate)."""
        self.rzs["pop"][STARI_GRAD] = [51000, 50000, 49000, 48500, 48000]
        self.rzs["pop_65"]["by_unit"].update({STARI_GRAD: 0.3, NOVI_BEOGRAD: 0.2})
        self.rzs["wages"]["net"].update({STARI_GRAD: 150000.0, NOVI_BEOGRAD: 100000.0})
        beograd = self.city(self.build()[0], srb.GRAD_BEOGRAD)
        # 65+: (0.3 × 48,000 + 0.2 × 210,000) ÷ 258,000; the wage: (150,000 × 5,000 + 100,000 × 20,000) ÷ 25,000.
        # The other fifteen opštine are employed but print no wage or share of their own: they stay out of both.
        self.assertEqual((beograd["age65"], beograd["wage_net"]), (0.2186, 110000.0))
        self.rzs["wages"]["net"].pop(NOVI_BEOGRAD)
        self.assertEqual(self.city(self.build()[0], srb.GRAD_BEOGRAD)["wage_net"], 150000.0)
        # a plain city keeps its own row, whatever its parts would average
        self.assertEqual(self.city(self.build()[0], ALEKSANDROVAC)["wage_net"], 104512.0)

    def test_the_census_population_only_checks_the_sum_of_the_parts(self):
        """Where the census has a row of its own for a city, its inhabitants should equal the parts' rows added up."""
        _, _, printed = self.build()
        self.assertNotIn("the census counts", printed)  # 238,000 on both sides
        self.census["units"][srb.GRAD_BEOGRAD]["population"] = 250000
        _, _, printed = self.build()
        self.assertIn("Grad Beograd: the census counts 250,000 inhabitants, its parts on file 238,000", printed)

    def test_the_own_census_row_of_an_aggregate_is_not_added_to_its_parts(self):
        """The census publishes Grad Beograd as well as its opštine: the city is the opštine, not both."""
        self.census["units"][srb.GRAD_BEOGRAD]["activity"]["employed"] = 999999
        self.assertEqual(self.city(self.build()[0], srb.GRAD_BEOGRAD)["employed"], 106000)

    def add_novi_sad(self):
        """Grad Novi Sad as the census publishes it: a row for the grad, none for its two city municipalities, which
        are its two units on the map."""
        self.world = make_world(BANDS[:-1] + [("RS123", NOVI_SAD), ("RS123", PETROVARADIN)] + BANDS[-1:], lakes={LAKE})[0]
        self.census["settlements"].append({"id": "802824", "name": "Novi Sad", "unit": GRAD_NOVI_SAD, "oblast": "RS123",
                                           "urban": True, "population": 250000, "age": None})
        self.census["units"][GRAD_NOVI_SAD] = census_unit(368000, 90000, 9000, {"A": 1000, "C": 15000, "F": 6000, "M": 20000, "J": 8000, "R": 2500})
        self.rzs["pop"][GRAD_NOVI_SAD] = [372000, 371000, 370000, 369000, 368000]
        self.rzs["employment"]["by_unit"][GRAD_NOVI_SAD] = {"total": 90000.0}
        self.rzs["pop_65"]["by_unit"][GRAD_NOVI_SAD] = 0.19
        self.rzs["wages"]["net"][GRAD_NOVI_SAD] = 105000.0
        self.gdp["nuts3"]["RS123"] = 2000.0
        lon, lat = self.at(22, 16)
        self.places["places"].append({"name": "Novi Sad", "name_lat": "Novi Sad", "fclass": "city", "population": None, "lon": lon, "lat": lat})

    def test_an_aggregate_whose_only_census_row_is_its_own_gives_the_city_that_row(self):
        """Novi Sad must not lose its counts for having no rows of its parts: the grad's row stands for them once.
        The census lists its settlement under the grad itself, not under a city municipality."""
        self.add_novi_sad()
        cities_json, units, printed = self.build()
        self.assertIn(GRAD_NOVI_SAD, [c["id"] for c in cities_json])
        novi_sad = self.city(cities_json, GRAD_NOVI_SAD)
        self.assertEqual((novi_sad["name"], novi_sad["population"], novi_sad["employed"]), ("Novi Sad", 368000, 90000))
        self.assertEqual(novi_sad["unemployment"], 0.0909)  # 9000 / 99000
        self.assertEqual({k: v for k, v in novi_sad["jobs"].items() if v},
                         {"agriculture": 1000, "manufacturing": 15000, "construction": 6000, "information": 8000,
                          "professional": 20000, "arts": 2500})
        self.assertEqual(novi_sad["gdp"], 2000.0 * 1e6)  # the grad's employment is the okrug's whole, counted once
        self.assertEqual((novi_sad["cell"], novi_sad["counties"]), (self.grid.index(22, 16), [NOVI_SAD, PETROVARADIN]))
        self.assertEqual((novi_sad["age65"], novi_sad["wage_net"]), (0.19, 105000.0))
        self.assertNotIn("the census counts", printed)  # the grad's own row agrees with the sum over its parts
        for part in (NOVI_SAD, PETROVARADIN):
            self.assertEqual(units["units"][part], {"is_city": False, "city": GRAD_NOVI_SAD, "why": "city municipality of 89010"})

    def test_a_city_without_any_census_row_has_null_counts(self):
        kruševac = self.city(self.build()[0], KRUŠEVAC)
        self.assertIsNone(kruševac["employed"])
        self.assertIsNone(kruševac["unemployment"])
        self.assertEqual(set(kruševac["jobs"].values()), {None})
        for field in ("education", "religion", "ethnicity", "commute"):
            self.assertIsNone(kruševac[field])
        self.assertEqual(kruševac["yields"], {"food": None, "production": None, "gold": 300000000, "science": None, "culture": None})

    def test_a_plain_city_carries_its_own_census_row(self):
        aleksandrovac = self.city(self.build()[0], ALEKSANDROVAC)
        self.assertEqual(aleksandrovac["name"], "Aleksandrovac")
        self.assertEqual(aleksandrovac["full"], "Aleksandrovac (Rasinski okrug)")
        self.assertEqual((aleksandrovac["population"], aleksandrovac["employed"]), (39000, 16800))
        self.assertEqual(aleksandrovac["unemployment"], 0.1158)  # 2200 / 19000
        self.assertEqual({k: aleksandrovac["jobs"][k] for k in ("agriculture", "mining", "manufacturing", "construction", "professional", "arts")},
                         {"agriculture": 3100, "mining": 80, "manufacturing": 3900, "construction": 1200, "professional": 1101, "arts": 200})
        self.assertEqual(aleksandrovac["yields"], {"food": 3100, "production": 5180, "gold": 80000000, "science": 1401, "culture": 200})
        self.assertEqual((aleksandrovac["age65"], aleksandrovac["wage_net"]), (0.213, 104512.0))
        self.assertEqual((aleksandrovac["counties"], aleksandrovac["settlement_population"]), ([ALEKSANDROVAC], 12000))

    def test_gdp_is_the_okrug_gdp_times_the_city_share_of_the_okrug_employment(self):
        cities_json, _, _ = self.build()
        aleksandrovac = self.city(cities_json, ALEKSANDROVAC)
        self.assertEqual(aleksandrovac["gdp"], 500.0 * 1e6 * 4000 / 25000)
        self.assertEqual(aleksandrovac["gdp_estimated"], ["total"])
        self.assertEqual(self.city(cities_json, ALEKSINAC)["gdp"], round(800.0 * 1e6 * 3000 / 9500))
        self.assertEqual(self.city(cities_json, srb.GRAD_BEOGRAD)["gdp"], 1000.0 * 1e6 * 40000 / 25000)

    def test_gdp_is_null_when_the_okrug_has_no_gdp_or_no_employment(self):
        cities_json, _, _ = self.build()
        arilje = self.city(cities_json, ARILJE)  # Zlatiborska oblast is missing from the GDP table
        self.assertIsNone(arilje["gdp"])
        self.assertIsNone(arilje["gdp_estimated"])
        self.assertIsNone(arilje["yields"]["gold"])

        self.rzs["employment"]["by_unit"][MEDIJANA] = {"total": None}  # a published row without a figure
        cities_json, _, _ = self.build()
        for unit_id in (ALEKSINAC, DOLJEVAC):
            self.assertIsNone(self.city(cities_json, unit_id)["gdp"])
            self.assertIsNone(self.city(cities_json, unit_id)["gdp_estimated"])

        # Units the office has no row for at all are left out of the sums: Doljevac has none, Aleksinac is all there is
        self.rzs["employment"]["by_unit"] = {ALEKSINAC: {"total": 3000.0}}
        cities_json, _, _ = self.build()
        self.assertEqual(self.city(cities_json, ALEKSINAC)["gdp"], 800.0 * 1e6)
        self.assertIsNone(self.city(cities_json, DOLJEVAC)["gdp"])

    # --- where a city stands ---------------------------------------------------------------------------------------

    def test_the_position_is_the_place_with_the_settlement_name_in_the_settlement_unit(self):
        aleksandrovac = self.city(self.build()[0], ALEKSANDROVAC)
        self.assertEqual((aleksandrovac["x"], aleksandrovac["y"], aleksandrovac["cell"]),
                         (*[round(v, 1) for v in self.grid.center(22, 6)], self.grid.index(22, 6)))

    def test_a_settlement_without_a_territory_id_is_no_position(self):
        """Doljevac's largest settlement has no id; the next urban one places the city."""
        doljevac = self.city(self.build()[0], DOLJEVAC)
        self.assertEqual((doljevac["cell"], doljevac["settlement_population"]), (self.grid.index(22, 13), 10500))

    def test_the_reviewed_file_places_a_city_whose_place_is_in_another_unit(self):
        """The only place called Kruševac stands in Brus: the name alone is not enough, the file's row places it."""
        kruševac = self.city(self.build()[0], KRUŠEVAC)
        self.assertEqual((kruševac["name"], kruševac["cell"]), ("Kruševac", self.grid.index(22, 8)))

    def test_a_city_without_a_position_is_left_out_and_printed(self):
        """Without its file row Kruševac has nothing; Grad Niš has neither a place nor a row."""
        self.csv.write_text("id,lon,lat\n", encoding="utf-8")
        cities_json, units, printed = self.build()
        for unit_id in (KRUŠEVAC, GRAD_NIŠ):
            self.assertNotIn(unit_id, [c["id"] for c in cities_json])
            self.assertEqual(units["units"][unit_id], {"is_city": False, "city": None, "why": "no position on the map"})
        self.assertIn("Kruševac", printed)
        self.assertIn("Grad Niš", printed)
        self.assertEqual(units["units"][MEDIJANA]["city"], None)

    def test_cells_are_unique_serbian_land_of_the_city_itself(self):
        cities_json, _, _ = self.build()
        cells = [c["cell"] for c in cities_json]
        self.assertEqual(len(cells), len(set(cells)))
        counties, owner, county, water = self.world["counties"], self.world["owner"], self.world["county"], self.world["water"]
        for c in cities_json:
            self.assertGreaterEqual(owner[c["cell"]], 0, c["id"])
            self.assertEqual(water[c["cell"]], srb.LAND)
            self.assertIn(counties[county[c["cell"]]], c["counties"])
            self.assertEqual(c["footprint"], sorted(set(c["footprint"]) | {c["cell"]}))
        aleksandrovac = self.city(cities_json, ALEKSANDROVAC)
        self.assertNotIn(self.grid.index(*LAKE), aleksandrovac["footprint"])  # a lake is not land
        self.assertEqual(len(aleksandrovac["footprint"]), COLS - 1)
        stari_grad = [self.grid.index(col, row) for row in range(3) for col in range(COLS)]
        novi_beograd = [self.grid.index(col, row) for row in (3, 4) for col in range(COLS)]
        self.assertEqual(cities_json[0]["footprint"], sorted(stari_grad + novi_beograd))

    def test_a_taken_cell_is_traded_for_the_nearest_free_one(self):
        x, y = self.grid.center(11, 5)
        left, here, right = (self.grid.index(col, 5) for col in (10, 11, 12))
        self.assertEqual(cities.claim_cell(self.grid, [left, here, right], x, y, set()), here)
        self.assertEqual(cities.claim_cell(self.grid, [left, here, right], x + 2, y, {here}), right)
        self.assertEqual(cities.claim_cell(self.grid, [left, here, right], x, y, {right, here}), left)
        self.assertEqual(cities.claim_cell(self.grid, [here], x, y, {here}), here)  # nothing free: shared, and printed
        self.assertIsNone(cities.claim_cell(self.grid, [], x, y, set()))

    # --- ranks, peers, series --------------------------------------------------------------------------------------

    def test_ranks_and_peers(self):
        cities_json, _, _ = self.build()
        for c in cities_json:
            self.assertEqual(list(c["ranks"]), RANK_KEYS)
            self.assertEqual(len(c["peers"]), 5)
            self.assertNotIn(c["id"], c["peers"])
        beograd = cities_json[0]
        self.assertEqual([beograd["ranks"][k] for k in ("population", "gdp", "gdp_per_capita", "growth", "production", "science", "culture")],
                         [1, 1, 6, 1, 1, 1, 1])  # GDP per resident: the estimate is shared out over 1.1 million people
        self.assertEqual(beograd["ranks"]["food"], 6)  # last but one: every agricultural town grows more food
        self.assertIsNone(self.city(cities_json, KRUŠEVAC)["ranks"]["food"])  # no census row
        self.assertIsNone(self.city(cities_json, ARILJE)["ranks"]["gdp"])  # no GDP
        self.assertEqual(beograd["peers"], [KRUŠEVAC, TRSTENIK, ALEKSANDROVAC, ALEKSINAC, ARILJE])  # nearest by ratio

    def test_peers_are_five_only_when_that_many_cities_exist(self):
        """Without the other places and the file row only the capital, Trstenik and Aleksandrovac can stand."""
        self.places["places"] = [p for p in self.places["places"] if p["name_lat"] in ("Aleksandrovac", "Trstenik")]
        self.csv.write_text("id,lon,lat\n", encoding="utf-8")
        cities_json, _, _ = self.build()
        self.assertEqual([c["id"] for c in cities_json], [srb.GRAD_BEOGRAD, TRSTENIK, ALEKSANDROVAC])
        for c in cities_json:
            self.assertEqual(len(c["peers"]), 2)  # the other two, nearest by ratio first
            self.assertEqual(sorted(c["peers"]), sorted(o["id"] for o in cities_json if o is not c))
        self.assertEqual(self.city(cities_json, TRSTENIK)["peers"], [ALEKSANDROVAC, srb.GRAD_BEOGRAD])

    def test_pop_series_keeps_the_missing_years_null(self):
        trstenik = self.city(self.build()[0], TRSTENIK)
        self.assertEqual(trstenik["pop_series"], {"2021": 43000, "2022": None, "2023": 42500, "2024": 42300, "2025": 42000})
        self.assertEqual((trstenik["growth"], trstenik["growth_years"]), (-0.0233, [2021, 2025]))


if __name__ == "__main__":
    unittest.main()
