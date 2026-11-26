"""Aggregate original raster pixels into hexes without losing peaks or class shares."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import rasterio
from rasterio.transform import from_origin

from pipeline.core import fetch, geo, hexgrid, terrain


class NativeTerrainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw_patch = mock.patch.object(fetch, "RAW", self.root)
        self.raw_patch.start()
        self.addCleanup(self.raw_patch.stop)
        albers = geo.Albers()
        x, y = albers(20.0, 45.0)
        self.proj = geo.MapProjection(x, y, 20)
        self.grid = hexgrid.HexGrid(radius=5, cols=12, rows=12)
        self.owner = [0] * self.grid.size
        self.water = [0] * self.grid.size

    def make_tile(self, name, array, nodata=-9999):
        path = self.root / name
        with rasterio.open(path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1], count=1,
                           dtype=array.dtype, crs="EPSG:4326", transform=from_origin(20, 45, .001, .001), nodata=nodata) as out:
            out.write(array, 1)
        return {"id": name, "path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_vectorized_cell_selection_matches_the_grid(self):
        rng = np.random.default_rng(942)
        lon = rng.uniform(19.7, 20.7, 1000)
        lat = rng.uniform(44.5, 45.3, 1000)
        got = terrain.cell_indices(lon, lat, self.grid, self.proj)
        self.assertEqual(got.tolist(), [self.grid.cell_at(*self.proj(float(x), float(y))) for x, y in zip(lon, lat)])

    def test_elevation_keeps_a_narrow_peak_and_skips_nodata(self):
        tile = self.make_tile("dem.tif", np.array([[0, 10, -9999], [20, 1000, -9999]], dtype=np.int16))
        result = terrain.aggregate_tiles([tile], self.grid, self.proj, self.owner, self.water, "dem")
        idx = self.grid.cell_at(*self.proj(20.0005, 44.9995))
        self.assertEqual(result["count"][idx], 4)
        self.assertEqual((result["min"][idx], result["max"][idx]), (0, 1000))
        self.assertAlmostEqual(result["weighted_sum"][idx] / result["area"][idx], 257.5, places=1)

    def test_land_cover_uses_all_valid_native_pixels(self):
        tile = self.make_tile("cover.tif", np.array([[10, 10], [40, 0]], dtype=np.uint8), nodata=0)
        result = terrain.aggregate_tiles([tile], self.grid, self.proj, self.owner, self.water, "landcover")
        idx = self.grid.cell_at(*self.proj(20.0005, 44.9995))
        shares = result["classes"][idx]
        self.assertAlmostEqual(shares[10] / sum(shares.values()), 2 / 3, places=4)
        self.assertAlmostEqual(shares[40] / sum(shares.values()), 1 / 3, places=4)

    def test_duplicate_tile_overlap_is_rejected(self):
        first = self.make_tile("first.tif", np.array([[10]], dtype=np.int16))
        second = self.make_tile("second.tif", np.array([[10]], dtype=np.int16))
        with self.assertRaisesRegex(ValueError, "overlap"):
            terrain.aggregate_tiles([first, second], self.grid, self.proj, self.owner, self.water, "dem")
