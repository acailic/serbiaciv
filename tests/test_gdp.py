"""GDP by oblast (Eurostat nama_10r_3gdp): which year is taken, how the values are split by level, and the vintage."""

import json
import unittest
from pathlib import Path

from pipeline.core import jsonstat, srb, territory
from pipeline.sources import gdp

FIXTURE = Path(__file__).parent / "fixtures" / "eurostat" / "nama_10r_3gdp.json"
VINTAGE = "Eurostat, BDP po oblastima (nama_10r_3gdp), "
KEYS = {"vintage", "year", "unit", "nuts3", "nuts2", "provisional"}


def _cell(geo, year, value, status=None):
    """A cell as jsonstat.parse returns it."""
    return {"freq": "A", "unit": "MIO_EUR", "geo": geo, "time": str(year), "value": value, "status": status}


OBLASTI, REGIONI = gdp.oblasti(), gdp.regioni()
# What Eurostat published on 2026-11-26, in shape: the oblasti answer to 2023, the regions to 2024; all of it provisional.
ANSWER = [_cell(geo, 2022, 1.0) for geo in OBLASTI] + [_cell(geo, 2023, 2.0, "p") for geo in OBLASTI]
ANSWER += [_cell(geo, year, 3.0, "p") for geo in REGIONI for year in (2023, 2024)]


class IdsTest(unittest.TestCase):
    def test_the_oblasti_are_the_level_3_ids_outside_kosovo(self):
        self.assertEqual(len(OBLASTI), 25)
        self.assertEqual(OBLASTI, sorted(k for k, v in territory.nodes().items() if v["level"] == 3 and k not in srb.KIM_OBLASTI))

    def test_the_regions_are_the_level_2_ids_outside_kosovo(self):
        self.assertEqual(REGIONI, ["RS11", "RS12", "RS21", "RS22"])


class PickYearTest(unittest.TestCase):
    def test_the_latest_year_in_which_every_oblast_has_a_value(self):
        self.assertEqual(gdp.pick_year(ANSWER), 2023)

    def test_a_year_with_a_gap_is_skipped(self):
        cells = [_cell(geo, 2021, 1.0) for geo in OBLASTI]
        cells += [_cell(OBLASTI[0], 2023, 3.0), _cell(OBLASTI[1], 2023, 3.0)] + [_cell(geo, 2022, None) for geo in OBLASTI]
        self.assertEqual(gdp.pick_year(cells), 2021)

    def test_no_complete_year_is_an_error(self):
        with self.assertRaises(RuntimeError):
            gdp.pick_year([_cell(geo, 2023, 1.0) for geo in OBLASTI[:-1]])


class ValuesTest(unittest.TestCase):
    CELLS = [
        _cell("RS110", 2023, 32418.65, "p"), _cell("RS110", 2022, 25637.62), _cell("RS110", 2024, 1.0),
        _cell("RS11", 2023, 32418.65, "p"), _cell("RS11", 2022, 25637.62),
        _cell("RS121", 2023, 1099.12, "p"), _cell("RS217", 2023, None, "p"),
    ]

    def test_the_values_of_one_year(self):
        ids = ["RS110", "RS121", "RS217", "RS225"]
        self.assertEqual(gdp.values(self.CELLS, 2023, ids), {"RS110": 32418.65, "RS121": 1099.12})
        self.assertEqual(gdp.values(self.CELLS, 2022, ["RS11"]), {"RS11": 25637.62})

    def test_provisional_lists_the_ids_asked_for(self):
        oblasti = ["RS110", "RS121", "RS217"]
        self.assertEqual(gdp.provisional(self.CELLS, 2023, oblasti), ["RS110", "RS121"])
        self.assertEqual(gdp.provisional(self.CELLS, 2023), ["RS11", "RS110", "RS121"])  # every id, as the vintage needs it
        self.assertEqual(gdp.provisional(self.CELLS, 2022), [])


class VintageTest(unittest.TestCase):
    def test_the_vintage_names_the_year(self):
        self.assertEqual(gdp.vintage(2022, []), VINTAGE + "2022")

    def test_the_vintage_says_when_any_id_is_provisional(self):
        self.assertEqual(gdp.vintage(2023, ["RS11"]), VINTAGE + "2023 — privremeni podaci")


class InterimTest(unittest.TestCase):
    def test_the_shape_of_the_interim(self):
        out = gdp.summarize(ANSWER)
        self.assertEqual(set(out), KEYS)
        self.assertEqual(out["year"], 2023)
        self.assertEqual(out["unit"], "MIO_EUR")
        self.assertEqual(out["vintage"], VINTAGE + "2023 — privremeni podaci")
        self.assertEqual(out["nuts3"], {geo: 2.0 for geo in OBLASTI})
        self.assertEqual(out["nuts2"], {geo: 3.0 for geo in REGIONI})
        self.assertEqual(out["provisional"], OBLASTI)

    def test_provisional_is_always_a_subset_of_the_oblasti(self):
        # A consumer that walks `provisional` and indexes `nuts3` must never meet a region id.
        out = gdp.summarize([c for c in ANSWER if not (c["geo"] == "RS110" and c["time"] == "2023")] + [_cell("RS110", 2023, 9.0)])
        self.assertEqual(out["provisional"], [geo for geo in OBLASTI if geo != "RS110"])
        self.assertTrue(set(out["provisional"]) <= set(out["nuts3"]))

    def test_final_data_says_so(self):
        out = gdp.summarize([_cell(geo, 2023, 2.0) for geo in OBLASTI + REGIONI])
        self.assertEqual((out["vintage"], out["provisional"]), (VINTAGE + "2023", []))

    def test_on_the_committed_response(self):
        # The fixture holds three oblasti, so it is not a whole answer: no year is picked from it.
        cells = jsonstat.parse(json.loads(FIXTURE.read_text(encoding="utf-8")))
        with self.assertRaises(RuntimeError):
            gdp.pick_year(cells)
        self.assertEqual(gdp.values(cells, 2023, gdp.oblasti()), {"RS110": 32418.65, "RS121": 1099.12, "RS217": 1714.84})
        self.assertEqual(gdp.provisional(cells, 2023, gdp.oblasti()), ["RS110", "RS121", "RS217"])
        self.assertEqual(gdp.provisional(cells, 2022, gdp.oblasti()), [])


class InfoTest(unittest.TestCase):
    def test_the_source_is_described_as_the_plan_fixes_it(self):
        info = gdp.Gdp.info
        self.assertEqual((info.id, info.title, info.publisher), ("gdp", "BDP po oblastima (nama_10r_3gdp)", "Eurostat"))
        self.assertEqual(info.homepage, "https://ec.europa.eu/eurostat/web/regions")
        self.assertEqual(info.license, "© Evropska unija, 1995–2026, CC BY 4.0")

    def test_the_request_repeats_a_parameter_per_geo_and_per_year(self):
        # Eurostat answers 400 to a comma-joined list; only a repeated parameter carries many values.
        url = gdp.request_url()
        self.assertIn("&geo=RS110&geo=RS121", url)
        self.assertIn("&unit=MIO_EUR&time=2019&time=2020", url)
        self.assertNotIn(",", url)
        self.assertEqual((url.count("&geo="), url.count("&time=")), (29, 6))


if __name__ == "__main__":
    unittest.main()
