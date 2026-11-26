import unittest

from pipeline.core import srb, territory


class File(unittest.TestCase):
    def test_loads_with_the_expected_shape(self):
        doc = territory.load()
        self.assertEqual(sorted(doc), ["datasets", "levels", "nodes", "retrieved", "source"])
        self.assertEqual(len(doc["nodes"]), 4961)
        self.assertEqual(doc["levels"]["3"], "oblast (NUTS-3)")

    def test_no_orphans(self):
        missing = [k for k, v in territory.nodes().items() if v["parent"] and v["parent"] not in territory.nodes()]
        self.assertEqual(missing, [])


class Oblasti(unittest.TestCase):
    def test_thirty_oblasti_five_of_them_in_kosovo(self):
        all_oblasti = sorted(k for k, v in territory.nodes().items() if v["level"] == 3)
        self.assertEqual(len(all_oblasti), 30)
        self.assertEqual(sorted(territory.children("RS23")), srb.KIM_OBLASTI)
        self.assertEqual([territory.name(k) for k in srb.KIM_OBLASTI],
                         ["Kosovska oblast", "Kosovsko-mitrovačka oblast", "Kosovsko-pomoravska oblast",
                          "Pećka oblast", "Prizrenska oblast"])

    def test_kosovo_municipalities_as_rzs_groups_them(self):
        grouped = {o: sorted(territory.name(c) for c in territory.children(o)) for o in srb.KIM_OBLASTI}
        for oblast, names in {
            "RS231": ["Glogovac", "Kačanik", "Kosovo Polje", "Lipljan", "Obilić", "Podujevo", "Priština", "Štimlje", "Štrpce", "Uroševac"],
            "RS232": ["Kosovska Mitrovica", "Leposavić", "Srbica", "Vučitrn", "Zubin Potok", "Zvečan"],
            "RS233": ["Gnjilane", "Kosovska Kamenica", "Novo Brdo", "Vitina"],
            "RS234": ["Dečani", "Đakovica", "Istok", "Klina", "Peć"],
            "RS235": ["Gora", "Orahovac", "Prizren", "Suva Reka"],
        }.items():
            with self.subTest(oblast):
                self.assertEqual(set(grouped[oblast]), set(names))


class Units(unittest.TestCase):
    def test_counts(self):
        units = territory.units()
        self.assertEqual(len(units), 204)
        self.assertEqual(sum(k.startswith("9") for k in units), 29)
        self.assertTrue(all(territory.is_unit(k) for k in units))

    def test_id_rules(self):
        self.assertTrue(territory.is_unit("70017"))
        self.assertTrue(territory.is_settlement("804452"))
        self.assertFalse(territory.is_unit("RS110"))
        self.assertFalse(territory.is_unit("804452"))
        self.assertFalse(territory.is_unit(None))

    def test_aggregates(self):
        self.assertEqual(territory.aggregates(), ["79014", "79022", "79049", "79057", "79065", "89010"])
        self.assertEqual(territory.name("79014"), "Grad Beograd")

    def test_parts_of(self):
        belgrade = territory.parts_of("79014")
        self.assertEqual(len(belgrade), 17)
        self.assertNotIn("79014", belgrade)
        self.assertTrue(all(k.startswith("7") for k in belgrade))  # 70xxx, except Surčin (71293)
        self.assertEqual(sorted(territory.parts_of("79022")), ["71285", "71307", "71315", "71323", "71331"])
        self.assertEqual(territory.parts_of("70017"), ["70017"])

    def test_city_municipality(self):
        self.assertTrue(territory.is_city_municipality("70114"))  # Vračar
        self.assertTrue(territory.is_city_municipality("71331"))  # Medijana
        self.assertFalse(territory.is_city_municipality("70017"))  # Aleksandrovac
        self.assertFalse(territory.is_city_municipality("79014"))  # Grad Beograd itself

    def test_oblast_of(self):
        self.assertEqual(territory.oblast_of("70017"), "RS216")
        self.assertEqual(territory.oblast_of("90263"), "RS231")
        self.assertEqual(territory.oblast_of("79014"), "RS110")
        self.assertIsNone(territory.oblast_of("RS"))

    def test_in_kosovo(self):
        self.assertTrue(territory.in_kosovo("90263"))
        self.assertTrue(territory.in_kosovo("RS235"))
        self.assertFalse(territory.in_kosovo("70017"))
        self.assertFalse(territory.in_kosovo("nope"))


class DataUnit(unittest.TestCase):
    """Whose published figures stand for a unit (the census of 2022 has Grad Novi Sad, not its two city municipalities)."""

    @staticmethod
    def rows(published: set) -> callable:
        return lambda unit_id: unit_id in published

    def test_aggregate_of(self):
        self.assertEqual(territory.aggregate_of("71285"), "79022")  # Niška Banja
        self.assertEqual(territory.aggregate_of("70114"), "79014")  # Vračar
        self.assertIsNone(territory.aggregate_of("70017"))  # a plain municipality
        self.assertIsNone(territory.aggregate_of("79022"))  # the aggregate itself

    def test_a_unit_with_its_own_row_stands_for_itself(self):
        self.assertEqual(territory.data_unit("70017", self.rows({"70017"})), "70017")

    def test_novi_sad_is_counted_once_on_its_first_part(self):
        rows = self.rows({"89010"})
        self.assertEqual(territory.parts_of("89010"), ["80284", "80519"])
        self.assertEqual(territory.data_unit("80284", rows), "89010")
        self.assertEqual(territory.data_unit("80519", rows), "80519")  # the second part inherits nothing
        self.assertEqual(territory.data_unit("89010", rows), "89010")

    def test_no_inheritance_while_any_part_has_its_own_row(self):
        rows = self.rows({"79014", "70114"})  # only Vračar has a row among Belgrade's opštine
        self.assertEqual(territory.data_unit("70203", rows), "70203")

    def test_no_inheritance_without_the_aggregates_row(self):
        self.assertEqual(territory.data_unit("80284", self.rows(set())), "80284")
        self.assertEqual(territory.data_unit("70017", self.rows(set())), "70017")


class FindUnit(unittest.TestCase):
    def test_by_name(self):
        self.assertEqual(territory.find_unit("Grad Niš"), "79022")
        self.assertEqual(territory.find_unit("Medijana"), "71331")
        self.assertEqual(territory.find_unit("Palilula (Niš)"), "71323")
        self.assertEqual(territory.find_unit("Palilula (Beograd)"), "70203")
        self.assertEqual(territory.find_unit("Palilula"), None)  # the office disambiguates the name itself
        self.assertEqual(territory.find_unit("Nišavska oblast"), None)  # oblasti are not units
        self.assertEqual(territory.find_unit("Nema me"), None)

    def test_parent_narrows(self):
        self.assertEqual(territory.find_unit("Medijana", parent="79022"), "71331")
        self.assertEqual(territory.find_unit("Medijana", parent="RS110"), None)


if __name__ == "__main__":
    unittest.main()
