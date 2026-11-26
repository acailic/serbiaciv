"""The world builder: the relief, cover and water rules, the tables the site reads, and a build on a tiny synthetic map."""

import contextlib
import io
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

import numpy as np

from pipeline.build import world
from pipeline.core import geo, hexgrid, lattice, srb, srtext, store


class ReliefRule(unittest.TestCase):
    def test_examples(self):
        for mean_m, range_m, expected in ((200, 30, srb.FLAT), (200, 60, srb.HILLS), (1200, 300, srb.MOUNTAINS),
                                          (1350, 400, srb.PEAKS), (100, 0, srb.FLAT)):
            with self.subTest(mean_m=mean_m, range_m=range_m):
                self.assertEqual(world.classify_relief(mean_m, range_m), expected)

    def test_thresholds_are_srb_s_and_the_mean_decides_first(self):
        hills, mountains, peaks = srb.RELIEF_HILLS_RANGE_M, srb.RELIEF_MOUNTAINS_RANGE_M, srb.PEAKS_MEAN_M
        self.assertEqual(world.classify_relief(peaks, 0), srb.PEAKS)
        self.assertEqual(world.classify_relief(peaks - 1, mountains - 1), srb.HILLS)
        self.assertEqual(world.classify_relief(peaks - 1, mountains), srb.MOUNTAINS)
        self.assertEqual(world.classify_relief(100, hills - 1), srb.FLAT)
        self.assertEqual(world.classify_relief(100, hills), srb.HILLS)


class CoverRule(unittest.TestCase):
    def test_cover_shares(self):
        shares = world.cover_shares(Counter({10: 5, 40: 3, 50: 2}))
        self.assertEqual({k: v for k, v in shares.items() if v}, {"forest": 50, "crop": 30, "developed": 20})
        self.assertEqual(sum(shares.values()), 100)

    def test_cover_shares_of_nothing(self):
        shares = world.cover_shares(Counter())
        self.assertTrue(shares)
        self.assertFalse(any(shares.values()))

    def test_cover_shares_are_of_the_samples_with_data(self):
        self.assertEqual(world.cover_shares(Counter({10: 5, 0: 5}))["forest"], 100)

    def test_urban_wins_from_its_threshold_whatever_else_is_there(self):
        self.assertEqual(world.dominant_cover(world.cover_shares(Counter({50: 3, 10: 7})), 100), 9)
        self.assertEqual(world.dominant_cover(world.cover_shares(Counter({50: 29, 10: 71})), 100), 1)

    def test_forest_type_is_a_drawing_choice_by_elevation(self):
        self.assertEqual(world.dominant_cover({"forest": 60, "crop": 40}, 800), 1)
        self.assertEqual(world.dominant_cover({"forest": 60, "crop": 40}, 900), 2)

    def test_the_largest_group_otherwise_and_nothing(self):
        self.assertEqual(world.dominant_cover(world.cover_shares(Counter({60: 4})), 200), 10)
        self.assertEqual(world.dominant_cover(world.cover_shares(Counter({20: 2, 30: 2, 40: 2, 90: 2})), 100), 4)
        self.assertEqual(world.dominant_cover({}, 100), 0)
        self.assertEqual(world.dominant_cover(world.cover_shares(Counter()), 0), 0)


UPSTREAM_COVER_KEYS = [
    "none", "forest_deciduous", "forest_evergreen", "forest_mixed", "scrub", "grassland",
    "pasture", "cropland", "wetland", "urban", "barren", "ice",
]
SERBIAN_LETTER = "[čćšžđČĆŠŽĐ]"  # a rule without one of these is almost certainly not Serbian
COLOR = "^#[0-9a-f]{6}$"


class Tables(unittest.TestCase):
    def test_water_table(self):
        table = world.water_table()
        self.assertEqual([r["id"] for r in table], [srb.LAND, srb.OCEAN, srb.COAST, srb.LAKE])
        self.assertEqual([r["name"] for r in table], ["Kopno", "Okean", "Obala", "Jezero"])

    def test_relief_table(self):
        table = world.relief_table()
        self.assertEqual([r["id"] for r in table], [srb.FLAT, srb.HILLS, srb.MOUNTAINS, srb.PEAKS])
        self.assertEqual([r["name"] for r in table], ["Ravnica", "Brdovit teren", "Planine", "Vrhovi"])  # docs/GLOSSARY.md

    def test_cover_table(self):
        table = world.cover_table()
        self.assertEqual([(r["id"], r["key"]) for r in table], list(enumerate(UPSTREAM_COVER_KEYS)))
        self.assertEqual([r["name"] for r in table][6:11], ["Livade i pašnjaci", "Njive", "Močvare", "Gradsko zemljište", "Golo zemljište"])

    def test_names_and_rules_are_serbian_latin_that_survives_the_cyrillic_pass(self):
        for table in (world.water_table(), world.relief_table(), world.cover_table()):
            for row in table:
                text = row["name"] + " " + row["rule"]
                self.assertRegex(text, SERBIAN_LETTER, row["id"])
                self.assertNotRegex(text, "[\u0400-\u04ff]", row["id"])  # Cyrillic is generated, never written here
                self.assertEqual(srtext.to_latin(srtext.to_cyrillic(text)), text)

    def test_cover_rules_name_the_product_so_it_stays_latin_in_cyrillic(self):
        for row in world.cover_table():
            self.assertIn("ESA WorldCover", srtext.to_cyrillic(row["rule"]), row["id"])

    def test_rules_state_their_numbers(self):
        hills, mountains, peaks = str(srb.RELIEF_HILLS_RANGE_M), str(srb.RELIEF_MOUNTAINS_RANGE_M), f"{srb.PEAKS_MEAN_M:,}".replace(",", ".")
        relief = {r["id"]: r["rule"] for r in world.relief_table()}
        for text in (relief[srb.FLAT], relief[srb.HILLS], relief[srb.MOUNTAINS]):
            self.assertIn(peaks, text)
        for text in (relief[srb.HILLS], relief[srb.MOUNTAINS]):
            self.assertIn(mountains, text)
        for text in (relief[srb.FLAT], relief[srb.HILLS]):
            self.assertIn(hills, text)
        self.assertIn(peaks, relief[srb.PEAKS])

        cover = {r["id"]: r["rule"] for r in world.cover_table()}
        self.assertIn("900", cover[1])
        self.assertIn("900", cover[2])
        self.assertIn("crtački", cover[2])  # WorldCover has one tree-cover class: the forest type is a drawing choice
        self.assertIn(f"{srb.URBAN_MIN_PCT} %", cover[9])
        for cover_id, worldcover in ((1, 10), (2, 10), (4, 20), (6, 30), (7, 40), (8, 90), (9, 50), (10, 60)):
            self.assertIn(f"WorldCover {worldcover})", cover[cover_id])

        water = {r["id"]: r["rule"] for r in world.water_table()}
        self.assertIn(f"{srb.LAKE_MIN_KM2:g} km²", water[srb.LAKE])
        for no_sea in (water[srb.OCEAN], water[srb.COAST]):
            self.assertIn("more", no_sea)  # the table says there is no sea on this map

    def test_colours(self):
        """Every row has a swatch colour, except the two that stand for "nothing": land and no cover."""
        for table, plain in ((world.water_table(), srb.LAND), (world.relief_table(), None), (world.cover_table(), 0)):
            for row in table:
                if row["id"] == plain:
                    self.assertNotIn("color", row)
                else:
                    self.assertRegex(row["color"], COLOR, row["id"])



# --- a tiny synthetic map around Novi Sad ---------------------------------------------------------------------------

def box(west, east, south, north):
    """A closed rectangular ring in lon/lat."""
    return [(west, south), (east, south), (east, north), (west, north), (west, south)]


def bounds(ring):
    """(west, east, south, north) of a ring made by box()."""
    xs, ys = zip(*ring)
    return min(xs), max(xs), min(ys), max(ys)


SOUTH, NORTH = 44.95, 45.55
JUZNOBACKA = box(19.6, 20.2, SOUTH, NORTH)  # RS123: the eastern of two neighbouring squares of 0.6°
ZAPADNOBACKA = box(19.0, 19.6, SOUTH, NORTH)  # RS121: the western one
GAP = 0.04  # "sea" between the okruzi and the neighbouring country, as when two outlines do not meet exactly
COUNTRY_HOLE = box(19.0 - GAP, 20.2 + GAP, SOUTH - GAP, NORTH + GAP)
NODATA = -32768
INSET = 0.045  # degrees, about 3.5 km: every sample point of a hex this far inside its okrug is inside too
RASTER = lattice.Lattice(18.9, 44.85, 0.01, 150, 100)  # 36″ steps over the two squares and 0.1° around them, so that foreign hexes have samples too

# Sombor (80381, RS121) is the whole western square. Apatin (80047, RS121) is a band inside the other okrug's outline,
# as when two sources disagree about a border. Grad Novi Sad (89010, RS123) is the rest of the eastern square, in two
# rings. The western okrug's id sorts before the eastern one's, its name after: okruzi must come out by name.
SOMBOR = box(19.0, 19.6, SOUTH, NORTH)
APATIN = box(19.6, 19.66, SOUTH, NORTH)
NOVI_SAD = [box(19.66, 19.9, SOUTH, NORTH), box(19.9, 20.2, SOUTH, NORTH)]

# Four mountains, one hex each: where to find the hex, the (mean, lowest, highest) elevation of its cells, and the
# relief class that must come out. The fourth lies in the neighbouring country: foreign land is flat whatever its height.
RELIEF_BLOCKS = [
    (19.1, 45.1, (200, 150, 240), srb.HILLS),
    (19.1, 45.235, (200, 50, 380), srb.MOUNTAINS),
    (19.1, 45.37, (1350, 1100, 1600), srb.PEAKS),
    (19.6, 45.665, (1350, 1100, 1600), srb.FLAT),
]
RIVERS = [
    {"name": "Бегеј", "name_lat": "Begej", "length_km": None, "mapped_km": 30, "lines": [[[19.7, 45.5], [19.8, 45.5]]]},
    {"name": "Тиса", "name_lat": "Tisa", "length_km": 100, "mapped_km": 60,
     "lines": [[[19.05, 45.02], [19.6, 45.02], [20.2, 45.02], [26.0, 45.02]]]},  # the last point lies off the map
]
DUNAV = {"name": "Дунав", "name_lat": "Dunav", "length_km": 200, "mapped_km": 100, "lines": [[[19.7, 45.3], [20.1, 45.3]]]}
MORIS = {"name": "Мориш", "name_lat": None, "length_km": None, "mapped_km": 100, "lines": [[[19.7, 45.2], [20.1, 45.2]]]}


def fitted_map(oblasti):
    """Rule 3: Albers over the okruzi's rings gives the projection; the grid covers that map with its margin."""
    albers = geo.Albers()
    xs, ys = zip(*(albers(lon, lat) for oblast in oblasti for ring in oblast["rings"] for lon, lat in ring))
    proj = geo.MapProjection(min(xs), max(ys), srb.MARGIN_KM)
    width, height = max(xs) - min(xs) + 2 * srb.MARGIN_KM, max(ys) - min(ys) + 2 * srb.MARGIN_KM
    return proj, hexgrid.HexGrid.covering(width, height, srb.HEX_RADIUS_KM)


class SyntheticMap(unittest.TestCase):
    """build() on a hand-made map: two okruzi, three opštine, a neighbouring country, lakes, rasters and rivers."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.web = root / "web"
        for patched in (mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", self.web)):
            patched.start()
            self.addCleanup(patched.stop)

        self.okruzi = [{"id": "RS123", "rings": [JUZNOBACKA]}, {"id": "RS121", "rings": [ZAPADNOBACKA]}]
        self.proj, self.grid = fitted_map(self.okruzi)
        self.hole_hex, hole = self.polygon(19.8, 45.25, 0.12, 0.12)
        self.okruzi[0]["rings"].append(hole)  # a hole in the outline that holds every sample point of hole_hex
        self.urban_hex, self.urban_block = self.polygon(20.05, 45.47, 0.1, 0.1)  # class 50 in the north-east corner
        self.lake_hex, big_lake = self.polygon(19.75, 45.4, 0.05, 0.1)  # 0.05° × 0.1° is about 44 km²
        self.small_lake_hex, small_lake = self.polygon(20.0, 45.3, 0.03, 0.05)  # about 13 km²
        self.lakes = [self.lake("Ђердап", "Đerdap", big_lake), self.lake("Палић", "Palić", small_lake)]
        self.relief = [self.polygon(lon, lat, 0.12, 0.12) for lon, lat, _, _ in RELIEF_BLOCKS]  # (hex, its block)
        # block is large enough to hold every raster cell of its hex
        self.forest_hex = self.hex_at(19.72, 45.1)
        self.crop_hex = self.hex_at(20.0, 45.1)
        cols, rows = np.arange(RASTER.cols), np.arange(RASTER.rows)
        self.cell_lon = RASTER.lon_min + (cols + 0.5) * RASTER.step_deg  # where the cells' centres are
        self.cell_lat = RASTER.lat_min + (RASTER.rows - rows - 0.5) * RASTER.step_deg
        self.means, self.lows, self.highs, self.classes = self.rasters()
        self.write_interims(RIVERS)
        self.world, self.interim = self.build()

    # --- the map

    def centre(self, i):
        """lon/lat of a hex's centre."""
        return self.proj.inverse(*self.grid.center(*self.grid.col_row(i)))

    def hex_at(self, lon, lat):
        return self.grid.cell_at(*self.proj(lon, lat))

    def polygon(self, lon, lat, wide, tall):
        """A `wide` × `tall` degree box centred on the hex that holds (lon, lat): (that hex, the box)."""
        cx, cy = self.centre(self.hex_at(lon, lat))
        return self.hex_at(lon, lat), box(cx - wide / 2, cx + wide / 2, cy - tall / 2, cy + tall / 2)

    def hexes_in(self, ring, inset=0.0):
        """Hexes whose centre lies inside a box made by box(), at least `inset` degrees from its edges."""
        west, east, south, north = bounds(ring)
        return [i for i in range(self.grid.size) if west + inset < self.centre(i)[0] < east - inset
                and south + inset < self.centre(i)[1] < north - inset]

    def cells_in(self, i):
        """(col, row) of the raster cells whose centre falls inside hex i and that have data."""
        return [(col, row) for row in range(RASTER.rows) for col in range(RASTER.cols)
                if self.hex_at(*RASTER.centre(col, row)) == i and self.means[row, col] != NODATA]

    def inside(self, ring):
        """Mask of the raster cells whose centre lies inside a ring made by box()."""
        west, east, south, north = bounds(ring)
        return ((west < self.cell_lon) & (self.cell_lon < east))[None, :] & ((south < self.cell_lat) & (self.cell_lat < north))[:, None]

    def in_squares(self, i):
        lon, lat = self.centre(i)
        return 19.0 < lon < 20.2 and SOUTH < lat < NORTH

    def dry_inside(self, square):
        """The land hexes this far inside an okrug that every sample point of theirs is inside it too."""
        return [i for i in self.hexes_in(square, INSET) if self.world["water"][i] != srb.LAKE]

    # --- the interims and the build

    def lake(self, name_sr, name_lat, ring):
        return {"name": name_sr, "name_lat": name_lat, "area_km2": self.area_km2(ring), "rings": [ring]}

    def area_km2(self, ring):
        return geo.Shape([[self.proj(*p) for p in ring]]).area_km2()

    def rasters(self):
        """The elevation rises linearly to the east; forest in the west, cropland in the east, a block of class 50 in
        the north-east corner. Each cell's lowest and highest source elevation lie 8 to 26 m below and 10 to 32 m above
        its mean, by a pattern of their own; the three mountain blocks override both."""
        cols, rows = np.arange(RASTER.cols), np.arange(RASTER.rows)
        means = np.broadcast_to(80 + 5 * cols, RASTER.shape).astype(np.int16)
        lows = (means - 8 - (5 * cols + 11 * rows[:, None]) % 19).astype(np.int16)
        highs = (means + 10 + (7 * cols + 3 * rows[:, None]) % 23).astype(np.int16)
        classes = np.broadcast_to(np.where(self.cell_lon < 19.9, 10, 40), RASTER.shape).astype(np.uint8)
        classes[self.inside(self.urban_block)] = 50
        for (_, ring), (_, _, (mean, low, high), _) in zip(self.relief, RELIEF_BLOCKS):
            for raster, value in zip((means, lows, highs), (mean, low, high)):
                raster[self.inside(ring)] = value
        col, row = RASTER.cell(*self.centre(self.crop_hex))  # samples without data: they must not count
        nodata = np.s_[row - 1:row + 2, col - 1:col + 2]
        for raster in (means, lows, highs):
            raster[nodata] = NODATA
        classes[nodata] = 0
        return means, lows, highs, classes

    def interims(self, rivers, extrema=True, units=()):
        west, east, south, north = bounds(COUNTRY_HOLE)
        dem = {"lat": RASTER.to_dict(), "nodata": NODATA, "elev_b64": lattice.Lattice.encode(self.means)}
        if extrema:
            dem.update(min_b64=lattice.Lattice.encode(self.lows), max_b64=lattice.Lattice.encode(self.highs))
        return {
            "boundaries": {
                "oblasti": [self.okruzi[0]], "regioni": [], "municipalities": [{"id": "89010", "rings": NOVI_SAD}],
                "countries": [{"iso": "HU", "name_sr": "Mađarska",
                               "rings": [box(west - 0.15, east + 0.15, south - 0.15, north + 0.15), COUNTRY_HOLE]}],
            },
            "kim": {"oblasti": [self.okruzi[1]],
                    "municipalities": [{"id": "80381", "rings": [SOMBOR]}, {"id": "80047", "rings": [APATIN]}] + list(units)},
            "dem": dem,
            "landcover": {"lat": RASTER.to_dict(), "nodata": 0, "classes_b64": lattice.Lattice.encode(self.classes)},
            "water": {"rivers": rivers, "lakes": self.lakes},
        }

    def write_interims(self, rivers, **how):
        for name, data in self.interims(rivers, **how).items():
            store.save_interim(name, data)

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            world.build()
        return json.loads((self.web / "world.json").read_text()), store.load_interim("_world")

    # --- what comes out of it

    def test_states_and_counties(self):
        self.assertEqual(self.world["states"], [
            {"fips": "RS123", "abbr": None, "name": "Južnobački okrug"}, {"fips": "RS121", "abbr": None, "name": "Zapadnobački okrug"}])
        self.assertEqual(self.world["counties"], [
            {"geoid": "80047", "name": "Apatin"}, {"geoid": "80381", "name": "Sombor"}, {"geoid": "89010", "name": "Grad Novi Sad"}])
        self.assertEqual(self.interim["states"], ["RS123", "RS121"])
        self.assertEqual(self.interim["counties"], ["80047", "80381", "89010"])
    def test_projection_grid_and_per_cell_arrays(self):
        self.assertEqual(self.world["projection"], {"min_x": self.proj.min_x, "max_y": self.proj.max_y, "margin": srb.MARGIN_KM})
        self.assertEqual(self.interim["projection"], self.world["projection"])
        self.assertEqual(self.world["grid"], self.grid.to_dict())
        self.assertEqual(self.world["margin"], srb.MARGIN_KM)
        n = self.grid.size
        for key in ("owner", "county", "elev", "elev_max", "elev_range", "water", "relief", "cover"):
            self.assertEqual(len(self.world[key]), n, key)
        self.assertEqual(list(self.world["pct"]), ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"])
        self.assertTrue(all(len(values) == n for values in self.world["pct"].values()))
        self.assertEqual(self.world["version"], 2)

    def test_okruzi_own_their_hexes_and_their_municipalities_follow(self):
        owner, county, water = (self.world[k] for k in ("owner", "county", "water"))
        for okrug, opstina, square in ((0, 2, JUZNOBACKA), (1, 1, ZAPADNOBACKA)):
            inside = self.dry_inside(square)
            self.assertGreater(len(inside), 10)
            self.assertEqual({(owner[i], county[i], water[i]) for i in inside}, {(okrug, opstina, srb.LAND)})

    def test_county_stays_inside_the_okrug(self):
        """Apatin's polygon lies inside Južnobačka's outline: a hex there is owned by the latter, so its opština is Grad
        Novi Sad although its centre lies in Apatin."""
        owner, county = self.world["owner"], self.world["county"]
        samples = self.interim["county_samples"]
        straddling = [i for i in range(self.grid.size) if owner[i] == 0 and samples[i][:1] == [0]]
        self.assertTrue(straddling)
        self.assertEqual({county[i] for i in straddling}, {2})

    def test_county_area_km2(self):
        """One area per opština in _world.counties order, from its whole polygon in the equal-area projection."""
        areas = self.interim["county_area_km2"]
        self.assertEqual(len(areas), 3)
        square = self.area_km2(SOMBOR)  # Sombor is exactly a 0.6° × 0.6° square
        self.assertAlmostEqual(areas[1], square, delta=square * 0.01)
        band = self.area_km2(APATIN)
        self.assertAlmostEqual(areas[0], band, delta=band * 0.01)
        two_rings = sum(self.area_km2(ring) for ring in NOVI_SAD)  # both rings of Grad Novi Sad together
        self.assertAlmostEqual(areas[2], two_rings, delta=two_rings * 0.01)

        self.write_interims(RIVERS, units=[{"id": "80055", "rings": []}])  # a unit without a polygon has no area
        _, interim = self.build()
        self.assertEqual([a is None for a in interim["county_area_km2"]], [False, True, False, False])
    def test_lake_hexes_are_water(self):
        owner, water = self.world["owner"], self.world["water"]
        self.assertGreaterEqual(self.lakes[0]["area_km2"], srb.LAKE_MIN_KM2)
        self.assertLess(self.lakes[1]["area_km2"], srb.LAKE_MIN_KM2)
        in_big = self.hexes_in(self.lakes[0]["rings"][0])
        self.assertEqual(in_big, [self.lake_hex])
        self.assertEqual([i for i in range(self.grid.size) if water[i] == srb.LAKE], in_big)
        for i in in_big:
            self.assertEqual((owner[i], self.world["elev"][i], self.world["cover"][i], self.world["county"][i]), (srb.WATER, 0, 0, -1))
        self.assertEqual((owner[self.small_lake_hex], water[self.small_lake_hex]), (0, srb.LAND))  # too small for a water hex

    def test_foreign_land_sea_and_the_sliver_fix(self):
        owner, water = self.world["owner"], self.world["water"]
        east = self.hex_at(20.315, 45.25)  # in the neighbouring country, east of the gap
        self.assertEqual((owner[east], water[east], self.world["county"][east], self.world["cover"][east]), (srb.FOREIGN, srb.LAND, -1, 0))
        self.assertGreater(self.world["elev"][east], 0)  # the raster reaches into the country, and land is sampled wherever it lies
        far = self.grid.index(1, 1)  # no land anywhere near: it stays water
        self.assertEqual((owner[far], water[far]), (srb.WATER, srb.OCEAN))

        # Serbia is landlocked, so "sea" that touches land became land. The owner comes from the land neighbours on
        # the map as it was before the fill, so the fill spreads exactly one ring beyond the country and no further.
        just_outside = self.hex_at(19.6, NORTH + GAP + 0.15 + 0.05)  # the ring of sea north of the country
        self.assertEqual((owner[just_outside], water[just_outside]), (srb.FOREIGN, srb.LAND))
        top_land_row = min(self.grid.col_row(i)[1] for i in range(self.grid.size) if water[i] == srb.LAND)
        col = self.grid.col_row(self.hex_at(19.6, 45.25))[0]
        beyond = self.grid.index(col, top_land_row - 1)
        self.assertEqual((owner[beyond], water[beyond]), (srb.WATER, srb.OCEAN))
        # No "sea" is left between the okruzi and the country, and none of what is left touches Serbia.
        gap_hexes = [i for i in self.hexes_in(COUNTRY_HOLE) if not self.in_squares(i)]
        self.assertTrue(gap_hexes)
        self.assertEqual({water[i] for i in gap_hexes}, {srb.LAND})
        self.assertTrue({owner[i] for i in gap_hexes} <= {0, 1, srb.FOREIGN})
        for i in range(self.grid.size):
            if water[i] not in (srb.LAND, srb.LAKE):
                self.assertFalse(any(owner[j] >= 0 for j in self.grid.neighbours(i)), i)

    def test_a_hole_in_the_okrug_outline_is_still_serbian_land(self):
        """Every sample point of hole_hex falls in the hole, so no okrug owns it by the count. It becomes land with the
        majority owner of its neighbours, and it keeps its opština."""
        owner, county, water = (self.world[k] for k in ("owner", "county", "water"))
        self.assertTrue(all(owner[j] == 0 for j in self.grid.neighbours(self.hole_hex)))
        self.assertEqual((owner[self.hole_hex], water[self.hole_hex], county[self.hole_hex]), (0, srb.LAND, 2))

    def test_elevation_rises_to_the_east(self):
        elev = self.world["elev"]
        inside = self.dry_inside(JUZNOBACKA)
        row = self.grid.col_row(self.forest_hex)[1]
        eastward = sorted((i for i in inside if self.grid.col_row(i)[1] == row), key=lambda i: self.grid.col_row(i)[0])
        self.assertGreaterEqual(len(eastward), 4)
        heights = [elev[i] for i in eastward]
        self.assertTrue(all(a < b for a, b in zip(heights, heights[1:])), heights)
        # the raster rises 500 m per degree of longitude from 77.5 m at its west edge, so a hex's mean is the height at its centre
        for i in inside:
            self.assertAlmostEqual(elev[i], 77.5 + 500 * (self.centre(i)[0] - RASTER.lon_min), delta=3)

    def test_elevation_is_the_mean_and_the_extremes_of_the_cells_inside_the_hex(self):
        elev, elev_max, elev_range = (self.world[k] for k in ("elev", "elev_max", "elev_range"))
        for i in self.dry_inside(JUZNOBACKA)[:5] + [self.crop_hex, self.urban_hex]:
            cells = self.cells_in(i)
            self.assertTrue(cells)
            means = [int(self.means[row, col]) for col, row in cells]
            lows = [int(self.lows[row, col]) for col, row in cells]
            highs = [int(self.highs[row, col]) for col, row in cells]
            self.assertEqual((elev[i], elev_max[i], elev_range[i]), (round(sum(means) / len(means)), max(highs), max(highs) - min(lows)), i)
            self.assertGreater(max(highs), max(means), i)  # the peaks stand above every cell mean ...
            self.assertLess(min(lows), min(means), i)  # ... and the valleys below every cell mean

    def test_relief_follows_the_elevation_of_the_cells(self):
        relief, elev, elev_max, elev_range = (self.world[k] for k in ("relief", "elev", "elev_max", "elev_range"))
        for (i, _), (_, _, (mean, low, high), expected) in zip(self.relief, RELIEF_BLOCKS):
            self.assertEqual((elev[i], elev_max[i], elev_range[i], relief[i]), (mean, high, high - low, expected))
        for i in self.dry_inside(JUZNOBACKA)[:5]:
            self.assertEqual(relief[i], world.classify_relief(elev[i], elev_range[i]), i)
        east = self.hex_at(20.315, 45.25)
        self.assertEqual((relief[self.lake_hex], relief[east]), (srb.FLAT, srb.FLAT))  # water and foreign land are flat

    def test_elevation_of_an_older_interim_falls_back_to_the_means(self):
        self.write_interims(RIVERS, extrema=False)
        self.world, _ = self.build()
        elev_max, elev_range = self.world["elev_max"], self.world["elev_range"]
        for i in self.dry_inside(JUZNOBACKA)[:5]:
            means = [int(self.means[row, col]) for col, row in self.cells_in(i)]
            self.assertEqual((elev_max[i], elev_range[i]), (max(means), max(means) - min(means)), i)

    def test_cover(self):
        cover, pct = self.world["cover"], self.world["pct"]
        self.assertEqual((cover[self.forest_hex], pct["forest"][self.forest_hex]), (1, 100))
        self.assertEqual((cover[self.crop_hex], pct["crop"][self.crop_hex]), (7, 100))  # the samples without data do not count
        self.assertEqual(cover[self.urban_hex], 9)
        hills, _, peaks, _ = (hex_ for hex_, _ in self.relief)
        self.assertEqual((cover[hills], cover[peaks]), (1, 2))  # forest is drawn as deciduous below 900 m, as conifer above
        self.assertGreaterEqual(pct["developed"][self.urban_hex], srb.URBAN_MIN_PCT)
        self.assertFalse(any(pct["grass"][i] for i in range(self.grid.size)))
        for i in (self.lake_hex, self.hex_at(20.315, 45.25)):  # water and foreign land
            self.assertEqual(cover[i], 0)
            self.assertFalse(any(pct[k][i] for k in pct))

    def test_rivers(self):
        rivers = self.world["rivers"]
        self.assertEqual(len(rivers), 1)
        river = rivers[0]
        self.assertEqual((river["name"], river["rank"]), ("Tisa", 1))
        self.assertEqual(river["pts"][:2], [round(v, 1) for v in self.proj(19.05, 45.02)])
        xs, ys = river["pts"][0::2], river["pts"][1::2]
        self.assertEqual(len(xs), 4)  # three points inside the map and the fourth clipped to its east edge
        self.assertTrue(all(0 <= x <= self.world["width"] for x in xs))
        self.assertTrue(all(0 <= y <= self.world["height"] for y in ys))
        self.assertAlmostEqual(xs[-1], self.world["width"], delta=0.1)

    def test_river_ranks(self):
        self.write_interims(RIVERS + [DUNAV, MORIS])
        self.world, _ = self.build()
        # longest first; equal lengths by name; a missing name_lat comes from the Cyrillic name
        self.assertEqual([(r["name"], r["rank"]) for r in self.world["rivers"]], [("Dunav", 1), ("Moriš", 2), ("Tisa", 3)])

    def test_cells_of_county(self):
        county, owner = self.world["county"], self.world["owner"]
        self.assertEqual(self.interim["cells_of_county"], [[i for i, k in enumerate(county) if k == c] for c in range(3)])
        for i, samples in enumerate(self.interim["county_samples"]):
            self.assertEqual(len(samples), 7 if owner[i] >= 0 else 0, i)


if __name__ == "__main__":
    unittest.main()
