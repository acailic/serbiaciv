import unittest

from pipeline.core import geom, geo, srb


class SrbConstants(unittest.TestCase):
    def test_values_fixed_by_the_design_spec(self):
        self.assertEqual(srb.HEX_RADIUS_KM, 5.0)
        self.assertEqual(srb.MARGIN_KM, 200.0)
        self.assertEqual(srb.ALBERS, {"lat1": 42.5, "lat2": 45.5, "lat0": 44.0, "lon0": 21.0})
        self.assertEqual(srb.BBOX_LONLAT, (18.8, 41.8, 23.2, 46.2))
        self.assertEqual((srb.RELIEF_HILLS_RANGE_M, srb.RELIEF_MOUNTAINS_RANGE_M, srb.PEAKS_MEAN_M), (60, 300, 1300))
        self.assertEqual(srb.LAKE_MIN_KM2, 40.0)
        self.assertEqual(srb.RIVER_MIN_LENGTH_KM, 50)
        self.assertEqual((srb.CITY_MIN_URBAN_POP, srb.CITY_MIN_POP, srb.HOME_BANNERS), (10000, 25000, 25))
        self.assertEqual(srb.KIM_REGION, "RS23")
        self.assertEqual(len(srb.KIM_OBLASTI), 5)

    def test_albers_defaults_match(self):
        a, b = geo.Albers(), geo.Albers(**srb.ALBERS)
        self.assertEqual(a(20.4606, 44.8125), b(20.4606, 44.8125))

    def test_projection_round_trips(self):
        proj = geo.MapProjection(-180.0, 250.0, srb.MARGIN_KM)
        lon, lat = 20.4606, 44.8125  # Novi Sad
        x, y = proj(lon, lat)
        self.assertAlmostEqual(proj.inverse(x, y)[0], lon, places=5)
        self.assertAlmostEqual(proj.inverse(x, y)[1], lat, places=5)

    def test_industries(self):
        self.assertEqual(len(srb.INDUSTRY_KEYS), 19)
        self.assertEqual(len(set(srb.INDUSTRY_KEYS)), 19)
        self.assertEqual(srb.INDUSTRY_KEYS[0], "agriculture")
        self.assertEqual(srb.NACE_TO_KEY["C"], "manufacturing")
        self.assertEqual(srb.NACE_TO_KEY["S"], "other")
        self.assertTrue(all(srb.INDUSTRY_NAMES[k] for k in srb.INDUSTRY_KEYS))

    def test_yields(self):
        self.assertEqual(srb.YIELD_KEYS, ["food", "production", "gold", "science", "culture"])
        for y in srb.YIELDS:
            self.assertTrue(set(y["industries"]) <= set(srb.INDUSTRY_KEYS), y["key"])
            self.assertEqual(y["unit"], "eur" if y["key"] == "gold" else "zaposleni")
            self.assertTrue(y["label"] and y["description"] and y["color"].startswith("#"))

    def test_rzs_dataset_ids_are_numeric(self):
        self.assertTrue(all(v.isdigit() for v in srb.RZS_DATASETS.values()))
        self.assertEqual(srb.RZS_DATASETS["employment_nace"], "240205")

    def test_county_columns_and_formats_are_pairs(self):
        """The checker zips the two: a column without a format must never shorten its loop."""
        self.assertEqual(len(srb.COUNTY_COLUMNS), len(srb.COUNTY_COLUMN_FORMATS))


class Shape(unittest.TestCase):
    def test_area_with_a_hole(self):
        outer = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole = [(4, 4), (4, 6), (6, 6), (6, 4), (4, 4)]  # opposite winding to the outer ring
        self.assertAlmostEqual(geo.Shape([outer]).area_km2(), 100.0)
        self.assertAlmostEqual(geo.Shape([outer, hole]).area_km2(), 96.0)

    def test_contains_and_index(self):
        shapes = [geo.Shape([[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]), geo.Shape([[(20, 20), (30, 20), (30, 30), (20, 30), (20, 20)]])]
        idx = geo.ShapeIndex(shapes, cell_km=5)
        self.assertEqual(idx.locate(5, 5), 0)
        self.assertEqual(idx.locate(25, 25), 1)
        self.assertEqual(idx.locate(15, 15), -1)


class Lines(unittest.TestCase):
    def test_clip_polyline(self):
        pieces = geom.clip_polyline([(-5, 5), (5, 5), (5, 15), (-5, 15)], 10, 10)
        self.assertEqual(pieces, [[(0.0, 5), (5, 5), (5, 10)]])

    def test_land_runs(self):
        runs = geom.land_runs([(0, 0), (10, 0)], lambda p: p[0] < 3 or p[0] > 7, step=1)
        self.assertEqual(len(runs), 2)
        self.assertEqual((runs[0][0], runs[0][-1]), ((0, 0), (2, 0)))
        self.assertEqual((runs[1][0], runs[1][-1]), ((8, 0), (10, 0)))

    def test_join_lines(self):
        joined = geom.join_lines([[(0, 0), (1, 0)], [(2, 0), (1, 0)]], tol=0.5)
        self.assertEqual(joined, [[(0, 0), (1, 0), (2, 0)]])

    def test_hex_lattice_stays_inside_the_hex(self):
        pts = geom.hex_lattice(5.0, 1.0)
        self.assertGreater(len(pts), 50)
        for x, y in pts:
            self.assertLessEqual(abs(y), 5.0 - abs(x) / 1.7320508 + 1e-9)

    def test_majority(self):
        self.assertEqual(geom.majority([1, 1, 2], 2), 1)
        self.assertEqual(geom.majority([1, 2], 2), 2)  # a tie goes to the centre when it is among the tied
        self.assertEqual(geom.majority([1, 2], 3), 1)  # else to the first seen


if __name__ == "__main__":
    unittest.main()
