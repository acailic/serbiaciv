import json, unittest
from pathlib import Path

from pipeline.core import jsonstat

FIXTURE = Path(__file__).parent / "fixtures" / "eurostat" / "nama_10r_3gdp.json"


class ParseTest(unittest.TestCase):
    def test_real_response(self):
        cells = jsonstat.parse(json.loads(FIXTURE.read_text(encoding="utf-8")))
        by = {(c["geo"], c["time"]): c for c in cells}
        self.assertEqual(by[("RS110", "2022")]["value"], 25637.62)
        self.assertEqual(by[("RS110", "2023")]["value"], 32418.65)
        self.assertEqual(by[("RS110", "2023")]["status"], "p")
        self.assertIsNone(by[("RS110", "2022")]["status"])
        self.assertEqual(by[("RS110", "2023")]["unit"], "MIO_EUR")
        self.assertEqual(len(cells), 6)

    def test_sparse_values_are_none(self):
        doc = {"version": "2.0", "id": ["a", "b"], "size": [2, 2],
               "dimension": {"a": {"category": {"index": {"x": 0, "y": 1}}}, "b": {"category": {"index": {"p": 0, "q": 1}}}},
               "value": {"0": 1.5, "3": 4.0}}
        cells = {(c["a"], c["b"]): c["value"] for c in jsonstat.parse(doc)}
        self.assertEqual(cells, {("x", "p"): 1.5, ("x", "q"): None, ("y", "p"): None, ("y", "q"): 4.0})


    def test_a_size_out_of_step_with_the_dimensions_is_refused(self):
        """A cut-off cube must not come back as cells that silently lack a dimension."""
        doc = {"version": "2.0", "id": ["a", "b"], "size": [2],
               "dimension": {"a": {"category": {"index": {"x": 0, "y": 1}}}, "b": {"category": {"index": {"p": 0, "q": 1}}}},
               "value": {"0": 1.5}}
        with self.assertRaises(ValueError):
            jsonstat.parse(doc)


if __name__ == "__main__":
    unittest.main()
