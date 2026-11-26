"""core.raster: tile names, the lattice's affine transform and warping one GeoTIFF onto the lattice."""

import unittest

import numpy as np
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from pipeline.core import lattice, raster, srb
from pipeline.core.lattice import Lattice

SERBIA = (18.8, 41.8, 23.2, 46.2)  # min lon, min lat, max lon, max lat: srb.BBOX_LONLAT
NODATA = lattice.ELEV_NODATA


def _geotiff(west: float, north: float, step: float, values: np.ndarray, nodata=None) -> MemoryFile:
    """An in-memory GeoTIFF of `step`° pixels with its north-west corner at (west, north); `values` is (rows, cols)."""
    rows, cols = values.shape
    mem = MemoryFile()
    with mem.open(driver="GTiff", width=cols, height=rows, count=1, crs="EPSG:4326", transform=from_origin(west, north, step, step),
                  dtype=values.dtype.name, nodata=nodata) as ds:
        ds.write(values, 1)
    return mem


class TileNames(unittest.TestCase):
    def test_copernicus_tiles_are_one_degree(self):
        names = raster.tile_names("dem", SERBIA)
        self.assertEqual(names[0], "N41_E018")
        self.assertEqual(len(names), 36)  # six rows south to north, six columns west to east
        self.assertEqual(names[:6], ["N41_E018", "N41_E019", "N41_E020", "N41_E021", "N41_E022", "N41_E023"])
        self.assertEqual(names[-6:], ["N46_E018", "N46_E019", "N46_E020", "N46_E021", "N46_E022", "N46_E023"])

    def test_worldcover_tiles_are_three_degrees(self):
        self.assertEqual(
            raster.tile_names("worldcover", SERBIA), ["N39E018", "N39E021", "N42E018", "N42E021", "N45E018", "N45E021"]
        )

    def test_a_box_inside_one_tile(self):
        self.assertEqual(raster.tile_names("dem", (19.5, 44.1, 19.9, 44.3)), ["N44_E019"])
        self.assertEqual(raster.tile_names("worldcover", (19.5, 44.1, 19.9, 44.3)), ["N42E018"])

    def test_the_tiles_of_the_bounding_box_cover_the_whole_lattice(self):
        """The lattice is a little larger than the bounding box; its tiles must still be among the box's."""
        s = lattice.SERBIA
        lattice_box = (s.lon_min, s.lat_min, s.lon_min + s.cols * s.step_deg, s.lat_min + s.rows * s.step_deg)
        for kind in ("dem", "worldcover"):
            with self.subTest(kind=kind):
                self.assertEqual(raster.tile_names(kind, lattice_box), raster.tile_names(kind, srb.BBOX_LONLAT))

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            raster.tile_names("corners", SERBIA)


class LatticeTransform(unittest.TestCase):
    def test_origin_is_the_north_west_corner_of_the_lattice(self):
        self.assertEqual(raster.lattice_transform(Lattice(19.0, 45.96, 0.01, 4, 4)), from_origin(19.0, 46.0, 0.01, 0.01))

    def test_serbia(self):
        s = lattice.SERBIA
        self.assertEqual(raster.lattice_transform(s), from_origin(18.6, 46.4, 1 / 360, 1 / 360))


SMALL = Lattice(19.0, 45.96, 0.01, 4, 4)  # lon 19.0–19.04, lat 45.96–46.0
STEP = 0.001  # ten raster pixels along each lattice cell
COLUMNS = np.tile(np.arange(40, dtype=np.int16), (40, 1))  # a 40 × 40 raster, each pixel holding its column index
ODD = np.tile((np.arange(40) * 4 + 1).astype(np.int16), (40, 1))  # every block of ten columns averages to a whole number


def _average(values, **kwargs):
    return raster.resample(_geotiff(19.0, 46.0, STEP, values), SMALL, resampling=Resampling.average, **kwargs)


class Resample(unittest.TestCase):
    def test_average(self):
        out = _average(COLUMNS, dtype=np.float32, nodata=-1.0)
        self.assertEqual((out.shape, out.dtype), ((4, 4), np.dtype("float32")))
        np.testing.assert_allclose(out, [[4.5, 14.5, 24.5, 34.5]] * 4)

    def test_average_into_int16_metres(self):
        out = _average(ODD, dtype=np.int16, nodata=NODATA)
        self.assertEqual(out.dtype, np.dtype("int16"))
        np.testing.assert_array_equal(out, [[19, 59, 99, 139]] * 4)

    def test_mode_into_uint8_classes(self):
        # in every block of ten columns nine pixels hold 20 + 10·c and one holds 21 + 10·c: the mode is 20 + 10·c
        # (0 is left out on purpose: it is the "no data" class)
        classes = (20 + (np.arange(40) // 10) * 10 + (np.arange(40) % 10 == 9)).astype(np.uint8)
        out = raster.resample(_geotiff(19.0, 46.0, STEP, np.tile(classes, (40, 1))), SMALL,
                              resampling=Resampling.mode, dtype=np.uint8, nodata=lattice.CLASS_NODATA)
        np.testing.assert_array_equal(out, [[20, 30, 40, 50]] * 4)

    def test_cells_no_tile_covers_are_nodata(self):
        east = _geotiff(19.02, 46.0, STEP, ODD[:, 20:])  # lon 19.02–19.04 only
        out = raster.resample(east, SMALL, resampling=Resampling.average, dtype=np.int16, nodata=NODATA)
        np.testing.assert_array_equal(out, [[NODATA, NODATA, 99, 139]] * 4)

    def test_a_second_tile_fills_only_the_cells_it_covers(self):
        whole = _average(COLUMNS, dtype=np.float32, nodata=-1.0)
        west = _geotiff(19.0, 46.0, STEP, np.tile(np.arange(20, dtype=np.int16) + 100, (40, 1)))  # lon 19.0–19.02
        out = raster.resample(west, SMALL, resampling=Resampling.average, dtype=np.float32, nodata=-1.0, dst=whole)
        np.testing.assert_allclose(out, [[104.5, 114.5, 24.5, 34.5]] * 4)

    def test_a_tiles_nodata_never_overwrites_another_tiles_value(self):
        whole = _average(ODD, dtype=np.int16, nodata=NODATA)
        east = np.tile(np.arange(20, dtype=np.int16) * 4 + 1001, (40, 1))  # lon 19.02–19.04; its eastern half is void
        east[:, 10:] = NODATA
        out = raster.resample(_geotiff(19.02, 46.0, STEP, east, nodata=int(NODATA)), SMALL,
                              resampling=Resampling.average, dtype=np.int16, nodata=NODATA, dst=whole)
        np.testing.assert_array_equal(out, [[19, 59, 1019, 139]] * 4)

    def test_a_tiles_voids_are_its_own_nodata_and_come_out_as_the_lattice_nodata(self):
        half_void = np.tile(np.where(np.arange(40) < 20, -9999, ODD[0]).astype(np.int16), (40, 1))
        out = raster.resample(_geotiff(19.0, 46.0, STEP, half_void, nodata=-9999), SMALL,
                              resampling=Resampling.average, dtype=np.int16, nodata=NODATA)
        np.testing.assert_array_equal(out, [[NODATA, NODATA, 99, 139]] * 4)

    def test_neighbouring_tiles_never_write_into_each_others_cells(self):
        """The warp reaches one cell beyond a tile's edge; each cell must keep the value of the tile that holds it."""
        west = _geotiff(19.0, 46.0, STEP, np.tile(np.arange(20, dtype=np.int16) + 100, (40, 1)))
        east = _geotiff(19.02, 46.0, STEP, np.tile(np.arange(20, dtype=np.int16), (40, 1)))
        kw = dict(resampling=Resampling.average, dtype=np.float32, nodata=-1.0)
        first_west = raster.resample(east, SMALL, dst=raster.resample(west, SMALL, **kw), **kw)
        first_east = raster.resample(west, SMALL, dst=raster.resample(east, SMALL, **kw), **kw)
        for out in (first_west, first_east):
            np.testing.assert_allclose(out, [[104.5, 114.5, 4.5, 14.5]] * 4)


if __name__ == "__main__":
    unittest.main()
