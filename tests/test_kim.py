"""Kosovo i Metohija: the committed stitch and seat tables, and the dissolve and the seat check on synthetic polygons."""

import collections
import tempfile
import unittest
from pathlib import Path

from pipeline.core import geo, srb, territory
from pipeline.sources import kim

STITCH_CSV = Path(__file__).parent.parent / "pipeline" / "data" / "kim_stitch.csv"
TOWNS_CSV = Path(__file__).parent.parent / "pipeline" / "data" / "kim_towns.csv"


class StitchTableTest(unittest.TestCase):
    def test_every_polygon_maps_into_a_kosovo_unit(self):
        table = kim.read_stitch(STITCH_CSV)  # {"<shapeName>": ("<unit id>", "<basis>")}
        self.assertEqual(len(table), 38)
        self.assertTrue(all(unit.startswith("9") for unit, _ in table.values()), sorted(table.values()))
        self.assertTrue(all(basis for _, basis in table.values()))

    def test_bad_rows_are_rejected_by_name(self):
        with self.assertRaises(RuntimeError) as ctx:
            kim.read_stitch_text("polygon,unit,basis\nNovo Nebo,70017,isto ime\n")
        self.assertIn("Novo Nebo", str(ctx.exception))
        with self.assertRaises(RuntimeError):
            kim.read_stitch_text("polygon,unit,basis\nNovo Nebo,nema,isto ime\n")

    def test_the_rules_agree_with_the_real_file(self):
        # 3 polygons carry their municipality's name, 25 its Albanian name, 10 needed a rule of their own;
        # together they cover the 29 municipalities of all five okruzi.
        table = kim.read_stitch(STITCH_CSV)
        rules = collections.Counter(basis.split(":")[0] for _, basis in table.values())
        self.assertEqual(rules, {"albanski naziv": 25, "pridružena": 10, "isto ime": 3})
        self.assertEqual(len({unit for unit, _ in table.values()}), 29)
        self.assertEqual(sorted({territory.oblast_of(unit) for unit, _ in table.values()}), srb.KIM_OBLASTI)

    def test_same_name_ignores_the_prefix_and_must_match_the_unit(self):
        table = kim.read_stitch_text("polygon,unit,basis\nMunicipality of Klina,90123,isto ime\n")
        self.assertEqual(table, {"Municipality of Klina": ("90123", "isto ime")})
        with self.assertRaises(RuntimeError) as ctx:
            kim.read_stitch_text("polygon,unit,basis\nMunicipality of Peja,90123,isto ime\n")  # Peja is Peć, not Klina
        self.assertIn("Municipality of Peja", str(ctx.exception))

    def test_a_polygon_twice_or_without_a_basis_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            kim.read_stitch_text("polygon,unit,basis\nMunicipality of Klina,90123,isto ime\nMunicipality of Klina,90123,isto ime\n")
        self.assertIn("Municipality of Klina", str(ctx.exception))
        with self.assertRaises(RuntimeError) as ctx:
            kim.read_stitch_text("polygon,unit,basis\nMunicipality of Klina,90123,\n")
        self.assertIn("Municipality of Klina", str(ctx.exception))

    def test_wrong_header_is_rejected(self):
        with self.assertRaises(RuntimeError):
            kim.read_stitch_text("polygon,unit\nMunicipality of Klina,90123\n")


# --- synthetic geometry: squares in lon/lat around Priština ---------------------------------------------

PROJECT = geo.MapProjection(0, 0, 0)  # the equal-area projection, unshifted: x, y are km


def _ring(lon0, lat0, lon1, lat1):
    """A closed square ring."""
    return [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]


def _polygon(shape_name, *rings):
    """A GeoJSON feature whose polygon has one part per ring, as geoBoundaries writes them."""
    return {"properties": {"shapeName": shape_name}, "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}}


def _lists(rings):
    return [[list(point) for point in ring] for ring in rings]


def _area_km2(*rings):
    """Rings of lon/lat points → km², through the equal-area projection."""
    return geo.Shape([[PROJECT(x, y) for x, y in ring] for ring in rings]).area_km2()


WEST, EAST, NORTH, FAR, ISLE, ROCK = (
    _ring(21.0, 42.0, 21.2, 42.2), _ring(21.2, 42.0, 21.4, 42.2), _ring(21.0, 42.2, 21.2, 42.4),
    _ring(21.5, 42.5, 21.9, 42.9), _ring(20.3, 42.5, 20.5, 42.6), _ring(20.6, 42.5, 20.7, 42.6),
)
# Five polygons: WEST and EAST are one municipality, which shares okrug RS231 with NORTH's; ISLE has two parts.
POLYGONS = [
    _polygon("Municipality of West", WEST), _polygon("Municipality of East", EAST), _polygon("Municipality of North", NORTH),
    _polygon("Municipality of Far", FAR), _polygon("Municipality of Isle", ISLE, ROCK),
]
TABLE = {
    "Municipality of West": ("90001", "x"), "Municipality of East": ("90001", "x"), "Municipality of North": ("90002", "x"),
    "Municipality of Far": ("90003", "x"), "Municipality of Isle": ("90004", "x"),
}
OKRUG_OF = {"90001": "RS231", "90002": "RS231", "90003": "RS232", "90004": "RS233"}.get
MUNICIPALITIES = {"90001": [WEST, EAST], "90003": [FAR]}


class DissolveTest(unittest.TestCase):
    def test_each_okrug_holds_its_municipalities_polygons_together(self):
        out = kim.dissolve(POLYGONS, TABLE, OKRUG_OF)
        self.assertEqual(list(out), ["RS231", "RS232", "RS233"])
        self.assertEqual(_lists(out["RS231"]), [WEST, EAST, NORTH])
        self.assertEqual(_lists(out["RS233"]), [ISLE, ROCK])  # a polygon of two parts stays two rings

    def test_municipalities_hold_their_own_polygons(self):
        out = kim.municipalities(POLYGONS, TABLE)
        self.assertEqual(list(out), ["90001", "90002", "90003", "90004"])
        self.assertEqual(_lists(out["90001"]), [WEST, EAST])
        self.assertEqual(_lists(out["90004"]), [ISLE, ROCK])

    def test_the_measure_is_true_area(self):
        # 0.2° × 0.2° at 42° N is 16.5 km × 22.2 km on the sphere: the projection adds or takes nothing
        self.assertAlmostEqual(_area_km2(WEST), 367.3, delta=1.0)

    def test_area_is_kept(self):
        before = sum(_area_km2(ring) for p in POLYGONS for part in p["geometry"]["coordinates"] for ring in part)
        after = sum(_area_km2(*rings) for rings in kim.dissolve(POLYGONS, TABLE, OKRUG_OF).values())
        self.assertAlmostEqual(after / before, 1.0, delta=0.01)

    def test_a_polygon_the_table_does_not_name_is_rejected_by_name(self):
        stranger = _polygon("Municipality of New", _ring(22.0, 42.0, 22.1, 42.1))
        with self.assertRaises(RuntimeError) as ctx:
            kim.dissolve(POLYGONS + [stranger], TABLE, OKRUG_OF)
        self.assertIn("Municipality of New", str(ctx.exception))
        with self.assertRaises(RuntimeError) as ctx:
            kim.municipalities(POLYGONS + [stranger], TABLE)
        self.assertIn("Municipality of New", str(ctx.exception))


class CheckTownsTest(unittest.TestCase):
    def test_a_seat_inside_its_own_municipality_passes(self):
        seat = {"name": "Zapad", "unit": "90001", "lon": 21.3, "lat": 42.1}  # in EAST, its municipality's second polygon
        self.assertIsNone(kim.check_towns([seat], MUNICIPALITIES))

    def test_a_town_outside_its_own_municipality_is_named(self):
        in_another = {"name": "Zapad", "unit": "90001", "lon": 21.6, "lat": 42.6}  # inside FAR, not inside 90001
        with self.assertRaises(RuntimeError) as ctx:
            kim.check_towns([in_another], MUNICIPALITIES)
        self.assertIn("Zapad", str(ctx.exception))
        nowhere = {"name": "Istočni Zapad", "unit": "90001", "lon": 22.0, "lat": 42.0}
        with self.assertRaises(RuntimeError) as ctx:
            kim.check_towns([nowhere], MUNICIPALITIES)
        self.assertIn("Istočni Zapad", str(ctx.exception))

    def test_a_seat_whose_municipality_has_no_rings_is_named(self):
        orphan = {"name": "Zapad", "unit": "90999", "lon": 21.3, "lat": 42.1}
        with self.assertRaises(RuntimeError) as ctx:
            kim.check_towns([orphan], MUNICIPALITIES)
        self.assertIn("Zapad", str(ctx.exception))


class TownsTableTest(unittest.TestCase):
    def test_every_municipality_has_exactly_one_seat(self):
        towns = kim.read_towns(TOWNS_CSV)
        kosovo = sorted(unit for okrug in srb.KIM_OBLASTI for unit in territory.children(okrug))
        self.assertEqual(sorted(t["unit"] for t in towns), kosovo)
        self.assertTrue(all(0 < t["lon"] < 180 and 0 < t["lat"] < 90 for t in towns))
        # 28 seats share their municipality's name; Gora's is the town of Dragaš
        self.assertEqual([t["name"] for t in towns if t["name"] != territory.name(t["unit"])], ["Dragaš"])

    def test_a_seat_of_no_municipality_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "towns.csv"
            path.write_text("name,osm_name,lon,lat\nNovo Nebo,Novo Nebo,21.1,42.1\n", encoding="utf-8")
            with self.assertRaises(RuntimeError) as ctx:
                kim.read_towns(path)
        self.assertIn("Novo Nebo", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
