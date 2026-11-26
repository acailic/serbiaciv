"""pipeline.check on a tiny synthetic dataset: 30 okruzi, 197 municipalities and a 6×2 grid.

Six hexes lie in one okrug, three in another, one in Kosovo and Metohija, one is water and one is foreign land. The
last ten of the 197 municipalities are in Kosovo and Metohija. tests/test_builder_checks.py uses the same dataset().
"""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import check
from pipeline.core import srb

KIM = list(srb.KIM_OBLASTI)
OKRUG_IDS = [f"RS{n:03d}" for n in range(1, 26)] + KIM  # 25 with statistics, then the five of Kosovo and Metohija
MUNICIPALITIES = [f"{i:05d}" for i in range(1, 186)] + ["80284", "80519"] + [f"900{n:02d}" for n in range(1, 11)]
KOSOVO_AT = MUNICIPALITIES.index("90001")  # the index of the first municipality in Kosovo and Metohija
in_kosovo = lambda geoid: geoid.startswith("9")
# hex:       0  1  2  3  4  5   6         7    8   9 10 11
OWNER =     [0, 0, 0, 0, 0, 0, 25,       -1,  -2,  1, 1, 1]
COUNTY =    [0, 0, 1, 1, 2, 2, KOSOVO_AT, -1, -1,  3, 3, 3]
SERBIA = [o >= 0 and OKRUG_IDS[o] not in KIM for o in OWNER]  # the nine hexes outside Kosovo and Metohija
ELEV = [100, 110, 120, 130, 140, 150, 500, -5, 200, 90, 95, 105]
PCT_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]
COVER_KEYS = ["none", "forest_deciduous", "forest_evergreen", "forest_mixed", "scrub", "grassland", "pasture", "cropland",
              "wetland", "urban", "barren", "ice"]

YIELDS = {"food": 10, "production": 20, "gold": 3.5e9, "science": 5, "culture": 30}
SMALL = {"food": 5, "production": 10, "gold": 1.75e9, "science": 2, "culture": 20}
JOBS = {key: (10 if key == "agriculture" else None) for key in srb.INDUSTRY_KEYS}  # a letter the census lacks gives None
ECON = {"population": 1000, "employed": 500, "yields": YIELDS, "jobs": JOBS,
        "median_income": None, "median_rent": None, "home_value": None, "rent_burden": None,  # not published below region level
        "unemployment": 0.05, "wage_net": 60000.0, "age65": 0.2,
        "gdp": 3.5e9, "gdp_year": 2023, "growth": 0.031, "growth_years": [2021, 2025]}
CITY_RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth"] + list(YIELDS)
LAND = {k: (0.5 if k == "forest" else 0.0) for k in PCT_KEYS}
LABEL = {"x": 10.0, "y": 10.0, "angle": 0, "size": 12}

COLUMNS = ["geoid", "name", "state", "population", "land_km2", "density", "age65", "education", "wage_net", "unemployment",
           "manufacturing", "commute", "orthodox", "serbs", "life_expectancy", "natural_increase", "forest", "crop", "pasture",
           "developed", "city", "cell"]
COUNTY_FORMATS = ["text", "text", "text", "int", "km2", "float", "pct", "pct", "rsd", "pct", "pct", "pct", "pct", "pct", "float",
                  "float", "pct", "pct", "pct", "pct", "text", "int"]
ROW = [1000, 100.0, 10.0, 0.2, 0.1, 60000, 0.05, 0.2, 0.3, 0.9, 0.95, 74.0, -2.0, 0.5, 0.3, 0.1, 0.1, None, None]  # after name and okrug
KOSOVO_ROW = [None, 100.0] + [None] * 11 + [0.5, 0.3, 0.1, 0.1, None, None]  # only the area and the land shares
# The twelve unit lenses: id, group, format, scale, higher_is, source, value on a Serbian hex, domain.
UNIT_LENSES = [
    ("density", "people", "int", "log", "neutral", "rzs_db", 10, [1, 2000]),
    ("pop_change", "people", "pct", "linear", "neutral", "rzs_db", 0.5, [-0.2, 0.2]),
    ("natural_increase", "people", "float", "linear", "neutral", "rzs_db", -2.0, [-15.0, 5.0]),
    ("age65", "people", "pct", "linear", "neutral", "rzs_db", 0.2, [0.1, 0.4]),
    ("education", "work", "pct", "linear", "good", "census", 0.3, [0.05, 0.5]),
    ("wages", "work", "rsd", "log", "good", "rzs_db", 60000, [40000, 150000]),
    ("unemployment", "work", "pct", "linear", "bad", "census", 0.05, [0.02, 0.3]),
    ("manufacturing", "work", "pct", "linear", "neutral", "census", 0.2, [0.05, 0.5]),
    ("commute", "work", "pct", "linear", "neutral", "census", 0.3, [0.1, 0.6]),
    ("orthodox", "identity", "pct", "linear", "neutral", "census", 0.9, [0.5, 1.0]),
    ("serbs", "identity", "pct", "linear", "neutral", "census", 0.9, [0.5, 1.0]),
    ("life_expectancy", "life", "float", "linear", "good", "rzs_db", 74.0, [70.0, 78.0]),
]


def lens(lid, group, fmt, scale, higher_is, source, domain, values, **extra):
    return {"id": lid, "group": group, "name": lid, "icon": f"l-{lid}", "emoji": "*", "unit": "", "format": fmt, "scale": scale,
            "domain": domain, "ramp": ["#000000", "#ffffff"], "higher_is": higher_is, "source": source,
            "description": "šta meri", "note": "godina i izvor", "values": values, **extra}


def categorical(lid, source, cats, values):
    return lens(lid, "land", "category", "linear", "neutral", source, [0, len(cats) - 1], values,
                ramp=[c["color"] for c in cats], categories=cats)


def okrug(fips, i):
    """One row of states.json. The i-th okrug with statistics ranks i + 1 in everything; Kosovo's have nothing."""
    nothing = {"population": None, "employed": None, "yields": {k: None for k in YIELDS}, "jobs": {k: None for k in JOBS},
               "median_income": None, "median_rent": None, "home_value": None, "rent_burden": None, "unemployment": None,
               "wage_net": None, "age65": None, "gdp": None, "gdp_year": None, "growth": None, "growth_years": None,
               "ranks": {k: None for k in YIELDS}}
    figures = {**ECON, "yields": {k: v * (25 - i) for k, v in YIELDS.items()}, "ranks": {k: i + 1 for k in YIELDS}}
    return {"fips": fips, "abbr": None, "name": f"Okrug {fips}", **(nothing if fips in KIM else figures),
            "gdp_by_industry": None, "gdp_undisclosed": None, "gdp_estimated": None, "label": dict(LABEL), "land": dict(LAND),
            "energy": None}


def dataset():
    """The seven files and three interims, all valid. Returns (web, interim)."""
    land = [o >= 0 for o in OWNER]
    world = {
        "version": 2, "grid": {"radius": 5.0, "cols": 6, "rows": 2}, "width": 600.0, "height": 200.0, "margin": 200.0,
        "projection": {"min_x": -200.0, "max_y": 400.0, "margin": 200.0},
        "owner": list(OWNER), "county": list(COUNTY), "elev": list(ELEV), "elev_max": [e + 10 if e > 0 else 0 for e in ELEV],
        "elev_range": [10, 10, 10, 10, 10, 10, 50, 0, 20, 10, 10, 80],
        "water": [0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0], "relief": [0, 1, 0, 0, 2, 2, 1, 0, 1, 0, 0, 3],
        "cover": [1, 1, 7, 7, 9, 9, 1, 0, 0, 4, 6, 3],
        "pct": {"forest": [60, 60, 0, 0, 0, 0, 50, 0, 0, 70, 80, 90], "crop": [30, 30, 0, 0, 0, 0, 10, 0, 0, 20, 10, 0],
                "pasture": [10, 10, 0, 0, 0, 0, 30, 0, 0, 10, 10, 10], "grass": [0] * 12, "shrub": [0] * 12, "wetland": [0] * 12,
                "developed": [0, 0, 0, 0, 100, 100, 10, 0, 0, 0, 0, 0]},
        "tables": {
            "water": [{"id": i, "name": n} for i, n in enumerate(["Zemlja", "Okean", "Obala", "Jezero"])],
            "relief": [{"id": i, "name": n} for i, n in enumerate(["Ravnica", "Brdovito", "Planine", "Vrhovi"])],
            "cover": [{"id": 0, "key": "none", "name": "Nema podataka"}]
            + [{"id": i, "key": k, "name": k, "color": "#123456"} for i, k in enumerate(COVER_KEYS) if i],
        },
        "states": [{"fips": f, "abbr": None, "name": f"Okrug {f}"} for f in OKRUG_IDS],
        "counties": [{"geoid": g, "name": f"Opština {g}"} for g in MUNICIPALITIES],
        "rivers": [{"name": "Velika reka", "rank": 1, "pts": [1.0, 1.0, 50.0, 30.0]}],
    }
    # The capital has more people; Mali grad the same GDP over ten people, so the higher GDP per person.
    cities = [
        {"id": "79014", "name": "Beograd", "full": "Beograd (Beogradski okrug)", "states": ["RS001"], "metro": False, "capital": True,
         "x": 1.0, "y": 1.0, "cell": 0, **copy.deepcopy(ECON), "counties": ["00001"], "footprint": [0, 1],
         "pop_series": {"2021": 990, "2025": 1000}, "ranks": {k: (2 if k == "gdp_per_capita" else 1) for k in CITY_RANK_KEYS},
         "peers": ["00002"]},
        {"id": "00002", "name": "Mali grad", "full": "Mali grad (Okrug RS001)", "states": ["RS001"], "metro": False, "capital": False,
         "x": 40.0, "y": 40.0, "cell": 4, **copy.deepcopy(ECON), "population": 10, "yields": dict(SMALL), "growth": None,
         "growth_years": None, "counties": ["00002"], "footprint": [4, 5], "pop_series": None,
         "ranks": {k: (None if k == "growth" else (1 if k == "gdp_per_capita" else 2)) for k in CITY_RANK_KEYS}, "peers": ["79014"]},
    ]
    states = [okrug(fips, i) for i, fips in enumerate(OKRUG_IDS)]
    nation = {"vintage": "Procene RZS 2025 · Popis 2022", "year": 2025, "gdp_vintage": "Eurostat, BDP po oblastima 2023",
              "nation": {**copy.deepcopy(ECON), "growth": 0.02}, "yields": copy.deepcopy(srb.YIELDS), "industries": dict(srb.INDUSTRY_NAMES)}
    lenses = {"vintage": "Procene RZS 2025 · Popis 2022",
              "groups": [{"id": "people", "name": "Stanovništvo"}, {"id": "work", "name": "Rad i zarade"},
                         {"id": "identity", "name": "Identitet"}, {"id": "life", "name": "Kvalitet života"},
                         {"id": "land", "name": "Zemljište"}],
              "lenses": [lens(*spec[:6], spec[7], [spec[6] if ok else None for ok in SERBIA]) for spec in UNIT_LENSES] + [
                  lens("elevation", "land", "int", "linear", "neutral", "dem", [80, 500], [e if ok else None for e, ok in zip(ELEV, land)]),
                  categorical("relief", "dem", [{"id": k, "name": k, "color": c} for k, c in zip(["flat", "hills", "mountains", "peaks"],
                                                                                               ["#6f9e4a", "#c2a24f", "#8d6e63", "#efe9df"])],
                              [r if ok else None for r, ok in zip(world["relief"], land)]),
                  categorical("land_cover", "landcover", [{"id": k, "name": k, "color": "#123456"} for k in COVER_KEYS[1:9]],
                              [0 if ok else None for ok in land]),
              ]}
    sources = [{"id": sid, "title": sid, "publisher": "p", "homepage": "h", "license": "l", "description": "d", "used_for": ["lenses"],
                "vintage": "2025", "files": [{"file": "a", "url": "u", "retrieved": "t", "sha256": "s", "bytes": 1}]}
               for sid in ("rzs_db", "census", "dem", "landcover")]
    rows = []
    for i, geoid in enumerate(MUNICIPALITIES):
        row = [geoid, f"Opština {geoid}", "RS231" if in_kosovo(geoid) else "RS001", *(list(KOSOVO_ROW) if in_kosovo(geoid) else list(ROW))]
        if i < 4:
            row[21] = [0, 2, 4, 9][i]  # four municipalities hold a hex
        rows.append(row)
    rows[0][20] = "79014"
    counties = {"vintage": "Procene RZS 2025 · Popis 2022",
                "fields": [{"key": k, "label": k, "format": f, "unit": None, "higher_is": "neutral", "source": "census", "description": "d"}
                           for k, f in zip(COLUMNS, COUNTY_FORMATS)],
                "columns": list(COLUMNS), "rows": rows}
    web = {"world.json": world, "cities.json": cities, "states.json": states, "nation.json": nation, "lenses.json": lenses,
           "sources.json": sources, "counties.json": counties}
    # The census has no rows for Novi Sad's two city municipalities (only Grad Novi Sad's) nor for Kosovo and Metohija.
    census_units = {g: {} for g in MUNICIPALITIES[:185]}
    pop = {g: [1, 2] for g in MUNICIPALITIES[:KOSOVO_AT]}
    pop.update({g: None for g in MUNICIPALITIES[KOSOVO_AT:]})
    interim = {"_world": {"data": {"counties": list(MUNICIPALITIES)}}, "census": {"data": {"units": census_units}},
               "rzs_db": {"data": {"pop": pop}}}
    return web, interim


class CheckTest(unittest.TestCase):
    def run_check(self, web, interim, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            wd, idir = Path(tmp) / "web", Path(tmp) / "interim"
            wd.mkdir()
            idir.mkdir()
            for name, doc in web.items():
                if doc is not None:
                    (wd / name).write_text(json.dumps(doc))
            for name, payload in interim.items():
                (idir / f"{name}.json").write_text(json.dumps(payload))
            return check.run(wd, idir, quiet=True, **kw)

    def levels(self, rep, level):
        return [m for lv, m in rep.lines if lv == level]

    def fails_for(self, web, interim, *texts):
        """The run failed, and each of `texts` is in some FAIL line."""
        rep = self.run_check(web, interim)
        fails = " | ".join(self.levels(rep, "FAIL"))
        self.assertTrue(rep.failed, "expected a FAIL")
        for text in texts:
            self.assertIn(text, fails)

    def test_the_valid_dataset_passes_without_a_warning(self):
        rep = self.run_check(*dataset())
        self.assertEqual(self.levels(rep, "FAIL"), [])
        self.assertEqual(self.levels(rep, "WARN"), [])
        passes = " | ".join(self.levels(rep, "PASS"))
        for name in check.REQUIRED:
            self.assertIn(f"{name}:", passes, name)

    def test_every_required_file_must_exist(self):
        for name in check.REQUIRED:
            web, interim = dataset()
            web[name] = None
            with self.subTest(name=name):
                self.fails_for(web, interim, f"{name}: missing")

    def test_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            wd, idir = Path(tmp) / "web", Path(tmp) / "interim"
            wd.mkdir()
            (wd / "nation.json").write_text("{not json")
            for name in check.REQUIRED:
                if name != "nation.json":
                    (wd / name).write_text(json.dumps(dataset()[0][name]))
            rep = check.run(wd, idir, quiet=True)
        self.assertTrue(any(m.startswith("nation.json: invalid JSON") for m in self.levels(rep, "FAIL")))

    def test_exit_code(self):
        web, interim = dataset()
        with tempfile.TemporaryDirectory() as tmp:
            wd, idir = Path(tmp) / "web", Path(tmp) / "interim"
            wd.mkdir()
            idir.mkdir()
            for name, doc in web.items():
                (wd / name).write_text(json.dumps(doc))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(check.main(wd, idir), 0)
                self.assertIn("0 fail", out.getvalue())
                (wd / "states.json").write_text(json.dumps([]))
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(check.main(wd, idir), 1)

    def test_contract_violations(self):
        cases = {
            # world.json
            "world not version 2": lambda w: w["world.json"].__delitem__("version"),
            "world grid without rows": lambda w: w["world.json"]["grid"].__delitem__("rows"),
            "world grid radius zero": lambda w: w["world.json"]["grid"].__setitem__("radius", 0),
            "world missing rivers": lambda w: w["world.json"].__delitem__("rivers"),
            "world has 29 okruzi": lambda w: w["world.json"]["states"].pop(24),
            "world has 196 municipalities": lambda w: w["world.json"]["counties"].pop(180),
            "world okrug id not RSddd": lambda w: w["world.json"]["states"][0].__setitem__("fips", "110"),
            "world okrug without a name": lambda w: w["world.json"]["states"][0].__delitem__("name"),
            "world okrug twice": lambda w: w["world.json"]["states"][1].__setitem__("fips", "RS001"),
            "world municipality id not 5 digits": lambda w: w["world.json"]["counties"][0].__setitem__("geoid", 1),
            "world municipality twice": lambda w: w["world.json"]["counties"][1].__setitem__("geoid", "00001"),
            "world owner out of range": lambda w: w["world.json"]["owner"].__setitem__(0, 30),
            "world county out of range": lambda w: w["world.json"]["county"].__setitem__(0, 197),
            "world elev too short": lambda w: w["world.json"]["elev"].pop(),
            "world elev not whole metres": lambda w: w["world.json"]["elev"].__setitem__(0, 10.5),
            "world elev_max negative": lambda w: w["world.json"]["elev_max"].__setitem__(0, -1),
            "world elev_range too short": lambda w: w["world.json"]["elev_range"].pop(),
            "world elev_range negative": lambda w: w["world.json"]["elev_range"].__setitem__(0, -1),
            "world without projection": lambda w: w["world.json"].__delitem__("projection"),
            "world projection without a number": lambda w: w["world.json"]["projection"].__setitem__("min_x", "x"),
            "world projection margin differs": lambda w: w["world.json"]["projection"].__setitem__("margin", 100.0),
            "world water out of range": lambda w: w["world.json"]["water"].__setitem__(0, 4),
            "world relief on water": lambda w: w["world.json"]["relief"].__setitem__(7, 1),
            "world water above sea level": lambda w: w["world.json"]["elev"].__setitem__(7, 5),
            "world cover out of range": lambda w: w["world.json"]["cover"].__setitem__(0, 12),
            "world pct over 100": lambda w: w["world.json"]["pct"]["crop"].__setitem__(0, 90),
            "world pct on foreign land": lambda w: w["world.json"]["pct"]["forest"].__setitem__(8, 30),
            "world pct without a class": lambda w: w["world.json"]["pct"].__delitem__("grass"),
            "world cover table wrong key": lambda w: w["world.json"]["tables"]["cover"][1].__setitem__("key", "wrong"),
            "world river without points": lambda w: w["world.json"]["rivers"].append({"name": "X", "rank": "one", "pts": [1, 2, 3]}),
            # nation.json
            "nation without a vintage": lambda w: w["nation.json"].__setitem__("vintage", ""),
            "nation without a gdp vintage": lambda w: w["nation.json"].__setitem__("gdp_vintage", None),
            "nation year as text": lambda w: w["nation.json"].__setitem__("year", "2025"),
            "nation yield renamed": lambda w: w["nation.json"]["yields"][0].__setitem__("key", "grain"),
            "nation yield in dollars": lambda w: w["nation.json"]["yields"][0].__setitem__("unit", "usd"),
            "nation yield without a description": lambda w: w["nation.json"]["yields"][0].__delitem__("description"),
            "nation without an industry": lambda w: w["nation.json"]["industries"].pop("manufacturing"),
            "nation population as text": lambda w: w["nation.json"]["nation"].__setitem__("population", "1000"),
            # cities.json
            "city id not 5 digits": lambda w: w["cities.json"][0].__setitem__("id", "14"),
            "city in Kosovo and Metohija": lambda w: w["cities.json"][0].__setitem__("id", "90001"),
            "city id twice": lambda w: w["cities.json"][1].__setitem__("id", "79014"),
            "cities not sorted": lambda w: w["cities.json"].reverse(),
            "city without a footprint": lambda w: w["cities.json"][0].pop("footprint"),
            "city in an unknown okrug": lambda w: w["cities.json"][0].__setitem__("states", ["ZZ"]),
            "city without an okrug": lambda w: w["cities.json"][0].__setitem__("states", []),
            "metro not a bool": lambda w: w["cities.json"][0].__setitem__("metro", "yes"),
            "capital not a bool": lambda w: w["cities.json"][1].__setitem__("capital", 0),
            "city cell out of range": lambda w: w["cities.json"][0].__setitem__("cell", 99),
            "city without a position": lambda w: w["cities.json"][0].__setitem__("x", None),
            "city yield key missing": lambda w: w["cities.json"][0].__setitem__("yields", {"food": 1}),
            "city jobs key missing": lambda w: w["cities.json"][0]["jobs"].pop("mining"),
            "city unemployment as a percentage": lambda w: w["cities.json"][0].__setitem__("unemployment", 5.0),
            "city age65 over 1": lambda w: w["cities.json"][0].__setitem__("age65", 65.0),
            "city wage as text": lambda w: w["cities.json"][0].__setitem__("wage_net", "60.000"),
            "city gdp_year as text": lambda w: w["cities.json"][0].__setitem__("gdp_year", "2023"),
            "city growth over 25%": lambda w: w["cities.json"][0].__setitem__("growth", 0.4),
            "city growth as a percentage": lambda w: w["cities.json"][0].__setitem__("growth", 3.1),
            "city growth_years reversed": lambda w: w["cities.json"][0].__setitem__("growth_years", [2025, 2021]),
            "city growth without years": lambda w: w["cities.json"][0].__setitem__("growth_years", None),
            "city growth year not whole": lambda w: w["cities.json"][0]["growth_years"].__setitem__(1, 2025.0),
            "footprint without its own cell": lambda w: w["cities.json"][0].__setitem__("footprint", [1]),
            "footprint unsorted": lambda w: w["cities.json"][0].__setitem__("footprint", [1, 0]),
            "footprint on water": lambda w: w["cities.json"][0].__setitem__("footprint", [0, 7]),
            "city county not a string": lambda w: w["cities.json"][0].__setitem__("counties", [1]),
            "pop_series negative": lambda w: w["cities.json"][0]["pop_series"].__setitem__("2021", -5),
            "pop_series bad year": lambda w: w["cities.json"][0]["pop_series"].__setitem__("y2", 5),
            "peer is the city itself": lambda w: w["cities.json"][0].__setitem__("peers", ["79014"]),
            "unknown peer": lambda w: w["cities.json"][0].__setitem__("peers", ["99999"]),
            "city ranks without a key": lambda w: w["cities.json"][0]["ranks"].pop("gdp_per_capita"),
            "city ranks against the value": lambda w: (w["cities.json"][0]["ranks"].__setitem__("gdp_per_capita", 1),
                                                       w["cities.json"][1]["ranks"].__setitem__("gdp_per_capita", 2)),
            "city rank on a null value": lambda w: w["cities.json"][1]["ranks"].__setitem__("growth", 1),
            # states.json
            "states has 29 okruzi": lambda w: w["states.json"].pop(0),
            "states not in world order": lambda w: w["states.json"].__setitem__(slice(0, 2), w["states.json"][1::-1]),
            "state id not RSddd": lambda w: w["states.json"][0].__setitem__("fips", "RS1"),
            "state without gdp": lambda w: w["states.json"][0].pop("gdp"),
            "state without a label": lambda w: w["states.json"][0].pop("label"),
            "state without land": lambda w: w["states.json"][0].pop("land"),
            "state ranks without a yield": lambda w: w["states.json"][0]["ranks"].pop("food"),
            "state rank on a null yield": lambda w: (w["states.json"][0]["yields"].__setitem__("food", None),
                                                     w["states.json"][0]["ranks"].__setitem__("food", 1)),
            "state ranks not a permutation": lambda w: w["states.json"][1]["ranks"].__setitem__("food", 1),
            "state ranks against the yield": lambda w: (w["states.json"][0]["ranks"].__setitem__("gold", 2),
                                                        w["states.json"][1]["ranks"].__setitem__("gold", 1)),
            "state rank too large": lambda w: w["states.json"][0]["ranks"].__setitem__("food", 31),
            "state label without a size": lambda w: w["states.json"][0]["label"].pop("size"),
            "state land as a percentage": lambda w: w["states.json"][0]["land"].__setitem__("forest", 50),
            "state land without a class": lambda w: w["states.json"][0]["land"].pop("crop"),
            "state growth null within a window": lambda w: w["states.json"][0].__setitem__("growth", None),
            "state energy without a note": lambda w: w["states.json"][0].__setitem__(
                "energy", {"unit": "MW", "total": 100, "by_type": {"nuclear": 100}, "sites": {"nuclear": 1}}),
            # growth across the files
            "growth windows differ": lambda w: w["cities.json"][0].__setitem__("growth_years", [2020, 2025]),
            "growth window ends before the nation's year": lambda w: [
                row.__setitem__("growth_years", [2021, 2024])
                for row in (*w["cities.json"], w["states.json"][0], w["nation.json"]["nation"])],
            "nation growth null within a window": lambda w: w["nation.json"]["nation"].__setitem__("growth", None),
            # lenses.json
            "lens missing": lambda w: w["lenses.json"]["lenses"].pop(),
            "lenses out of order": lambda w: w["lenses.json"]["lenses"].reverse(),
            "lens in an unknown group": lambda w: w["lenses.json"]["lenses"][0].__setitem__("group", "faith"),
            "lens groups out of order": lambda w: w["lenses.json"]["groups"].reverse(),
            "lens group without a name": lambda w: w["lenses.json"]["groups"][0].pop("name"),
            "lens in dollars": lambda w: w["lenses.json"]["lenses"][0].__setitem__("format", "usd"),
            "lens in minutes": lambda w: w["lenses.json"]["lenses"][0].__setitem__("format", "minutes"),
            "lens on a square-root scale": lambda w: w["lenses.json"]["lenses"][0].__setitem__("scale", "sqrt"),
            "lens higher is better": lambda w: w["lenses.json"]["lenses"][0].__setitem__("higher_is", "better"),
            "lens domain reversed": lambda w: w["lenses.json"]["lenses"][0].__setitem__("domain", [5, 1]),
            "lens log domain from zero": lambda w: w["lenses.json"]["lenses"][0].__setitem__("domain", [0, 2000]),
            "lens ramp of one colour": lambda w: w["lenses.json"]["lenses"][0].__setitem__("ramp", ["#000000"]),
            "lens ramp not a colour": lambda w: w["lenses.json"]["lenses"][0].__setitem__("ramp", ["black", "white"]),
            "lens without a note": lambda w: w["lenses.json"]["lenses"][0].pop("note"),
            "lens with an empty note": lambda w: w["lenses.json"]["lenses"][0].__setitem__("note", ""),
            "lens with an empty description": lambda w: w["lenses.json"]["lenses"][0].__setitem__("description", ""),
            "lens without a source": lambda w: w["lenses.json"]["lenses"][0].__setitem__("source", None),
            "lens values too short": lambda w: w["lenses.json"]["lenses"][0]["values"].pop(),
            "lens value as text": lambda w: w["lenses.json"]["lenses"][0]["values"].__setitem__(0, "10"),
            "lens value on water": lambda w: w["lenses.json"]["lenses"][0]["values"].__setitem__(7, 10),
            "lens value on foreign land": lambda w: w["lenses.json"]["lenses"][0]["values"].__setitem__(8, 10),
            "statistic on a hex of Kosovo and Metohija": lambda w: w["lenses.json"]["lenses"][0]["values"].__setitem__(6, 10),
            "pct lens as a percentage": lambda w: w["lenses.json"]["lenses"][1]["values"].__setitem__(0, 50.0),
            "category value out of range": lambda w: w["lenses.json"]["lenses"][13]["values"].__setitem__(0, 4),
            "category value not whole": lambda w: w["lenses.json"]["lenses"][13]["values"].__setitem__(0, 1.5),
            "category ramp in another order": lambda w: w["lenses.json"]["lenses"][13].__setitem__("ramp", ["#8d6e63", "#c2a24f", "#6f9e4a", "#efe9df"]),
            "category domain too wide": lambda w: w["lenses.json"]["lenses"][13].__setitem__("domain", [0, 3.5]),
            "category lens with one category": lambda w: w["lenses.json"]["lenses"][13].__setitem__("categories", [{"id": "a", "name": "A", "color": "#6f9e4a"}]),
            "category lens without a colour": lambda w: w["lenses.json"]["lenses"][13]["categories"][0].pop("color"),
            "category lens with an id twice": lambda w: w["lenses.json"]["lenses"][13]["categories"][1].__setitem__("id", "flat"),
            "categories on a numeric lens": lambda w: w["lenses.json"]["lenses"][0].__setitem__("categories", [{"id": "a", "name": "A", "color": "#000000"}]),
            # counties.json
            "county columns against fields": lambda w: w["counties.json"]["columns"].reverse(),
            "county without the city column": lambda w: (w["counties.json"]["columns"].pop(20), w["counties.json"]["fields"].pop(20),
                                                         [row.pop(20) for row in w["counties.json"]["rows"]]),
            "county field in an unknown format": lambda w: w["counties.json"]["fields"][3].__setitem__("format", "weird"),
            "county field without a description": lambda w: w["counties.json"]["fields"][3].pop("description"),
            "county row too short": lambda w: w["counties.json"]["rows"][0].pop(),
            "county geoid not 5 digits": lambda w: w["counties.json"]["rows"][0].__setitem__(0, "1"),
            "county name as a number": lambda w: w["counties.json"]["rows"][0].__setitem__(1, 5),
            "county pct as a percentage": lambda w: w["counties.json"]["rows"][0].__setitem__(6, 20.0),
            "county population negative": lambda w: w["counties.json"]["rows"][0].__setitem__(3, -1),
            "county wage as text": lambda w: w["counties.json"]["rows"][0].__setitem__(8, "60.000"),
            "county of an unknown city": lambda w: w["counties.json"]["rows"][0].__setitem__(20, "99999"),
            "county rows in another order": lambda w: w["counties.json"]["rows"].reverse(),
            # sources.json
            "sources not a list": lambda w: w.__setitem__("sources.json", {}),
            "source id twice": lambda w: w["sources.json"][1].__setitem__("id", "rzs_db"),
            "source without a title": lambda w: w["sources.json"][0].pop("title"),
            "source file without a checksum": lambda w: w["sources.json"][0]["files"][0].pop("sha256"),
        }
        for label, mutate in cases.items():
            web, interim = dataset()
            web = copy.deepcopy(web)
            mutate(web)
            with self.subTest(label):
                self.assertTrue(self.run_check(web, interim).failed, label)

    def test_a_kosovo_okrug_is_null_in_every_statistic(self):
        """An okrug of Kosovo and Metohija keeps its id, its name, its label and its land, and has nothing else."""
        own = {"population": 1, "employed": 1, "unemployment": 0.1, "wage_net": 1.0, "age65": 0.2, "gdp": 1.0, "gdp_year": 2023,
               "growth": 0.1, "growth_years": [2021, 2025], "abbr": "RS23"}
        nested = {"yields": "food", "jobs": "agriculture", "ranks": "food"}
        for field, value in own.items():
            web, interim = dataset()
            web["states.json"][25][field] = value
            with self.subTest(field=field):
                self.fails_for(web, interim, "states.json RS231")
        for field, key in nested.items():
            web, interim = dataset()
            web["states.json"][25][field][key] = 1
            with self.subTest(field=f"{field}.{key}"):
                self.fails_for(web, interim, "states.json RS231")
        for field in ("name", "label", "land"):
            web, interim = dataset()
            del web["states.json"][25][field]
            with self.subTest(field=f"without {field}"):
                self.fails_for(web, interim, "states.json RS231")
        web, interim = dataset()
        web["states.json"][25]["energy"] = {"unit": "MW", "total": 1, "by_type": {"nuclear": 1}, "sites": {"nuclear": 1}, "note": "n"}
        self.fails_for(web, interim, "states.json RS231")

    def test_a_kosovo_municipality_is_null_in_every_statistic(self):
        """Its row keeps the id, the name, the okrug, the area, the land shares and the hex."""
        values = {"population": 1, "density": 1.0, "age65": 0.2, "education": 0.1, "wage_net": 1, "unemployment": 0.1,
                  "manufacturing": 0.1, "commute": 0.1, "orthodox": 0.1, "serbs": 0.1, "life_expectancy": 74.0,
                  "natural_increase": -2.0, "city": "79014"}
        for column, value in values.items():
            web, interim = dataset()
            web["counties.json"]["rows"][-1][COLUMNS.index(column)] = value
            with self.subTest(column=column):
                self.fails_for(web, interim, "counties.json")

    def test_nothing_outside_kosovo_is_null(self):
        """A null where the sources do have figures hides a lost municipality."""
        rows = [("states.json", 0, "population"), ("states.json", 0, "employed"), ("states.json", 0, "unemployment"),
                ("cities.json", 0, "population"), ("cities.json", 0, "employed"), ("cities.json", 0, "unemployment")]
        for name, i, field in rows:
            web, interim = dataset()
            web[name][i][field] = None
            with self.subTest(name=name, field=field):
                self.fails_for(web, interim, "null")
        web, interim = dataset()
        web["counties.json"]["rows"][0][COLUMNS.index("population")] = None
        self.fails_for(web, interim, "counties.json")

    def test_what_the_sources_do_not_publish_may_be_null_anywhere(self):
        web, interim = dataset()
        for row in (web["states.json"][0], web["cities.json"][0]):
            row.update(median_income=None, median_rent=None, home_value=None, rent_burden=None, wage_net=None, age65=None,
                       gdp=None, gdp_year=None, growth=None, growth_years=None,
                       yields={k: None for k in YIELDS}, jobs={k: None for k in JOBS})
            row["ranks"] = {k: None for k in row["ranks"]}
        rep = self.run_check(web, interim)
        self.assertEqual(self.levels(rep, "FAIL"), [])

    def test_the_capital_must_be_grad_beograd(self):
        web, interim = dataset()
        web["cities.json"][0]["capital"] = False
        warns = " | ".join(self.levels(self.run_check(web, interim), "WARN"))
        self.assertIn("capital", warns)

    def test_lens_sources_must_be_in_the_catalog(self):
        web, interim = dataset()
        web["lenses.json"]["lenses"][0]["source"] = "acs_5yr"
        warns = " | ".join(self.levels(self.run_check(web, interim), "WARN"))
        self.assertIn("lenses.json density", warns)
        self.assertIn("'acs_5yr'", warns)

    def test_cities_on_water_or_sharing_a_hex(self):
        web, interim = dataset()
        web["cities.json"][1]["cell"] = 7
        warns = " | ".join(self.levels(self.run_check(web, interim), "WARN"))
        self.assertIn("non-land cells: 1", warns)
        self.assertIn("Mali grad", warns)
        web, interim = dataset()
        web["cities.json"][1].update(cell=0, footprint=[0, 4, 5])
        rep = self.run_check(web, interim)
        self.assertFalse(rep.failed)
        self.assertIn("cells holding more than one city: 1", " | ".join(self.levels(rep, "WARN")))

    def test_the_null_share_of_each_lens(self):
        """Counted over Serbia's hexes outside Kosovo and Metohija, where the statistics exist."""
        web, interim = dataset()
        passes = " | ".join(self.levels(self.run_check(web, interim), "PASS"))
        self.assertIn("lens density: 0.0% of 9 Serbian cells are null", passes)
        web["lenses.json"]["lenses"][0]["values"][0] = None
        warns = " | ".join(self.levels(self.run_check(web, interim), "WARN"))
        self.assertIn("lens density: 11.1% of 9 Serbian cells are null", warns)

    def test_units_missing_from_a_source_are_named(self):
        """A difference between the unit lists is not a failure, but every unit is named."""
        web, interim = dataset()
        interim["census"]["data"]["units"]["70999"] = {}  # a municipality the map does not have yet
        interim["rzs_db"]["data"]["pop"]["70999"] = [1, 2]
        del interim["census"]["data"]["units"]["00005"]  # on the map, but the census prints no row for it
        interim["rzs_db"]["data"]["pop"]["89010"] = [1, 2]  # Grad Novi Sad itself, which the map splits into its parts
        rep = self.run_check(web, interim)
        self.assertFalse(rep.failed)
        warns = " | ".join(self.levels(rep, "WARN"))
        self.assertIn("70999", warns)
        self.assertIn("00005", warns)
        self.assertNotIn("80284", warns)
        notes = " | ".join(self.levels(rep, "NOTE"))
        self.assertIn("80284", notes)  # a part of an aggregate: the census has the grad's row instead
        self.assertIn("80519", notes)
        self.assertIn("89010", notes)  # an aggregate itself
        self.assertIn("90001", notes)  # Kosovo and Metohija: the census covers none of it

    def test_unit_lists_need_all_three_interims(self):
        web, interim = dataset()
        del interim["census"]
        rep = self.run_check(web, interim)
        self.assertEqual(self.levels(rep, "WARN"), [])
        self.assertTrue(any("unit lists" in m and "census" in m for m in self.levels(rep, "NOTE")))


if __name__ == "__main__":
    unittest.main()
