"""pipeline.check's builder checks (part 3 of the report): check(web_dir) is discovered in pipeline/build, and its
lines, its errors and its mistakes reach the report under the builder's name. The dataset is tests/test_check.py's.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import build as build_pkg
from pipeline import check

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


class BuilderChecksTest(unittest.TestCase):
    def run_check(self, web, interim, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            wd, idir = Path(tmp) / "web", Path(tmp) / "interim"
            wd.mkdir()
            idir.mkdir()
            for name, doc in web.items():
                if doc is not None:
                    (wd / name).write_text(json.dumps(doc))
            for name, payload in interim.items():
                (idir / f"{name}.json").write_text(json.dumps(payload))
            return check.run(wd, idir, quiet=True, **kw)

    def test_a_check_is_discovered_by_its_module_file(self):
        with tempfile.TemporaryDirectory() as tmp, fake_builders(tmp):
            found = dict(check.builder_checks())
        self.assertEqual(list(found), ["fake_layer"])
        self.assertTrue(callable(found["fake_layer"]))

    def test_a_module_without_check_is_not_one(self):
        with tempfile.TemporaryDirectory() as tmp, fake_builders(tmp, "PRODUCES = ['fake.json']\n"):
            self.assertEqual(check.builder_checks(), [])
        with tempfile.TemporaryDirectory() as tmp, fake_builders(tmp, "check = 'not a function'\n"):
            self.assertEqual(check.builder_checks(), [])

    def test_the_real_builders_may_define_one(self):
        """Nothing in pipeline/build defines check yet; whatever does is found with its module's name."""
        names = [name for name, _ in check.builder_checks()]
        self.assertEqual(names, sorted(names))
        for name, fn in check.builder_checks():
            self.assertIn(name, build_pkg.BUILDERS)
            self.assertTrue(callable(fn))

    def test_lines_reach_the_report_under_the_builder_s_name(self):
        r = check.Report(quiet=True)
        check.run_builder_checks(r, Path("."), [("lenses", lambda web_dir: [("PASS", "a"), ("warn", "b")])])
        self.assertEqual(r.lines, [("PASS", "lenses: a"), ("WARN", "lenses: b")])

    def test_nothing_to_run_adds_nothing(self):
        r = check.Report(quiet=True)
        check.run_builder_checks(r, Path("."), [])
        check.run_builder_checks(r, Path("."), [("quiet", lambda web_dir: None)])
        self.assertEqual(r.lines, [])

    def test_a_check_that_raises_fails_and_the_others_still_run(self):
        def boom(web_dir):
            raise ValueError("nope")

        r = check.Report(quiet=True)
        check.run_builder_checks(r, Path("."), [("a", boom), ("b", lambda web_dir: [("PASS", "fine")])])
        self.assertEqual(r.lines, [("FAIL", "a: check() raised ValueError: nope"), ("PASS", "b: fine")])
        self.assertTrue(r.failed)

    def test_mistaken_lines_fail_with_the_builder_s_name(self):
        for bad in ("PASS", ("FINE", "x"), ("PASS",), ("PASS", "x", "y"), None):
            with self.subTest(line=bad):
                r = check.Report(quiet=True)
                check.run_builder_checks(r, Path("."), [("m", lambda web_dir, bad=bad: [bad])])
                self.assertEqual(r.lines[0][0], "FAIL")
                self.assertTrue(r.lines[0][1].startswith("m: "))
                self.assertTrue(r.failed)

    def test_run_runs_the_discovered_checks_unless_told_otherwise(self):
        web, interim = dataset()
        with tempfile.TemporaryDirectory() as tmp, fake_builders(tmp):
            rep = self.run_check(web, interim)
            self.assertIn(("NOTE", "fake_layer: from the builder"), rep.lines)
            self.assertFalse(rep.failed)
            rep = self.run_check(web, interim, builder_checks_=[])
            self.assertNotIn(("NOTE", "fake_layer: from the builder"), rep.lines)
            rep = self.run_check(web, interim, builder_checks_=[("x", lambda web_dir: [("WARN", "only this")])])
            self.assertEqual([m for lv, m in rep.lines if lv == "WARN"], ["x: only this"])
            self.assertFalse(rep.failed)

    def test_a_file_a_builder_checks_is_not_reported_as_unchecked(self):
        web, interim = dataset()
        web["fake.json"] = {}
        web["nobody.json"] = {}
        with tempfile.TemporaryDirectory() as tmp, fake_builders(tmp):
            rep = self.run_check(web, interim)
        notes = [m for lv, m in rep.lines if "not checked" in m]
        self.assertEqual(len(notes), 1)
        self.assertIn("nobody.json", notes[0])
        self.assertNotIn("fake.json", notes[0])
        with tempfile.TemporaryDirectory() as tmp, fake_builders(tmp):
            rep = self.run_check(web, interim, builder_checks_=[])
        self.assertIn("fake.json", [m for lv, m in rep.lines if "not checked" in m][0])


if __name__ == "__main__":
    unittest.main()
