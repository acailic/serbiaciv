"""The deploy package must reject a site that cannot start."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from pipeline import package


class PackageTest(unittest.TestCase):
    def test_missing_startup_data_is_rejected_before_existing_output_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            web, site = root / "web", root / "dist" / "serbiaciv"
            (web / "data").mkdir(parents=True)
            for name in ("index.html", "data/world.json", "data/cities.json"):
                (web / name).write_text("{}")
            site.mkdir(parents=True)
            (site / "keep.txt").write_text("existing package")
            with mock.patch.object(package, "WEB", web), mock.patch.object(package, "SITE", site), \
                    mock.patch.object(package, "ROOT", root), mock.patch.object(package, "DIST", root / "dist"):
                with self.assertRaisesRegex(SystemExit, "nation.json"):
                    package.cmd_package()
            self.assertTrue((site / "keep.txt").exists())

    def test_source_archive_leaves_out_the_media_under_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("docs/trailer.mp4", "docs/images/hero.jpg", "docs/preview.gif", "docs/GLOSSARY.md", "pipeline/core/x.py",
                        "web/data/cities.json"):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x" * 10)
            out = root / "serbiaciv-source.zip"
            with mock.patch.object(package, "ROOT", root):
                package.write_source_archive(out)
            names = zipfile.ZipFile(out).namelist()
            self.assertEqual(sorted(names), ["serbiaciv/docs/GLOSSARY.md", "serbiaciv/pipeline/core/x.py", "serbiaciv/web/data/cities.json"])
