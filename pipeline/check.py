"""Validate web/data/*.json against the data contracts and report data quality.

    python -m pipeline check

Part 1 checks each file's shape: required keys, types, per-cell array lengths and value ranges, cross references
(lens sources, okrug order, cities' okruzi) and the rule of Kosovo and Metohija: on the map with its land, null in
every statistic. The contracts are the constants of pipeline.core.srb (lens ids, groups and formats, the
municipalities table's columns) and pipeline.core.territory (okrug and municipality ids, the aggregates).

Part 2 is a data-quality report: the density lens against the population, cities on water or sharing a hex, null
and zero yields, growth, rivers outside the map, municipalities without a hex, per-lens null shares, the nation
against the sum of its okruzi, and the unit lists of the census and of the RZS against the map.

Every line is PASS, WARN or FAIL (NOTE for information). The exit code is 1 if anything FAILed. WARN thresholds are
the constants below.

Part 3 runs builder-level checks: any module in pipeline/build/ may define

    def check(web_dir: Path) -> list[tuple[str, str]]   # [(level, message)], level in PASS/NOTE/WARN/FAIL

to validate the files it PRODUCES, so a new builder never has to edit this file. It is discovered
automatically (see run_builder_checks); a missing output should be reported as a NOTE (or WARN), not a FAIL,
unless the file is required. A check that raises is reported as a FAIL with the error.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TypeGuard

from .core import srb, territory
from .core.paths import INTERIM, WEB_DATA

LENS_NULL_WARN = 0.05  # share of Serbian cells with a null lens value
GROWTH_MAX = 0.25  # the pipeline nulls |growth| above this (pipeline/build/yields.py, GROWTH_LIMIT)
DENSITY_TOLERANCE = 0.02  # density × land_km2 against the population, per municipality (both are rounded)
NATION_SUM_TOLERANCE = 0.01  # the nation against the sum of the okruzi with statistics: a wider gap is not rounding
# What a value can physically be, per lens: anything outside is a unit mix-up (months for years, people per m² for km²).
LENS_BOUNDS = {"density": (0, 50000), "life_expectancy": (30, 100), "natural_increase": (-50, 50), "elevation": (-500, 9000)}
CITY_RANK_BASE = ["population", "gdp", "gdp_per_capita", "growth"]
PEERS = 5

REQUIRED = ["world.json", "cities.json", "states.json", "nation.json", "lenses.json", "sources.json", "counties.json"]
OPTIONAL = ["lens-values.json", "kim_towns.json"]  # checked when present; a lens may still require lens-values.json
OKRUZI = 25 + len(srb.KIM_OBLASTI)  # the okruzi on the map: 25 with statistics, then the five of Kosovo and Metohija

WATER_IDS = range(0, 4)
RELIEF_IDS = range(0, 4)
LENS_SCALES = {"log", "linear"}
HIGHER_IS = {"good", "bad", "neutral"}
YIELD_UNITS = {y["unit"] for y in srb.YIELDS}  # zaposleni for the four counted in people, eur for gold: whatever srb.YIELDS declares
OKRUG_ID = re.compile(r"RS\d{3}")
UNIT_ID = re.compile(r"\d{5}")
YEAR = re.compile(r"\d{4}")
COLOR = re.compile(r"^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?([0-9a-fA-F]{2})?$")
ECON_NUMBERS = ["population", "employed", "median_income", "median_rent", "home_value", "unemployment", "rent_burden",
                "wage_net", "age65", "gdp"]  # number or null
ECON_REQUIRED = ["population", "employed", "unemployment"]  # published for every unit outside Kosovo and Metohija
# The economic shape shared by a city, an okrug and nation.json "nation" (gdp_by_industry etc. are optional).
ECON_KEYS = ["population", "employed", "yields", "jobs", "median_income", "median_rent", "home_value", "rent_burden",
             "unemployment", "wage_net", "age65", "gdp", "gdp_year", "growth", "growth_years"]
# What an okrug of Kosovo and Metohija must not have: everything but its id, name, label and land.
KIM_NULL = ECON_KEYS + ["abbr", "energy", "gdp_by_industry", "gdp_undisclosed", "gdp_estimated"]
# counties.json columns that are null in Kosovo and Metohija and published everywhere else.
COUNTY_STAT_COLUMNS = ["population", "density", "age65", "education", "wage_net", "unemployment", "manufacturing",
                       "commute", "orthodox", "serbs", "life_expectancy", "natural_increase"]
COUNTY_LAND = ["forest", "crop", "pasture", "developed"]  # the land shares a municipality without a hex has no value for
LENS_VALUE_FILES = {"municipality": "lens-values.json"}  # value_source.kind → the file that holds the values


# ---------------------------------------------------------------- territory


def in_kosovo(unit_id) -> bool:
    """Kosovo and Metohija: the territory tree says so, or an id the tree does not know in the office's 9xxxx range
    (every unit of the region is numbered 9xxxx and no other unit is; the tree is the authority where it has the unit)."""
    unit_id = unit_id if isinstance(unit_id, str) else ""
    return territory.in_kosovo(unit_id) or (unit_id not in territory.nodes() and unit_id.startswith("9"))


def ident(obj) -> str:
    """A list entry's id for a report line: its id, or the value itself when it is not an object."""
    return str(obj.get("id")) if isinstance(obj, dict) else repr(obj)


def unit_label(unit_id: str) -> str:
    """An id with its name where the territory tree knows it: "89010 Grad Novi Sad"."""
    return f"{unit_id} {territory.name(unit_id)}" if isinstance(unit_id, str) and unit_id in territory.nodes() else str(unit_id)


# ---------------------------------------------------------------- reporting


class Report:
    """Collects PASS/WARN/FAIL/NOTE lines and prints them as they come."""

    def __init__(self, quiet: bool = False):
        self.lines: list[tuple[str, str]] = []
        self.quiet = quiet

    def _add(self, level: str, msg: str) -> None:
        self.lines.append((level, msg))
        if not self.quiet:
            print(f"  {level:4}  {msg}")

    def ok(self, msg):
        self._add("PASS", msg)

    def warn(self, msg):
        self._add("WARN", msg)

    def fail(self, msg):
        self._add("FAIL", msg)

    def note(self, msg):
        self._add("NOTE", msg)

    def section(self, title):
        if not self.quiet:
            print(f"\n[{title}]")

    def count(self, level: str) -> int:
        return sum(1 for lv, _ in self.lines if lv == level)

    @property
    def failed(self) -> bool:
        return self.count("FAIL") > 0


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v) -> TypeGuard[float]:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _sample(items, n=5) -> str:
    items = list(items)
    more = f" … (+{len(items) - n})" if len(items) > n else ""
    return ", ".join(str(x) for x in items[:n]) + more


def need_keys(r: Report, what: str, obj, keys) -> bool:
    """FAIL (once per object kind) if `obj` is not a dict or lacks keys. Returns True if all present."""
    if not isinstance(obj, dict):
        r.fail(f"{what}: expected an object, got {type(obj).__name__}")
        return False
    missing = [k for k in keys if k not in obj]
    if missing:
        r.fail(f"{what}: missing {', '.join(missing)}")
        return False
    return True


def check_cells(r: Report, name: str, arr, n: int, lo=None, hi=None, *, kind="int", none_ok=False) -> bool:
    """A per-cell array: length n, every value an int (or a number) within [lo, hi]; null allowed where the raster has
    no sample (water and foreign land)."""
    if not isinstance(arr, list) or len(arr) != n:
        got = len(arr) if isinstance(arr, list) else type(arr).__name__
        r.fail(f"{name}: expected {n} values, got {got}")
        return False
    test = is_int if kind == "int" else is_num
    bad = [i for i, v in enumerate(arr) if (v is None and not none_ok) or (v is not None and (not test(v) or (lo is not None and v < lo) or (hi is not None and v > hi)))]
    if bad:
        r.fail(f"{name}: {len(bad)} values not {kind}{' or null' if none_ok else ''} in [{lo}, {hi}] (cells {_sample(bad)}; e.g. {arr[bad[0]]!r})")
        return False
    return True


# ---------------------------------------------------------------- validators


def check_world(r: Report, w) -> dict | None:
    """Validate world.json. Returns a small context (n, owner, states, …) for the other checks, or None."""
    if not isinstance(w, dict):
        r.fail("world.json: not an object")
        return None
    fails_before = r.count("FAIL")
    if w.get("version") != 2:
        r.fail(f"world.json: version is {w.get('version')!r}, expected 2 (still v1?)")
    if not need_keys(r, "world.json grid", w.get("grid"), ["radius", "cols", "rows"]):
        return None
    g = w["grid"]
    if not (is_num(g["radius"]) and g["radius"] > 0 and is_int(g["cols"]) and is_int(g["rows"]) and g["cols"] > 0 and g["rows"] > 0):
        r.fail(f"world.json grid: bad values {g}")
        return None
    n = g["cols"] * g["rows"]
    need_keys(r, "world.json", w, ["width", "height", "margin", "owner", "county", "elev", "water", "relief", "cover", "pct", "tables", "states", "counties", "rivers", "projection"])
    for k in ("width", "height", "margin"):
        if k in w and not is_num(w[k]):
            r.fail(f"world.json {k}: not a number ({w[k]!r})")

    states, counties = w.get("states") or [], w.get("counties") or []
    if not isinstance(states, list) or not states or not all(isinstance(s, dict) and {"fips", "abbr", "name"} <= s.keys() for s in states):
        r.fail("world.json states: every entry needs fips, abbr, name")
    elif len(states) != OKRUZI:
        r.fail(f"world.json states: {len(states)} okruzi, expected {OKRUZI} (25 with statistics and the five of Kosovo and Metohija)")
    else:
        fips = [s.get("fips") for s in states]
        bad = [f for f in fips if not (isinstance(f, str) and OKRUG_ID.fullmatch(f))]
        if bad:
            r.fail(f"world.json states: okrug ids must be RSddd: {_sample(bad)}")
        dup = [f for f, k in Counter(fips).items() if k > 1]
        if dup:
            r.fail(f"world.json states: duplicate okrug ids {_sample(dup)}")
        if not set(srb.KIM_OBLASTI) <= set(fips):
            r.fail(f"world.json states: Kosovo and Metohija's okruzi {srb.KIM_OBLASTI} must be on the map")
        if not all(is_text(s.get("name")) for s in states):
            r.fail("world.json states: every okrug needs a name")
        # Where the territory tree knows an okrug it must be a NUTS-3 oblast, not a region or a municipality.
        wrong = [f for f in fips if isinstance(f, str) and f in territory.nodes() and territory.level(f) != 3]
        if wrong:
            r.fail(f"world.json states: not oblasti of the territory tree: {_sample(wrong)}")
    if not isinstance(counties, list) or not counties or not all(isinstance(c, dict) and {"geoid", "name"} <= c.keys() for c in counties):
        r.fail("world.json counties: every entry needs geoid, name")
    elif len(counties) != srb.MAP_MUNICIPALITIES:
        r.fail(f"world.json counties: {len(counties)} municipalities, expected {srb.MAP_MUNICIPALITIES} (srb.MAP_MUNICIPALITIES)")
    else:
        geoids = [c.get("geoid") for c in counties]
        bad = [x for x in geoids if not (isinstance(x, str) and UNIT_ID.fullmatch(x))]
        if bad:
            r.fail(f"world.json counties: municipality ids must be 5-digit strings: {_sample(bad)}")
        dup = [x for x, k in Counter(geoids).items() if k > 1]
        if dup:
            r.fail(f"world.json counties: duplicate municipality ids {_sample(dup)}")
        if not all(is_text(c.get("name")) for c in counties):
            r.fail("world.json counties: every municipality needs a name")

    ok = True
    owner = w.get("owner")
    ok &= check_cells(r, "world.json owner", owner, n, -2, len(states) - 1)
    ok &= check_cells(r, "world.json county", w.get("county"), n, -1, len(counties) - 1)
    for k, hi in (("elev", None), ("elev_max", 9000), ("elev_range", None)):
        if k in w:
            ok &= check_cells(r, f"world.json {k}", w[k], n, 0 if k != "elev" else None, hi, none_ok=True)
    water = w.get("water")
    if "water" in w:
        ok &= check_cells(r, "world.json water", water, n, 0, 3, none_ok=True)
    if "relief" in w:
        ok &= check_cells(r, "world.json relief", w["relief"], n, 0, 3, none_ok=True)
    if "cover" in w:
        ok &= check_cells(r, "world.json cover", w["cover"], n, 0, len(srb.COVER_KEYS) - 1, none_ok=True)
    owner_ok = isinstance(owner, list) and len(owner) == n and all(is_int(v) for v in owner)

    def cells(name):
        arr = w.get(name)
        return arr if isinstance(arr, list) and len(arr) == n else None

    if owner_ok and (water := cells("water")) and all(v is None or is_int(v) for v in water):
        wet_land = sum(1 for o, wt in zip(owner, water) if o != -1 and wt)
        dry_water = sum(1 for o, wt in zip(owner, water) if o == -1 and not wt)
        if wet_land or dry_water:
            r.warn(f"world.json: owner/water disagree on {wet_land} land cells with water>0 and {dry_water} water cells with water=0")
        if (relief := cells("relief")) and all(v is None or is_int(v) for v in relief):
            bad = sum(1 for wt, rl in zip(water, relief) if wt and rl)
            if bad:
                r.fail(f"world.json relief: {bad} water cells have relief != 0")
        if (elev := cells("elev")) and all(v is None or is_num(v) for v in elev):
            high = [i for i, (wt, e) in enumerate(zip(water, elev)) if wt and e is not None and e > 0]
            if high:
                r.fail(f"world.json elev: {len(high)} water cells have elev > 0 (water elev is mean depth, <= 0; cells {_sample(high)})")
            if (elev_max := cells("elev_max")) and all(v is None or is_num(v) for v in elev_max):
                low = [i for i, (e, m) in enumerate(zip(elev, elev_max)) if e is not None and m is not None and m < e]
                if low:
                    r.fail(f"world.json elev_max: {len(low)} cells have elev_max below elev (cells {_sample(low)})")

    pct = w.get("pct")
    if "pct" in w:
        if need_keys(r, "world.json pct", pct, srb.PCT_KEYS):
            for k in srb.PCT_KEYS:
                ok &= check_cells(r, f"world.json pct.{k}", pct[k], n, 0, 100, none_ok=True)
            if owner_ok and all(isinstance(pct[k], list) and len(pct[k]) == n for k in srb.PCT_KEYS):
                over = [i for i in range(n) if owner[i] >= 0 and sum(pct[k][i] or 0 for k in srb.PCT_KEYS) > 100 + len(srb.PCT_KEYS)]
                outside = [i for i in range(n) if owner[i] < 0 and any(pct[k][i] for k in srb.PCT_KEYS)]
                if over:
                    r.fail(f"world.json pct: {len(over)} cells sum above 100% (cells {_sample(over)})")
                if outside:
                    r.fail(f"world.json pct: {len(outside)} non-Serbian cells have non-zero land-cover shares (must be 0 or null)")

    tables = w.get("tables")
    if "tables" in w and need_keys(r, "world.json tables", tables, ["water", "relief", "cover"]):
        for t, ids in (("water", WATER_IDS), ("relief", RELIEF_IDS)):
            entries = tables[t] if isinstance(tables[t], list) else []
            got = sorted(e.get("id") for e in entries if isinstance(e, dict) and is_int(e.get("id")))
            if got != list(ids) or not all(isinstance(e, dict) and is_text(e.get("name")) for e in entries):
                r.fail(f"world.json tables.{t}: expected ids {list(ids)} with names, got {got}")
        entries = tables["cover"] if isinstance(tables["cover"], list) else []
        bad = [e for e in entries if not isinstance(e, dict) or not is_int(e.get("id")) or not 0 <= e["id"] < len(srb.COVER_KEYS)
               or e.get("key") != srb.COVER_KEYS[e["id"]] or not is_text(e.get("name")) or (e["id"] and not COLOR.match(str(e.get("color", ""))))]
        if bad or sorted(e["id"] for e in entries if isinstance(e, dict) and is_int(e.get("id"))) != list(range(len(srb.COVER_KEYS))):
            r.fail(f"world.json tables.cover: must list the fixed cover ids 0..{len(srb.COVER_KEYS) - 1} with their keys, names and colours: {_sample(bad, 2)}")

    rivers = w.get("rivers") or []
    bad = [i for i, rv in enumerate(rivers) if not isinstance(rv, dict) or not {"name", "rank", "pts"} <= rv.keys() or not is_text(rv["name"])
           or not is_int(rv["rank"]) or not isinstance(rv["pts"], list) or len(rv["pts"]) < 4 or len(rv["pts"]) % 2 or not all(is_num(v) for v in rv["pts"])]
    if bad or not isinstance(rivers, list):
        r.fail(f"world.json rivers: {len(bad)} malformed (need name, int rank, pts=[x0,y0,x1,y1,…])")

    proj = w.get("projection")
    if "projection" in w:
        if need_keys(r, "world.json projection", proj, ["min_x", "max_y", "margin"]):
            if not all(is_num(proj[k]) for k in ("min_x", "max_y", "margin")):
                r.fail(f"world.json projection: min_x, max_y and margin must be numbers, got {proj}")
            elif is_num(w.get("margin")) and proj["margin"] != w["margin"]:
                r.fail(f"world.json projection: margin {proj['margin']!r} differs from the map's margin {w['margin']!r}")

    if ok and r.count("FAIL") == fails_before:
        r.ok(f"world.json: {g['cols']}×{g['rows']} grid, {len(states)} okruzi, {len(counties)} municipalities, {len(rivers) if isinstance(rivers, list) else 0} rivers")
    return {
        "n": n, "grid": g, "owner": owner if owner_ok else None, "states": states if isinstance(states, list) else [],
        "counties": counties if isinstance(counties, list) else [], "width": w.get("width"), "height": w.get("height"),
        "rivers": rivers if isinstance(rivers, list) else [], "w": w,
    }


def kim_owners(ctx: dict | None) -> set[int]:
    """The owner codes (okrug indices) of Kosovo and Metohija."""
    return {i for i, s in enumerate(ctx["states"]) if isinstance(s, dict) and s.get("fips") in srb.KIM_OBLASTI} if ctx else set()


def _check_econ(r: Report, what: str, obj: dict, yield_keys, *, required=ECON_REQUIRED) -> None:
    """The economic fields shared by cities, okruzi and the nation (outside Kosovo and Metohija)."""
    bad = [k for k in ECON_NUMBERS if k in obj and obj[k] is not None and not is_num(obj[k])]
    if bad:
        r.fail(f"{what}: non-numeric {', '.join(bad)}")
    null = [k for k in required if obj.get(k) is None]
    if null:
        r.fail(f"{what}: {', '.join(null)} is null although the sources publish it outside Kosovo and Metohija (a lost unit?)")
    y = obj.get("yields")
    if not isinstance(y, dict) or set(y) != set(yield_keys) or not all(v is None or is_num(v) for v in y.values()):
        r.fail(f"{what}: yields must have exactly {list(yield_keys)} with number|null values, got {y!r}"[:240])
    jobs = obj.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != set(srb.INDUSTRY_KEYS) or not all(v is None or is_num(v) for v in jobs.values()):
        r.fail(f"{what}: jobs must have exactly the {len(srb.INDUSTRY_KEYS)} industries with number|null values")
    for k in ("unemployment", "rent_burden", "age65"):
        v = obj.get(k)
        if is_num(v) and not 0 <= v <= 1:
            r.fail(f"{what}: {k}={v} is not a 0..1 fraction")
    gdp, year = obj.get("gdp"), obj.get("gdp_year")
    if year is not None and not is_int(year):
        r.fail(f"{what}: gdp_year={year!r} must be null or a whole year")
    elif gdp is not None and year is None:
        r.fail(f"{what}: gdp without gdp_year (the figure's year must be shown)")
    g, gy = obj.get("growth"), obj.get("growth_years")
    if g is not None and not (is_num(g) and abs(g) <= GROWTH_MAX):
        r.fail(f"{what}: growth={g!r} must be null or a fraction within ±{GROWTH_MAX:.0%}")
    if gy is not None and not (isinstance(gy, list) and len(gy) == 2 and all(is_int(v) for v in gy) and gy[0] < gy[1]):
        r.fail(f"{what}: growth_years must be null or [earlier, later] whole years, got {gy!r}")
    elif g is not None and gy is None:
        r.fail(f"{what}: growth without growth_years")


def _check_kim_nulls(r: Report, what: str, obj: dict) -> None:
    """Kosovo and Metohija: every statistic is null, in the row and in its nested tables."""
    own = [k for k in KIM_NULL if k not in ("yields", "jobs", "ranks") and k in obj and obj[k] is not None]
    nested = [f"{k}.{sub}" for k in ("yields", "jobs", "ranks") for sub, v in (obj[k].items() if isinstance(obj.get(k), dict) else []) if v is not None]
    if own or nested:
        r.fail(f"{what}: an okrug of Kosovo and Metohija has null in every statistic, but has {_sample(own + nested)}")


def check_growth(r: Report, docs: dict) -> None:
    """Growth invariants across files: one growth window everywhere, ending at nation.json's year,
    and every okrug and the nation have a rate whenever the window is set (their borders are fixed)."""
    nat = docs.get("nation.json") if isinstance(docs.get("nation.json"), dict) else None
    nation = nat.get("nation") if nat and isinstance(nat.get("nation"), dict) else None
    states = [s for s in docs.get("states.json") or [] if isinstance(s, dict)]
    cities = [c for c in docs.get("cities.json") or [] if isinstance(c, dict)]
    fixed = [("nation.json nation", nation)] if nation else []  # fixed borders: always a rate
    fixed += [(f"states.json {s.get('abbr') or s.get('fips')}", s) for s in states]
    rows = fixed + [(f"cities.json {c.get('id')}", c) for c in cities]
    windows = {tuple(o["growth_years"]) for _, o in rows if isinstance(o.get("growth_years"), list) and len(o["growth_years"]) == 2}
    bad = 0
    if len(windows) > 1:
        r.fail(f"growth_years differ between rows: {sorted(windows)}")
        bad += 1
    year = nat.get("year") if nat else None
    for wnd in windows:
        if is_int(year) and wnd[1] != year:
            r.fail(f"growth_years end in {wnd[1]} but nation.json year is {year} (growth must end at the year shown)")
            bad += 1
    for what, o in fixed:
        if o.get("growth_years") is not None and o.get("growth") is None:
            r.fail(f"{what}: growth is null although growth_years is set (okruzi and the nation always have one)")
            bad += 1
    if not bad and windows:
        (wnd,) = windows
        r.ok(f"growth: one window {wnd[0]}→{wnd[1]} ending at nation.json year; every okrug and the nation have a rate")


def check_cities(r: Report, cities, ctx: dict | None, yield_keys=srb.YIELD_KEYS) -> dict:
    """Validate cities.json. Returns {id: city} for the municipalities table."""
    if not isinstance(cities, list) or not cities:
        r.fail("cities.json: expected a non-empty list")
        return {}
    keys = ["id", "name", "full", "states", "metro", "capital", "x", "y", "cell"] + ECON_KEYS
    fails_before = r.count("FAIL")
    missing = Counter(k for c in cities for k in keys if not isinstance(c, dict) or k not in c)
    if missing:
        r.fail(f"cities.json: missing keys {dict(missing)} (counts of cities)")
    ids = Counter(c.get("id") for c in cities if isinstance(c, dict))
    dup = [i for i, k in ids.items() if k > 1]
    if dup:
        r.fail(f"cities.json: duplicate ids {_sample(dup)}")
    bad_id = [c.get("id") for c in cities if not (isinstance(c.get("id"), str) and UNIT_ID.fullmatch(c["id"]))]
    if bad_id:
        r.fail(f"cities.json: ids must be 5-digit municipality id strings: {_sample(bad_id)}")
    kim = [c.get("id") for c in cities if isinstance(c.get("id"), str) and in_kosovo(c["id"])]
    if kim:
        r.fail(f"cities.json: no city lies in Kosovo and Metohija (every statistic there is null): {_sample(kim)}")
    pops = [c.get("population") for c in cities if isinstance(c, dict)]
    if any(not is_num(p) or p <= 0 for p in pops):
        r.fail("cities.json: every city needs a positive population")
    elif pops != sorted(pops, reverse=True):
        r.fail("cities.json: not sorted by population, descending")
    capitals = [c.get("name") for c in cities if isinstance(c, dict) and c.get("capital") is True]
    capital = [c for c in cities if isinstance(c, dict) and c.get("id") == srb.GRAD_BEOGRAD]
    if len(capitals) != 1 or not capital or capital[0].get("capital") is not True:
        r.warn(f"cities.json: the capital must be Grad Beograd ({srb.GRAD_BEOGRAD}) and the only capital; found {capitals}")
    elif capital[0].get("states") != [territory.BEOGRAD_OBLAST]:
        r.warn(f"cities.json: the capital must stand in the Beogradski okrug ({territory.BEOGRAD_OBLAST}); "
               f"Grad Beograd's okruzi are {capital[0].get('states')}")
    n = ctx["n"] if ctx else None
    okrugs = {s.get("fips") for s in ctx["states"] if isinstance(s, dict)} if ctx else None
    for c in cities:
        if not isinstance(c, dict):
            r.fail(f"cities.json: every city must be an object, got {type(c).__name__}")
            continue
        what = f"cities.json {c.get('id')} {c.get('name')}"
        if not (is_text(c.get("name")) and is_text(c.get("full"))):
            r.fail(f"{what}: name and full must be non-empty strings")
        if not (is_num(c.get("x")) and is_num(c.get("y"))):
            r.fail(f"{what}: x/y must be numbers")
        if not is_int(c.get("cell")) or (n is not None and not 0 <= c["cell"] < n):
            r.fail(f"{what}: cell {c.get('cell')!r} out of range")
        if not isinstance(c.get("states"), list) or not c.get("states"):
            r.fail(f"{what}: states must be a non-empty list")
        elif okrugs is not None and not set(c["states"]) <= okrugs:
            r.fail(f"{what}: okruzi {sorted(set(map(str, c['states'])) - okrugs)} are not world.json okrug ids")
        if not (isinstance(c.get("metro"), bool) and isinstance(c.get("capital"), bool)):
            r.fail(f"{what}: metro and capital must be true/false")
        _check_econ(r, what, c, yield_keys)
        _check_city_view(r, what, c, ctx, set(ids))
        if r.count("FAIL") - fails_before > 20:
            r.fail("cities.json: too many errors, stopping")
            return {c["id"]: c for c in cities if isinstance(c, dict) and "id" in c}
    _check_rank_table(r, "cities.json", [c for c in cities if isinstance(c, dict)], CITY_RANK_BASE + list(yield_keys), lambda c: c.get("id"), exact=True)
    if r.count("FAIL") == fails_before:
        r.ok(f"cities.json: {len(cities)} cities, footprints {sum(len(c.get('footprint') or []) for c in cities if isinstance(c, dict))} hexes, "
             f"ranks are 1..N permutations")
    return {c["id"]: c for c in cities if isinstance(c, dict) and "id" in c}


def _check_city_view(r: Report, what: str, c: dict, ctx: dict | None, ids: set) -> None:
    """counties, footprint, pop_series, peers of one city (ranks are checked across cities)."""
    fp = c.get("footprint")
    if not (isinstance(fp, list) and fp and all(is_int(v) for v in fp) and fp == sorted(set(fp))):
        r.fail(f"{what}: footprint must be a non-empty sorted list of distinct cell ints")
    else:
        if c.get("cell") not in fp:
            r.fail(f"{what}: footprint does not include the city's own cell {c.get('cell')}")
        owner = ctx["owner"] if ctx else None
        if owner and any(not 0 <= v < ctx["n"] or owner[v] < 0 for v in fp):
            r.fail(f"{what}: footprint has cells that are not Serbian land (water or foreign)")
    cs = c.get("counties")
    if not (isinstance(cs, list) and all(isinstance(g, str) and UNIT_ID.fullmatch(g) for g in cs)):
        r.fail(f"{what}: counties must be a list of 5-digit municipality id strings")
    elif ctx and ctx["counties"]:
        off = [g for g in cs if g not in {c.get("geoid") for c in ctx["counties"]}]
        if off:
            r.warn(f"{what}: municipalities {off} are not on the map")
    ps = c.get("pop_series")
    if ps is not None and not (isinstance(ps, dict) and ps and all(isinstance(y, str) and YEAR.fullmatch(y) for y in ps)
                               and all(v is None or (is_num(v) and v > 0) for v in ps.values())):
        r.fail(f"{what}: pop_series must be null or {{year: positive number|null}}")
    peers, n_peers = c.get("peers"), min(PEERS, len(ids) - 1)
    if not (isinstance(peers, list) and len(peers) == n_peers and len(set(peers)) == len(peers)
            and c.get("id") not in peers and set(peers) <= ids):
        r.fail(f"{what}: peers must be {n_peers} distinct other city ids, got {peers!r}"[:200])


def _rank_value(row: dict, k: str):
    """The figure behind a rank key (pipeline/build/yields.py: rank_value)."""
    if k == "gdp_per_capita":
        return row["gdp"] / row["population"] if is_num(row.get("gdp")) and is_num(row.get("population")) and row["population"] else None
    return (row.get("yields") or {}).get(k) if k in srb.YIELD_KEYS else row.get(k)


def _check_rank_table(r: Report, what: str, rows: list, keys: list, row_id, exact: bool = False) -> None:
    """The ranks of okruzi or cities, per key. A rank on a null value is a FAIL; a null rank where the value exists
    is tolerated (a row the ranking left out, e.g. one with nothing to rank): then the ranks need only be distinct,
    within 1..N and ordered by the value; otherwise they are a permutation of 1..N (1 = largest)."""
    if exact:
        bad = [row_id(row) for row in rows if not isinstance(row.get("ranks"), dict) or set(row["ranks"]) != set(keys)]
        if bad:
            r.fail(f"{what} ranks: every row must have exactly {keys} (null where there is no value): {_sample(bad)}")
            return
    for k in keys:
        ranked = [(row["ranks"].get(k), _rank_value(row, k), row_id(row)) for row in rows if isinstance(row.get("ranks"), dict) and k in row["ranks"]]
        if not ranked:
            continue
        bad = [a for rk, v, a in ranked if rk is not None and v is None]
        if bad:
            r.fail(f"{what} ranks.{k}: a rank on a null value for {_sample(bad)}")
            continue
        have = sorted((rk, v, a) for rk, v, a in ranked if is_int(rk) and is_num(v))
        if not have:
            continue
        ranks = [rk for rk, _, _ in have]
        if len(set(ranks)) != len(ranks) or ranks[-1] > len(rows):
            r.fail(f"{what} ranks.{k}: ranks must be distinct and at most {len(rows)}, got {ranks}")
            continue
        unranked = [a for rk, v, a in ranked if rk is None and v is not None]
        if unranked:  # a row the ranking left out keeps the others' ranks as they were
            r.note(f"{what} ranks.{k}: {len(unranked)} rows with a value have no rank ({_sample(unranked)})")
        elif ranks != list(range(1, len(have) + 1)) and not any(isinstance(row.get("ranks"), dict) and row["ranks"] and all(v is None for v in row["ranks"].values()) for row in rows):
            r.fail(f"{what} ranks.{k}: not a permutation of 1..{len(have)}")
            continue
        if any(have[i][1] < have[i + 1][1] for i in range(len(have) - 1)):
            r.fail(f"{what} ranks.{k}: rank order does not follow the value (1 = largest)")


def check_states(r: Report, states, ctx: dict | None, yield_keys=srb.YIELD_KEYS) -> list:
    """Validate states.json (the okruzi). Returns the okruzi with statistics."""
    if not isinstance(states, list) or not states:
        r.fail("states.json: expected a non-empty list")
        return []
    fails_before = r.count("FAIL")
    if len(states) != OKRUZI:
        r.fail(f"states.json: {len(states)} okruzi, expected {OKRUZI}")
    if ctx and [s.get("fips") for s in states if isinstance(s, dict)] != [s.get("fips") for s in ctx["states"]]:
        r.fail("states.json: not in the same order (fips) as world.json states")
    with_data = []
    for s in states:
        what = f"states.json {s.get('fips') if isinstance(s, dict) else ident(s)}"
        if not need_keys(r, what, s, ["fips", "abbr", "name", "ranks", "label", "land"] + ECON_KEYS):
            continue
        if not (isinstance(s["fips"], str) and OKRUG_ID.fullmatch(s["fips"])) or not is_text(s["name"]):
            r.fail(f"{what}: fips must be RSddd and name a non-empty string")
        kosovo = s["fips"] in srb.KIM_OBLASTI
        if kosovo:
            _check_kim_nulls(r, what, s)
        else:
            _check_econ(r, what, s, yield_keys)
            with_data.append(s)
        ranks = s["ranks"]
        keys = set(CITY_RANK_BASE) | set(yield_keys)
        if not (kosovo and ranks is None) and (not isinstance(ranks, dict) or not set(yield_keys) <= set(ranks) <= keys
                                               or not all(v is None or (is_int(v) and 1 <= v <= len(states)) for v in ranks.values())):
            r.fail(f"{what}: ranks must be {{key: 1..{len(states)} | null}} for the yields {list(yield_keys)} and may add {CITY_RANK_BASE}, got {ranks!r}"[:240])
        lab = s.get("label")
        if lab is not None and not (isinstance(lab, dict) and all(is_num(lab.get(k)) for k in ("x", "y", "angle", "size"))):
            r.fail(f"{what}: label must be {{x, y, angle, size}} numbers")
        elif lab is None and not kosovo:
            r.fail(f"{what}: label is null although the okrug has hexes (its name would not be drawn)")
        land = s.get("land", "missing")
        if land is not None and not (isinstance(land, dict) and set(land) == set(srb.PCT_KEYS)
                                     and all(is_num(v) and 0 <= v <= 1 for v in land.values())
                                     and sum(land.values()) <= 1 + 0.01 * len(srb.PCT_KEYS)):
            r.fail(f"{what}: land must be null or {{{', '.join(srb.PCT_KEYS)}}} 0..1 fractions, got {land!r}"[:240])
        _check_energy(r, what, s.get("energy"))
        if r.count("FAIL") - fails_before > 20:
            r.fail("states.json: too many errors, stopping")
            return with_data
    _check_rank_table(r, "states.json", with_data, CITY_RANK_BASE + list(yield_keys), lambda s: s.get("fips"))
    if r.count("FAIL") == fails_before:
        r.ok(f"states.json: {len(states)} okruzi ({len(with_data)} with statistics), ranks are 1..N permutations ordered by value")
    return with_data


def _check_energy(r: Report, what: str, e) -> None:
    if e is None:
        return
    if not need_keys(r, f"{what} energy", e, ["unit", "total", "by_type", "sites", "note"]):
        return
    bt, st = e["by_type"], e["sites"]
    if e["unit"] != "MW" or not is_text(e["note"]):
        r.fail(f"{what} energy: unit must be 'MW' and note a non-empty string")
    if not (isinstance(bt, dict) and isinstance(st, dict) and set(bt) == set(st)
            and all(is_num(v) and v >= 0 for v in bt.values()) and all(is_int(v) and v >= 0 for v in st.values())):
        r.fail(f"{what} energy: by_type/sites must be {{type: MW >= 0}} / {{type: count}} with the same keys")
    elif not is_num(e["total"]) or abs(e["total"] - sum(bt.values())) > 1:
        r.fail(f"{what} energy: total {e['total']!r} != sum of by_type {sum(bt.values())}")
    elif any((bt[k] > 0) != (st[k] > 0) for k in bt):
        r.fail(f"{what} energy: MW and site counts disagree on which types are present")


def check_nation(r: Report, nat) -> list[str]:
    """Validate nation.json; returns the yield keys it defines (for the city/okrug checks)."""
    if not need_keys(r, "nation.json", nat, ["vintage", "year", "gdp_vintage", "nation", "yields", "industries"]):
        return list(srb.YIELD_KEYS)
    fails_before = r.count("FAIL")
    if not is_text(nat["vintage"]) or not is_int(nat["year"]):
        r.fail("nation.json: vintage must be a non-empty string and year an int")
    if not is_text(nat["gdp_vintage"]):
        r.fail("nation.json: gdp_vintage must be a non-empty string (the GDP's source and year are always shown)")
    keys = []
    for y in nat["yields"] if isinstance(nat["yields"], list) else []:
        if not need_keys(r, f"nation.json yield {ident(y)}", y,
                         ["key", "icon", "emoji", "label", "color", "unit", "description"]):
            continue
        keys.append(y["key"])
        if y["unit"] not in YIELD_UNITS or not COLOR.match(str(y["color"])) or not is_text(y["description"]) or not is_text(y["label"]):
            r.fail(f"nation.json yield {y['key']}: unit must be {'|'.join(sorted(YIELD_UNITS))}, color #hex, label and description text")
    if keys != list(srb.YIELD_KEYS):
        r.fail(f"nation.json yields: keys must be srb.YIELD_KEYS in order {list(srb.YIELD_KEYS)}, got {keys}")
    industries = nat["industries"]
    if not isinstance(industries, dict) or set(industries) != set(srb.INDUSTRY_KEYS) or not all(isinstance(v, str) and v for v in industries.values()):
        r.fail("nation.json: industries must be {industry key: label} for exactly srb.INDUSTRY_KEYS")
    if need_keys(r, "nation.json nation", nat["nation"], ECON_KEYS):
        _check_econ(r, "nation.json nation", nat["nation"], list(srb.YIELD_KEYS))
    if r.count("FAIL") == fails_before:
        r.ok(f"nation.json: {nat['vintage']}, yields {keys}")
    return keys or list(srb.YIELD_KEYS)


def check_lenses(r: Report, doc, ctx: dict | None, source_ids: set | None, docs: dict) -> dict:
    """Validate lenses.json. Returns {lens id: format} for the other checks."""
    if not need_keys(r, "lenses.json", doc, ["vintage", "groups", "lenses"]):
        return {}
    fails_before = r.count("FAIL")
    if not is_text(doc["vintage"]):
        r.fail("lenses.json: vintage must be a non-empty string")
    groups = [g for g in doc["groups"] if isinstance(g, dict)] if isinstance(doc["groups"], list) else []
    if [g.get("id") for g in groups] != list(srb.LENS_GROUPS) or not all(is_text(g.get("name")) for g in groups):
        r.fail(f"lenses.json groups: must be {srb.LENS_GROUPS} in order, each with a name")
    group_ids = {g.get("id") for g in groups}
    lenses = doc["lenses"] if isinstance(doc["lenses"], list) else []
    ids = Counter(l.get("id") for l in lenses if isinstance(l, dict))
    if any(k > 1 for k in ids.values()):
        r.fail(f"lenses.json: duplicate lens ids {[i for i, k in ids.items() if k > 1]}")
    if [l.get("id") for l in lenses if isinstance(l, dict)] != list(srb.LENS_IDS):
        r.fail(f"lenses.json: lenses must be {srb.LENS_IDS} in the site's order, got {[l.get('id') for l in lenses if isinstance(l, dict)]}")
    keys = ["id", "group", "name", "icon", "emoji", "unit", "format", "scale", "domain", "ramp", "higher_is", "source", "description", "note"]
    formats = {}
    for lens in lenses:
        what = f"lenses.json {ident(lens)}"
        if not need_keys(r, what, lens, keys):
            continue
        lid = lens["id"]
        formats[lid] = lens["format"]
        if not is_text(lens["name"]):
            r.fail(f"{what}: name must be a non-empty string")
        if lens["group"] not in group_ids:
            r.fail(f"{what}: unknown group {lens['group']!r}")
        if lens["format"] not in srb.LENS_FORMATS or lens["scale"] not in LENS_SCALES or lens["higher_is"] not in HIGHER_IS:
            r.fail(f"{what}: format/scale/higher_is must be one of {list(srb.LENS_FORMATS)}/{sorted(LENS_SCALES)}/{sorted(HIGHER_IS)}")
        d = lens["domain"]
        if not (isinstance(d, list) and len(d) == 2 and all(is_num(v) for v in d) and d[0] < d[1]) or (lens["scale"] == "log" and d[0] <= 0):
            r.fail(f"{what}: domain must be [lo, hi] with lo < hi (lo > 0 for log): {d!r}")
        if not (isinstance(lens["ramp"], list) and len(lens["ramp"]) >= 2 and all(COLOR.match(str(c)) for c in lens["ramp"])):
            r.fail(f"{what}: ramp must be ≥2 #hex colours")
        if not is_text(lens["source"]):
            r.fail(f"{what}: source must be a non-empty source id")
        elif source_ids is not None and lens["source"] not in source_ids:
            r.warn(f"{what}: source {lens['source']!r} is not in sources.json")
        if not is_text(lens["description"]) or not is_text(lens["note"]):
            r.fail(f"{what}: description and note must be non-empty strings (the legend always shows them)")
        if lens["format"] == "category":
            _check_categories(r, what, lens)
        elif "categories" in lens:
            r.fail(f"{what}: categories is only for format 'category'")
        if lid in srb.STATISTICAL_LENSES and lens["format"] == "category":
            r.fail(f"{what}: a statistical lens is numeric (land lenses alone are categorical)")
        vals = _lens_values(r, what, lens, ctx, docs)
        if vals is None or ctx is None:  # no world.json: nothing to lay the values over
            continue
        if not isinstance(vals, list) or len(vals) != ctx["n"]:
            r.fail(f"{what}: values must have {ctx['n']} entries, got {len(vals) if isinstance(vals, list) else type(vals).__name__}")
            continue
        bad = [i for i, v in enumerate(vals) if v is not None and not is_num(v)]
        if bad:
            r.fail(f"{what}: {len(bad)} values are neither number nor null (cells {_sample(bad)}; e.g. {vals[bad[0]]!r})")
        if ctx["owner"]:
            off = [i for i, v in enumerate(vals) if v is not None and ctx["owner"][i] < 0]
            if off:
                r.fail(f"{what}: {len(off)} values on water or foreign cells (must be null; cells {_sample(off)})")
            kim = kim_owners(ctx)
            if lid in srb.STATISTICAL_LENSES and kim:
                on_kim = [i for i, v in enumerate(vals) if v is not None and ctx["owner"][i] in kim]
                if on_kim:
                    r.fail(f"{what}: {len(on_kim)} values on hexes of Kosovo and Metohija (every statistic there is null; cells {_sample(on_kim)})")
        if lens["format"] == "pct" and any(is_num(v) and abs(v) > 1 + 1e-9 for v in vals):
            r.fail(f"{what}: format pct but some values are beyond ±1 (a pct lens holds fractions, not percentages)")
        bounds = LENS_BOUNDS.get(lid)
        if bounds:
            outside = [v for v in vals if is_num(v) and not bounds[0] <= v <= bounds[1]]
            if outside:
                r.fail(f"{what}: values outside {bounds[0]}–{bounds[1]}{' ' + lens['unit'] if lens['unit'] else ''} "
                       f"({_sample(outside, 3)}): a unit mix-up?")
        if lens["format"] == "category":
            nc = len(lens["categories"]) if isinstance(lens.get("categories"), list) else 0
            if any(is_num(v) and not (is_int(v) and 0 <= v < nc) for v in vals):
                r.fail(f"{what}: category values must be integer indices into categories (0..{nc - 1}) or null")
    if r.count("FAIL") == fails_before:
        r.ok(f"lenses.json: {len(lenses)} lenses in {len(groups)} groups ({doc['vintage']})")
    return formats


def _check_categories(r: Report, what: str, lens: dict) -> None:
    """A categorical lens: categories [{id, name, color}], ramp = their colours, linear domain [0, n-1]."""
    cats = lens.get("categories")
    if not (isinstance(cats, list) and len(cats) >= 2
            and all(isinstance(c, dict) and {"id", "name", "color"} <= c.keys() and is_text(c["id"]) and is_text(c["name"]) and COLOR.match(str(c["color"])) for c in cats)):
        r.fail(f"{what}: format category needs categories: [{{id, name, color}}] (≥2, #hex colours)")
        return
    n = len(cats)
    if [str(c).lower() for c in lens["ramp"]] != [str(c["color"]).lower() for c in cats]:
        r.fail(f"{what}: ramp must list the categories' colours in order")
    if lens["scale"] != "linear" or lens["domain"] != [0, n - 1]:
        r.fail(f"{what}: a categorical lens needs scale 'linear' and domain [0, {n - 1}]")
    if len({c["id"] for c in cats}) != n:
        r.fail(f"{what}: duplicate category ids")


def _lens_values(r: Report, what: str, lens: dict, ctx: dict | None, docs: dict) -> list | None:
    """A lens's per-cell values: its own `values`, or the ones its `value_source` names (pipeline/build/lenses.py):
    a statistical lens reads lens-values.json (one value per municipality, spread over its hexes), a land lens a
    field of world.json. None on water and foreign land."""
    if "values" in lens:
        return lens["values"]
    vs = lens.get("value_source")
    if not isinstance(vs, dict) or vs.get("kind") not in ("municipality", "world"):
        r.fail(f"{what}: needs per-cell values or value_source {{kind: municipality|world, …}}")
        return None
    want = "municipality" if lens.get("id") in srb.STATISTICAL_LENSES else "world"
    if vs["kind"] != want:
        r.fail(f"{what}: value_source.kind must be {want!r} for this lens, got {vs['kind']!r}")
    if ctx is None:
        return None
    owner, county, n = ctx["owner"], ctx["w"].get("county"), ctx["n"]
    if not owner or not isinstance(county, list) or len(county) != n:
        return None
    if vs["kind"] == "municipality":
        if vs.get("file") != LENS_VALUE_FILES["municipality"]:
            r.fail(f"{what}: value_source.file must be {LENS_VALUE_FILES['municipality']!r}, got {vs.get('file')!r}")
        lv = docs.get(LENS_VALUE_FILES["municipality"])
        col = (lv.get("values") or {}).get(vs.get("key", lens.get("id"))) if isinstance(lv, dict) else None
        ids = lv.get("municipality_ids") if isinstance(lv, dict) else None
        if not isinstance(col, list) or not isinstance(ids, list) or len(col) != len(ids) or len(col) != len(ctx["counties"]):
            r.fail(f"{what}: value_source names {LENS_VALUE_FILES['municipality']} column {vs.get('key', lens.get('id'))!r}, "
                   f"which must hold one value per municipality ({len(ctx['counties'])})")
            return None
        return [col[k] if o >= 0 and 0 <= k < len(col) else None for o, k in zip(owner, county)]
    arr = ctx["w"].get(vs.get("field"))
    if not isinstance(arr, list) or len(arr) != n:
        r.fail(f"{what}: value_source.field {vs.get('field')!r} is not a per-cell array of world.json")
        return None
    mapping = vs.get("categoryValues") if isinstance(vs.get("categoryValues"), dict) else None
    out = []
    for o, v in zip(owner, arr):
        if o < 0 or v is None:
            out.append(None)
        else:
            out.append(mapping.get(str(v)) if mapping else v)
    if mapping:
        unshown = sorted({v for o, v in zip(owner, arr) if o >= 0 and v is not None and str(v) not in mapping})
        if unshown:
            r.warn(f"{what}: {sum(1 for o, v in zip(owner, arr) if o >= 0 and v in unshown)} land hexes have a {vs.get('field')} code the lens does not show {unshown} (they read as no data)")
    return out


def check_lens_values(r: Report, doc, ctx: dict | None, formats: dict) -> None:
    """lens-values.json: one value per municipality on the map for each statistical lens, null in Kosovo and Metohija."""
    if not need_keys(r, "lens-values.json", doc, ["version", "municipality_ids", "values"]):
        return
    fails_before = r.count("FAIL")
    ids, values = doc["municipality_ids"], doc["values"]
    if doc["version"] != 2:
        r.fail(f"lens-values.json: version is {doc['version']!r}, expected 2")
    if not isinstance(ids, list) or not ids or not all(isinstance(g, str) for g in ids):
        r.fail("lens-values.json: municipality_ids must be a non-empty list of id strings")
        return
    if ctx and ctx["counties"] and ids != [c.get("geoid") for c in ctx["counties"]]:
        r.fail("lens-values.json: municipality_ids must be world.json counties, in the same order")
    if not isinstance(values, dict) or set(values) != set(srb.STATISTICAL_LENSES):
        r.fail(f"lens-values.json: values must have exactly the statistical lenses {srb.STATISTICAL_LENSES}, got {sorted(values) if isinstance(values, dict) else type(values).__name__}")
        return
    kosovo = [i for i, g in enumerate(ids) if in_kosovo(g)]
    for lid, col in values.items():
        what = f"lens-values.json {lid}"
        if not isinstance(col, list) or len(col) != len(ids):
            r.fail(f"{what}: expected {len(ids)} values, got {len(col) if isinstance(col, list) else type(col).__name__}")
            continue
        bad = [i for i, v in enumerate(col) if v is not None and not is_num(v)]
        if bad:
            r.fail(f"{what}: {len(bad)} values are neither number nor null ({_sample(unit_label(ids[i]) for i in bad)})")
        kim = [ids[i] for i in kosovo if col[i] is not None]
        if kim:
            r.fail(f"{what}: {len(kim)} municipalities of Kosovo and Metohija have a value (every statistic there is null): {_sample(kim)}")
        if formats.get(lid) == "pct":
            over = [ids[i] for i, v in enumerate(col) if is_num(v) and abs(v) > 1 + 1e-9]
            if over:
                r.fail(f"{what}: {len(over)} values beyond ±1 for a pct lens (fractions, not percentages): {_sample(over)}")
    if r.count("FAIL") == fails_before:
        r.ok(f"lens-values.json: {len(ids)} municipalities × {len(values)} statistical lenses")


def check_counties(r: Report, doc, ctx: dict | None, cities: dict, source_ids: set | None) -> None:
    """counties.json: the municipalities table, its columns in srb.COUNTY_COLUMNS order."""
    if not need_keys(r, "counties.json", doc, ["vintage", "fields", "columns", "rows"]):
        return
    fails_before = r.count("FAIL")
    fields, cols, rows = doc["fields"], doc["columns"], doc["rows"]
    if not is_text(doc["vintage"]):
        r.fail("counties.json: vintage must be a non-empty string")
    fkeys = ["key", "label", "format", "unit", "higher_is", "source", "description"]
    if not (isinstance(fields, list) and all(isinstance(f, dict) and set(fkeys) <= f.keys() for f in fields)):
        r.fail(f"counties.json fields: each needs {', '.join(fkeys)}")
        return
    if [f["key"] for f in fields] != cols or cols != list(srb.COUNTY_COLUMNS):
        r.fail(f"counties.json: columns must be srb.COUNTY_COLUMNS in order {list(srb.COUNTY_COLUMNS)}, got {cols if isinstance(cols, list) else cols!r}")
        return
    bad = []
    for f, fmt in zip(fields, srb.COUNTY_COLUMN_FORMATS, strict=True):  # a column without a format must stop this, not shorten it
        if f["format"] != fmt or f["higher_is"] not in HIGHER_IS or not is_text(f["label"]) or not is_text(f["description"]) \
                or not is_text(f["source"]) or (f["unit"] is not None and not isinstance(f["unit"], str)):
            bad.append(f["key"])
        elif source_ids is not None and f["source"] not in source_ids:
            r.warn(f"counties.json field {f['key']}: source {f['source']!r} is not in sources.json")
    if bad:
        r.fail(f"counties.json fields: format must follow srb.COUNTY_COLUMN_FORMATS, with label, description, source and higher_is: {_sample(bad)}")
    if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(cols) for row in rows):
        r.fail(f"counties.json: rows must be lists of {len(cols)} values")
        return
    fmt = dict(zip(cols, srb.COUNTY_COLUMN_FORMATS, strict=True))
    okrugs = {s.get("fips") for s in ctx["states"] if isinstance(s, dict)} if ctx and ctx["states"] else None
    geoids = [c.get("geoid") for c in ctx["counties"]] if ctx and ctx["counties"] else None
    holds = set(k for k in (ctx["w"].get("county") or []) if is_int(k) and k >= 0) if ctx else set()
    errs = Counter()
    examples = defaultdict(list)

    def err(code, example):
        errs[code] += 1
        if len(examples[code]) < 3:
            examples[code].append(example)

    for index, row in enumerate(rows):
        rec = dict(zip(cols, row))
        geoid, label = rec["geoid"], rec["geoid"] if isinstance(rec["geoid"], str) else index
        if not (isinstance(geoid, str) and UNIT_ID.fullmatch(geoid)):
            err("geoid not 5 digits", geoid)
        for k, v in rec.items():
            if v is None:
                continue
            if fmt[k] == "text":
                if not isinstance(v, str):
                    err(f"{k} not text", v)
                continue
            if not is_num(v) or (fmt[k] == "int" and not is_int(v)):
                err(f"{k} not a whole number" if fmt[k] == "int" else f"{k} not a number", v)
            elif (fmt[k] == "pct" and not 0 <= v <= 1) or (k in ("population", "land_km2", "density") and v < 0) or (fmt[k] == "km2" and v <= 0):
                err(f"{k} out of range", v)
        kosovo = isinstance(rec["state"], str) and rec["state"] in srb.KIM_OBLASTI
        if okrugs is not None and rec["state"] not in okrugs:
            err("state not a world.json okrug id", rec["state"])
        if kosovo:
            for k in COUNTY_STAT_COLUMNS + ["city"]:
                if rec[k] is not None:
                    err("a statistic on a municipality of Kosovo and Metohija", f"{label} {k}={rec[k]!r}")
        else:
            for k in COUNTY_STAT_COLUMNS + ["land_km2"]:
                if rec[k] is None:
                    err("null outside Kosovo and Metohija", f"{label} {k}")
            for k in COUNTY_LAND:
                if rec[k] is None and (geoid in holds if geoids is None else geoids.index(geoid) in holds if geoid in geoids else False):
                    err("land share null although the municipality holds a hex", f"{label} {k}")
        if rec["city"] is not None:
            city = cities.get(rec["city"])
            if city is None:
                err("city not a cities.json id", rec["city"])
            elif not isinstance(city.get("counties"), list) or geoid not in city["counties"]:
                err("city whose counties do not list the municipality", f"{label} → {rec['city']}")
        if rec["cell"] is not None and ctx and holds:
            cell = rec["cell"]
            if not is_int(cell) or not 0 <= cell < ctx["n"] or ctx["w"]["county"][cell] != (geoids.index(geoid) if geoid in geoids else -1):
                err("cell not a hex of the municipality", f"{label} cell {cell!r}")
        if r.count("FAIL") - fails_before > 20:
            break
    for code, k in errs.items():
        r.fail(f"counties.json: {k} rows: {code} (e.g. {_sample(examples[code], 3)})")
    if geoids is not None and [row[cols.index("geoid")] for row in rows] != geoids:
        r.fail("counties.json: rows must be world.json municipalities, in the same order")
    if r.count("FAIL") == fails_before:
        r.ok(f"counties.json: {len(rows)} municipalities × {len(cols)} columns ({doc['vintage']})")


def check_kim_towns(r: Report, doc, ctx: dict | None) -> None:
    """kim_towns.json: the seat of every municipality of Kosovo and Metohija, on a hex of the region."""
    if not need_keys(r, "kim_towns.json", doc, ["version", "vintage", "sources", "towns"]):
        return
    fails_before = r.count("FAIL")
    towns = doc["towns"]
    if doc["version"] != 1 or not is_text(doc["vintage"]) or not isinstance(doc["sources"], list) or "kim" not in doc["sources"]:
        r.fail("kim_towns.json: version must be 1, vintage a string and sources must name kim")
    if not isinstance(towns, list) or not towns:
        r.fail("kim_towns.json: expected a non-empty list of towns")
        return
    kim = kim_owners(ctx)
    owner = ctx["owner"] if ctx else None
    W, H = (ctx or {}).get("width"), (ctx or {}).get("height")
    bad, outside, cells = 0, 0, Counter()
    for t in towns:
        what = f"kim_towns.json {t.get('name') if isinstance(t, dict) else t!r}"
        if not need_keys(r, what, t, ["name", "x", "y", "cell"]):
            continue
        if not (is_text(t["name"]) and is_num(t["x"]) and is_num(t["y"]) and is_int(t["cell"])):
            bad += 1
            continue
        cells[t["cell"]] += 1
        if ctx and (not 0 <= t["cell"] < ctx["n"] or (owner and owner[t["cell"]] not in kim)):
            bad += 1
        elif ctx and is_num(W) and is_num(H) and not (0 <= t["x"] <= W and 0 <= t["y"] <= H):
            outside += 1
    if bad:
        r.fail(f"kim_towns.json: {bad} towns malformed or not on a land hex of Kosovo and Metohija (need name, x, y and such a cell)")
    shared = [c for c, k in cells.items() if k > 1]
    (r.warn if shared else r.ok)(f"kim_towns.json: hexes holding more than one town: {len(shared)}" + (f" ({_sample(shared)})" if shared else ""))
    if outside:
        r.warn(f"kim_towns.json: {outside} towns outside the map")
    if r.count("FAIL") == fails_before:
        r.ok(f"kim_towns.json: {len(towns)} towns ({doc['vintage']})")


def check_sources(r: Report, doc) -> set | None:
    if not isinstance(doc, list):
        r.fail("sources.json: expected a list")
        return None
    fails_before = r.count("FAIL")
    keys = ["id", "title", "publisher", "homepage", "license", "description", "used_for", "vintage", "files"]
    ids = set()
    for s in doc:
        what = f"sources.json {ident(s)}"
        if not need_keys(r, what, s, keys):
            continue
        if s["id"] in ids:
            r.fail(f"{what}: duplicate id")
        ids.add(s["id"])
        if not (is_text(s["title"]) and is_text(s["publisher"]) and is_text(s["description"]) and isinstance(s["used_for"], list)):
            r.fail(f"{what}: title, publisher and description must be text and used_for a list")
        if not (is_text(s["vintage"]) or (isinstance(s["vintage"], dict) and s["vintage"])):
            r.fail(f"{what}: vintage must be a non-empty string or object")
        files = s["files"]
        bad = [f for f in files if not isinstance(f, dict) or not {"file", "url", "retrieved", "sha256", "bytes"} <= f.keys()] if isinstance(files, list) else files
        if bad:
            r.fail(f"{what}: {len(bad) if isinstance(bad, list) else type(files).__name__} file entries lack file/url/retrieved/sha256/bytes")
        elif not files:
            (r.note if s.get("curated") else r.warn)(
                f"{what}: read by hand, nothing fetched: the homepage is the citation" if s.get("curated")
                else f"{what}: no files cited (not fetched yet?)")
    if r.count("FAIL") == fails_before:
        r.ok(f"sources.json: {len(doc)} sources, {sum(len(s['files']) for s in doc if isinstance(s, dict) and isinstance(s.get('files'), list))} files")
    return ids


# ---------------------------------------------------------------- data quality


def _interim(interim_dir: Path, name: str):
    p = Path(interim_dir) / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError as exc:
        print(f"  NOTE  {name}.json interim: invalid JSON ({exc}); skipped")
        return None


def _interim_data(payload, name: str):
    """The `data` of an interim payload, or None."""
    return payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else None


def quality_density(r: Report, ctx: dict, docs: dict, density: list | None) -> None:
    """The density lens against the population. Hex by hex, Σ density × hex area against the people of the
    municipalities that hold a hex (hexes outsize small municipalities, so the ratio is information, not a test);
    municipality by municipality, density × land_km2 against the population (both rounded: a tolerance)."""
    counties = docs.get("counties.json") if isinstance(docs.get("counties.json"), dict) else None
    if not isinstance(counties, dict) or not isinstance(counties.get("rows"), list) or "density" not in (counties.get("columns") or []):
        r.note("density: no municipalities table to compare with")
        return
    cols = counties["columns"]
    table = [dict(zip(cols, row)) for row in counties["rows"] if isinstance(row, list) and len(row) == len(cols)]
    on_map = [t for t in table if not in_kosovo(t["geoid"])]
    hexes = set(k for k in (ctx["w"].get("county") or []) if is_int(k) and k >= 0) if ctx["owner"] else set()
    geoids = [c.get("geoid") for c in ctx["counties"]]
    drawn = [t for t in on_map if t["geoid"] in geoids and geoids.index(t["geoid"]) in hexes]
    undrawn = [t for t in on_map if t not in drawn]
    total = sum(t["population"] for t in on_map if is_num(t.get("population")))
    un_people = sum(t["population"] for t in undrawn if is_num(t.get("population")))
    r.note(
        f"municipalities without a hex: {len(undrawn)} of {len(on_map)} outside Kosovo and Metohija"
        + (f" ({_sample(t['name'] for t in undrawn)}), {un_people:,.0f} people = {un_people / total:.1%} of the population, not on the density lens" if undrawn and total else ""))
    if density and ctx["owner"]:
        hex_area = 1.5 * math.sqrt(3) * ctx["grid"]["radius"] ** 2
        kim = kim_owners(ctx)
        sigma = sum(v * hex_area for i, v in enumerate(density) if is_num(v) and ctx["owner"][i] >= 0 and ctx["owner"][i] not in kim)
        people = sum(t["population"] for t in drawn if is_num(t.get("population")))
        if people > 0:
            r.note(f"density lens: Σ density × hex area = {sigma / 1e6:.2f}M vs the population of the municipalities with a hex {people / 1e6:.2f}M "
                   f"(×{sigma / people:.2f}; hexes outsize small municipalities)")
    off = [t for t in on_map if t["density"] is not None and t["population"] and t["land_km2"]
           and abs(t["density"] * t["land_km2"] - t["population"]) > DENSITY_TOLERANCE * t["population"]]
    sample = _sample(f'{t["name"]} {t["density"]} × {t["land_km2"]} vs {t["population"]}' for t in off) if off else ""
    (r.warn if off else r.ok)(
        f"density × land_km2 against the population: {len(off)} of {len(on_map)} municipalities off by more than {DENSITY_TOLERANCE:.0%}"
        + (f" ({sample})" if off else ""))


def quality_nation_sum(r: Report, docs: dict, with_data: list) -> None:
    """nation.json's figures against the sum of the okruzi with statistics. Rounding is a NOTE; a wider gap is a WARN,
    since then the nation or an okrug is wrong and the two are read side by side."""
    nat = docs.get("nation.json") if isinstance(docs.get("nation.json"), dict) else None
    nation = nat.get("nation") if nat and isinstance(nat.get("nation"), dict) else None
    if not nation or not with_data:
        return
    keys = ["population", "employed", "gdp"] + [k for k in srb.YIELD_KEYS if k != "gold"]
    off, rounding = [], []
    for k in keys:
        mine = nation.get(k) if k in ("population", "employed", "gdp") else (nation.get("yields") or {}).get(k)
        theirs = sum((_rank_value(s, k) or 0) for s in with_data)
        if not is_num(mine):
            off.append(f"{k} {mine!r} vs {theirs:,.0f}")
        elif abs(mine - theirs) > max(1, NATION_SUM_TOLERANCE * abs(theirs)):
            off.append(f"{k} {mine!r} vs {theirs:,.0f}")
        elif abs(mine - theirs) > max(1, 1e-6 * abs(theirs)):
            rounding.append(f"{k} {mine!r} vs {theirs:,.0f}")
    if off:
        r.warn(f"nation.json: the nation is not the sum of the okruzi with statistics (more than {NATION_SUM_TOLERANCE:.0%} off): "
               f"{_sample(off, 6)}")
    elif rounding:
        r.note(f"nation.json: the nation differs from the sum of the okruzi with statistics by rounding: {_sample(rounding, 6)}")
    else:
        r.ok("nation.json: population, employed, GDP and the yields are the sum of the okruzi")


def quality_cities(r: Report, ctx: dict, cities: list) -> None:
    owner = ctx["owner"]
    if owner:
        wet = [(c["name"], c.get("population")) for c in cities if is_int(c.get("cell")) and 0 <= c["cell"] < ctx["n"] and owner[c["cell"]] < 0]
        (r.warn if wet else r.ok)(f"cities on non-land cells: {len(wet)}" + (f" ({_sample([n for n, _ in wet], 8)})" if wet else ""))
    by_cell = defaultdict(list)
    for c in cities:
        by_cell[c.get("cell")].append(c.get("name"))
    shared = {cell: names for cell, names in by_cell.items() if len(names) > 1}
    (r.warn if shared else r.ok)(
        f"cells holding more than one city: {len(shared)}" + (f" ({_sample(['+'.join(v) for v in shared.values()], 6)})" if shared else ""))


def quality_null_yields(r: Report, name: str, rows: list) -> None:
    """Null and zero yields outside Kosovo and Metohija. A zero is a WARN: a stand-in for unknown?"""
    nulls, zeros = Counter(), Counter()
    for row in rows:
        if row.get("fips") in srb.KIM_OBLASTI:
            continue
        for k, v in (row.get("yields") or {}).items():
            if v is None:
                nulls[k] += 1
            elif v == 0:
                zeros[k] += 1
    r.note(f"{name} null yields: {dict(nulls) or 'none'}")
    if zeros:
        r.warn(f"{name} yields exactly 0 (a stand-in for unknown?): {dict(zeros)}")


def quality_growth(r: Report, name: str, rows: list) -> None:
    """How many rows have a growth rate (pipeline/build/yields.py: growth says when a city has none)."""
    have = [row["growth"] for row in rows if is_num(row.get("growth"))]
    if not rows:
        return
    years = next((row.get("growth_years") for row in rows if row.get("growth_years")), None)
    span = f" {years[0]}→{years[1]}" if isinstance(years, list) and len(years) == 2 else ""
    rng = f", range {min(have):+.1%} … {max(have):+.1%}" if have else ""
    r.note(f"{name} growth{span}: {len(have)} of {len(rows)} have a rate{rng}")


def quality_rivers(r: Report, ctx: dict) -> None:
    W, H = ctx["width"], ctx["height"]
    if not (is_num(W) and is_num(H)):
        return
    outside_all, stray = [], 0
    for rv in ctx["rivers"]:
        pts = rv.get("pts") if isinstance(rv, dict) else None
        if not isinstance(pts, list):
            continue
        inside = [0 <= pts[j] <= W and 0 <= pts[j + 1] <= H for j in range(0, len(pts) - 1, 2)]
        if not any(inside):
            outside_all.append(rv.get("name"))
        stray += inside.count(False)
    if outside_all:
        r.warn(f"rivers entirely outside the map: {len(outside_all)} ({_sample(outside_all)})")
    elif stray:
        r.warn(f"rivers: {stray} vertices outside the map (the contract says clipped)")
    else:
        r.ok(f"rivers: all {len(ctx['rivers'])} inside the map")


def quality_lens_nulls(r: Report, ctx: dict, lenses: dict, values: dict) -> None:
    """Per lens, the share of null values where the data exists: over Serbia's hexes outside Kosovo and Metohija for
    a statistic, over every Serbian land hex for land."""
    if not ctx["owner"]:
        return
    kim = kim_owners(ctx)
    statistics = [i for i, o in enumerate(ctx["owner"]) if o >= 0 and o not in kim]
    land = [i for i, o in enumerate(ctx["owner"]) if o >= 0]
    for lens in lenses.get("lenses", []) if isinstance(lenses, dict) else []:
        vals = values.get(lens.get("id")) if isinstance(lens, dict) else None
        if not isinstance(vals, list) or len(vals) != ctx["n"]:
            continue
        where = statistics if lens.get("id") in srb.STATISTICAL_LENSES else land
        if not where:
            continue
        share = sum(1 for i in where if vals[i] is None) / len(where)
        what = "Serbian cells" if lens.get("id") in srb.STATISTICAL_LENSES else "Serbian land cells"
        (r.warn if share > LENS_NULL_WARN else r.ok)(f"lens {lens.get('id')}: {share:.1%} of {len(where)} {what} are null (warn above {LENS_NULL_WARN:.0%})")


def quality_unit_lists(r: Report, world_interim: dict | None, census: dict | None, rzs: dict | None) -> None:
    """The municipalities on the map against the units the census and the RZS publish a row for. A difference is a
    WARN unless it is explained: Kosovo and Metohija (no statistics), or an aggregate the map draws as its parts, or
    a part whose aggregate the source counts instead (Grad Novi Sad in the census of 2022)."""
    missing = [n for n, d in (("_world", world_interim), ("census", census), ("rzs_db", rzs)) if not isinstance(d, dict)]
    if missing:
        r.note(f"unit lists: the comparison of the map with the sources needs the _world, census and rzs_db interims ({', '.join(missing)} missing)")
        return
    on_map = [g for g in (world_interim.get("counties") or []) if isinstance(g, str)]
    on_map_set = set(on_map)
    tables = {"census": (census.get("units") or {}, lambda row: isinstance(row, dict), "census"),
              "rzs_db": (rzs.get("pop") or {}, lambda row: isinstance(row, list), "RZS estimates")}
    for name, (table, has_row, label) in tables.items():
        if not isinstance(table, dict):
            r.note(f"unit lists: {name} interim has no unit table; skipped")
            continue
        has = lambda u: isinstance(u, str) and has_row(table.get(u))
        extra = [u for u in table if has(u) and u not in on_map_set]
        lacking = [u for u in on_map if not has(u)]
        aggregates = [u for u in extra if territory.parts_of(u) != [u] and any(p in on_map_set for p in territory.parts_of(u))]
        drawn = lambda u: [p for p in territory.parts_of(territory.aggregate_of(u)) if p in on_map_set] if territory.aggregate_of(u) else []
        siblings = [u for u in extra if u not in aggregates and drawn(u)]
        strangers = [u for u in extra if u not in aggregates and u not in siblings]
        kim = [u for u in lacking if in_kosovo(u)]
        parts = [u for u in lacking if u not in kim and territory.aggregate_of(u) is not None
                 and not any(has(p) for p in territory.parts_of(territory.aggregate_of(u)))]
        lost = [u for u in lacking if u not in kim and u not in parts]
        if strangers:
            r.warn(f"{name}: {len(strangers)} units with a row are not on the map and are no part of one on it: {_sample(unit_label(u) for u in strangers)}")
        if siblings:
            r.warn(f"{name}: {len(siblings)} units with a row are parts of an aggregate the map draws only in part: "
                   + _sample(f"{unit_label(u)} (of {unit_label(territory.aggregate_of(u))}; on the map: {', '.join(drawn(u))})" for u in siblings))
        if lost:
            r.warn(f"{name}: {len(lost)} municipalities on the map have no row in the {label}: {_sample(unit_label(u) for u in lost)}")
        if parts:
            r.note(f"{name}: {len(parts)} municipalities on the map are parts of an aggregate the {label} counts instead: "
                   f"{_sample(unit_label(u) for u in parts)} (of {', '.join(unit_label(a) for a in dict.fromkeys(territory.aggregate_of(u) for u in parts))})")
        if kim:
            r.note(f"{name}: {len(kim)} municipalities of Kosovo and Metohija have no row in the {label} (it covers none of the region): {_sample(kim)}")
        if aggregates:
            r.note(f"{name}: {len(aggregates)} units with a row are not on the map because the map draws their parts: {_sample(unit_label(u) for u in aggregates)}")
        if not lacking and not extra:
            r.ok(f"{name}: the map's municipalities and the units with a row are the same")


# ---------------------------------------------------------------- entry point


def _load(r: Report, web_dir: Path, name: str, required: bool):
    p = Path(web_dir) / name
    if not p.exists():
        (r.fail if required else r.note)(f"{name}: missing" + ("" if required else " (optional, skipped)"))
        return None
    try:
        return json.loads(p.read_text())
    except ValueError as exc:
        r.fail(f"{name}: invalid JSON ({exc})")
        return None


LEVELS = ("PASS", "NOTE", "WARN", "FAIL")


def builder_checks() -> list[tuple[str, object]]:
    """(builder module name, check function) for every pipeline/build module that defines check(web_dir).

    Helpers without build() count too, so a module can check a file another builder writes.
    """
    import importlib
    import pkgutil

    from . import build as build_pkg

    out = []
    for m in sorted(pkgutil.iter_modules(build_pkg.__path__), key=lambda m: m.name):
        mod = importlib.import_module(f"{build_pkg.__name__}.{m.name}")
        fn = getattr(mod, "check", None)
        if callable(fn):
            out.append((m.name, fn))
    return out


def run_builder_checks(r: Report, web_dir: Path, checks=None) -> None:
    """Run each builder's check(web_dir) and add its lines to the report (prefixed with the builder name)."""
    checks = builder_checks() if checks is None else checks
    if not checks:
        return
    r.section("builder checks")
    for name, fn in checks:
        try:
            lines = fn(web_dir) or []
        except Exception as exc:  # a broken check must not hide the rest of the report
            r.fail(f"{name}: check() raised {type(exc).__name__}: {exc}")
            continue
        for item in lines:
            try:
                level, msg = item
            except (TypeError, ValueError):
                r.fail(f"{name}: check() returned {item!r}, expected (level, message)")
                continue
            level = str(level).upper()
            if level not in LEVELS:
                r.fail(f"{name}: unknown level {level!r} for: {msg}")
                continue
            r._add(level, f"{name}: {msg}")


def unchecked(web_dir: Path, checks: list) -> list[str]:
    """JSON files in web_dir that this run reads no check for: neither part 1 (REQUIRED, OPTIONAL) nor a builder's
    check(web_dir) covers them (a builder covers what its module's PRODUCES names)."""
    import importlib

    from . import build as build_pkg

    covered = set(REQUIRED) | set(OPTIONAL)
    for name, _ in checks:
        try:
            mod = importlib.import_module(f"{build_pkg.__name__}.{name}")
        except ImportError:  # a check handed in under a name that is not a builder module covers nothing by name
            continue
        covered |= set(getattr(mod, "PRODUCES", []))
    return sorted(p.name for p in Path(web_dir).glob("*.json") if p.name not in covered)


def run(web_dir: Path = WEB_DATA, interim_dir: Path = INTERIM, quiet: bool = False, builder_checks_=None) -> Report:
    """Run every check and return the report.

    builder_checks_: None = discover the builder check() functions (part 3); a list of (name, fn) to run those
    instead; [] to skip part 3.
    """
    r = Report(quiet)
    checks = builder_checks() if builder_checks_ is None else builder_checks_
    r.section("contracts")
    docs = {name: _load(r, web_dir, name, True) for name in REQUIRED}
    docs.update({name: _load(r, web_dir, name, False) for name in OPTIONAL})
    if Path(web_dir).is_dir():
        unknown = unchecked(web_dir, checks)
        if unknown:
            r.note(f"not checked (no check in pipeline/check.py or in a builder): {', '.join(unknown)}")
    ctx = check_world(r, docs["world.json"]) if docs["world.json"] is not None else None
    source_ids = check_sources(r, docs["sources.json"]) if docs["sources.json"] is not None else None
    yield_keys = check_nation(r, docs["nation.json"]) if docs["nation.json"] is not None else list(srb.YIELD_KEYS)
    cities: dict = {}
    if docs["cities.json"] is not None:
        cities = check_cities(r, docs["cities.json"], ctx, yield_keys)
    with_data: list = []
    if docs["states.json"] is not None:
        with_data = check_states(r, docs["states.json"], ctx, yield_keys)
    formats: dict = {}
    values: dict = {}
    if docs["lenses.json"] is not None:
        formats = check_lenses(r, docs["lenses.json"], ctx, source_ids, docs)
        for lens in (docs["lenses.json"].get("lenses") or []) if isinstance(docs["lenses.json"], dict) else []:
            if isinstance(lens, dict):
                vals = _lens_values(Report(True), f"lenses.json {ident(lens)}", lens, ctx, docs)
                if isinstance(vals, list):
                    values[lens.get("id")] = vals
    if docs["lens-values.json"] is not None:
        check_lens_values(r, docs["lens-values.json"], ctx, formats)
    if docs["counties.json"] is not None:
        check_counties(r, docs["counties.json"], ctx, cities, source_ids)
    if docs["kim_towns.json"] is not None:
        check_kim_towns(r, docs["kim_towns.json"], ctx)
    check_growth(r, docs)

    r.section("data quality")
    if ctx is None:
        r.note("world.json unusable; skipping the data-quality report")
        run_builder_checks(r, web_dir, checks)
        return r
    world_interim = _interim_data(_interim(interim_dir, "_world"), "_world")
    census = _interim_data(_interim(interim_dir, "census"), "census")
    rzs = _interim_data(_interim(interim_dir, "rzs_db"), "rzs_db")
    if isinstance(docs["lenses.json"], dict):
        quality_density(r, ctx, docs, values.get("density"))
        quality_lens_nulls(r, ctx, docs["lenses.json"], values)
    if isinstance(docs["cities.json"], list):
        cities_list = [c for c in docs["cities.json"] if isinstance(c, dict)]
        quality_cities(r, ctx, cities_list)
        quality_null_yields(r, "cities", cities_list)
        quality_growth(r, "cities", cities_list)
    if isinstance(docs["states.json"], list):
        states = [s for s in docs["states.json"] if isinstance(s, dict)]
        quality_null_yields(r, "okruzi", states)
        quality_growth(r, "okruzi", states)
        quality_nation_sum(r, docs, with_data)
    quality_rivers(r, ctx)
    quality_unit_lists(r, world_interim, census, rzs)
    run_builder_checks(r, web_dir, checks)
    return r


def main(web_dir: Path = WEB_DATA, interim_dir: Path = INTERIM) -> int:
    r = run(web_dir, interim_dir)
    print(f"\ncheck: {r.count('PASS')} pass, {r.count('WARN')} warn, {r.count('FAIL')} fail")
    return 1 if r.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
