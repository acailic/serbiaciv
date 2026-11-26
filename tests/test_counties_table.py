"""The municipalities table (counties.json) on the fixture of test_lenses.py: one row per municipality on the map."""

import unittest

from pipeline.build import counties, lenses
from test_lenses import OPSTINE, build, fixture

COLUMNS = ["geoid", "name", "state", "population", "land_km2", "density", "age65", "education", "wage_net", "unemployment",
           "manufacturing", "commute", "orthodox", "serbs", "life_expectancy", "natural_increase", "forest", "crop", "pasture",
           "developed", "city", "cell"]
FIELD_KEYS = {"key", "label", "format", "unit", "higher_is", "source", "description"}


class CountiesTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = build(counties, fixture())
        cls.rows = {row[0]: dict(zip(cls.doc["columns"], row)) for row in cls.doc["rows"]}

    def test_the_columns_in_their_order(self):
        self.assertEqual(self.doc["columns"], COLUMNS)

    def test_every_field_describes_its_column(self):
        self.assertEqual([field["key"] for field in self.doc["fields"]], self.doc["columns"])
        for column, field in zip(self.doc["columns"], self.doc["fields"]):
            with self.subTest(column):
                self.assertEqual(set(field), FIELD_KEYS)
                self.assertTrue(field["label"].strip() and field["description"].strip())
                self.assertIn(field["higher_is"], ("good", "bad", "neutral"))
        self.assertEqual({field["key"]: field["format"] for field in self.doc["fields"]}, {
            "geoid": "text", "name": "text", "state": "text", "population": "int", "land_km2": "km2", "density": "float",
            "age65": "pct", "education": "pct", "wage_net": "rsd", "unemployment": "pct", "manufacturing": "pct",
            "commute": "pct", "orthodox": "pct", "serbs": "pct", "life_expectancy": "float", "natural_increase": "float",
            "forest": "pct", "crop": "pct", "pasture": "pct", "developed": "pct", "city": "text", "cell": "int"})
        fields = {field["key"]: field for field in self.doc["fields"]}
        self.assertEqual(fields["wage_net"]["unit"], "RSD")
        self.assertEqual(fields["state"]["label"], "Okrug")

    def test_one_row_per_municipality_on_the_map_in_world_order(self):
        self.assertEqual([row[0] for row in self.doc["rows"]], OPSTINE)
        for row in self.doc["rows"]:
            self.assertEqual(len(row), len(COLUMNS), row[0])

    def test_a_rows_values(self):
        self.assertEqual(self.rows["70017"], {
            "geoid": "70017", "name": "Aleksandrovac", "state": "RS216", "population": 10000, "land_km2": 395.0, "density": 25.3,
            "age65": 0.213, "education": 0.2455, "wage_net": 104512, "unemployment": 0.1158, "manufacturing": 0.2321,
            "commute": 0.3929, "orthodox": 0.9379, "serbs": 0.9607, "life_expectancy": 74.8, "natural_increase": -6.2,
            "forest": 0.6, "crop": 0.3, "pasture": 0.1, "developed": 0.0, "city": "70017", "cell": 0})

    def test_the_names_and_the_okrug(self):
        names = {row["geoid"]: (row["name"], row["state"]) for row in self.rows.values()}
        self.assertEqual(names, {
            "70017": ("Aleksandrovac", "RS216"), "71331": ("Medijana", "RS225"), "70025": ("Aleksinac", "RS225"),
            "70467": ("Gadžin Han", "RS225"), "90034": ("Glogovac", "RS231"), "70378": ("Varvarin", "RS216"),
            "80284": ("Novi Sad", "RS123"), "80519": ("Petrovaradin", "RS123")})

    def test_the_city_column_names_the_city_the_municipality_belongs_to(self):
        self.assertEqual(self.rows["70017"]["city"], "70017")  # a city is its own city
        self.assertEqual(self.rows["71331"]["city"], "79022")  # a city municipality of Niš
        self.assertEqual(self.rows["80284"]["city"], "89010")
        self.assertIsNone(self.rows["70025"]["city"])  # not a city
        self.assertIsNone(self.rows["70467"]["city"])  # _cities does not list it

    def test_a_kosovo_row_carries_only_what_the_map_knows(self):
        """Kosovo and Metohija is on the map, with real land, but the site shows no statistics for it."""
        row = self.rows["90034"]
        self.assertEqual({column for column, value in row.items() if value is not None},
                         {"geoid", "name", "state", "land_km2", "forest", "crop", "pasture", "developed", "cell"})
        self.assertEqual((row["name"], row["state"], row["land_km2"], row["forest"], row["crop"], row["cell"]),
                         ("Glogovac", "RS231", 290.0, 0.5, 0.1, 6))

    def test_nulls_where_a_source_has_nothing(self):
        row = self.rows["70025"]
        for column in ("education", "wage_net", "unemployment", "commute", "life_expectancy"):
            self.assertIsNone(row[column], column)
        self.assertEqual((row["population"], row["manufacturing"], row["serbs"]), (14400, 0.1, 0.9938))

    def test_a_municipality_smaller_than_a_hex_keeps_its_figures_but_cannot_be_pointed_at(self):
        row = self.rows["70378"]
        self.assertEqual((row["population"], row["land_km2"], row["density"], row["age65"], row["life_expectancy"]),
                         (1800, 249.0, 7.2, 0.28, 72.5))
        self.assertIsNone(row["cell"])
        for column in ("forest", "crop", "pasture", "developed"):
            self.assertIsNone(row[column], column)

    def test_the_first_part_of_an_aggregate_inherits_its_row(self):
        """Shaped like Novi Sad: the census of 2022 has Grad Novi Sad (89010), the map has its two city municipalities."""
        novi, petrovaradin = self.rows["80284"], self.rows["80519"]
        self.assertEqual((novi["population"], novi["education"], novi["wage_net"], novi["density"]), (320000, 0.3, 90000, 1280.0))
        self.assertEqual((petrovaradin["population"], petrovaradin["education"], petrovaradin["density"]), (32000, None, 376.5))

    def test_land_shares_are_the_mean_over_the_municipalitys_hexes(self):
        row = self.rows["70467"]
        self.assertEqual((row["forest"], row["crop"], row["pasture"], row["developed"]), (0.8, 0.1, 0.1, 0.0))

    def test_a_hex_without_land_cover_samples_does_not_dilute_the_shares(self):
        fx = fixture()
        world = fx["interim"]["_world"]["data"]
        world["cover"][1] = 0  # no samples: its shares are 0, which means no data
        world["pct"]["forest"][1] = 0
        doc = build(counties, fx)
        row = dict(zip(doc["columns"], doc["rows"][0]))
        self.assertEqual(row["forest"], 0.6)  # hex 0 alone, not (60 + 0) / 2

    def test_the_table_shows_the_numbers_the_lenses_show(self):
        """The columns the lenses also draw from carry the same values (pop_change is a lens only; density is rounded
        to a decimal in the table and to a whole number in the lens)."""
        lens_values = {lens["id"]: lens["values"] for lens in build(lenses, fixture())["lenses"]}
        for lid, column in [("natural_increase", "natural_increase"), ("age65", "age65"),
                            ("education", "education"), ("wages", "wage_net"), ("life_expectancy", "life_expectancy"),
                            ("unemployment", "unemployment"), ("manufacturing", "manufacturing"), ("commute", "commute"),
                            ("orthodox", "orthodox"), ("serbs", "serbs")]:
            for geoid, row in self.rows.items():
                if row["cell"] is not None:
                    with self.subTest(lid=lid, geoid=geoid):
                        self.assertEqual(lens_values[lid][row["cell"]], row[column])

    def test_vintage_names_both_editions(self):
        self.assertEqual(self.doc["vintage"], "Procene RZS 2025 · Popis 2022")

    def test_the_builder_declares_what_it_reads_and_writes(self):
        self.assertEqual(counties.REQUIRES, ["_world", "_cities", "census", "rzs_db"])
        self.assertEqual(counties.PRODUCES, ["counties.json"])


if __name__ == "__main__":
    unittest.main()
