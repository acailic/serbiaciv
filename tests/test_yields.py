import unittest

from pipeline.build import yields


class JobsTest(unittest.TestCase):
    def test_nace_letters_map_to_keys_and_unknowns_are_dropped(self):
        jobs = yields.jobs_from_nace({"A": 10.4, "C": 20.6, "Z": 99.0, "total": 30.0, "unknown": 5.0, "F": None})
        self.assertEqual(jobs["agriculture"], 10)
        self.assertEqual(jobs["manufacturing"], 21)
        self.assertIsNone(jobs["construction"])
        self.assertEqual(len(jobs), 19)
        self.assertNotIn("Z", jobs)


class YieldsTest(unittest.TestCase):
    def test_formulas_and_missing_values(self):
        jobs = {k: 1.0 for k in ("agriculture", "manufacturing", "construction", "mining", "professional", "information", "arts")}
        y = yields.yields_of(jobs, 1e9)
        self.assertEqual((y["food"], y["production"], y["science"], y["culture"], y["gold"]), (1.0, 3.0, 2.0, 1.0, 1e9))
        jobs["construction"] = None
        self.assertIsNone(yields.yields_of(jobs, 1e9)["production"])
        self.assertIsNone(yields.yields_of(jobs, None)["gold"])


class GrowthTest(unittest.TestCase):
    def test_growth(self):
        self.assertEqual(yields.growth([100, 102, 98], [2023, 2024, 2025], start=2023), (-0.02, [2023, 2025]))
        self.assertEqual(yields.growth(None, [2025], start=2021), (None, None))
        self.assertEqual(yields.growth([100, None], [2021, 2025]), (None, None))
        self.assertEqual(yields.growth([100, 200], [2021, 2025]), (None, None))  # more than 25 %: not believed

    def test_a_series_out_of_step_with_its_years_is_refused(self):
        with self.assertRaises(ValueError):
            yields.growth([100, 102], [2021, 2022, 2025])
        with self.assertRaises(ValueError):
            yields.growth([100, 102, 104, 106], [2021, 2022, 2025])


class RankTest(unittest.TestCase):
    def test_ranks_and_peers(self):
        rows = [{"id": "a", "population": 300, "gdp": 10.0}, {"id": "b", "population": 200, "gdp": 10.0},
                {"id": "c", "population": 100, "gdp": None}, {"id": "d", "population": 400, "gdp": 5.0}]
        yields.ranks(rows, ["population", "gdp"])
        self.assertEqual([r["ranks"]["gdp"] for r in rows], [1, 2, None, 3])  # the tie goes to the larger population
        self.assertEqual([r["ranks"]["population"] for r in rows], [2, 3, 4, 1])
        yields.peers(rows, n=2)
        self.assertEqual(rows[1]["peers"], ["a", "c"])


if __name__ == "__main__":
    unittest.main()
