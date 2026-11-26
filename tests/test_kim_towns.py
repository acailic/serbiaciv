"""Kosovo's towns on a hand-made world: where each municipal seat stands and which hex it gets.

Nothing is written outside a temporary store: the tests patch store.INTERIM and store.WEB_DATA.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.build import kim_towns
from pipeline.core import geo, srb, store
from pipeline.core.hexgrid import HexGrid

COLS, ROWS = 36, 4
LAKE = (30, 0)
KIM_VINTAGE = "geoBoundaries XKX ADM2 (OpenStreetMap, januar 2023); podela Republičkog zavoda za statistiku"


def make_world():
    """The _world interim of a grid whose first three rows are one Kosovo okrug's land, bar a lake hex; the last row
    is foreign ground."""
    grid = HexGrid(srb.HEX_RADIUS_KM, COLS, ROWS)
    proj = geo.MapProjection(min_x=0.0, max_y=0.0, margin=200.0)
    owner, county, water = [], [], []
    for row in range(ROWS):
        for col in range(COLS):
            foreign = row == ROWS - 1
            owner.append(srb.FOREIGN if foreign else 0)
            county.append(-1 if foreign else 0)
            water.append(srb.LAKE if (col, row) == LAKE else srb.LAND)
    world = {
        "grid": grid.to_dict(), "projection": proj.to_dict(), "owner": owner, "county": county, "water": water,
        "states": ["RS231"], "counties": ["90263"],
        "cells_of_county": [[c for c, k in enumerate(county) if k == i] for i in range(1)],
    }
    return world, grid, proj


def make_towns(grid, proj):
    """29 seats: 27 along the first row, one in the hex of another (Zvečan lies in Kosovska Mitrovica's hex) and one
    on the lake."""
    def seat(name, col, row, dx=0.0, dy=0.0):
        x, y = grid.center(col, row)
        return {"name": name, "lon": proj.inverse(x + dx, y + dy)[0], "lat": proj.inverse(x + dx, y + dy)[1]}

    return [seat(f"Town {col:02d}", col, 0) for col in range(27)] + [seat("Zvečan", 10, 0, 2, 3), seat("On the lake", 30, 0, 3)]


class KimTownsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for patched in (mock.patch.object(store, "INTERIM", root / "interim"), mock.patch.object(store, "WEB_DATA", root / "web")):
            patched.start()
            self.addCleanup(patched.stop)
        self.world, self.grid, self.proj = make_world()
        self.kim = {"oblasti": [], "municipalities": [], "stitch": [], "area_km2": 10888.0, "towns": make_towns(self.grid, self.proj)}

    def build(self):
        """Write the interims, run the builder, and return (kim_towns.json, what it printed)."""
        store.save_interim("kim", self.kim, vintage=KIM_VINTAGE)
        store.save_interim("_world", self.world)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            kim_towns.build()
        return json.loads((store.WEB_DATA / "kim_towns.json").read_text(encoding="utf-8")), printed.getvalue()

    def test_requires_and_produces(self):
        self.assertEqual(kim_towns.REQUIRES, ["kim", "_world"])
        self.assertEqual(kim_towns.PRODUCES, ["kim_towns.json"])

    def test_the_file_names_its_version_vintage_and_source(self):
        out, _ = self.build()
        self.assertEqual(list(out), ["version", "vintage", "sources", "towns"])
        self.assertEqual((out["version"], out["vintage"], out["sources"]), (1, KIM_VINTAGE, ["kim"]))

    def test_every_town_stands_on_its_own_serbian_land_hex(self):
        towns, _ = self.build()
        out = towns["towns"]
        self.assertEqual(len(out), 29)
        self.assertEqual([t["name"] for t in out], [t["name"] for t in self.kim["towns"]])
        for t, col in zip(out[:27], range(27)):
            self.assertEqual(list(t), ["name", "x", "y", "cell"])
            self.assertEqual((t["x"], t["y"], t["cell"]),
                             (*[round(v, 1) for v in self.grid.center(col, 0)], self.grid.index(col, 0)))
        cells = [t["cell"] for t in out]
        self.assertEqual(len(cells), len(set(cells)))
        for t in out:
            self.assertGreaterEqual(self.world["owner"][t["cell"]], 0, t["name"])
            self.assertEqual(self.world["water"][t["cell"]], srb.LAND, t["name"])

    def test_a_seat_on_water_takes_the_nearest_land_hex_and_a_shared_hex_is_traded(self):
        out, _ = self.build()
        zvečan, on_the_lake = out["towns"][27], out["towns"][28]
        self.assertEqual(zvečan["cell"], self.grid.index(10, 1))  # its own hex is Town 10's
        self.assertEqual(on_the_lake["cell"], self.grid.index(31, 0))  # east of the lake, nearer than the west

    def test_x_and_y_are_the_seat_projected(self):
        """The hex may move; the marker stays where the seat is."""
        out, _ = self.build()
        for t, seat in zip(out["towns"], self.kim["towns"]):
            x, y = self.proj(seat["lon"], seat["lat"])
            self.assertEqual((t["x"], t["y"]), (round(x, 1), round(y, 1)), t["name"])


if __name__ == "__main__":
    unittest.main()
