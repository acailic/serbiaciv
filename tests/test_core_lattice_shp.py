import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import shapefile

from pipeline.core import lattice, shp
from pipeline.core.lattice import Lattice


class SerbiaLattice(unittest.TestCase):
    def test_dimensions(self):
        s = lattice.SERBIA
        self.assertEqual((s.cols, s.rows), (1728, 1728))
        self.assertAlmostEqual(s.step_deg, 1 / 360)
        self.assertAlmostEqual(s.lon_min + s.cols * s.step_deg, lattice.LON_MAX)
        self.assertAlmostEqual(s.lat_min + s.rows * s.step_deg, lattice.LAT_MAX)

    def test_row_zero_is_north(self):
        s = lattice.SERBIA
        lon, lat = s.centre(0, 0)
        self.assertAlmostEqual(lat, lattice.LAT_MAX - s.step_deg / 2)
        self.assertAlmostEqual(lon, lattice.LON_MIN + s.step_deg / 2)
        self.assertEqual(s.cell(lon, lat), (0, 0))

    def test_a_known_place_lands_in_the_right_cell(self):
        s = lattice.SERBIA
        col, row = s.cell(20.4606, 44.8125)  # Belgrade
        self.assertEqual(s.cell(*s.centre(col, row)), (col, row))
        self.assertLess(row, s.rows * 0.6)  # the north half

    def test_outside_is_none(self):
        self.assertIsNone(lattice.SERBIA.cell(10.0, 44.0))
        self.assertIsNone(lattice.SERBIA.cell(21.0, 50.0))

    def test_round_trip_int16_and_uint8(self):
        small = Lattice(19.0, 45.0, 0.1, 4, 3)
        elev = np.array([[1, -5, 32767, lattice.ELEV_NODATA], [0, 0, 0, 0], [12, 34, 56, 78]], dtype=np.int16)
        back = small.decode(small.encode(elev), np.int16, small.shape)
        self.assertEqual(back.dtype, elev.dtype)
        np.testing.assert_array_equal(back, elev)
        cls = np.array([[10, 20, 0, 50], [0, 0, 0, 0], [255, 1, 2, 3]], dtype=np.uint8)
        np.testing.assert_array_equal(small.decode(small.encode(cls), np.uint8, small.shape), cls)

    def test_decode_rejects_wrong_size(self):
        small = Lattice(19.0, 45.0, 0.1, 4, 3)
        with self.assertRaises(ValueError):
            small.decode(small.encode(np.zeros((4, 4), dtype=np.int16)), np.int16, small.shape)

    def test_value(self):
        small = Lattice(19.0, 45.0, 0.1, 4, 3)
        arr = np.arange(12, dtype=np.int16).reshape(3, 4)
        self.assertEqual(int(small.value(arr, 19.05, 45.25, -1)), int(arr[0, 0]))  # north-west
        self.assertEqual(int(small.value(arr, 19.35, 45.05, -1)), int(arr[2, 3]))  # south-east
        self.assertEqual(small.value(arr, 30.0, 45.0, -1), -1)

    def test_dict_round_trip(self):
        self.assertEqual(Lattice.from_dict(lattice.SERBIA.to_dict()), lattice.SERBIA)


def _write(shape_type: int, rows: list) -> dict[str, bytes]:
    """One in-memory shapefile per call: rows are (geometry, properties, [field value])."""
    bufs = {ext: io.BytesIO() for ext in shp.MEMBERS}
    w = shapefile.Writer(shp=bufs[".shp"], shx=bufs[".shx"], dbf=bufs[".dbf"], shapeType=shape_type)
    w.field("name", "C")
    w.field("n", "N")
    for geometry, name, n in rows:
        if shape_type == shapefile.POLYGON:
            w.poly(geometry)  # a list of rings: one shapefile record, however many rings
        else:
            w.line(geometry)
        w.record(name, n)
    w.close()
    return {ext: bufs[ext].getvalue() for ext in shp.MEMBERS}


def _f(rings):  # pyshp writes floats only
    return [[(float(x), float(y)) for x, y in ring] for ring in rings]


SQUARE_WITH_HOLE = _f([[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], [(4, 4), (4, 6), (6, 6), (6, 4), (4, 4)]])
TRIANGLE = _f([[(20, 20), (30, 20), (30, 30)]])
RIVER = _f([[(0, 0), (5, 5), (9, 1)]])


class ShapefileReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.poly = _write(shapefile.POLYGON, [(SQUARE_WITH_HOLE, "Šumadija", 7), (TRIANGLE, "Mačva", 1)])
        self.line = _write(shapefile.POLYLINE, [(RIVER, "Reka", 0)])

    def tearDown(self):
        self.tmp.cleanup()

    def _loose(self, files: dict) -> Path:
        for ext, data in files.items():
            (self.dir / f"x{ext}").write_bytes(data)
        return self.dir / "x.shp"

    def _zip(self, layout: dict[str, bytes]) -> Path:
        path = self.dir / "data.zip"
        with zipfile.ZipFile(path, "w") as zf:
            for name, data in layout.items():
                zf.writestr(name, data)
        return path

    def test_loose_polygon_rings_and_properties(self):
        recs = list(shp.records(shp.open_shapefile(self._loose(self.poly))))
        self.assertEqual([p for p, _ in recs], [{"name": "Šumadija", "n": 7}, {"name": "Mačva", "n": 1}])
        props, rings = recs[0]
        self.assertEqual(len(rings), 2)
        self.assertEqual(rings[1][0], (4.0, 4.0))

    def test_to_shape_respects_holes(self):
        reader = shp.open_shapefile(self._loose(self.poly))
        shape = shp.to_shape(next(iter(reader.shapes())))
        self.assertTrue(shape.contains(1, 1))
        self.assertFalse(shape.contains(5, 5))
        self.assertAlmostEqual(shape.area_km2(), 96.0)

    def test_lines(self):
        (props, lines), = shp.records(shp.open_shapefile(self._loose(self.line)))
        self.assertEqual(props["name"], "Reka")
        self.assertEqual(lines, [[(0.0, 0.0), (5.0, 5.0), (9.0, 1.0)]])

    def test_flat_zip(self):
        path = self._zip({f"gis{ext}": self.poly[ext] for ext in shp.MEMBERS} | {f"wat{ext}": self.line[ext] for ext in shp.MEMBERS})
        self.assertEqual(shp.shapefile_bases(path), ["gis", "wat"])
        self.assertEqual(list(shp.records(shp.open_shapefile(path, "gis")))[1][0]["name"], "Mačva")  # the member named
        self.assertEqual(list(shp.records(shp.open_shapefile(path)))[0][0]["name"], "Šumadija")  # the first one

    def test_nested_zip_as_eurostat_ships_them(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zf:
            for ext in shp.MEMBERS:
                zf.writestr("LAU_RG_01M_2024_4326" + ext, self.poly[ext])
        path = self._zip({"LAU_RG_01M_2024_4326.shp.zip": inner.getvalue(), "release-notes.txt": b"hi"})
        self.assertEqual(shp.shapefile_bases(path), ["LAU_RG_01M_2024_4326.shp.zip/LAU_RG_01M_2024_4326"])
        self.assertEqual(len(list(shp.records(shp.open_shapefile(path)))), 2)

    def test_missing_member(self):
        path = self._zip({f"gis{ext}": self.poly[ext] for ext in shp.MEMBERS})
        with self.assertRaises(FileNotFoundError):
            shp.open_shapefile(path, "nope")
        with self.assertRaises(FileNotFoundError):
            shp.open_shapefile(self._zip({"readme.txt": b"x"}))


if __name__ == "__main__":
    unittest.main()
