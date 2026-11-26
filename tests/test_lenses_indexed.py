"""The published lens data stores each municipality's value once."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.build import lenses
from pipeline.core import store
from tests.test_lenses import fixture, write_fixture


class IndexedLensesTest(unittest.TestCase):
    def test_manifest_and_values_are_aligned_without_per_hex_duplication(self):
        fx = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, fx)
            with mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", root / "web"), \
                    mock.patch.object(lenses, "WEB_DATA", root / "web"):
                lenses.build()
            manifest = json.loads((root / "web" / "lenses.json").read_text())
            values = json.loads((root / "web" / "lens-values.json").read_text())
        self.assertEqual((manifest["version"], values["version"]), (2, 2))
        self.assertEqual(values["municipality_ids"], fx["interim"]["_world"]["data"]["counties"])
        self.assertTrue(all("values" not in lens for lens in manifest["lenses"]))
        density = next(l for l in manifest["lenses"] if l["id"] == "density")
        self.assertEqual(density["value_source"], {"kind": "municipality", "file": "lens-values.json", "key": "density"})
        self.assertEqual(values["values"]["density"], [25, 1233, 20, 9, None, 7, 1280, 376])
        self.assertEqual(next(l for l in manifest["lenses"] if l["id"] == "elevation")["value_source"],
                         {"kind": "world", "field": "elev"})
