"""sources.json (pipeline/build/catalog.py) says which sources were read by hand, and pipeline/check takes them at
their word: a source that fetched nothing has no file to cite, which is a note, not a warning."""

import pathlib
import tempfile
import unittest
from unittest import mock

from pipeline import check
from pipeline.build import catalog
from pipeline.core import store
from pipeline.sources import SOURCES
from pipeline.sources.sites import Curated
from pipeline.sources.territory import RzsTerritoryTree

try:
    from test_check import dataset
except ImportError:  # run from the repository root: python -m unittest tests.test_catalog
    from tests.test_check import dataset


class CatalogTest(unittest.TestCase):
    def entries(self):
        """The bibliography as it would be written with nothing on disk: no interim, no fetched file."""
        with mock.patch.object(catalog, "load_interim_payload", side_effect=FileNotFoundError), \
                mock.patch.object(catalog, "read_manifest", return_value={}):
            return catalog.source_entries()

    def test_every_source_says_whether_it_was_read_by_hand(self):
        entries = self.entries()
        self.assertEqual([e["id"] for e in entries], [s.id for s in SOURCES])
        self.assertEqual([e["curated"] for e in entries], [isinstance(s, Curated) for s in SOURCES])
        self.assertTrue(any(e["curated"] for e in entries))
        self.assertTrue(all(e["files"] == [] for e in entries))

    def test_the_territory_tree_cites_the_pages_its_refresh_downloaded(self):
        # Read by hand, but off pages that were downloaded: the bibliography names them, as for a fetched source
        pages = {f"p{i}.html": {"url": f"https://data.stat.gov.rs/Home/Result/{i}?languageCode=sr-Latn",
                                "retrieved": "2026-11-26T21:14:15+00:00", "sha256": "00", "bytes": 1} for i in range(3)}
        source = RzsTerritoryTree()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(store, "INTERIM", pathlib.Path(tmp)), \
                mock.patch.object(catalog, "read_manifest", side_effect=lambda sid: pages if sid == "rzs_territory" else {}):
            store.save_interim(source.id, source.process(), vintage=source.vintage)
            entries = {e["id"]: e for e in catalog.source_entries()}
        self.assertEqual(entries["rzs_territory"]["curated"], True)
        self.assertEqual([f["file"] for f in entries["rzs_territory"]["files"]], ["p0.html", "p1.html", "p2.html"])
        self.assertEqual(entries["rzs_territory"]["vintage"], source.vintage)
        # a hand-read source with nothing on disk still cites its homepage alone
        self.assertEqual(entries["project_curated_landmarks"]["files"], [])

    def test_the_checker_takes_a_hand_read_source_at_its_word(self):
        for flag, level, phrase in ((True, "NOTE", "read by hand"), (False, "WARN", "no files cited"), (None, "WARN", "no files cited")):
            with self.subTest(curated=flag):
                doc, _ = dataset()
                doc = doc["sources.json"]
                doc[0]["files"] = []
                if flag is not None:
                    doc[0]["curated"] = flag
                r = check.Report(quiet=True)
                check.check_sources(r, doc)
                lines = [(lv, m) for lv, m in r.lines if "read by hand" in m or "no files cited" in m]
                self.assertEqual([(lv, phrase in m) for lv, m in lines], [(level, True)])


if __name__ == "__main__":
    unittest.main()
