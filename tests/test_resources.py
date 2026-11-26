"""The resources layer on a world made here: the upstream usaciv shape, every site on Serbian land in its okrug, a
blank figure where nothing is published, Serbian Latin only, and a source for every figure.

Nothing is written outside a temporary store: the tests patch store.INTERIM and store.WEB_DATA. The world has the real
projection and grid (so the curated CSV coordinates land where they do on the map), one okrug for the north, a Kosovo
okrug and a band okrug for the south, a lake hex under the Đerdap 1 dam and a foreign last row.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.build import resources, sites
from pipeline.core import srb, store
from pipeline.core.geo import MapProjection
from pipeline.core.hexgrid import HexGrid

COLS, ROWS, RADIUS = 85, 119, 5.0
PROJ = MapProjection(-164.85846045456168, 244.10217307727817, 200.0)
STATES = ["RS110", "RS234", "RS224"]  # north / Kosovo (Peć) / a band between them
COUNTIES = ["70001"]
CITIES = [{"id": 79014, "name": "Beograd", "counties": ["70001"]}]
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
DOCS = Path(__file__).resolve().parent.parent / "docs" / "SITES.md"


def make_world():
    grid = HexGrid(RADIUS, COLS, ROWS)
    owner, county, water = [], [], []
    south = PROJ(21.0, 43.2)[1]   # map km (y grows southward): from here south everything is the Kosovo okrug ...
    band = PROJ(21.0, 42.9)[1]    # ... and from here south the band okrug (Lece lies in it)
    for cell in range(grid.size):
        x, y = grid.center(*grid.col_row(cell))
        foreign = grid.col_row(cell)[1] == ROWS - 1
        owner.append(srb.FOREIGN if foreign else (1 if south < y <= band else (2 if y > band else 0)))
        county.append(-1 if foreign or y > south else 0)
        water.append(srb.LAND)
    world = {"grid": grid.to_dict(), "projection": PROJ.to_dict(), "width": 727.4, "height": 882.3, "owner": owner,
             "county": county, "water": water, "states": STATES, "counties": COUNTIES,
             "county_samples": [], "county_area_km2": [1.0], "cover": [0] * grid.size}
    return world, grid


def dam_cell(grid):
    x, y = PROJ(22.52917, 44.67083)  # HE Đerdap 1: the dam stands in the Danube
    return grid.cell_at(x, y)


class ResourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world, cls.grid = make_world()
        cls.world["water"][dam_cell(cls.grid)] = srb.LAKE
        cls.placer = resources.Placer(cls.world, CITIES)
        cls.rows = resources.read_sites(resources.CSV)
        cls.items, cls.skipped, cls.moved = resources.items_from(cls.rows, cls.placer)
        cls.types = [t for t in resources.TYPES if t["id"] in {it["type"] for it in cls.items}]
        cls.doc = {"types": cls.types, "items": cls.items, "summary": resources.summarize(cls.items, cls.types)}
        cls.by_name = {it["name"]: it for it in cls.items}

    def test_nothing_is_skipped_and_nothing_below_a_threshold(self):
        self.assertEqual(self.skipped, [])
        limits = {"wind": resources.MIN_WIND_MW, "solar": resources.MIN_SOLAR_MW}
        for it in self.items:
            limit = limits.get(it["type"], resources.MIN_MW if it["type"] in ("coal_plant", "gas_plant", "hydro",
                                                                               "pumped_storage") else 0)
            if it["value"] is not None:
                self.assertGreaterEqual(it["value"], limit, it["name"])

    def test_a_row_below_the_threshold_is_reported_not_published(self):
        rows = [dict(r) for r in self.rows if r["id"] == "pp-kolubara"]
        rows[0]["value"] = "90"
        items, skipped, _ = resources.items_from(rows, self.placer)
        self.assertEqual(items, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("threshold", skipped[0])
        rows[0].update(value="216", type="uranium")
        self.assertIn("unknown type", resources.items_from(rows, self.placer)[1][0])

    def test_shape_is_the_upstream_contract(self):
        d = self.doc
        self.assertEqual(set(d), {"types", "items", "summary"})
        for t in d["types"]:
            self.assertEqual(set(t), {"id", "name", "category", "emoji", "icon", "color", "unit", "description",
                                      "source"})
            self.assertEqual(t["icon"], f"r-{t['id']}")
            self.assertIn(t["category"], ("energy", "mineral", "agri"))
            self.assertTrue(t["description"] and t["source"] and t["color"].startswith("#"), t["id"])
        self.assertEqual(len({t["id"] for t in d["types"]}), len(d["types"]))
        for it in d["items"]:
            self.assertEqual(set(it), {"type", "name", "x", "y", "cell", "value", "detail", "state", "cbsa"})
            self.assertIn(it["type"], {t["id"] for t in d["types"]})
            self.assertTrue(it["detail"], it["name"])
            self.assertIn(it["state"], ("RS110", "RS224"), it["name"])
        self.assertEqual(self.by_name["Rudnik Lece"]["state"], "RS224")  # the okrug the source files it under
        self.assertEqual(set(d["summary"]), {"note", "national", "states"})
        self.assertEqual(set(d["summary"]["national"]), {t["id"] for t in d["types"]})
        self.assertEqual(list(d["summary"]["states"]), ["RS110", "RS224"])
        for st in d["summary"]["states"].values():  # only the types present in the okrug
            self.assertTrue(st and set(st) <= {t["id"] for t in d["types"]})
        self.assertIn("lead_zinc", d["summary"]["states"]["RS224"])  # Lece: the only mine in the southern band
        self.assertTrue(d["summary"]["note"])

    def test_every_item_on_serbian_land_in_its_okrug_and_the_city_of_its_county(self):
        owner, water, county = self.world["owner"], self.world["water"], self.world["county"]
        for it in self.items:
            c = it["cell"]
            self.assertGreaterEqual(owner[c], 0, it["name"])
            self.assertEqual(water[c], srb.LAND, it["name"])
            self.assertEqual(STATES[owner[c]], it["state"], it["name"])
            self.assertEqual(it["cbsa"], "79014" if county[c] >= 0 else None, it["name"])
            cx, cy = self.grid.center(*self.grid.col_row(c))
            self.assertEqual((it["x"], it["y"]), (round(cx, 1), round(cy, 1)))

    def test_a_dam_in_the_river_moves_to_the_nearest_land_hex(self):
        he = self.by_name["HE Đerdap 1"]
        self.assertNotEqual(he["cell"], dam_cell(self.grid))
        self.assertEqual(self.world["water"][he["cell"]], srb.LAND)
        self.assertIn("HE Đerdap 1", self.moved)
        self.assertIn(he["cell"], self.grid.neighbours(dam_cell(self.grid)))

    def test_an_okrug_in_the_csv_wins_over_the_raster(self):
        row = next(dict(r) for r in self.rows if r["id"] == "lz-lece")
        row["okrug"] = ""  # the raster alone puts Lece's hex in the band okrug (here: RS224 is what the CSV wants)
        without, _, _ = resources.items_from([row], self.placer)
        self.assertEqual(without[0]["state"], "RS224")
        row.update(okrug="RS110", lat="43.1")  # a point the raster gives to the Kosovo okrug
        moved_rows, skipped, _ = resources.items_from([row], self.placer)
        self.assertEqual(skipped, [])
        self.assertEqual(moved_rows[0]["state"], "RS110")
        self.assertEqual(self.world["owner"][moved_rows[0]["cell"]], 0)

    def test_a_point_on_foreign_ground_moves_to_the_nearest_serbian_hex(self):
        last = self.grid.index(40, ROWS - 1)
        x, y = self.grid.center(40, ROWS - 1)
        lon, lat = PROJ.inverse(x, y)
        cell = self.placer.cell(lon, lat)
        self.assertGreaterEqual(self.world["owner"][cell], 0)
        self.assertNotEqual(cell, last)

    def test_null_means_no_data_never_zero(self):
        self.assertIsNone(self.by_name["Ibarski rudnici (Baljevac)"]["value"])
        self.assertIsNone(self.by_name["Rudnik Lece"]["value"])
        for it in self.items:
            self.assertNotEqual(it["value"], 0, it["name"])
        coal = self.doc["summary"]["national"]["coal_mine"]
        self.assertEqual((coal["count"], coal["value"]), (3, 22_000_000 + 9_000_000))  # the null mine adds nothing

    def test_totals_are_sums_of_the_mapped_sites(self):
        nat = self.doc["summary"]["national"]
        self.assertEqual(nat["coal_plant"], {"count": 6, "value": 1594 + 1220 + 216 + 108 + 281 + 941, "unit": "MW"})
        self.assertEqual(nat["hydro"]["count"], 5)
        self.assertEqual(nat["pumped_storage"]["value"], 614)
        self.assertEqual(nat["wind"]["value"], 158 + 104.5 + 66)
        self.assertEqual(nat["oil"]["value"], 4_800_000)
        self.assertEqual(nat["solar"]["value"], 9.75)
        self.assertEqual(nat["lead_zinc"]["value"], 9000)

    def test_key_sites_are_present(self):
        for name in ("TE Nikola Tesla A", "TE Nikola Tesla B", "TE Kostolac B", "TE-TO Pančevo", "TE-TO Novi Sad",
                     "HE Đerdap 1", "HE Đerdap 2", "HE Bajina Bašta", "RHE Bajina Bašta", "HE Zvornik",
                     "Vetropark Čibuk 1", "Vetropark Kovačica", "Rudarski basen Kolubara", "Površinski kop Drmno",
                     "Rudnik Veliki Krivelj", "Rudnik Majdanpek", "Rudnik Rudnik", "Rafinerija nafte Pančevo"):
            self.assertIn(name, self.by_name)
        self.assertEqual(len({self.by_name[n]["cell"] for n in ("TE Nikola Tesla A", "TE-TO Novi Sad",
                                                                "HE Bajina Bašta")}), 3)

    def test_serbian_latin_only(self):
        self.assertIsNone(CYRILLIC.search(json.dumps(self.doc, ensure_ascii=False)))
        self.assertIsNone(CYRILLIC.search((sites.DATA / resources.CSV).read_text(encoding="utf-8")))

    def test_every_figure_has_a_source_line_in_docs(self):
        docs = DOCS.read_text(encoding="utf-8")
        for row in self.rows:
            self.assertTrue(row["detail"], row["id"])
            if row["value"]:
                self.assertTrue(row["source"] and row["source"] != "NONE", row["id"])
                self.assertIn(row["source"], docs, f"{row['id']}: source {row['source']} not documented")
                self.assertTrue(row["year"], row["id"])
        self.assertEqual({t["id"] for t in self.types},
                         {"coal_plant", "gas_plant", "hydro", "pumped_storage", "wind", "solar", "coal_mine",
                          "copper", "lead_zinc", "oil"})

    def test_cyrillic_in_the_csv_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.csv").write_text("id,name\na,Београд\n", encoding="utf-8")
            with mock.patch.object(sites, "DATA", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "Cyrillic"):
                    resources.read_sites("x.csv")


class ResourcesBuildTest(unittest.TestCase):
    def test_build_writes_the_file_into_the_patched_store(self):
        world, _ = make_world()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", root / "web"):
                store.save_interim("_world", world, vintage="test")
                store.save_interim("_cities", {"cities": CITIES, "units": {}}, vintage="test")
                (root / "web").mkdir()
                resources.build()
                data = json.loads((root / "web" / "resources.json").read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"types", "items", "summary"})
        self.assertGreater(len(data["items"]), 20)


if __name__ == "__main__":
    unittest.main()
