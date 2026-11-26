"""GDP by oblast (Eurostat nama_10r_3gdp): the gold of every okrug, in millions of euro at current prices.

Eurostat publishes the series for Serbia's NUTS regions except Kosovo and Metohija, where it publishes nothing for
Serbia. The newest year fills in late (in November 2026 the oblasti end at 2023), so the year taken is the newest in
which all 25 oblasti answer, and the vintage says when any value is still provisional. The regions (NUTS 2) are taken
as Eurostat publishes them, not as sums of their oblasti.
"""

from __future__ import annotations

import json
from collections import defaultdict

from ..core import jsonstat, srb, territory
from ..core.source import Source, SourceInfo

DATASET = "nama_10r_3gdp"
FILE = f"{DATASET}.json"
TITLE = f"BDP po oblastima ({DATASET})"
UNIT = "MIO_EUR"
YEARS = tuple(range(2019, 2025))  # asked of Eurostat; the answer decides which year is taken
PROVISIONAL = "p"  # Eurostat's status for a value that may still change


def oblasti() -> list[str]:
    """The 25 oblasti Eurostat publishes GDP for: the level-3 ids of the tree outside Kosovo and Metohija."""
    return sorted(k for k, v in territory.nodes().items() if v["level"] == 3 and k not in srb.KIM_OBLASTI)


def regioni() -> list[str]:
    """The 4 regions, the level-2 ids of the tree outside Kosovo and Metohija."""
    return sorted(k for k, v in territory.nodes().items() if v["level"] == 2 and k != srb.KIM_REGION)


def request_url() -> str:
    """Eurostat's answer for every oblast and region. A list goes as a repeated parameter: joined with commas, it is a 400."""
    return srb.EUROSTAT_GDP_URL.format(
        dataset=DATASET, geos="&geo=".join(oblasti() + regioni()), unit=UNIT, times="&time=".join(map(str, YEARS))
    )


def pick_year(cells: list[dict]) -> int:
    """The latest year in which each of the 25 oblasti has a value."""
    answered: dict[int, set[str]] = defaultdict(set)
    for cell in cells:
        if cell["value"] is not None:
            answered[int(cell["time"])].add(cell["geo"])
    wanted = set(oblasti())
    for year in sorted(answered, reverse=True):
        if wanted <= answered[year]:
            return year
    raise RuntimeError("Eurostat has no year in which all 25 oblasti have a value")


def values(cells: list[dict], year: int, ids) -> dict:
    """{id: value} of `ids` in one year, in the order of `ids`. An id without a value is left out: no data is never a number."""
    published = {c["geo"]: c["value"] for c in cells if int(c["time"]) == year and c["value"] is not None}
    return {geo: published[geo] for geo in ids if geo in published}


def provisional(cells: list[dict], year: int, ids=None) -> list[str]:
    """The ids of one year whose Eurostat status is provisional, sorted: every id, or only those among `ids`."""
    wanted = {c["geo"] for c in cells} if ids is None else set(ids)
    return sorted(
        c["geo"] for c in cells
        if int(c["time"]) == year and c["geo"] in wanted and c["value"] is not None and c["status"] == PROVISIONAL
    )


def vintage(year: int, provisional_ids) -> str:
    """What was published, for which year, and whether any id in it is still provisional."""
    return f"Eurostat, {TITLE}, {year}" + (" — privremeni podaci" if provisional_ids else "")


def summarize(cells: list[dict]) -> dict:
    """The interim's content from a response's cells.

    `provisional` holds oblasti only, so it is always a subset of `nuts3`'s keys: a consumer that walks the list and
    indexes `nuts3` never meets a region. The vintage looks at both levels.
    """
    year = pick_year(cells)
    return {
        "vintage": vintage(year, provisional(cells, year)),
        "year": year,
        "unit": UNIT,
        "nuts3": values(cells, year, oblasti()),
        "nuts2": values(cells, year, regioni()),
        "provisional": provisional(cells, year, oblasti()),
    }


class Gdp(Source):
    info = SourceInfo(
        id="gdp",
        title=TITLE,
        publisher="Eurostat",
        homepage="https://ec.europa.eu/eurostat/web/regions",
        license="© Evropska unija, 1995–2026, CC BY 4.0",
        description="Bruto domaći proizvod u tekućim evrima po oblastima i regionima Srbije bez Kosova i Metohije, za koji "
                    "Eurostat ne objavljuje podatke. Uzima se najnovija godina u kojoj svih 25 oblasti ima vrednost; "
                    "vrednosti koje su još privremene označene su.",
        used_for=["Prinos Zlato (BDP)", "BDP okruga, regiona i gradova"],
    )

    def fetch(self, force=False):
        self.download(request_url(), FILE, force=force, expect_binary=True)

    def process(self) -> dict:
        with open(self.raw_dir / FILE, encoding="utf-8") as f:
            data = summarize(jsonstat.parse(json.load(f)))
        print(f"    year {data['year']}, {len(data['nuts3'])} oblasti, {len(data['nuts2'])} regioni, "
              f"{len(data['provisional'])} provisional")
        return {**data, "_files": [FILE]}
