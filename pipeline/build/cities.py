"""Cities: the municipalities that are towns, each placed at its urban settlement.

A unit is a city only when all of these hold:

* it is outside Kosovo;
* it is not a city municipality (territory.is_city_municipality: the seventeen opštine of Grad Beograd and the
  5-digit sub-units of Niš, Požarevac, Vranje, Užice and Novi Sad). Only the aggregate can be a city, so the map
  shows one city per urban area; Grad Beograd qualifies through its parts;
* the census lists an urban settlement of at least srb.CITY_MIN_URBAN_POP in it or in one of its parts;
* its latest RZS population estimate is at least srb.CITY_MIN_POP;
* and something places it (below).

Each city keeps its true position (x, y) and gets one Serbian land hex of its own territory for its banner. The
position is the place (OpenStreetMap) named like the city's largest urban settlement and lying in that settlement's
unit; failing that, a row of pipeline/data/city_positions.csv; failing that, the city is left out and printed. The
capital stands on Stari grad, where the fortress is.

GDP (gold) is an estimate: the okrug's GDP (Eurostat) times the city's share of the okrug's registered employment.
The other counts come from the census rows of the city's parts, summed; the population and its change from the RZS
estimates. A row is read through territory.data_unit: where a source publishes an aggregate but not its parts (the
census has Grad Novi Sad, not its two city municipalities), the aggregate's row stands for the first part, once.

The _cities interim tells the checker, for every unit outside Kosovo, whether it is a city, which city it belongs to
and why it is not one.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from ..core import srb, store, territory
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.srtext import fold_key, okrug_name
from .yields import RANK_KEYS, growth, jobs_from_nace, peers, ranks, rank_value, yields_of

REQUIRES = ["census", "rzs_db", "gdp", "places", "_world"]
PRODUCES = ["cities.json", "_cities"]

POSITIONS_FILE = Path(__file__).resolve().parents[1] / "data" / "city_positions.csv"
STARI_GRAD = "70246"  # where the fortress is: the capital's marker stands here
CENSUS_TABLES = ["education", "religion", "ethnicity", "commute"]  # a city's census counts, as the census names them
PLACE_CLASSES = ["city", "town", "village"]  # OpenStreetMap's kinds of place, the most urban first


def reviewed_positions() -> dict[str, tuple[float, float]]:
    """pipeline/data/city_positions.csv (id,lon,lat): where a city stands when no place can place it."""
    with POSITIONS_FILE.open(encoding="utf-8", newline="") as f:
        return {row["id"].strip(): (float(row["lon"]), float(row["lat"])) for row in csv.DictReader(f) if row["id"].strip()}


def sum_values(values: list) -> float | None:
    """The sum of the parts' values, None when a part has none: a sum over the other parts would pass for the whole.
    A part without a published row is left out before, by the caller."""
    return None if not values or any(v is None for v in values) else sum(values)


def sum_tables(tables: list) -> dict | None:
    """sum_values for {category: count} tables. The categories keep the order of the first table that has them."""
    if not tables or any(t is None for t in tables):
        return None
    categories = list(dict.fromkeys(category for t in tables for category in t))
    return {category: sum_values([t.get(category) for t in tables]) for category in categories}


def weighted_mean(values: list, weights: list) -> float | None:
    """Σ(value × weight) ÷ Σ weight over the pairs where both are known; None without such a pair."""
    pairs = [(v, w) for v, w in zip(values, weights, strict=True) if v is not None and w]
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs) if pairs else None


def unit_row(table: dict, unit_id: str):
    """The row a source publishes for a unit, from its {unit id: row} table: the unit's own or, where the aggregate
    is the only current row, its aggregate's once (territory.row_for: the census of 2022 has Grad Novi Sad, not its
    two city municipalities, and the estimates have had the grad alone since 2020). None when no row stands for it."""
    return territory.row_for(table, unit_id)


def own_or_weighted(table: dict, unit_id: str, parts: list, weight_of, digits: int) -> float | None:
    """A city's net wage or 65+ share: the row the office publishes for the grad itself (Grad Niš, Grad Novi Sad) and,
    where it publishes none for the grad, the weighted mean over the units the grad is made of, as an okrug's figure is
    made in states.figures (Grad Beograd is printed as its seventeen opštine, not as the grad). None without either."""
    own = unit_row(table, unit_id)
    if own is not None or not parts:
        return own
    mean = weighted_mean([unit_row(table, p) for p in parts], [weight_of(p) for p in parts])
    return round(mean, digits) if mean is not None else None


def census_counts(rows: list[dict]) -> dict:
    """What the census rows of a city's parts, or of an okrug's units, add up to: employed, unemployed, jobs, the
    four tables of CENSUS_TABLES and the unemployment rate (unemployed ÷ labour force). With no row at all, every
    field is None."""
    activity = sum_tables([r.get("activity") for r in rows]) or {}
    employed, unemployed = activity.get("employed"), activity.get("unemployed")
    labour = sum_values([employed, unemployed])
    counts = {table: sum_tables([r.get(table) for r in rows]) for table in CENSUS_TABLES}
    counts.update(
        employed=employed,
        unemployed=unemployed,
        jobs=jobs_from_nace(sum_tables([r.get("industry") for r in rows])),
        unemployment=round(unemployed / labour, 4) if unemployed is not None and labour else None,
    )
    return counts


def check_parts(unit_id: str, rows: list[dict], census_units: dict) -> None:
    """The census population is not published here, only kept for this check: when the census has a row of its own
    for a city, its inhabitants should equal the sum of the parts' rows."""
    own = census_units.get(unit_id)
    parts = sum_values([r.get("population") for r in rows])
    if own and parts is not None and own.get("population") is not None and own["population"] != parts:
        print(f"    {territory.name(unit_id)}: the census counts {own['population']:,} inhabitants, "
              f"its parts on file {parts:,}")


def serbian_land(world: dict) -> list[bool]:
    """Per hex: owned by an okrug and not water. Kosovo's hexes are Serbian land too."""
    return [owner >= 0 and water == srb.LAND for owner, water in zip(world["owner"], world["water"], strict=True)]


def claim_cell(grid: HexGrid, cells, x: float, y: float, taken: set) -> int | None:
    """The hex of `cells` whose centre is nearest to (x, y): the nearest free one when another city holds it, and
    that nearest one after all when none is free. None when there is no cell."""
    def nearer(cell):
        cx, cy = grid.center(*grid.col_row(cell))
        return math.hypot(cx - x, cy - y), cell

    if not cells:
        return None
    cell = min(cells, key=nearer)
    if cell in taken:
        cell = min((c for c in cells if c not in taken), key=nearer, default=cell)
    return cell


def centre_of(grid: HexGrid, cells) -> tuple[float, float]:
    """The centroid of the centres of some hexes."""
    points = [grid.center(*grid.col_row(c)) for c in cells]
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def build() -> None:
    census = store.load_interim("census")
    rzs = store.load_interim("rzs_db")
    gdp = store.load_interim_payload("gdp")
    places = store.load_interim("places")["places"]
    world = store.load_interim("_world")
    grid, proj = HexGrid(**world["grid"]), MapProjection(**world["projection"])
    land = serbian_land(world)
    land_cells = [[c for c in cells if land[c]] for cells in world["cells_of_county"]]
    county_index = {unit: i for i, unit in enumerate(world["counties"])}
    reviewed = reviewed_positions()
    employment_of = rzs["employment"]["by_unit"]
    on_map: dict[str, list[str]] = {}  # oblast → the okrug's units on the map
    for unit in world["counties"]:
        on_map.setdefault(territory.oblast_of(unit), []).append(unit)
    places_by_name: dict[str, list[dict]] = {}
    for p in places:
        places_by_name.setdefault(fold_key(p.get("name_lat")), []).append(p)
    settlements_in: dict[str, list[dict]] = {}
    for s in census["settlements"]:
        settlements_in.setdefault(s.get("unit"), []).append(s)

    def cells_of(units) -> list[int]:
        """The Serbian land hexes of these municipalities."""
        return sorted(c for u in units if u in county_index for c in land_cells[county_index[u]])

    def employment(units) -> float | None:
        """Registered employment (RZS) of these units: the published rows added up, each once."""
        return sum_values([row["total"] for u in units if (row := unit_row(employment_of, u)) is not None])

    def urban_settlements(unit_id: str) -> list[dict]:
        """The census's urban settlements inside a unit or one of its parts, the most populous first. A grad's own
        settlement (Novi Sad) is listed under the grad, not under a city municipality."""
        inside = dict.fromkeys([unit_id, *territory.parts_of(unit_id)])
        found = [s for part in inside for s in settlements_in.get(part, ()) if s.get("urban") and s.get("population")]
        return sorted(found, key=lambda s: -s["population"])

    def municipality_at(lon: float, lat: float) -> str | None:
        """The municipality whose hex holds (lon, lat): None off the grid or off Serbia."""
        cell = grid.cell_at(*proj(lon, lat))
        county = world["county"][cell] if cell >= 0 else -1
        return world["counties"][county] if county >= 0 else None

    def position(unit_id: str, settlement: dict) -> tuple[float, float] | None:
        """(x, y) the city stands at, or None when nothing places it."""
        old_town = cells_of([STARI_GRAD]) if unit_id == srb.GRAD_BEOGRAD else []
        if old_town:  # the capital's marker goes where the fortress is, not out in a suburb
            return grid.center(*grid.col_row(claim_cell(grid, old_town, *centre_of(grid, old_town), set())))
        units = territory.parts_of(settlement.get("unit"))
        hits = [p for p in places_by_name.get(fold_key(settlement.get("name")), ())
                if municipality_at(p["lon"], p["lat"]) in units]
        if hits:  # of several places of that name in the unit, the most urban, then the most populous
            def urbanity(p):
                rank = PLACE_CLASSES.index(p["fclass"]) if p.get("fclass") in PLACE_CLASSES else len(PLACE_CLASSES)
                return rank, -(p.get("population") or 0)

            best = min(hits, key=urbanity)
            return proj(best["lon"], best["lat"])
        return proj(*reviewed[unit_id]) if unit_id in reviewed else None

    candidates, why = [], {}
    for unit_id in territory.units():
        if territory.in_kosovo(unit_id) or territory.is_city_municipality(unit_id):
            continue  # never a city by itself: settled when the units are written below
        settlements = urban_settlements(unit_id)
        if not settlements or settlements[0]["population"] < srb.CITY_MIN_URBAN_POP:
            why[unit_id] = f"no urban settlement of {srb.CITY_MIN_URBAN_POP:,}+"
            continue
        series = unit_row(rzs["pop"], unit_id) or []
        if not series or series[-1] is None:
            why[unit_id] = "no population estimate"
            continue
        if series[-1] < srb.CITY_MIN_POP:
            why[unit_id] = f"population below {srb.CITY_MIN_POP:,}"
            continue
        settlement = next((s for s in settlements if s.get("id")), None)  # the one that places the city
        point = position(unit_id, settlement) if settlement else None
        if point is None:
            why[unit_id] = "no position on the map"
            print(f"    no position on the map for {territory.name(unit_id)} ({unit_id}): "
                  f"add a row to pipeline/data/{POSITIONS_FILE.name}")
            continue

        parts = territory.parts_of(unit_id)
        rows = [row for row in (unit_row(census["units"], p) for p in parts) if row]
        check_parts(unit_id, rows, census["units"])
        counts = census_counts(rows)
        oblast = territory.oblast_of(unit_id)
        nuts = gdp["data"]["nuts3"].get(oblast)
        city, okrug = employment(parts), employment(on_map.get(oblast, ()))
        gdp_value = round(nuts * 1e6 * city / okrug) if nuts is not None and city and okrug else None
        name = re.sub(r"^Grad ", "", territory.name(unit_id))
        change, years = growth(series, rzs["pop_years"])
        employed_of = lambda u: (unit_row(rzs["employment"]["by_unit"], u) or {}).get("total")  # a wage's weight
        latest_of = lambda u: (unit_row(rzs["pop"], u) or [None])[-1]  # a share's weight
        candidates.append({
            "id": unit_id,
            "name": name,
            "full": f"{name} ({okrug_name(territory.name(oblast))})",
            "states": [oblast],
            "metro": True,  # upstream's flag for the larger kind of city: its leaderboards rank only `metro !== false`
            "capital": unit_id == srb.GRAD_BEOGRAD,
            "x": round(point[0], 1),
            "y": round(point[1], 1),
            "cell": None,  # claimed below, the larger cities first
            "population": round(series[-1]),
            "employed": counts["employed"],
            "yields": yields_of(counts["jobs"], gdp_value),
            "jobs": counts["jobs"],
            "median_income": None, "median_rent": None, "home_value": None, "rent_burden": None,  # not published below the region
            "unemployment": counts["unemployment"],
            "wage_net": own_or_weighted(rzs["wages"]["net"], unit_id, parts, employed_of, 2),
            "age65": own_or_weighted(rzs["pop_65"]["by_unit"], unit_id, parts, latest_of, 4),
            "gdp": gdp_value,
            "gdp_year": gdp["data"]["year"],
            "gdp_by_industry": None,
            "gdp_undisclosed": None,
            "gdp_estimated": ["total"] if gdp_value is not None else None,
            "growth": change,
            "growth_years": years,
            "counties": sorted(parts),
            "footprint": [],
            "pop_series": {str(year): round(v) if v is not None else None for year, v in zip(rzs["pop_years"], series, strict=True)},
            "ranks": {},
            "peers": [],
            "settlement_population": settlement["population"],
            **{table: counts[table] for table in CENSUS_TABLES},
        })

    candidates.sort(key=lambda c: (-c["population"], c["id"]))
    cities, taken = [], set()
    for c in candidates:
        cells = cells_of(c["counties"])
        cell = claim_cell(grid, cells, c["x"], c["y"], taken)
        if cell is None:
            why[c["id"]] = "no cells on the map"
            print(f"    no hex on the map for {c['name']} ({c['id']})")
            continue
        if cell in taken:
            print(f"    {c['name']} shares its hex with a larger city: no free hex of its own")
        taken.add(cell)
        c["cell"] = cell
        c["footprint"] = sorted(set(cells) | {cell})
        cities.append(c)
    ranks(cities, RANK_KEYS, value=rank_value)
    peers(cities)

    city_ids = {c["id"] for c in cities}
    units = {}
    for unit_id in territory.units():
        if territory.in_kosovo(unit_id):
            continue
        if unit_id in city_ids:
            units[unit_id] = {"is_city": True, "city": unit_id, "why": None}
        elif territory.is_city_municipality(unit_id):
            aggregate = territory.aggregate_of(unit_id)
            units[unit_id] = {
                "is_city": False,
                "city": aggregate if aggregate in city_ids else None,
                "why": f"city municipality of {aggregate}" if aggregate else "city municipality",
            }
        else:
            units[unit_id] = {"is_city": False, "city": None, "why": why[unit_id]}

    print(f"    {len(cities)} cities")
    store.write_web("cities.json", cities)
    store.save_interim("_cities", {"cities": cities, "units": units})
