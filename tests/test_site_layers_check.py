"""pipeline.check's builder checks (part 3 of the report): check(web_dir) is discovered in pipeline/build, and its
lines, its errors and its mistakes reach the report under the builder's name. The dataset is tests/test_check.py's.

The two site layers (resources.json, wonders.json) are checked by their builders and are read here as a reader of the
published files would: on the test map, with the test bibliography.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import build as build_pkg
from pipeline import check
from pipeline.build import resources, wonders
from pipeline.core import srb

try:
    from test_check import dataset
except ImportError:  # run from the repository root: python -m unittest tests.test_builder_checks
    from tests.test_check import dataset

FAKE = """PRODUCES = ["fake.json"]


def check(web_dir):
    return [("NOTE", "from the builder")]
"""


def fake_builders(tmp: str, source: str = FAKE):
    """A pipeline/build package whose only module is the fake one (written to a temporary directory)."""
    Path(tmp, "fake_layer.py").write_text(source)
    sys.modules.pop("pipeline.build.fake_layer", None)
    return mock.patch.object(build_pkg, "__path__", [tmp])


class SiteLayerChecksTest(unittest.TestCase):
    """resources.check and wonders.check: the published file read on its own, on the test map."""

    def setUp(self):
        web, _ = dataset()
        self.world = web["world.json"]
        owner, water = self.world["owner"], self.world["water"]
        self.land = next(i for i, (o, w) in enumerate(zip(owner, water)) if o >= 0 and w == srb.LAND)
        self.sea = next(i for i, (o, w) in enumerate(zip(owner, water)) if o < 0)
        self.sources = web["sources.json"]
        self.src = self.sources[0]["id"]
        self.types = [{"id": "coal_plant"}, {"id": "wind"}]
        self.sites = [{"type": "coal_plant", "name": "TE", "cell": self.land, "value": 5},
                      {"type": "wind", "name": "VE", "cell": self.land, "value": None}]
        self.rules = [{"id": r["id"], "kind": r["kind"], "text": "t"} for r in wonders.RULES]
        self.wlist = [{"id": f"w{i}", "name": f"W{i}", "kind": r["kind"], "rule": r["id"], "cell": self.land}
                      for i, r in enumerate(wonders.RULES)]
        self.doc = {"version": 1, "vintage": {}, "sources": [self.src], "rules": self.rules, "national": {}, "wonders": self.wlist}

    def layer(self, name: str, fn, doc=None, raw=None, with_map=True):
        """fn(web_dir) with the test map and bibliography beside the file (doc None: the file is not there)."""
        with tempfile.TemporaryDirectory() as tmp:
            wd = Path(tmp)
            if with_map:
                (wd / "world.json").write_text(json.dumps(self.world))
            (wd / "sources.json").write_text(json.dumps(self.sources))
            if doc is not None or raw is not None:
                (wd / name).write_text(raw if raw is not None else json.dumps(doc))
            return fn(wd)

    @staticmethod
    def levels(lines):
        return [lv for lv, _ in lines]

    def test_both_are_discovered(self):
        self.assertIn("resources", [name for name, _ in check.builder_checks()])
        self.assertIn("wonders", [name for name, _ in check.builder_checks()])

    # ---- resources.json ---------------------------------------------------------------------------------------------

    def test_resources_pass(self):
        lines = self.layer("resources.json", resources.check, {"types": self.types, "items": self.sites, "summary": {}})
        self.assertEqual(lines, [("PASS", "2 types, 2 sites, all on Serbian land")])

    def test_resources_not_built_is_a_note(self):
        self.assertEqual(self.layer("resources.json", resources.check), [("NOTE", "not built — run: python -m pipeline build resources")])

    def test_resources_invalid_json_fails(self):
        lines = self.layer("resources.json", resources.check, raw="{not json")
        self.assertEqual(self.levels(lines), ["FAIL"])
        self.assertIn("invalid JSON", lines[0][1])

    def test_resources_wrong_shape_fails(self):
        for doc in ([], {"types": {}, "items": [], "summary": {}}, {"types": [], "items": []}):
            with self.subTest(doc=doc):
                self.assertEqual(self.levels(self.layer("resources.json", resources.check, doc)), ["FAIL"])

    def test_resources_type_outside_the_catalog_fails(self):
        doc = {"types": self.types + [{"id": "nope"}], "items": self.sites, "summary": {}}
        lines = self.layer("resources.json", resources.check, doc)
        self.assertIn(("FAIL", "types not in this module's catalog: nope"), lines)

    def test_resources_type_twice_fails(self):
        doc = {"types": self.types + [{"id": "wind"}], "items": self.sites, "summary": {}}
        self.assertIn("FAIL", self.levels(self.layer("resources.json", resources.check, doc)))

    def test_resources_site_of_no_type_or_with_a_text_figure_fails(self):
        for site in ({"type": "nope", "name": "X", "cell": self.land}, {"type": "wind", "name": "Y", "cell": self.land, "value": "5"}):
            with self.subTest(site=site):
                lines = self.layer("resources.json", resources.check, {"types": self.types, "items": self.sites + [site], "summary": {}})
                self.assertEqual(self.levels(lines), ["FAIL"])
                self.assertIn(site["name"], lines[0][1])

    def test_resources_site_off_the_land_warns(self):
        sites = [{"type": "coal_plant", "name": "TE", "cell": self.sea, "value": 5}]
        lines = self.layer("resources.json", resources.check, {"types": self.types, "items": sites, "summary": {}})
        self.assertEqual(self.levels(lines), ["WARN"])
        self.assertIn("TE (cell %d)" % self.sea, lines[0][1])

    def test_resources_without_a_map_the_land_is_not_checked(self):
        doc = {"types": self.types, "items": [{"type": "wind", "name": "VE", "cell": self.sea}], "summary": {}}
        self.assertEqual(self.layer("resources.json", resources.check, doc, with_map=False), [("PASS", "2 types, 1 sites")])

    # ---- wonders.json -----------------------------------------------------------------------------------------------

    def test_wonders_pass(self):
        lines = self.layer("wonders.json", wonders.check, self.doc)
        self.assertEqual(lines, [("PASS", f"{len(self.wlist)} wonders: " + ", ".join(f"{r['id']} 1" for r in wonders.RULES)
                                               + ", all on Serbian land")])

    def test_wonders_not_built_is_a_note(self):
        self.assertEqual(self.layer("wonders.json", wonders.check), [("NOTE", "not built — run: python -m pipeline build wonders")])

    def test_wonders_invalid_json_fails(self):
        lines = self.layer("wonders.json", wonders.check, raw="[")
        self.assertEqual(self.levels(lines), ["FAIL"])

    def test_wonders_wrong_version_fails(self):
        doc = {**self.doc, "version": 2}
        self.assertEqual(self.levels(self.layer("wonders.json", wonders.check, doc)), ["FAIL"])

    def test_wonders_rules_other_than_the_module_s_fail(self):
        doc = {**self.doc, "rules": self.rules[::-1]}
        lines = self.layer("wonders.json", wonders.check, doc)
        self.assertTrue(any(lv == "FAIL" and m.startswith("rules differ from this module's") for lv, m in lines))

    def test_wonders_source_outside_the_bibliography_fails(self):
        doc = {**self.doc, "sources": ["nope"]}
        self.assertIn(("FAIL", "sources not in sources.json: nope"), self.layer("wonders.json", wonders.check, doc))

    def test_wonders_without_a_source_fails(self):
        doc = {**self.doc, "sources": []}
        self.assertIn(("FAIL", "no sources cited"), self.layer("wonders.json", wonders.check, doc))

    def test_wonders_of_no_rule_or_listed_twice_fail(self):
        odd = {"id": "odd", "name": "Odd", "kind": "natural", "rule": "nope", "cell": self.land}
        lines = self.layer("wonders.json", wonders.check, {**self.doc, "wonders": self.wlist + [odd]})
        self.assertTrue(any(lv == "FAIL" and "odd (rule 'nope'" in m for lv, m in lines))
        lines = self.layer("wonders.json", wonders.check, {**self.doc, "wonders": self.wlist + [dict(self.wlist[0])]})
        self.assertIn(("FAIL", "wonders listed twice: w0"), lines)

    def test_wonders_off_the_land_warns(self):
        wlist = [dict(w) for w in self.wlist]
        wlist[0]["cell"] = self.sea
        lines = self.layer("wonders.json", wonders.check, {**self.doc, "wonders": wlist})
        self.assertEqual(self.levels(lines), ["WARN"])
        self.assertIn("W0 (cell %d)" % self.sea, lines[0][1])

    def test_wonders_a_rule_with_no_wonder_is_a_note(self):
        lines = self.layer("wonders.json", wonders.check, {**self.doc, "wonders": self.wlist[1:]})
        self.assertEqual(self.levels(lines), ["NOTE", "PASS"])
        self.assertIn(f"rules with no wonder: {wonders.RULES[0]['id']}", lines[0][1])

    def test_wonders_without_a_map_the_land_is_not_checked(self):
        self.assertEqual(self.layer("wonders.json", wonders.check, self.doc, with_map=False),
                         [("PASS", f"{len(self.wlist)} wonders: " + ", ".join(f"{r['id']} 1" for r in wonders.RULES))])


if __name__ == "__main__":
    unittest.main()
