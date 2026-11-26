"""The yields: which real numbers the game plays with.

Serbia's five yields are defined once in pipeline.core.srb (YIELDS) and reach the browser with nation.json, so the
UI and the Almanac always describe exactly what was computed. Gold is GDP (Eurostat, by oblast; a city's share of its
okrug's GDP is an estimate); the other yields count workers by industry where they live (Popis 2022, NACE sections).

This module holds the pure helpers about figures that cities and okruzi share: jobs, yields, growth, ranks and
peers. (cities.py holds the ones about units and hexes.) It has no build(): it is not a builder.
"""

from __future__ import annotations

import math

from ..core import srb

# What cities and okruzi are ranked on: the row's own numbers, GDP per resident, then the yields.
RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth"] + [y["key"] for y in srb.YIELDS]
PEERS = 5
GROWTH_LIMIT = 0.25  # a population change beyond this, either way, is a change of borders and is not believed


def jobs_from_nace(by_nace: dict[str, float | None]) -> dict[str, int | None]:
    """The census `industry` row → {industry key: whole jobs}, in srb.INDUSTRIES order.

    The row has one figure per NACE section, beside "total" and "unknown". Only the 19 sections of srb.INDUSTRIES
    are kept and each is rounded to whole jobs. None stays None, and a section the row does not have is None too:
    an unknown is never read as 0.
    """
    by_nace = by_nace or {}
    jobs = {}
    for key, nace, _ in srb.INDUSTRIES:
        value = by_nace.get(nace)
        jobs[key] = None if value is None else round(value)
    return jobs


def yields_of(jobs: dict, gdp: float | None) -> dict:
    """{yield key: value} in srb.YIELDS order. Gold is the GDP. Every other yield is the sum of its industries and is
    None when one of them is unknown."""
    jobs = jobs or {}
    out = {}
    for y in srb.YIELDS:
        if y["key"] == "gold":
            out[y["key"]] = gdp
            continue
        values = [jobs.get(k) for k in y["industries"]]
        out[y["key"]] = None if any(v is None for v in values) else sum(values)
    return out


def growth(series: list | None, years: list[int], start: int = srb.GROWTH_YEARS[0]) -> tuple[float | None, list[int] | None]:
    """(latest ÷ start − 1, [start year, latest year]) of a per-year series, the change rounded to 4 decimals.

    (None, None) when the start or the latest figure is missing, and when the change exceeds GROWTH_LIMIT either way.
    """
    points = list(zip(series or (), years))
    if not points:
        return None, None
    latest, latest_year = points[-1]
    first = next((value for value, year in points if year == start), None)
    if latest is None or not first:
        return None, None
    change = latest / first - 1
    if abs(change) > GROWTH_LIMIT:
        return None, None
    change = round(change, 4)
    return (0.0 if change == 0 else change), [start, latest_year]  # no "-0.0" in the data


def rank_value(row: dict, key: str):
    """The figure behind a rank key: GDP per resident is derived, the yields are read under "yields", the rest is the
    row's own."""
    if key == "gdp_per_capita":
        gdp, population = row.get("gdp"), row.get("population")
        return gdp / population if gdp is not None and population else None
    if key in srb.YIELD_KEYS:
        return (row.get("yields") or {}).get(key)
    return row.get(key)


def ranks(rows: list[dict], keys: list[str], value=lambda r, k: r.get(k)) -> None:
    """Write r["ranks"][key] for every row and key: 1 = the largest value, a tie going to the larger population and
    then to the earlier row; None where the value is None. Keys ranked before are kept."""
    for key in keys:
        have = [r for r in rows if value(r, key) is not None]
        have.sort(key=lambda r: (-value(r, key), -(r.get("population") or 0)))
        for place, r in enumerate(have, 1):
            r.setdefault("ranks", {})[key] = place
        for r in rows:
            r.setdefault("ranks", {}).setdefault(key, None)


def peers(rows, n: int = PEERS) -> None:
    """Write r["peers"]: the ids of the n other rows whose population is closest to r's by ratio (so 200 is as near
    to 100 as to 400); a tie keeps the row order. A row without a population has no peers."""
    with_population = [(i, r) for i, r in enumerate(rows) if r.get("population")]
    for i, r in enumerate(rows):
        near = []
        if r.get("population"):
            log_p = math.log(r["population"])
            near = sorted((abs(math.log(o["population"]) - log_p), j) for j, o in with_population if j != i)
        r["peers"] = [rows[j]["id"] for _, j in near[:n]]
