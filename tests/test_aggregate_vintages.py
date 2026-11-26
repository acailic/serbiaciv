"""City-aggregate figures must not be lost or counted twice when source coverage changes by year."""
import unittest

from pipeline.build import lenses, states


class AggregateVintagesTest(unittest.TestCase):
    def setUp(self):
        self.units = ["80284", "80519"]
        self.rzs = {
            "pop_years": [2015, 2025],
            "pop": {"80284": [300000, None], "80519": [30000, None], "89010": [330000, 373652]},
            "employment": {"by_unit": {"80284": {"total": None}, "80519": {"total": None}, "89010": {"total": 177999}}},
            "pop_65": {"by_unit": {"80284": None, "80519": None, "89010": .18}},
            "wages": {"net": {"80284": None, "80519": None, "89010": 120000}},
        }

    def test_district_counts_each_published_population_once_for_each_year(self):
        result = states.figures(self.units, {"units": {}}, self.rzs)
        self.assertEqual(result["pop_series"], [330000, 373652])
        self.assertEqual(result["population"], 373652)
        self.assertEqual(result["employment"], 177999)
        self.assertEqual(result["age65"], .18)
        self.assertEqual(result["wage_net"], 120000)

    def test_lens_uses_a_comparable_aggregate_series_only_once(self):
        first = lenses.rzs_values(self.rzs, "80284")
        second = lenses.rzs_values(self.rzs, "80519")
        self.assertEqual(first["population"], 373652)
        self.assertAlmostEqual(first["pop_change"], 373652 / 330000 - 1)
        self.assertIsNone(second["population"])
        self.assertIsNone(second["pop_change"])
