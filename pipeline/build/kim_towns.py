"""Kosovo's towns: the seat of each of the 29 municipalities, with the hex its marker sits on.

The hexes are Serbia's on the map (owned by an okrug, not water), Kosovo's okruzi included. A seat that stands on
water, or in a hex another seat already has (Zvečan lies in Kosovska Mitrovica's hex), takes the nearest free one;
the marker itself stays where the seat is.
"""

from __future__ import annotations

from ..core import store
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from .cities import claim_cell, serbian_land

REQUIRES = ["kim", "_world"]
PRODUCES = ["kim_towns.json"]


def build() -> None:
    kim = store.load_interim_payload("kim")
    world = store.load_interim("_world")
    grid, proj = HexGrid(**world["grid"]), MapProjection(**world["projection"])
    land = [c for c, is_land in enumerate(serbian_land(world)) if is_land]
    towns, taken = [], set()
    for seat in kim["data"]["towns"]:
        x, y = proj(seat["lon"], seat["lat"])
        cell = claim_cell(grid, land, x, y, taken)
        towns.append({"name": seat["name"], "x": round(x, 1), "y": round(y, 1), "cell": cell})
        taken.add(cell)
    print(f"    {len(towns)} towns")
    store.write_web("kim_towns.json", {"version": 1, "vintage": kim["vintage"], "sources": ["kim"], "towns": towns})
