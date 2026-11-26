"""The wonders layer on a world made here: the upstream usaciv shape, every site on Serbian land in its okrug, ranks
that are whole and unique per rule, blank statistics where nothing is published (Kosovo and Metohija included), and
Serbian Latin only.

Nothing is written outside a temporary store: the tests patch store.INTERIM and store.WEB_DATA. The world has the real
projection and grid, one okrug for the north, a Kosovo okrug below 42.75 N, a second Kosovo okrug below 42.38 N, a lake hex under
Golubac fortress (the Danube) and a foreign last row.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.build import sites, wonders
from pipeline.core import srb, store
from pipeline.core.geo import MapProjection
from pipeline.core.territory import in_kosovo
from pipeline.core.hexgrid import HexGrid

COLS, ROWS, RADIUS = 85, 119, 5.0
PROJ = MapProjection(-164.85846045456168, 244.10217307727817, 200.0)
STATES = ["RS110", "RS234", "RS235"]  # north / Kosovo (Peć) / Kosovo (Prizren) south of 42.38 N
COUNTIES = ["70001", "90239"]
CITIES = [{"id": 79014, "name": "Beograd", "counties": ["70001"]}]
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
DOCS = Path(__file__).resolve().parent.parent / "docs" / "SITES.md"
KIM_NAMES = {"Manastir Visoki Dečani", "Patrijaršija u Peći", "Bogorodica Ljeviška", "Manastir Gračanica",
             "Nacionalni park Šar-planina"}


def make_world():
    grid = HexGrid(RADIUS, COLS, ROWS)
    owner, county, water = [], [], []
    south = PROJ(21.0, 42.75)[1]  # map km (y grows southward): from here south everything is the Peć okrug ...
    band = PROJ(21.0, 42.38)[1]   # ... and from here south the Prizren okrug (both in Kosovo and Metohija)
    for cell in range(grid.size):
        x, y = grid.center(*grid.col_row(cell))
        foreign = grid.col_row(cell)[1] == ROWS - 1
        owner.append(srb.FOREIGN if foreign else (1 if south < y <= band else (2 if y > band else 0)))
        county.append(-1 if foreign or y > south else 0)
        water.append(srb.LAND)
    world = {"grid": grid.to_dict(), "projection": PROJ.to_dict(), "width": 727.4, "height": 882.3, "owner": owner,
             "county": county, "water": water, "states": STATES, "counties": COUNTIES,
             "county_samples": [], "county_area_km2": [1.0, 1.0], "cover": [0] * grid.size}
    return world, grid


def make_doc(world):
    placer = wonders.Placer(world, CITIES)
    rows = wonders.read_sites(wonders.CSV)
    ws, moved = wonders.build_wonders(rows, placer)
    rules = []
    for r in wonders.RULES:
        r = dict(r)
        if "{landmarks}" in r["text"]:
            r["text"] = r["text"].format(landmarks=sum(1 for w in ws if w["rule"] == "landmark"))
        rules.append(r)
    return {"version": 1, "sources": ["x"], "rules": rules, "national": {}, "wonders": ws, "vintage": {}}, moved


class WondersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world, cls.grid = make_world()
        x, y = PROJ(21.67848, 44.66119)  # Golubačka tvrđava stands in the Danube
        cls.world["water"][cls.grid.cell_at(x, y)] = srb.LAKE
        cls.doc, cls.moved = make_doc(cls.world)
        cls.by_name = {w["name"]: w for w in cls.doc["wonders"]}

    def test_shape_is_the_upstream_contract(self):
        d = self.doc
        self.assertEqual(d["version"], 1)
        self.assertTrue(isinstance(d["sources"], list) and d["sources"])
        rule_ids = [r["id"] for r in d["rules"]]
        self.assertEqual(rule_ids, ["national_park", "park_unit", "research_university", "unesco_site", "landmark"])
        for r in d["rules"]:
            self.assertTrue({"id", "kind", "kinds", "text"} <= set(r) <= {"id", "kind", "kinds", "text", "year", "curated"}, r)
            self.assertTrue(r["text"] and "{" not in r["text"])
            self.assertIn(r["kind"], r["kinds"])
        curated = {r["id"] for r in d["rules"] if r.get("curated")}
        self.assertEqual(curated, {"unesco_site", "landmark"})
        n = len(d["wonders"])
        self.assertTrue(30 <= n <= 60, n)
        self.assertLess(len(json.dumps(d, ensure_ascii=False).encode()) / 1000, 300)
        for w in d["wonders"]:
            self.assertEqual(set(w) - {"listed_as", "state_note", "note"},
                             {"id", "name", "short", "kind", "rule", "rank", "metrics", "x", "y", "cell", "county",
                              "cbsa", "state", "cells", "curated"})
            self.assertIn(w["kind"], ("natural", "university", "landmark"))
            self.assertIn(w["kind"], next(r for r in d["rules"] if r["id"] == w["rule"])["kinds"])
            self.assertIsNone(w["cells"])
            self.assertEqual(w["curated"], w["rule"] in curated)
            self.assertIsInstance(w["rank"], int)
            self.assertGreaterEqual(w["rank"], 1)
            self.assertIsInstance(w["metrics"], dict)
            for key, v in w["metrics"].items():
                self.assertTrue(v is None or (isinstance(v, str) and v) or (isinstance(v, (int, float)) and v > 0),
                                (w["id"], key, v))

    def test_ranks_are_whole_and_unique_per_rule(self):
        by_rule = {}
        for w in self.doc["wonders"]:
            by_rule.setdefault(w["rule"], []).append(w["rank"])
        for rule, ranks in by_rule.items():
            self.assertEqual(sorted(ranks), list(range(1, len(ranks) + 1)), rule)

    def test_rule_counts_and_orders(self):
        counts = {}
        for w in self.doc["wonders"]:
            counts[w["rule"]] = counts.get(w["rule"], 0) + 1
        self.assertEqual(counts, {"national_park": 5, "park_unit": 4, "research_university": 4, "unesco_site": 8,
                                  "landmark": 13})
        parks = [w for w in self.doc["wonders"] if w["rule"] == "national_park"]
        areas = [w["metrics"]["area_km2"] for w in parks]
        self.assertEqual(areas, sorted(areas, reverse=True))
        self.assertEqual([w["short"] for w in parks], ["Đerdap", "Fruška gora", "Tara", "Šar-planina", "Kopaonik"])
        unis = [w for w in self.doc["wonders"] if w["rule"] == "research_university"]
        self.assertEqual([w["metrics"]["enrollment"] for w in unis], [89299, 42552, 22756, 13996])
        lm = [w["name"] for w in self.doc["wonders"] if w["rule"] == "landmark"]
        self.assertEqual(lm, sorted(lm))
        self.assertEqual({w["metrics"]["inscribed"] for w in self.doc["wonders"] if w["rule"] == "unesco_site"},
                         {1979, 1986, 2004, 2006, 2007, 2016})
        self.assertEqual([w["short"] for w in self.doc["wonders"] if w["rule"] == "park_unit"],
                         ["Golija", "Uvac", "Đavolja varoš", "Deliblatska peščara"])  # by area; no area = last

    def test_every_item_on_serbian_land_in_its_okrug_and_the_city_of_its_county(self):
        owner, water, county = self.world["owner"], self.world["water"], self.world["county"]
        cells = [w["cell"] for w in self.doc["wonders"]]
        self.assertEqual(len(set(cells)), len(cells))  # one wonder per hex
        for w in self.doc["wonders"]:
            c = w["cell"]
            self.assertGreaterEqual(owner[c], 0, w["name"])
            self.assertEqual(water[c], srb.LAND, w["name"])
            self.assertEqual(w["state"], STATES[owner[c]], w["name"])
            self.assertEqual(w["county"], COUNTIES[county[c]] if county[c] >= 0 else None, w["name"])
            self.assertEqual(w["cbsa"], "79014" if county[c] == 0 else None, w["name"])
            cx, cy = self.grid.center(*self.grid.col_row(c))
            self.assertEqual((w["x"], w["y"]), (round(cx, 1), round(cy, 1)))

    def test_kim_sites_have_real_positions_and_null_statistics(self):
        for name in KIM_NAMES:
            w = self.by_name[name]
            self.assertTrue(in_kosovo(w["state"]), (name, w["state"]))
            self.assertIn(w["state"], ("RS234", "RS235"), name)
            self.assertIn("Kosovo i Metohija", w["state_note"])
            self.assertIsNone(w["metrics"]["visits"])
            self.assertIsNone(w["metrics"].get("enrollment"))
            self.assertIsNone(w["county"])
            self.assertIsNone(w["cbsa"])
        others = [w for w in self.doc["wonders"] if w["name"] not in KIM_NAMES]
        self.assertEqual([w["name"] for w in others if w["state"] != "RS110"], [])
        self.assertEqual([w["name"] for w in others if "state_note" in w], [])

    def test_a_fortress_in_the_river_moves_to_land_and_no_two_wonders_share_a_hex(self):
        golubac = self.by_name["Golubačka tvrđava"]
        x, y = PROJ(21.67848, 44.66119)
        self.assertNotEqual(golubac["cell"], self.grid.cell_at(x, y))
        self.assertIn("Golubačka tvrđava", self.moved)
        kalemegdan, unibg = self.by_name["Beogradska tvrđava (Kalemegdan)"], self.by_name["Univerzitet u Beogradu"]
        self.assertNotEqual(kalemegdan["cell"], unibg["cell"])
        self.assertIn(kalemegdan["cell"], self.grid.neighbours(unibg["cell"]))

    def test_null_means_no_data_never_zero(self):
        for w in self.doc["wonders"]:
            for key, v in w["metrics"].items():
                self.assertNotEqual(v, 0, (w["id"], key))
        parks = [w for w in self.doc["wonders"] if w["rule"] in ("national_park", "park_unit")]
        self.assertTrue(all(w["metrics"]["visits"] is None for w in parks))
        self.assertIsNone(self.by_name["Park prirode Deliblatska peščara"]["metrics"]["area_km2"])
        self.assertEqual(self.by_name["Đavolja varoš"]["metrics"]["designated"], 1959)
        unis = [w for w in self.doc["wonders"] if w["rule"] == "research_university"]
        self.assertTrue(all(w["metrics"]["rd_usd"] is None for w in unis))
        self.assertEqual(unis[0]["metrics"]["enrollment_year"], "2024/25")

    def test_listed_as_and_unesco_components(self):
        whs = {w["short"]: w for w in self.doc["wonders"] if w["rule"] == "unesco_site"}
        self.assertEqual(set(whs), {"Stari Ras i Sopoćani", "Studenica", "Gamzigrad", "Visoki Dečani",
                                    "Patrijaršija u Peći", "Bogorodica Ljeviška", "Gračanica", "Stećci"})
        self.assertTrue(all(w["listed_as"] for w in whs.values()))
        self.assertEqual(whs["Stari Ras i Sopoćani"]["metrics"]["inscribed"], 1979)
        landmarks = [w for w in self.doc["wonders"] if w["rule"] == "landmark"]
        self.assertTrue(all("listed_as" not in w for w in landmarks))
        self.assertIn("Đurđevi stupovi", {w["short"] for w in landmarks})  # Ras, not the UNESCO-listed namesake

    def test_an_unknown_rule_is_refused(self):
        rows = wonders.read_sites(wonders.CSV)
        rows[0]["rule"] = "military_base"
        with self.assertRaisesRegex(ValueError, "unknown rule"):
            wonders.build_wonders(rows, wonders.Placer(self.world, CITIES))

    def test_serbian_latin_only(self):
        self.assertIsNone(CYRILLIC.search(json.dumps(self.doc, ensure_ascii=False)))
        self.assertIsNone(CYRILLIC.search((wonders.DATA / wonders.CSV).read_text(encoding="utf-8")))

    def test_every_figure_has_a_source_line_in_docs(self):
        docs = DOCS.read_text(encoding="utf-8")
        for row in wonders.read_sites(wonders.CSV):
            if row["value"]:
                self.assertTrue(row["year"], row["id"])
                self.assertIn(row["rule"], docs, row["id"])
            self.assertTrue(row["note"], row["id"])
        for source in ("rzs_G20251236", "unesco_whc_rs", "wikipedia_sr_protected_areas", "wikipedia_en_coordinates"):
            self.assertIn(source, docs)

    def test_cyrillic_in_the_csv_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.csv").write_text("id,name\na,Београд\n", encoding="utf-8")
            with mock.patch.object(sites, "DATA", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "Cyrillic"):
                    wonders.read_sites("x.csv")


class WondersBuildTest(unittest.TestCase):
    def test_build_writes_the_file_into_the_patched_store(self):
        world, _ = make_world()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", root / "web"):
                store.save_interim("_world", world, vintage="test")
                store.save_interim("_cities", {"cities": CITIES, "units": {}}, vintage="test")
                (root / "web").mkdir()
                wonders.build()
                data = json.loads((root / "web" / "wonders.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(set(data), {"version", "vintage", "sources", "rules", "national", "wonders"})
        self.assertEqual(data["national"]["national_parks"], 5)
        self.assertEqual(data["national"]["unesco_sites"], 5)
        self.assertIn("13 najpoznatijih", next(r for r in data["rules"] if r["id"] == "landmark")["text"])


if __name__ == "__main__":
    unittest.main()
