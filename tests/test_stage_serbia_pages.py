"""Publishing must stage every file the app loads, reject the inherited U.S. data and refuse mismatched assets."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.stage_serbia_pages import ASSETS, stage


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class StageSerbiaPagesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.web = self.root / "web"
        self.data = self.web / "data"
        self.data.mkdir(parents=True)
        (self.web / "index.html").write_text("site", encoding="utf-8")
        (self.web / "js").mkdir()
        (self.web / "js" / "main.js").write_text("site", encoding="utf-8")
        (self.web / "dev").mkdir()
        (self.web / "dev" / "private.html").write_text("dev", encoding="utf-8")
        self.cols, self.rows = 85, 119
        self.ids = [f"{n:05d}" for n in range(1, 198)]
        states = [{"fips": f"RS{n:03d}"} for n in range(1, 31)]
        write_json(self.data / "world.json", {"grid": {"radius": 5, "cols": self.cols, "rows": self.rows},
                                              "states": states, "counties": [{"geoid": i} for i in self.ids]})
        write_json(self.data / "states.json", states)
        write_json(self.data / "cities.json", [{"id": "79014", "name": "Beograd", "capital": True}])
        write_json(self.data / "nation.json", {"nation": {"fips": "RS", "population": 1}})
        write_json(self.data / "sources.json", [{"id": i} for i in ("census", "rzs_db", "dem", "landcover")])
        write_json(self.data / "counties.json", {"columns": ["geoid"], "rows": [[i] for i in self.ids]})
        self.lens_ids = ("density pop_change natural_increase age65 education wages unemployment manufacturing commute "
                         "orthodox serbs life_expectancy elevation relief land_cover").split()
        write_json(self.data / "lenses.json", {"version": 2, "lenses": [{"id": i} for i in self.lens_ids]})
        write_json(self.data / "lens-values.json", {"version": 2, "municipality_ids": self.ids,
                                                    "values": {i: [None] * len(self.ids) for i in self.lens_ids[:12]}})
        write_json(self.data / "kim_towns.json", [])
        write_json(self.data / "resources.json", {"types": [{"id": "thermal"}],
                                                   "items": [{"id": "nt", "name": "Nikola Tesla", "type": "thermal", "cell": 10}]})
        write_json(self.data / "wonders.json", {"version": 1, "wonders": [{"id": "np1", "name": "Tara", "cell": 11}]})
        write_json(self.data / "infrastructure.json", {"version": 1, "roads": [[0, 1, 0]], "rail": [[1, 2, 0]],
                                                        "ports": [{"id": "p1", "name": "Smederevo", "cell": 12}],
                                                        "airports": [{"id": "a1", "name": "Surčin", "cell": 13}]})
        write_json(self.data / "citizens.json", {"version": 1, "cities": {"79014": {"workforce": {}}}})
        write_json(self.data / "districts.json", {"version": 1, "cities": {"79014": {"districts": []}},
                                                  "counties": {"00001": {"districts": []}, "79014": {"districts": []}}})
        # Left over from the American original; nothing in the app loads it.
        write_json(self.data / "trade.json", {"old": "US-only data"})
        self.dest = self.root / "staged"

    def assert_refused(self, message):
        with self.assertRaisesRegex(ValueError, message):
            stage(self.web, self.dest)
        self.assertFalse(self.dest.exists(), "a refused app must not be left half staged")

    def test_stages_every_file_the_app_loads_and_nothing_else(self):
        stage(self.web, self.dest)
        self.assertTrue((self.dest / "js" / "main.js").is_file())
        self.assertEqual(sorted(p.name for p in (self.dest / "data").iterdir()), sorted(ASSETS))
        for name in ASSETS:
            self.assertEqual((self.dest / "data" / name).read_bytes(), (self.data / name).read_bytes(), name)
        self.assertFalse((self.dest / "data" / "trade.json").exists())
        self.assertFalse((self.dest / "dev").exists())
        with zipfile.ZipFile(self.dest / "serbiaciv-source.zip") as archive:
            self.assertIn("serbiaciv/scripts/stage_serbia_pages.py", archive.namelist())
            self.assertIn("serbiaciv/scripts/report_data_size.py", archive.namelist())

    def test_the_site_and_city_view_files_are_among_the_assets(self):
        for name in ("infrastructure.json", "resources.json", "wonders.json", "citizens.json", "districts.json"):
            self.assertIn(name, ASSETS)

    def test_rejects_non_serbian_states_before_staging(self):
        world = read_json(self.data / "world.json")
        world["states"][0]["fips"] = "06"
        write_json(self.data / "world.json", world)
        self.assert_refused("Serbian district")

    def test_rejects_misaligned_lens_values(self):
        write_json(self.data / "lens-values.json", {"version": 2, "municipality_ids": list(reversed(self.ids)), "values": {}})
        self.assert_refused("municipality IDs")

    def test_rejects_a_file_the_app_loads_when_it_is_missing(self):
        (self.data / "districts.json").unlink()
        self.assert_refused("missing Serbian build asset.*districts.json")

    def test_rejects_a_file_that_is_not_json(self):
        (self.data / "wonders.json").write_text("{not json", encoding="utf-8")
        self.assert_refused("invalid JSON.*wonders.json")

    def test_rejects_a_site_outside_the_map(self):
        wonders = read_json(self.data / "wonders.json")
        wonders["wonders"][0]["cell"] = self.cols * self.rows
        write_json(self.data / "wonders.json", wonders)
        self.assert_refused("wonders.json: 'Tara' is not on a hex of the map")

    def test_rejects_a_site_layer_without_sites(self):
        infrastructure = read_json(self.data / "infrastructure.json")
        infrastructure["ports"] = []
        write_json(self.data / "infrastructure.json", infrastructure)
        self.assert_refused("infrastructure.json: no sites to show")

    def test_rejects_a_network_without_lines(self):
        infrastructure = read_json(self.data / "infrastructure.json")
        infrastructure["rail"] = []
        write_json(self.data / "infrastructure.json", infrastructure)
        self.assert_refused("no roads or no rail lines")

    def test_rejects_a_city_view_file_that_lacks_a_city(self):
        citizens = read_json(self.data / "citizens.json")
        del citizens["cities"]["79014"]
        write_json(self.data / "citizens.json", citizens)
        self.assert_refused("citizens.json: its cities are not exactly the cities of cities.json")

    def test_rejects_a_district_row_for_a_unit_the_map_does_not_have(self):
        districts = read_json(self.data / "districts.json")
        districts["counties"]["99999"] = {"districts": []}
        write_json(self.data / "districts.json", districts)
        self.assert_refused("districts.json: a municipality row names a unit the map does not have")


if __name__ == "__main__":
    unittest.main()
