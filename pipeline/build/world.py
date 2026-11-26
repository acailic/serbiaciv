"""The map itself: hex grid, land and water, relief, land cover, okruzi, opštine and rivers.

Also saves interim "_world" (grid + projection + per-cell okrug/opština/water/cover) so the other builders can drop
their data onto the same hexes.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np

from ..core import lattice, terrain, territory
from ..core.geo import Albers, MapProjection, Shape, ShapeIndex
from ..core.geom import clip_polyline, join_lines, majority, simplify
from ..core.hexgrid import HexGrid
from ..core.srb import (
    COAST, FLAT, FOREIGN, HEX_RADIUS_KM, HILLS, LAKE, LAKE_MIN_KM2, LAND, MARGIN_KM, MOUNTAINS, OCEAN, PEAKS, PEAKS_MEAN_M,
    RELIEF_HILLS_RANGE_M, RELIEF_MOUNTAINS_RANGE_M, RIVER_MIN_LENGTH_KM, URBAN_MIN_PCT, WATER,
)
from ..core.srtext import okrug_name, to_latin
from ..core.store import load_interim, save_interim, write_web

REQUIRES = ["boundaries", "kim", "dem", "landcover", "water"]
PRODUCES = ["_world", "world.json"]

# --- numbers only this builder uses --------------------------------------------------------------------------------

SAMPLE_SHARE = 0.6  # the six outer sample points of a hex lie this share of the way from its centre to its corners
FOREST_CONIFER_MIN_M = 900  # from this mean elevation a forest hex is drawn as conifer
RIVER_PIECE_MIN_KM = 1.0  # clipped river pieces shorter than this are dropped
RIVER_SIMPLIFY_KM = 0.8  # a river point closer than this to the previous kept point is dropped

# --- rules ---------------------------------------------------------------------------------------------------------

def classify_relief(mean_m: float, range_m: float) -> int:
    """Relief class of a hex from its mean elevation and its elevation range (highest − lowest sample), in metres."""
    if mean_m >= PEAKS_MEAN_M:
        return PEAKS
    if range_m >= RELIEF_MOUNTAINS_RANGE_M:
        return MOUNTAINS
    if range_m >= RELIEF_HILLS_RANGE_M:
        return HILLS
    return FLAT


# ESA WorldCover classes behind each cover group. "grass" has none: WorldCover's grassland (30) is pasture here.
COVER_CLASSES = {
    "forest": (10,), "crop": (40,), "pasture": (30,), "shrub": (20,), "wetland": (90,), "developed": (50,), "barren": (60,),
}
PCT_KEYS = ("forest", "crop", "pasture", "grass", "shrub", "wetland", "developed")  # world.json "pct", in upstream's order
# The groups that compete for the dominant cover, with the cover id each one gives. The order breaks ties.
COVER_ID = {"forest": 1, "shrub": 4, "pasture": 6, "crop": 7, "wetland": 8, "barren": 10}
FOREST_EVERGREEN_ID = 2
URBAN_ID = 9


def cover_shares(class_counts: Counter) -> dict[str, int]:
    """Whole-percent share of each cover group among the hex's samples with data (a WorldCover class other than 0)."""
    shares = dict.fromkeys((*PCT_KEYS, "barren"), 0)
    valid = sum(n for cls, n in class_counts.items() if cls)
    if valid:
        for group, classes in COVER_CLASSES.items():
            shares[group] = round(100 * sum(class_counts.get(cls, 0) for cls in classes) / valid)
    return shares


def dominant_cover(shares: dict[str, int], mean_m: float) -> int:
    """Cover id of a hex from its cover shares and mean elevation (metres); 0 when no group has a share."""
    if shares.get("developed", 0) >= URBAN_MIN_PCT:
        return URBAN_ID
    best = max(COVER_ID, key=lambda group: shares.get(group, 0))  # the largest group; COVER_ID's order breaks ties
    if not shares.get(best):
        return 0
    if best == "forest" and mean_m >= FOREST_CONIFER_MIN_M:
        return FOREST_EVERGREEN_ID
    return COVER_ID[best]


# --- tables (written to world.json so the frontend and the Almanac read one definition) ----------------

def _number(value: float) -> str:
    """`1300` → "1.300" and `40.0` → "40": the glossary's number style, with the dot as thousands separator."""
    return f"{value:,.0f}".replace(",", ".")


def water_table() -> list[dict]:
    """Upstream's four water ids. Serbia is landlocked: Ocean and Coast stay reserved and say so."""
    return [
        {
            "id": LAND, "name": "Kopno",
            "rule": "Najmanje 4 od 7 tačaka uzorkovanja (središte heksa i šest na 60 % poluprečnika) nalazi se u okrugu "
                    "ili u susednoj državi. O okrugu ili tuđem zemljištu odlučuje većina tih tačaka, a kod izjednačenja "
                    "središnja tačka.",
        },
        {
            "id": OCEAN, "name": "Okean", "color": "#1b4266",
            "rule": "Srbija nema more: heks koji nije jezero, a ima bar jednog suseda kopna, postaje kopno i dobija "
                    "vlasnika većine svojih suseda kopna. Okean ostaju samo heksovi bez ijednog suseda kopna, daleko od "
                    "svih granica.",
        },
        {
            "id": COAST, "name": "Obala", "color": "#2d6d97",
            "rule": "Srbija nema more, pa na ovoj karti nema ni obale: klasa je rezervisana za crtež i ne pojavljuje se.",
        },
        {
            "id": LAKE, "name": "Jezero", "color": "#3a80b0",
            "rule": f"Središte heksa leži u jezeru ili akumulaciji od najmanje {LAKE_MIN_KM2:g} km². Manja jezera ne daju "
                    "heksove vode.",
        },
    ]


def relief_table() -> list[dict]:
    """Upstream's four relief ids, now read from the elevation range inside the hex instead of a standard deviation."""
    hills, mountains, peaks = (str(RELIEF_HILLS_RANGE_M), str(RELIEF_MOUNTAINS_RANGE_M), _number(PEAKS_MEAN_M))
    spread = "Razlika između najviše i najniže tačke u heksu"
    return [
        {
            "id": FLAT, "name": "Ravnica", "color": "#8fb04e",
            "rule": f"{spread} manja je od {hills} m, a srednja visina ispod {peaks} m. Strana zemljišta i heksovi vode "
                    "uvek su ravnica.",
        },
        {
            "id": HILLS, "name": "Brdovit teren", "color": "#b3a25f",
            "rule": f"{spread} je {hills} m ili više, a manja od {mountains} m; srednja visina je ispod {peaks} m.",
        },
        {
            "id": MOUNTAINS, "name": "Planine", "color": "#9a7f60",
            "rule": f"{spread} je {mountains} m ili više, a srednja visina je ispod {peaks} m.",
        },
        {
            "id": PEAKS, "name": "Vrhovi", "color": "#e3e7ea",
            "rule": f"Srednja visina heksa je {peaks} m ili više, bez obzira na razliku visina.",
        },
    ]


def cover_table() -> list[dict]:
    """Upstream's twelve cover ids and keys. The Serbian names follow docs/GLOSSARY.md.

    "ESA WorldCover" is spelled out because the product name stays Latin in the generated Cyrillic (srtext.PROTECTED).
    """
    wc = "ESA WorldCover"
    return [
        {"id": 0, "key": "none", "name": "Nema podataka",
         "rule": f"Voda, strana zemljišta ili heks u kome {wc} nema nijedan uzorak sa podacima."},
        {"id": 1, "key": "forest_deciduous", "name": "Listopadna šuma", "color": "#4f7a35",
         "rule": f"Šuma ({wc} 10) najveća je grupa u heksu, a srednja visina heksa je ispod {FOREST_CONIFER_MIN_M} m."},
        {"id": 2, "key": "forest_evergreen", "name": "Četinarska šuma", "color": "#2f5a3a",
         "rule": f"Šuma ({wc} 10) najveća je grupa u heksu, a srednja visina heksa je {FOREST_CONIFER_MIN_M} m ili više. "
                 f"{wc} ima samo jednu klasu šume, pa se listopadna i četinarska šuma po podacima ne razlikuju: podela po "
                 "visini je crtački izbor."},
        {"id": 3, "key": "forest_mixed", "name": "Mešovita šuma", "color": "#43703f",
         "rule": f"Na ovoj karti se ne pojavljuje: {wc} ima samo jednu klasu šume (10), pa se mešovita šuma ne razlikuje."},
        {"id": 4, "key": "scrub", "name": "Žbunje", "color": "#c9b07a",
         "rule": f"Žbunje ({wc} 20) najveća je grupa u heksu."},
        {"id": 5, "key": "grassland", "name": "Travnjaci", "color": "#a9b35a",
         "rule": f"Na ovoj karti se ne pojavljuje: travnjaci ({wc} 30) broje se kao livade i pašnjaci."},
        {"id": 6, "key": "pasture", "name": "Livade i pašnjaci", "color": "#8fb04e",
         "rule": f"Livade i pašnjaci, odnosno travnjaci ({wc} 30), najveća su grupa u heksu."},
        {"id": 7, "key": "cropland", "name": "Njive", "color": "#c2b84e",
         "rule": f"Njive, odnosno obradivo zemljište ({wc} 40), najveća su grupa u heksu."},
        {"id": 8, "key": "wetland", "name": "Močvare", "color": "#4f8a6e",
         "rule": f"Močvare ({wc} 90) najveća su grupa u heksu."},
        {"id": 9, "key": "urban", "name": "Gradsko zemljište", "color": "#8a8378",
         "rule": f"Izgrađeno zemljište ({wc} 50) zauzima najmanje {URBAN_MIN_PCT} % heksa, bez obzira na ostatak."},
        {"id": 10, "key": "barren", "name": "Golo zemljište", "color": "#bfae95",
         "rule": f"Golo ili retko obraslo zemljište ({wc} 60) najveća je grupa u heksu."},
        {"id": 11, "key": "ice", "name": "Led i sneg", "color": "#e8eef2",
         "rule": f"Na ovoj karti se ne pojavljuje: led i sneg ({wc} 70) ne učestvuju u izboru pokrova."},
    ]


# --- the build -----------------------------------------------------------------------------------------------------

def _hexes_of_lattice_cells(lat: lattice.Lattice, grid: HexGrid, proj: MapProjection) -> list[int]:
    """The hex each cell of a lattice falls in by its centre (row-major from the north); -1 where it falls off the grid."""
    return [grid.cell_at(*proj(*lat.centre(col, row))) for row in range(lat.rows) for col in range(lat.cols)]


def build() -> None:
    bounds = load_interim("boundaries")
    kim = load_interim("kim")
    dem = load_interim("dem")
    landcover = load_interim("landcover")
    water_src = load_interim("water")

    # --- okruzi and opštine: the order of world.json "states" and "counties" ---------------------------------
    okruzi = sorted(bounds["oblasti"] + kim["oblasti"], key=lambda o: okrug_name(territory.name(o["id"])))
    opstine = sorted(bounds["municipalities"] + kim["municipalities"], key=lambda m: m["id"])

    # --- projection: fit the okruzi with a margin, as upstream fitted the lower 48 -----------------------
    albers = Albers()
    xs, ys = zip(*(albers(lon, lat) for okrug in okruzi for ring in okrug["rings"] for lon, lat in ring))
    proj = MapProjection(min(xs), max(ys), MARGIN_KM)
    width = max(xs) - min(xs) + 2 * MARGIN_KM
    height = max(ys) - min(ys) + 2 * MARGIN_KM
    grid = HexGrid.covering(width, height, HEX_RADIUS_KM)
    print(f"    grid {grid.cols}×{grid.rows} = {grid.size} hexes of {HEX_RADIUS_KM:g} km")

    def shape(rings):
        """A (multi)polygon's lon/lat rings in map km."""
        return Shape([[proj(lon, lat) for lon, lat in r] for r in rings])

    lakes = []
    for lake in water_src["lakes"]:
        polygon = shape(lake["rings"])
        area = lake.get("area_km2")
        if (polygon.area_km2() if area is None else area) >= LAKE_MIN_KM2:  # no published area: measure the polygon
            lakes.append(polygon)
    lake_idx = ShapeIndex(lakes)
    oblast_idx = ShapeIndex([shape(o["rings"]) for o in okruzi])
    foreign_idx = ShapeIndex([shape(c["rings"]) for c in bounds["countries"]], cell_km=200)
    opstina_idx = ShapeIndex([shape(m["rings"]) for m in opstine], cell_km=60)

    # --- ownership: the majority of 7 sample points ------------------------------------------------
    # The centre plus six points 60 % of the way to each corner. Each point lies in a lake, an okrug, a foreign
    # country or in none of them ("sea"). A hex whose centre lies in a big lake is a lake hex, whatever else.
    offsets = [(0.0, 0.0)] + [
        (SAMPLE_SHARE * HEX_RADIUS_KM * math.cos(math.radians(60 * k - 30)),
         SAMPLE_SHARE * HEX_RADIUS_KM * math.sin(math.radians(60 * k - 30)))
        for k in range(6)
    ]
    centres = [grid.center(*grid.col_row(i)) for i in range(grid.size)]
    owner = [WATER] * grid.size
    water = [OCEAN] * grid.size

    def kind(x, y):
        """What lies at a sample point: "lake", an okrug index, FOREIGN or "sea"."""
        if lake_idx.locate(x, y) >= 0:
            return "lake"
        if (o := oblast_idx.locate(x, y)) >= 0:
            return o
        return FOREIGN if foreign_idx.locate(x, y) >= 0 else "sea"

    for i, (cx, cy) in enumerate(centres):
        if lake_idx.locate(cx, cy) >= 0:
            water[i] = LAKE
            continue
        kinds = [kind(cx + dx, cy + dy) for dx, dy in offsets]
        land = [k for k in kinds if isinstance(k, int)]
        if len(land) * 2 <= len(kinds):
            continue  # "sea": see the fill below
        ours = [k for k in land if k >= 0]
        if len(ours) > len(land) - len(ours) or (len(ours) * 2 == len(land) and kinds[0] != FOREIGN):
            owner[i] = majority(ours, kinds[0])
        else:
            owner[i] = FOREIGN
        water[i] = LAND

    # Serbia is landlocked, so a "sea" hex only means that two outlines do not meet: it becomes land with the
    # majority owner of its land neighbours as soon as it has one, and only hexes with no land neighbour at all
    # stay OCEAN. The majority is read off the map as it was before the fill, so the fill cannot spread.
    filled = []
    for i in range(grid.size):
        if water[i] != OCEAN:
            continue
        land_neighbours = [owner[j] for j in grid.neighbours(i) if water[j] == LAND]
        if land_neighbours:
            filled.append((i, Counter(land_neighbours).most_common(1)[0][0]))
    for i, o in filled:
        owner[i], water[i] = o, LAND
    print(f"    {len(filled)} \"sea\" hexes with a land neighbour became land")

    # --- opštine of the Serbian hexes ------------------------------------------------------------------------
    # The centre sample if it lies in the hex's okrug, else the most common sample that does, else any sample:
    # majority ownership can differ from the centre point.
    county = [-1] * grid.size
    county_samples: list[list[int]] = [[] for _ in range(grid.size)]
    for i, (cx, cy) in enumerate(centres):
        if owner[i] >= 0:
            county_samples[i] = [opstina_idx.locate(cx + dx, cy + dy) for dx, dy in offsets]
    oblast_of = [territory.oblast_of(m["id"]) for m in opstine]
    for i, samples in enumerate(county_samples):
        found = [k for k in samples if k >= 0]
        if not found:
            continue
        in_okrug = [k for k in found if oblast_of[k] == okruzi[owner[i]]["id"]]
        pool = in_okrug or found
        county[i] = samples[0] if samples[0] in pool else Counter(pool).most_common(1)[0][0]
    county_area_km2 = [shape(m["rings"]).area_km2() if m.get("rings") else None for m in opstine]
    cells_of_county = [[] for _ in opstine]
    for i, k in enumerate(county):
        if owner[i] >= 0 and k >= 0:
            cells_of_county[k].append(i)

    # --- elevation, relief and range from the dem lattice -------------------------------------------
    # Every lattice cell whose centre falls inside a land hex is a sample: its mean elevation, and (when the
    # interim has them) the lowest and the highest source elevation it was made from. A sample without data does
    # not count; an interim without the two arrays falls back on the means, as does a sample without a value there.
    native = "tiles" in dem
    if native != ("tiles" in landcover):
        raise ValueError("DEM and land-cover interims must use the same raster representation")
    if native:
        lonlat = [p for okrug in okruzi for ring in okrug["rings"] for p in ring]
        buffer = terrain.BUFFER_DEGREES
        bounds = (min(p[0] for p in lonlat) - buffer, min(p[1] for p in lonlat) - buffer,
                  max(p[0] for p in lonlat) + buffer, max(p[1] for p in lonlat) + buffer)
        print("    aggregating native elevation pixels", flush=True)
        result = terrain.aggregate_tiles(dem["tiles"], grid, proj, owner, water, "dem", bounds=bounds)
        count = result["count"]
        elev, elev_max, elev_range, relief = ([None] * grid.size for _ in range(4))
        for i in range(grid.size):
            if count[i]:
                elev[i] = round(float(result["weighted_sum"][i] / result["area"][i]))
                elev_max[i] = round(float(result["max"][i]))
                elev_range[i] = round(float(result["max"][i] - result["min"][i]))
                relief[i] = classify_relief(elev[i], elev_range[i])
    else:
        # Backward compatibility for synthetic fixtures and old cached lattice interims.
        dem_grid = lattice.Lattice.from_dict(dem["lat"])
        nodata = dem["nodata"]
        means = lattice.Lattice.decode(dem["elev_b64"], np.int16, dem_grid.shape).reshape(-1).tolist()

        def extremes(key):
            return lattice.Lattice.decode(dem[key], np.int16, dem_grid.shape).reshape(-1).tolist() if key in dem else means

        lows, highs = extremes("min_b64"), extremes("max_b64")
        count, total = [0] * grid.size, [0] * grid.size
        lowest, highest = [None] * grid.size, [None] * grid.size
        for k, i in enumerate(_hexes_of_lattice_cells(dem_grid, grid, proj)):
            if i < 0 or water[i] != LAND or means[k] == nodata:
                continue
            lo = lows[k] if lows[k] != nodata else means[k]
            hi = highs[k] if highs[k] != nodata else means[k]
            count[i] += 1
            total[i] += means[k]
            lowest[i] = lo if lowest[i] is None or lo < lowest[i] else lowest[i]
            highest[i] = hi if highest[i] is None or hi > highest[i] else highest[i]
        elev, elev_max, elev_range = ([0] * grid.size for _ in range(3))
        relief = [FLAT] * grid.size
        for i in range(grid.size):
            if count[i]:
                elev[i] = round(total[i] / count[i])
                elev_max[i] = highest[i]
                elev_range[i] = highest[i] - lowest[i]
                relief[i] = classify_relief(elev[i], elev_range[i]) if owner[i] >= 0 else FLAT
    no_elev = sum(1 for i in range(grid.size) if owner[i] >= 0 and not count[i])

    # --- land cover from the ESA WorldCover lattice -------------------------------------------------
    if native:
        print("    aggregating native land-cover pixels", flush=True)
        result = terrain.aggregate_tiles(landcover["tiles"], grid, proj, owner, water, "landcover", bounds=bounds)
        counts = result["classes"]
        cover = [None] * grid.size
        pct = {key: [None] * grid.size for key in PCT_KEYS}
    else:
        cover_grid = lattice.Lattice.from_dict(landcover["lat"])
        classes = lattice.Lattice.decode(landcover["classes_b64"], np.uint8, cover_grid.shape).reshape(-1).tolist()
        cover_cells = _hexes_of_lattice_cells(cover_grid, grid, proj)
        counts = [Counter() for _ in range(grid.size)]
        nodata_cover = landcover["nodata"]
        for k, i in enumerate(cover_cells):
            if i >= 0 and owner[i] >= 0 and classes[k] != nodata_cover:
                counts[i][classes[k]] += 1
        cover = [0] * grid.size
        pct = {key: [0] * grid.size for key in PCT_KEYS}
    for i in range(grid.size):
        if owner[i] >= 0 and (not native or counts[i]):
            shares = cover_shares(counts[i])
            cover[i] = dominant_cover(shares, elev[i] if elev[i] is not None else 0)
            for key in PCT_KEYS:
                pct[key][i] = shares[key]

    # --- rivers -------------------------------------------------------------------------------------
    # Kept from RIVER_MIN_LENGTH_KM of published or mapped length, longest first, equal lengths by name.
    kept = []
    for r in water_src["rivers"]:
        length = r.get("length_km") or r.get("mapped_km") or 0
        if length >= RIVER_MIN_LENGTH_KM:
            kept.append((length, r.get("name_lat") or to_latin(r.get("name") or ""), r))
    kept.sort(key=lambda item: (-item[0], item[1]))
    rivers = []
    for rank, (length, name, r) in enumerate(kept, 1):
        parts = [piece for line in r["lines"] for piece in clip_polyline([proj(lon, lat) for lon, lat in line], width, height)]
        for piece in join_lines(parts):
            if sum(math.dist(a, b) for a, b in zip(piece, piece[1:])) < RIVER_PIECE_MIN_KM:
                continue  # a corner clipped down to nothing
            points = simplify(piece, RIVER_SIMPLIFY_KM)
            if len(points) >= 2:
                rivers.append({"name": name, "rank": rank, "pts": [round(v, 1) for p in points for v in p]})

    # --- the outputs --------------------------------------------------------------------------------
    state_ids = [o["id"] for o in okruzi]
    write_web("world.json", {
        "version": 2,
        "grid": grid.to_dict(),
        "width": round(width, 1),
        "height": round(height, 1),
        "margin": MARGIN_KM,
        "projection": proj.to_dict(),
        "owner": owner,
        "county": county,
        "elev": elev,
        "elev_max": elev_max,
        "elev_range": elev_range,
        "water": water,
        "relief": relief,
        "cover": cover,
        "pct": pct,
        "tables": {"water": water_table(), "relief": relief_table(), "cover": cover_table()},
        "states": [{"fips": o["id"], "abbr": None, "name": okrug_name(territory.name(o["id"]))} for o in okruzi],
        "counties": [{"geoid": m["id"], "name": territory.name(m["id"])} for m in opstine],
        "rivers": rivers,
    })
    save_interim("_world", {
        "grid": grid.to_dict(),
        "projection": proj.to_dict(),
        "width": width,
        "height": height,
        "owner": owner,
        "county": county,
        "county_samples": county_samples,
        "states": state_ids,
        "counties": [m["id"] for m in opstine],
        "county_area_km2": county_area_km2,
        "water": water,
        "cover": cover,
        "pct": pct,
        "cells_of_county": cells_of_county,
    })
    serbian = sum(1 for o in owner if o >= 0)
    no_county = sum(1 for i in range(grid.size) if owner[i] >= 0 and county[i] < 0)
    no_cover = sum(1 for i in range(grid.size) if owner[i] >= 0 and not cover[i])
    print(f"    {serbian} hexes in {len(okruzi)} okruzi, {len(rivers)} river lines; {no_county} Serbian hexes without an opština, "
          f"{no_elev} without elevation samples, {no_cover} without land-cover samples")
