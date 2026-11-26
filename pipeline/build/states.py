"""Okruzi: the figures a city has, for Serbia's okruzi, with ranks and a label anchor; and the nation.

Sums are over the okrug's units on the map (_world.counties), each published row counted once (cities.unit_row).
Rates are never summed: the share aged 65+ is population-weighted, the net wage employment-weighted, and
unemployment is taken from the summed counts. GDP (gold) is the okrug's own figure from Eurostat, in euros (a
city's is only its share of it). Growth is the change of the summed population series since srb.GROWTH_YEARS[0].

Kosovo and Metohija has no statistics here: its five okruzi carry only their id, name, label anchor and land cover.

nation.json adds the 25 okruzi up into one row of the same shape (its ranks and energy stay null; its label and
land cover are taken over all their hexes) and exports srb.YIELDS and srb.INDUSTRY_NAMES for the browser.

The label is {x, y, angle: 0, size} at the centroid of the okrug's hexes. The font height grows with the square
root of their number and stays between 3 and 22 map km.
"""

from __future__ import annotations

import math

from ..core import srb, store, territory
from ..core.hexgrid import HexGrid
from ..core.srtext import okrug_name
from .cities import census_counts, centre_of, sum_values, unit_row, weighted_mean
from .yields import RANK_KEYS, growth, ranks, rank_value, yields_of

REQUIRES = ["census", "rzs_db", "gdp", "_world"]
PRODUCES = ["states.json", "nation.json"]

COUNTRY = "RS"  # the nation's row carries the country's id from the territory tree
ECONOMY_KEYS = ["population", "employed", "yields", "jobs", "median_income", "median_rent", "home_value",
                "rent_burden", "unemployment", "wage_net", "age65", "gdp", "gdp_year", "gdp_by_industry",
                "gdp_undisclosed", "gdp_estimated", "growth", "growth_years"]
MIN_LABEL_KM, MAX_LABEL_KM = 3.0, 22.0
LABEL_KM_PER_CELL = 3.2  # font height is about this × √(hexes), clamped to the range above


def figures(units: list[str], census: dict, rzs: dict) -> dict:
    """What the sources say about a set of units on the map, an okrug's or the whole nation's: the latest population,
    the population series, the census counts, the registered employment, and the 65+ share and the net wage as
    weighted means. Every row is read through cities.unit_row, so a published row is counted once; a unit without a
    row is left out of a sum, a published figure of None makes it unknown."""
    by_employment = rzs["employment"]["by_unit"]
    estimates = {u: unit_row(rzs["pop"], u) for u in units}  # None where the office publishes no estimates
    employment = {u: unit_row(by_employment, u) for u in units}  # None where it publishes no employment
    series = [s for s in estimates.values() if s]
    latest = [s[-1] if s else None for s in estimates.values()]
    return {
        "population": sum_values([s[-1] for s in series]),
        "pop_series": [sum_values([s[i] if len(s) > i else None for s in series]) for i in range(len(rzs["pop_years"]))],
        "census": census_counts([row for row in (unit_row(census["units"], u) for u in units) if row]),
        "employment": sum_values([row["total"] for row in employment.values() if row is not None]),
        "age65": weighted_mean([unit_row(rzs["pop_65"]["by_unit"], u) for u in units], latest),
        "wage_net": weighted_mean([unit_row(rzs["wages"]["net"], u) for u in units],
                                  [(employment[u] or {}).get("total") for u in units]),
    }


def economy(units: list[str], gdp_value, gdp_year: int, census: dict, rzs: dict) -> dict:
    """The figures an okrug and the nation share, in the order of ECONOMY_KEYS. `gdp_value` is in euros."""
    f = figures(units, census, rzs)
    counts = f["census"]
    g, years = growth(f["pop_series"], rzs["pop_years"])
    return {
        "population": round(f["population"]) if f["population"] is not None else None,
        "employed": counts["employed"],
        "yields": yields_of(counts["jobs"], gdp_value),
        "jobs": counts["jobs"],
        "median_income": None, "median_rent": None, "home_value": None, "rent_burden": None,  # not published below the region
        "unemployment": counts["unemployment"],
        "wage_net": round(f["wage_net"], 2) if f["wage_net"] is not None else None,
        "age65": round(f["age65"], 4) if f["age65"] is not None else None,
        "gdp": gdp_value,
        "gdp_year": gdp_year,
        "gdp_by_industry": None,
        "gdp_undisclosed": None,
        "gdp_estimated": None,
        "growth": g,
        "growth_years": years,
    }


def label_of(grid: HexGrid, cells) -> dict | None:
    """{x, y, angle: 0, size} at the centroid of some hexes, or None without a hex."""
    if not cells:
        return None
    x, y = centre_of(grid, cells)
    size = max(MIN_LABEL_KM, min(MAX_LABEL_KM, LABEL_KM_PER_CELL * math.sqrt(len(cells))))
    return {"x": round(x, 1), "y": round(y, 1), "angle": 0, "size": round(size, 1)}


def land_cover(world: dict, cells) -> dict | None:
    """The mean land-cover shares of some hexes, as 0..1 fractions, over the hexes that have samples; None when
    none has."""
    sampled = [c for c in cells if world["cover"][c] > 0]
    if not sampled:
        return None
    return {key: round(sum(column[c] for c in sampled) / len(sampled) / 100, 3) for key, column in world["pct"].items()}


def build() -> None:
    census = store.load_interim("census")
    rzs = store.load_interim("rzs_db")
    gdp = store.load_interim_payload("gdp")
    world = store.load_interim("_world")
    grid = HexGrid(**world["grid"])
    units_of: dict[str, list[str]] = {}  # okrug → its units on the map
    for unit in world["counties"]:
        units_of.setdefault(territory.oblast_of(unit), []).append(unit)

    okruzi, with_data = [], []
    for index, fips in enumerate(world["states"]):
        cells = [c for c, owner in enumerate(world["owner"]) if owner == index]
        row = {"fips": fips, "abbr": None, "name": okrug_name(territory.name(fips))}
        kosovo = fips in srb.KIM_OBLASTI
        if kosovo:
            row.update(dict.fromkeys(ECONOMY_KEYS))  # Kosovo and Metohija: on the map, without statistics
        else:
            nuts = gdp["data"]["nuts3"].get(fips)
            row.update(economy(units_of.get(fips, []), None if nuts is None else round(nuts * 1e6), gdp["data"]["year"], census, rzs))
            with_data.append(row)
        row.update(ranks=None if kosovo else {}, label=label_of(grid, cells), land=land_cover(world, cells), energy=None)
        okruzi.append(row)
    ranks(with_data, RANK_KEYS, value=rank_value)

    # The nation: the same sums over all the units of the okruzi with statistics, its GDP their added figures.
    with_data_fips = {s["fips"] for s in with_data}
    cells = [c for c, owner in enumerate(world["owner"]) if owner >= 0 and world["states"][owner] in with_data_fips]
    nation = {"fips": COUNTRY, "abbr": None, "name": territory.name(COUNTRY)}
    nation.update(economy([u for fips in with_data_fips for u in units_of.get(fips, [])],
                          sum_values([s["gdp"] for s in with_data]), gdp["data"]["year"], census, rzs))
    nation.update(ranks=None, label=label_of(grid, cells), land=land_cover(world, cells), energy=None)

    latest_year = rzs["pop_years"][-1]
    print(f"    {len(okruzi)} okruzi, {len(with_data)} with statistics; the nation is their sum")
    store.write_web("states.json", okruzi)
    store.write_web("nation.json", {
        "vintage": f"Procene RZS {latest_year} · Popis 2022",
        "year": latest_year,
        "gdp_vintage": gdp["vintage"],
        "nation": nation,
        "yields": srb.YIELDS,
        "industries": srb.INDUSTRY_NAMES,
    })
