"""The world builder consumes verified native rasters rather than averaged lattice pixels."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import rasterio
from rasterio.transform import from_origin

from pipeline.build import world
from pipeline.core import fetch, store


class NativeWorldBuildTest(unittest.TestCase):
    def test_native_pixels_reach_the_published_world_and_missing_stays_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = (mock.patch.object(fetch, "RAW", root / "raw"), mock.patch.object(store, "INTERIM", root / "interim"),
                       mock.patch.object(store, "WEB_DATA", root / "web"))
            for patch in patches:
                patch.start()
                self.addCleanup(patch.stop)
            (root / "raw").mkdir()
            (root / "web").mkdir()

            def tile(name, values, nodata):
                path = root / "raw" / name
                with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1, dtype=values.dtype,
                                   crs="EPSG:4326", transform=from_origin(20.049, 44.051, .001, .001), nodata=nodata) as out:
                    out.write(values, 1)
                return {"id": name, "path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

            dem = tile("dem.tif", np.array([[10, 20], [30, 1000]], dtype=np.int16), -9999)
            cover = tile("cover.tif", np.array([[10, 10], [40, 50]], dtype=np.uint8), 0)
            ring = [(20, 44), (20.1, 44), (20.1, 44.1), (20, 44.1), (20, 44)]
            store.save_interim("boundaries", {"oblasti": [{"id": "RS216", "rings": [ring]}], "regioni": [],
                                               "municipalities": [{"id": "70017", "rings": [ring]}], "countries": []})
            store.save_interim("kim", {"oblasti": [], "municipalities": []})
            store.save_interim("dem", {"tiles": [dem]})
            store.save_interim("landcover", {"tiles": [cover]})
            store.save_interim("water", {"rivers": [], "lakes": []})
            world.build()
            data = json.loads((root / "web" / "world.json").read_text())
            sampled = [i for i, maximum in enumerate(data["elev_max"]) if maximum == 1000]
            self.assertEqual(len(sampled), 1)
            i = sampled[0]
            self.assertEqual(data["elev_range"][i], 990)
            self.assertEqual(data["pct"]["forest"][i], 50)
            self.assertEqual(data["pct"]["crop"][i], 25)
            self.assertEqual(data["pct"]["developed"][i], 25)
            self.assertTrue(any(value is None for value in data["elev"]))
            self.assertTrue(any(value is None for value in data["cover"]))
