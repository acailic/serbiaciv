"""Tile improvements: motorways, main roads and railroads rasterised onto hex links, plus river ports and airports.

Lines are never shipped as polylines. Each Natural Earth 1:10m line is sampled every SAMPLE_KM along its length,
each sample is mapped to its hex, repeats in a row are dropped, a cell whose neighbours on the line already touch is
dropped (the line only clipped its corner; this keeps a road along a row boundary from zigzagging), and every step
between two cells becomes a link between neighbouring cells (a step that skips cells is filled with a hex line walk).
The browser draws a link as a road or rail segment from hex centre to hex centre.

A link is kept when at least one of its hexes is Serbian land (owner >= 0, Kosovo and Metohija's okruzi included)
and neither is foreign land (owner == -2): a road may cross a river hex or run in from a border hex, never through
another country. Rail samples on foreign land are dropped before linking, because Natural Earth's railroads carry no
country.

Filtering keeps the map readable. Roads: class 0 "Auto-put" is every road Natural Earth flags as an expressway (a dual
carriageway; it has no motorway type of its own) up to MOTORWAY_MAX_SCALERANK; class 1 "Magistralni put" is every
European road (level E) up to MAJOR_MAX_SCALERANK where no motorway already joins the same two hexes. Rail: scale rank
<= RAIL_MAX_SCALERANK, tier 0 "Glavna pruga" at <= RAIL_MAIN_SCALERANK. A link's name is the route label Natural
Earth gives the line (E75, E70 / A3, E761 / 5), the lowest European number winning where routes share a link.

Ports: the AUL's port areas by transshipped tonnes, placed at the town the area is named after (OpenStreetMap place,
or the city marker from cities.json). Airports: Serbia's large and medium airports (OurAirports) with the passengers
Eurostat or the airport's operator publishes. A site's `cell` is the Serbian land hex at its point, or the nearest one
up to SITE_RINGS hexes away; x/y stay the true position.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from ..core import srb, territory
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web
from ..core.srtext import fold_key, to_latin

REQUIRES = ["_world", "natural_earth_roads", "river_ports", "airports", "airport_traffic", "places", "cities.json"]
PRODUCES = ["infrastructure.json"]

SAMPLE_KM = 4.0
MOTORWAY_MAX_SCALERANK = 5  # above this the expressway flag marks E-roads that are ordinary roads (E79 / 1, E80 / 8, E851)
MAJOR_MAX_SCALERANK = 6  # European roads up to rank 6: Serbia's main roads; rank 7 and 8 (local) are left out
RAIL_MAX_SCALERANK = 7
RAIL_MAIN_SCALERANK = 5  # Serbia has rail at ranks 4, 6 and 7 only: rank 4 are the main lines
SITE_RINGS = 2
HUB_MIN = {"L": 1_000_000, "M": 100_000, "S": 1}  # passengers handled in the year; N = no published figure
ROAD_CLASSES = [{"id": "motorway", "name": "Auto-put"}, {"id": "major", "name": "Magistralni put"}]
RAIL_TIERS = [{"id": "main", "name": "Glavna pruga"}, {"id": "secondary", "name": "Sporedna pruga"}]
HUBS = {"L": "Veliki čvor", "M": "Srednji čvor", "S": "Mali čvor",
        "N": "Aerodrom sa malim ili nepoznatim prometom putnika"}
PLACE_CLASSES = ["city", "town", "village"]  # OpenStreetMap's kinds of place, the most urban first

RULES = {
    "roads": "Natural Earth 1:10m putevi na teritoriji Srbije (sa KiM), uzorkovani svakih 4 km i pripisani vezama "
             "između centara heksa. Razred 0 (auto-put): putevi koje Natural Earth označava kao puteve sa odvojenim "
             "saobraćajnim trakama (expressway) do ranga 5. Razred 1 (magistralni put): evropski putevi (oznaka E) do "
             f"ranga {MAJOR_MAX_SCALERANK}, gde auto-put već ne povezuje iste hekse. Natural Earth u ovom razmeru ne "
             "nosi državne puteve II reda ni lokalne puteve, pa ih na karti nema. Oznaka veze je oznaka puta iz "
             "Natural Earth-a (evropski i državni broj); sloj je crtež, ne statistika.",
    "rail": "Natural Earth 1:10m pruge do ranga 7, uzorkovane svakih 4 km i pripisane vezama između centara heksa; "
            f"rang 0 (glavna pruga) je rang {RAIL_MAIN_SCALERANK} ili niži (u Srbiji Natural Earth ima pruge samo "
            "rangova 4, 6 i 7). Natural Earth nosi deo stvarne mreže pruga, bez imena i bez podataka o saobraćaju.",
    "ports": "Lučka područja po količini pretovarenog tereta u tonama iz godišnje analize Agencije za upravljanje "
             "lukama (AUL); sve su rečne luke. Luka je postavljena na naselje po kome je lučko područje imenovano "
             "(OpenStreetMap), pa su duge rečne luke približne. Promet po smeru (domaći, inostrani, uvoz, izvoz) po "
             "lukama nije objavljen u mašinski čitljivom obliku, pa je null.",
    "airports": "Veliki i srednji aerodromi u Srbiji po OurAirports (sportski aerodromi nisu prikazani), sa položajem "
                "iz istog izvora. Broj putnika je broj prevezenih putnika u godini, a ne broj ukrcanih: Beograd i "
                "Niš po Eurostatu (avia_paoa), Kraljevo po statistici Aerodroma Morava; za aerodrome bez objavljenog "
                f"broja polje je null. Čvorovi: L od {HUB_MIN['L']:,} putnika, M od {HUB_MIN['M']:,}, S bar jedan, "
                "N bez objavljenog prometa. Težina tereta (cargo_lbs) je null: teretni saobraćaj se objavljuje samo "
                "u PDF izveštajima aerodroma.",
}


# ------------------------------------------------------------------ hex helpers

def _axial(grid: HexGrid, cell: int) -> tuple[int, int]:
    col, row = grid.col_row(cell)
    return col - (row - (row & 1)) // 2, row


def _from_axial(grid: HexGrid, q: int, r: int) -> int:
    col = q + (r - (r & 1)) // 2
    if 0 <= col < grid.cols and 0 <= r < grid.rows:
        return grid.index(col, r)
    return -1


def hex_distance(grid: HexGrid, a: int, b: int) -> int:
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    return (abs(q1 - q2) + abs(r1 - r2) + abs((q1 + r1) - (q2 + r2))) // 2


def hex_walk(grid: HexGrid, a: int, b: int) -> list[int]:
    """Cells on the hex line from a to b, both included (cube lerp with a tiny nudge to break ties)."""
    n = hex_distance(grid, a, b)
    if n <= 1:
        return [a, b] if a != b else [a]
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    out = []
    for i in range(n + 1):
        t = i / n
        x = q1 + (q2 - q1) * t + 1e-6
        z = r1 + (r2 - r1) * t + 1e-6
        y = -x - z
        rx, ry, rz = round(x), round(y), round(z)
        dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        c = _from_axial(grid, rx, rz)
        if c >= 0 and (not out or out[-1] != c):
            out.append(c)
    return out


def sample_cells(grid: HexGrid, pts: list[tuple[float, float]], keep=None) -> list[list[int]]:
    """Runs of distinct consecutive cells along a projected line, sampled every SAMPLE_KM. `keep(x, y)` False
    breaks the run (the sample is dropped)."""
    runs, run = [], []

    def add(x, y):
        nonlocal run
        if keep is not None and not keep(x, y):
            if len(run) > 1:
                runs.append(run)
            run = []
            return
        c = grid.cell_at(x, y)
        if c < 0:
            return
        if not run or run[-1] != c:
            run.append(c)

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / SAMPLE_KM))
        for i in range(steps):
            t = i / steps
            add(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    if pts:
        add(*pts[-1])
    if len(run) > 1:
        runs.append(run)
    return runs


def straighten(grid: HexGrid, run: list[int]) -> list[int]:
    """Drop detour cells: where the cells before and after a cell are neighbours themselves, the line only clipped
    that cell's corner. Without this, a road running along a row boundary zigzags between two rows."""
    out = []
    for c in run:
        while len(out) >= 2 and c in grid.neighbours(out[-2]):
            out.pop()
        if not out or out[-1] != c:
            out.append(c)
    return out


def links_of(grid: HexGrid, run: list[int]) -> list[tuple[int, int]]:
    out = []
    run = straighten(grid, [c for path in ([run[0]], *(hex_walk(grid, a, b)[1:] for a, b in zip(run, run[1:])))
                            for c in path])
    for a, b in zip(run, run[1:]):
        path = hex_walk(grid, a, b)
        for u, v in zip(path, path[1:]):
            if u != v:
                out.append((u, v) if u < v else (v, u))
    return out


def link_ok(owner, a: int, b: int) -> bool:
    """Serbian land at one end at least, foreign land at neither (water hexes and the border's edge are allowed)."""
    return not (owner[a] < 0 and owner[b] < 0) and owner[a] != -2 and owner[b] != -2


# ------------------------------------------------------------------ roads and rail

def road_class(feature: dict) -> int | None:
    """0 motorway, 1 main road, None for a road the map leaves out."""
    sr = feature["scalerank"] if feature["scalerank"] is not None else 99
    if feature["expressway"] and sr <= MOTORWAY_MAX_SCALERANK:
        return 0
    if feature.get("level") == "E" and sr <= MAJOR_MAX_SCALERANK:
        return 1
    return None


def _route_name(feature: dict) -> str | None:
    """The route label Natural Earth gives the line: its European road and state road number ("E75 / 1"), else the
    name field. Latin: Natural Earth's Serbian labels are Latin already, Cyrillic ones are transliterated."""
    parts = [p for p in (feature.get("label"), feature.get("label2")) if p]
    name = " / ".join(parts) or feature.get("name")
    return to_latin(name).strip() if name and name.strip() else None


def _route_key(name: str) -> tuple:
    digits = "".join(ch for ch in name if ch.isdigit())
    return (len(digits) or 9, int(digits) if digits else 999, name)


def build_roads(grid, proj, owner, ne) -> list[list]:
    cls_of: dict[tuple[int, int], int] = defaultdict(lambda: 9)
    names: dict[tuple[int, int], Counter] = defaultdict(Counter)
    for f in ne["roads"]:
        cls = road_class(f)
        if cls is None:
            continue
        name = _route_name(f)
        for line in f["lines"]:
            pts = [proj(lon, lat) for lon, lat in line]
            for run in sample_cells(grid, pts):
                for a, b in links_of(grid, run):
                    if not link_ok(owner, a, b):
                        continue
                    if cls < cls_of[(a, b)]:
                        cls_of[(a, b)] = cls
                        names[(a, b)].clear()
                    if cls == cls_of[(a, b)] and name:
                        names[(a, b)][name] += 1
    roads = []
    for (a, b), cls in sorted(cls_of.items()):
        nm = min(names[(a, b)], key=_route_key) if names[(a, b)] else None
        roads.append([a, b, cls, nm])
    return roads


def rail_tier(scalerank: int | None) -> int | None:
    """0 main line, 1 secondary line, None for a line the map leaves out."""
    if scalerank is None or scalerank > RAIL_MAX_SCALERANK:
        return None
    return 0 if scalerank <= RAIL_MAIN_SCALERANK else 1


def build_rail(grid, proj, owner, ne) -> list[list]:
    tier_of: dict[tuple[int, int], int] = {}

    def keep(x, y):
        c = grid.cell_at(x, y)
        return c < 0 or owner[c] != -2  # the railroads carry no country: foreign land is recognised by its hex

    for f in ne["rail"]:
        tier = rail_tier(f["scalerank"])
        if tier is None:
            continue
        for line in f["lines"]:
            pts = [proj(lon, lat) for lon, lat in line]
            for run in sample_cells(grid, pts, keep):
                for a, b in links_of(grid, run):
                    if link_ok(owner, a, b):
                        tier_of[(a, b)] = min(tier, tier_of.get((a, b), 9))
    return [[a, b, t] for (a, b), t in sorted(tier_of.items())]


# ------------------------------------------------------------------ sites

def slug(text: str) -> str:
    """A stable id from a Latin name: "Bačka Palanka" → "backa-palanka"."""
    folded = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


class Locator:
    """Where a site stands: its Serbian land hex, the municipality (opština) of that hex, the city (cities.json)
    that holds the municipality and the okrug."""

    def __init__(self, world: dict, grid: HexGrid, proj: MapProjection, cities: list[dict]):
        self.grid, self.proj, self.world = grid, proj, world
        self.owner, self.county, self.geoids = world["owner"], world["county"], world["counties"]
        self.state_of = {i: s for i, s in enumerate(world["states"])}  # hex owner (index) → okrug fips
        self.cities = cities
        by_geoid: dict[str, list[dict]] = defaultdict(list)
        for c in cities:
            for g in c.get("counties", []):
                by_geoid[g].append(c)
        self.city_of = {g: sorted(cs, key=lambda c: (c["id"] != g, -(c.get("population") or 0)))[0] for g, cs in by_geoid.items()}

    def land_cell(self, x: float, y: float, rings=SITE_RINGS) -> int:
        """The Serbian land hex holding (x, y), else the nearest one up to `rings` hexes away, else -1."""
        grid, owner = self.grid, self.owner
        cell = grid.cell_at(x, y)
        if cell < 0:
            return -1
        if owner[cell] >= 0:
            return cell
        seen, frontier = {cell}, [cell]
        for _ in range(rings):
            ring = [n for c in frontier for n in grid.neighbours(c) if n not in seen]
            ring = list(dict.fromkeys(ring))
            seen.update(ring)
            land = [n for n in ring if owner[n] >= 0]
            if land:
                return min(land, key=lambda n: math.dist(grid.center(*grid.col_row(n)), (x, y)))
            frontier = ring
        return -1

    def place(self, x: float, y: float) -> dict | None:
        cell = self.land_cell(x, y)
        if cell < 0:
            return None
        ci = self.county[cell]
        geoid = self.geoids[ci] if ci >= 0 else None
        return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "county": geoid,
                "cbsa": self.city_of[geoid]["id"] if geoid in self.city_of else None,
                "state": self.state_of[self.owner[cell]]}

    def city_name(self, at: dict) -> str | None:
        """The city a site serves: the mapped city holding its municipality, else the municipality's own name."""
        if at.get("cbsa"):
            return next((c["name"] for c in self.cities if c["id"] == at["cbsa"]), None)
        return territory.name(at["county"]) if at.get("county") else None


def port_position(port: dict, places: list[dict], cities: list[dict], proj: MapProjection) -> tuple[float, float] | None:
    """(x, y) of the town a port area is named after: OpenStreetMap's place point (the most urban, then the most
    populous of that name), else the mapped city's marker. None when nothing places it."""
    hits = [p for p in places if fold_key(p.get("name_lat", "")) == fold_key(port["name"])]
    if hits:
        def urbanity(p):
            rank = PLACE_CLASSES.index(p["fclass"]) if p.get("fclass") in PLACE_CLASSES else len(PLACE_CLASSES)
            return rank, -(p.get("population") or 0)
        best = min(hits, key=urbanity)
        return proj(best["lon"], best["lat"])
    city = next((c for c in cities if fold_key(c["name"]) == fold_key(port["name"])), None)
    return (city["x"], city["y"]) if city else None


def build_ports(loc: Locator, ports: dict, places: list[dict]) -> list[dict]:
    ranked = sorted(ports["ports"], key=lambda p: -p["tons"])
    out = []
    for rank, p in enumerate(ranked, start=1):
        at_xy = port_position(p, places, loc.cities, loc.proj)
        at = loc.place(*at_xy) if at_xy else None
        if at is None:
            print(f"    ! port {p['name']} has no place on the map; left out")
            continue
        out.append({"id": f"RS-{slug(p['name'])}", "name": p["name"], "type": "inland", "rank": rank, "tons": p["tons"],
                    "domestic": None, "foreign": None, "imports": None, "exports": None, "year": ports["year"], **at})
    return out


def hub_of(passengers: int | None) -> str:
    """L/M/S by the passengers handled in the year, N when no figure was published."""
    if passengers is None:
        return "N"
    for hub, floor in HUB_MIN.items():
        if passengers >= floor:
            return hub
    return "N"


def build_airports(loc: Locator, airports: dict, traffic: dict, latest_year: int | None = None) -> list[dict]:
    """One entry per airport: the latest published passenger figure with the year before it, or null figures and
    hub N where nothing was published (then `year` is the latest year of the traffic source, for the tooltip)."""
    out = []
    for a in airports["airports"]:
        series = {int(y): v for y, v in (traffic.get(a["icao"]) or {}).items()}
        years = sorted(y for y, v in series.items() if v is not None)
        year = years[-1] if years else latest_year
        at = loc.place(*loc.proj(a["lon"], a["lat"]))
        if at is None:
            print(f"    ! airport {a['icao']} has no Serbian land hex at its point; left out")
            continue
        pax = series.get(year) if year is not None else None
        out.append({"id": a["icao"], "name": srb.AIRPORT_NAMES.get(a["icao"], a["icao"]), "city": loc.city_name(at),
                    "hub": hub_of(pax), "enplanements": pax,
                    "enplanements_prev": series.get(year - 1) if (year is not None and pax is not None) else None,
                    "cargo_lbs": None, "year": year, **at})
    out.sort(key=lambda x: -(x["enplanements"] or 0))
    return out


# ------------------------------------------------------------------ build

def build() -> None:
    world = load_interim("_world")
    grid, proj, owner = HexGrid(**world["grid"]), MapProjection(**world["projection"]), world["owner"]
    ne_payload = load_interim_payload("natural_earth_roads")
    ne = ne_payload["data"]
    roads = build_roads(grid, proj, owner, ne)
    rail = build_rail(grid, proj, owner, ne)

    cities = json.loads((WEB_DATA / "cities.json").read_text(encoding="utf-8"))
    loc = Locator(world, grid, proj, cities)
    ports_payload, airports_payload, traffic_payload = (load_interim_payload(k) for k in ("river_ports", "airports", "airport_traffic"))
    traffic = traffic_payload["data"]["traffic"]
    latest_year = max((int(y) for s in traffic.values() for y, v in s.items() if v is not None), default=None)
    ports = build_ports(loc, ports_payload["data"], load_interim("places")["places"])
    airports = build_airports(loc, airports_payload["data"], traffic, latest_year)

    doc = {
        "version": 1,
        "vintage": {"roads": ne_payload["vintage"], "rail": ne_payload["vintage"], "ports": ports_payload["vintage"],
                    "airports": f"{airports_payload['vintage']}; {traffic_payload['vintage']}"},
        "sources": ["natural_earth_roads", "river_ports", "airports", "airport_traffic"],
        "rules": RULES,
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": HUBS,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
    }
    write_web("infrastructure.json", doc)
    road_cells = {c for a, b, *_ in roads for c in (a, b) if owner[c] >= 0}
    rail_cells = {c for a, b, _ in rail for c in (a, b) if owner[c] >= 0}
    land = sum(1 for o in owner if o >= 0)
    n0 = sum(1 for r in roads if r[2] == 0)
    hubs = Counter(a["hub"] for a in airports)
    print(f"    roads: {n0} motorway + {len(roads) - n0} main-road links on {len(road_cells)} of {land} land hexes; "
          f"rail: {sum(1 for r in rail if r[2] == 0)} main + {sum(1 for r in rail if r[2] == 1)} secondary links on "
          f"{len(rail_cells)} hexes; {len(ports)} ports; {len(airports)} airports "
          f"({', '.join(f'{k} {v}' for k, v in sorted(hubs.items()))})")


# ------------------------------------------------------------------ check

def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "infrastructure.json"
    if not path.exists():
        return [("NOTE", "infrastructure.json not built (optional; run: build infrastructure --deps)")]
    out = []
    doc = json.loads(path.read_text())
    for k in ("version", "vintage", "sources", "road_classes", "roads", "rail", "ports", "airports"):
        if k not in doc:
            out.append(("FAIL", f"infrastructure.json lacks '{k}'"))
    if any(lv == "FAIL" for lv, _ in out):
        return out
    if doc["version"] != 1:
        out.append(("FAIL", f"infrastructure.json version {doc['version']!r} (expected 1)"))
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else None
    if not world or "grid" not in world:
        return out + [("NOTE", "infrastructure.json: world.json unavailable, cell checks skipped")]
    grid = HexGrid(**world["grid"])
    owner = world.get("owner") or []
    n = grid.size
    county_ids = {c["geoid"] for c in world.get("counties", [])}
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c["id"] for c in json.loads(cpath.read_text())} if cpath.exists() else None
    spath = Path(web_dir) / "sources.json"
    if spath.exists():
        src = json.loads(spath.read_text())
        ids = {s["id"] for s in (src.get("sources", src) if isinstance(src, dict) else src) if isinstance(s, dict)}
        miss = [s for s in doc["sources"] if s not in ids]
        if ids and miss:
            out.append(("WARN", f"infrastructure.json cites sources missing from sources.json: {miss}"))

    def bad_link(link, ncls):
        if not isinstance(link, list) or len(link) < 3:
            return "shape"
        a, b, c = link[:3]
        if not all(isinstance(v, int) for v in (a, b, c)):
            return "types"
        if not (0 <= a < b < n):
            return "order/range"
        if b not in grid.neighbours(a):
            return "not neighbours"
        if len(owner) == n and (owner[a] < 0 and owner[b] < 0 or owner[a] == -2 or owner[b] == -2):
            return "no Serbian land end / foreign land"
        if not 0 <= c < ncls:
            return "class"
        return None

    for key, ncls in (("roads", len(doc["road_classes"])), ("rail", len(doc.get("rail_tiers") or [0, 1]))):
        links = doc[key]
        bad = [(l, why) for l in links if (why := bad_link(l, ncls))]
        pairs = [tuple(l[:2]) for l in links if isinstance(l, list)]
        dup = len(pairs) - len(set(pairs))
        if bad or dup:
            out.append(("FAIL", f"infrastructure.json {key}: {len(bad)} bad links (e.g. {bad[:2]}), {dup} duplicates"))
        else:
            cells = {c for l in links for c in l[:2]}
            out.append(("PASS", f"infrastructure.json {key}: {len(links)} neighbour links on {len(cells)} hexes"))
    if any(not (r[3] is None or isinstance(r[3], str)) for r in doc["roads"] if len(r) > 3):
        out.append(("FAIL", "infrastructure.json roads: route name must be a string or null"))

    def check_sites(key, num_keys):
        probs = []
        for s in doc[key]:
            c = s.get("cell")
            if not isinstance(c, int) or not 0 <= c < n or (len(owner) == n and owner[c] < 0):
                probs.append(f"{s.get('id')}: cell {c!r} is not Serbian land")
                continue
            if any(s.get(k) is not None and not isinstance(s.get(k), (int, float)) for k in num_keys):
                probs.append(f"{s.get('id')}: non-numeric value")
            cx, cy = grid.center(*grid.col_row(c))
            if not all(isinstance(s.get(k), (int, float)) for k in ("x", "y")) or \
                    math.dist((cx, cy), (s["x"], s["y"])) > (SITE_RINGS + 1) * world["grid"]["radius"] * 2:
                probs.append(f"{s.get('id')}: x/y far from its cell")
            if s.get("county") is not None and county_ids and s["county"] not in county_ids:
                probs.append(f"{s.get('id')}: unknown county {s['county']}")
            if s.get("cbsa") is not None and city_ids is not None and s["cbsa"] not in city_ids:
                probs.append(f"{s.get('id')}: unknown cbsa {s['cbsa']}")
        ids = [s.get("id") for s in doc[key]]
        if len(ids) != len(set(ids)):
            probs.append("duplicate ids")
        return probs

    for key, nums in (("ports", ("tons", "domestic", "foreign", "imports", "exports", "rank")),
                      ("airports", ("enplanements", "enplanements_prev", "cargo_lbs"))):
        probs = check_sites(key, nums)
        if probs:
            out.append(("FAIL", f"infrastructure.json {key}: {len(probs)} problems, e.g. {probs[:3]}"))
        else:
            metro = sum(1 for s in doc[key] if s.get("cbsa"))
            out.append(("PASS", f"infrastructure.json {key}: {len(doc[key])} sites, {metro} in a mapped city"))
    hubs = Counter(a.get("hub") for a in doc["airports"])
    out.append(("NOTE", "infrastructure.json airports by hub: " + ", ".join(f"{k or 'no class'} {v}" for k, v in
                                                                         sorted(hubs.items(), key=lambda kv: str(kv[0])))))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"infrastructure.json is {size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
