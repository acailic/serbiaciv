"""Shared placement for the site layers (resources.json, wonders.json): a published lon/lat → a hex on Serbian land.

The frame is the Serbia map from `world`: every hex has an owner (the index of its okrug, -1 for foreign ground) and a
water code. A site whose point falls on a foreign hex or on water (a dam stands in the river, a border fortress on the
line) moves to the nearest Serbian land hex, preferring the okrug that owns the hex the point fell in. Nothing here
touches files; the two builders own their outputs.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

from ..core import srb
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid

DATA = Path(__file__).resolve().parent.parent / "data"
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
MAX_RINGS = 16


def read_sites(name: str) -> list[dict]:
    """A curated, reviewable CSV in pipeline/data (UTF-8, header row); every cell must be Cyrillic-free."""
    with (DATA / name).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key, value in row.items():
            if value and CYRILLIC.search(value):
                raise ValueError(f"{name}: Cyrillic in {row['id']}.{key}: {value!r} (UI strings are Serbian Latin)")
    return rows


def number(text: str | None) -> float | None:
    """'' → None (no data, never 0); anything else must parse."""
    if text is None or not text.strip():
        return None
    return float(text.replace(",", "."))


class Placer:
    """Projects lon/lat with the map's projection and finds a Serbian land hex for it."""

    def __init__(self, world: dict, cities: list[dict] | None = None):
        self.world = world
        self.grid = HexGrid(**world["grid"])
        self.proj = MapProjection(**world["projection"])
        owner, water = world["owner"], world["water"]
        self.owner = owner
        self.land = [o >= 0 and w == srb.LAND for o, w in zip(owner, water)]
        self.states = world["states"]
        self.counties = world["counties"]
        self.county_of = world["county"]
        self.cbsa_of = {code: str(c["id"]) for c in (cities or []) for code in c.get("counties", [])}

    def project(self, lon: float, lat: float) -> tuple[float, float]:
        return self.proj(lon, lat)

    def cell(self, lon: float, lat: float, avoid: frozenset[int] = frozenset(), okrug: str | None = None) -> int:
        """The land hex for a point: the one it falls in when that is Serbian land (and not in `avoid`), else the
        nearest Serbian land hex, searched ring by ring; within a ring the hex whose centre is closest, preferring
        the okrug that owns the hex the point fell in. With `okrug` (the okrug id the source files the site under)
        the hex must lie in that okrug: a site on a border hex that the raster gives to a neighbour moves to the
        nearest hex of its own okrug."""
        x, y = self.project(lon, lat)
        start = self.grid.cell_at(x, y)
        if start < 0:  # outside the frame: start from the nearest column/row that is inside (same rounding as cell_at)
            cols, rows, r = self.grid.cols, self.grid.rows, self.grid.radius
            col = min(max(math.floor((math.sqrt(3) / 3 * x - y / 3) / r + 0.5), 0), cols - 1)
            row = min(max(math.floor((2 / 3 * y) / r + 0.5), 0), rows - 1)
            start = self.grid.index(col, row)
        wanted = self.states.index(okrug) if okrug in self.states else None
        if self.land[start] and start not in avoid and (wanted is None or self.owner[start] == wanted):
            return start
        same_owner = wanted if wanted is not None else (self.owner[start] if self.owner[start] >= 0 else None)
        seen = {start}
        frontier = [start]

        def dist(c):
            cx, cy = self.grid.center(*self.grid.col_row(c))
            return math.hypot(cx - x, cy - y)

        for _ in range(MAX_RINGS):
            ring = []
            for c in frontier:
                for n in self.grid.neighbours(c):
                    if n not in seen:
                        seen.add(n)
                        ring.append(n)
            free = [c for c in ring if self.land[c] and c not in avoid]
            if wanted is not None:
                free = [c for c in free if self.owner[c] == wanted]
            elif same_owner is not None and any(self.owner[c] == same_owner for c in free):
                free = [c for c in free if self.owner[c] == same_owner]
            if free:
                return min(free, key=dist)
            frontier = ring
            if not frontier:
                break
        raise RuntimeError(f"no Serbian land hex within {MAX_RINGS} rings of lon={lon} lat={lat}")

    def locate(self, cell: int, moved_from: int | None = None) -> dict:
        """Position fields for a hex: map km (one decimal, like cities), the okrug id, the opština code and the city
        whose opštine contain it (`cbsa`, the Serbia stand-in for the upstream metro code)."""
        cx, cy = self.grid.center(*self.grid.col_row(cell))
        o, k = self.owner[cell], self.county_of[cell]
        out = {"x": round(cx, 1), "y": round(cy, 1), "cell": cell, "county": self.counties[k] if k >= 0 else None,
               "cbsa": self.cbsa_of.get(self.counties[k]) if k >= 0 else None,
               "state": self.states[o] if o >= 0 else None}
        if moved_from is not None and moved_from != cell:
            out["moved_to_land"] = True
        return out

    def place(self, lon: float, lat: float, avoid: frozenset[int] = frozenset(), okrug: str | None = None) -> dict:
        x, y = self.project(lon, lat)
        start = self.grid.cell_at(x, y)
        cell = self.cell(lon, lat, avoid, okrug)
        return self.locate(cell, moved_from=start if start != cell else None)


def land_cells(web_dir: Path) -> list[bool] | None:
    """Which hexes of the published map are Serbian land (the Placer's rule), or None when world.json is not there or
    not the map this pipeline writes: the contract checker owns that file's shape, a site layer only reads it."""
    try:
        world = json.loads((Path(web_dir) / "world.json").read_text(encoding="utf-8"))
        land = [o >= 0 and w == srb.LAND for o, w in zip(world["owner"], world["water"])]
        if len(land) == world["grid"]["cols"] * world["grid"]["rows"]:
            return land
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def source_ids(web_dir: Path) -> set[str] | None:
    """The ids in sources.json, or None when the bibliography is not there."""
    try:
        doc = json.loads((Path(web_dir) / "sources.json").read_text(encoding="utf-8"))
        return {s["id"] for s in doc if isinstance(s, dict) and isinstance(s.get("id"), str)}
    except (OSError, ValueError, KeyError, TypeError):
        return None
