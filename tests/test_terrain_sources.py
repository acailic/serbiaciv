"""Native raster sources must preserve provenance and cover the territory they serve."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.core import fetch, terrain


class TerrainSourcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raw = Path(self.tmp.name)
        self.patch = mock.patch.object(fetch, "RAW", self.raw)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.raw / "dem").mkdir()

    def cached(self, name, data=b"raster"):
        (self.raw / "dem" / name).write_bytes(data)
        return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "url": "https://example.test/tile"}

    def test_validated_tile_descriptors_reference_the_raw_cache(self):
        manifest = {"one.tif": self.cached("one.tif")}
        (self.raw / "dem" / "manifest.json").write_text(json.dumps(manifest))
        result = terrain.verified_tiles("dem", {"N44_E020": "one.tif"})
        self.assertEqual(result, [{"id": "N44_E020", "path": "dem/one.tif", "sha256": manifest["one.tif"]["sha256"]}])

    def test_missing_file_and_wrong_checksum_fail(self):
        entry = self.cached("one.tif")
        (self.raw / "dem" / "manifest.json").write_text(json.dumps({"one.tif": entry}))
        (self.raw / "dem" / "one.tif").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "one.tif"):
            terrain.verified_tiles("dem", {"N44_E020": "one.tif"})
        (self.raw / "dem" / "one.tif").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "checksum"):
            terrain.verified_tiles("dem", {"N44_E020": "one.tif"})

    def test_tiles_cover_polygon_edges_and_corner_touch(self):
        rings = [[(20.0, 44.2), (20.3, 44.2), (20.3, 44.7), (20.0, 44.7), (20.0, 44.2)]]
        features = [{"rings": rings}]
        self.assertEqual(terrain.required_tiles("dem", features, buffer_deg=0), ["N44_E019", "N44_E020"])


if __name__ == "__main__":
    unittest.main()
