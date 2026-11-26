"""The RZS dissemination database: population, vital statistics, wages, employment and life expectancy by unit.

pipeline.core.rzs exports the tables from the Statistical Office's database (data.stat.gov.rs); this module
turns them into the interim rzs_db, one table per topic over all 204 units of pipeline.core.territory.

* Kosovo and Metohija has no statistics here: null, never 0.
* Grad Beograd (79014) is not a row of the office's tables. Its counts are the sum of its 17 city municipalities
  (territory.parts_of); a rate, a share or a wage is never summed and stays null. The other aggregates (Grad Niš,
  Grad Novi Sad…) have rows of their own and keep them.
* A cell the office cannot fill arrives as "-" (status M) or as no row at all: both are null. A real zero is 0.

SELECTIONS pins every node id that is asked for, with the label it carries on the office's result page.
"""

from __future__ import annotations

import json

from ..core import rzs, territory
from ..core.source import Source, SourceInfo
from ..core.srb import INDUSTRIES

# Labels as the office writes them, in the trees and in the records.
TOTAL, MALE, FEMALE = "Ukupno", "Muško", "Žensko"  # nPol, nStarGrupa, nKD08
AGED_65 = ("65–69", "70–74", "75–79", "80–84", "85 i više godina")  # nStarGrupa: the five oldest groups
POPULATION = "Procene stanovništva, po starosti i polu, uporedni pregled na opštinskom nivou"  # skrIndikator
BIRTHS, DEATHS, NATURAL_INCREASE = "Živorođeni", "Umrli", "Stopa prirodnog priraštaja"  # skrIndikator
NET, GROSS = "Prosečne neto zarade", "Prosečne bruto zarade"  # skrIndikator
EMPLOYMENT = ("Zaposleni u pravnim licima, lica koja samostalno obavljaju delatnost, preduzetnici i zaposleni kod "
              "njih, po sektorima KD2010 i prema opštini rada (NSTJ)")  # skrIndikator
LIFE_EXPECTANCY = "Očekivano trajanje života živorođenih, prema skraćenim aproksimativnim tablicama mortaliteta"  # skrIndikator
NACE_LETTERS = [nace for _, nace, _ in INDUSTRIES]  # "A" … "S"

LATEST = {"202500": "2025"}  # agg-2 "Period": the year the one-year tables are read from

# Every node id this source selects, with the label it has on the dataset's result page (data.stat.gov.rs,
# languageCode=sr-Latn, read on 2026-11-26). Key: the export, cached as data/raw/rzs_db/<key>.json.
# The territory (agg-102, "Teritorija - NSTJ") is not listed: every unit outside Kosovo and Metohija that the
# dataset's tree has is selected, 174 today; Grad Beograd is in no tree.
# Exports are cached under their key, so after changing an id here run `pipeline fetch rzs_db --force`.
SELECTIONS = {
    "pop_estimate": {
        "dataset": "18010602",
        "indicators": {"18030302IND01": POPULATION},
        "dims": {
            "agg-40": {"0": TOTAL},  # Starosne grupe
            "agg-23": {"0": TOTAL},  # Pol
            "agg-2": {  # Period: one node a year, the id is the year followed by "00"
                "199100": "1991", "199200": "1992", "199300": "1993", "199400": "1994", "199500": "1995",
                "199600": "1996", "199700": "1997", "199800": "1998", "199900": "1999", "200000": "2000",
                "200100": "2001", "200200": "2002", "200300": "2003", "200400": "2004", "200500": "2005",
                "200600": "2006", "200700": "2007", "200800": "2008", "200900": "2009", "201000": "2010",
                "201100": "2011", "201200": "2012", "201300": "2013", "201400": "2014", "201500": "2015",
                "201600": "2016", "201700": "2017", "201800": "2018", "201900": "2019", "202000": "2020",
                "202100": "2021", "202200": "2022", "202300": "2023", "202400": "2024", "202500": "2025",
            },
        },
    },
    "pop_65": {
        "dataset": "18010602",
        "indicators": {"18030302IND01": POPULATION},
        "dims": {
            "agg-40": {"0": TOTAL, "65-69": AGED_65[0], "70-74": AGED_65[1], "75-79": AGED_65[2], "80-84": AGED_65[3], "85": AGED_65[4]},
            "agg-23": {"0": TOTAL},  # Pol
            "agg-2": LATEST,  # Period
        },
    },
    "births_deaths": {
        "dataset": "180304",
        "indicators": {"180304IND03": BIRTHS, "180304IND04": DEATHS, "180304IND10": NATURAL_INCREASE},
        "dims": {"agg-2": LATEST},  # Period
    },
    "wages": {
        "dataset": "2403040403",
        "indicators": {"2403040403IND01": NET, "2403040403IND02": GROSS},
        "dims": {"agg-2": LATEST},  # Period
    },
    "employment": {
        "dataset": "240205",
        "indicators": {"240205IND01": EMPLOYMENT},
        "dims": {
            "agg-101": {  # Delatnost KD2010
                "0": TOTAL,
                "A": "A - Poljoprivreda, šumarstvo i ribarstvo",
                "B": "B - Rudarstvo",
                "C": "C - Prerađivačka industrija",
                "D": "D - Snabdevanje električnom energijom, gasom, parom i klimatizacija",
                "E": "E - Snabdevanje vodom; upravljanje otpadnim vodama, kontrolisanje procesa uklanjanja otpada i "
                     "slične aktivnosti",
                "F": "F - Građevinarstvo",
                "G": "G - Trgovina na veliko i trgovina na malo; popravka motornih vozila i motocikala",
                "H": "H - Saobraćaj i skladištenje",
                "I": "I - Usluge smeštaja i ishrane",
                "J": "J - Informisanje i komunikacije",
                "K": "K - Finansijske delatnosti i delatnost osiguranja",
                "L": "L - Poslovanje nekretninama",
                "M": "M - Stručne, naučne i tehničke delatnosti",
                "N": "N - Administrativne i pomoćne uslužne delatnosti",
                "O": "O - Državna uprava i odbrana; obavezno socijalno osiguranje",
                "P": "P - Obrazovanje",
                "Q": "Q - Zdravstvena i socijalna zaštita",
                "R": "R - Umetnost; zabava i rekreacija",
                "S": "S - Ostale uslužne delatnosti",
            },
            "agg-2": LATEST,  # Period
        },
    },
    "life_expectancy": {
        "dataset": "18050202",
        "indicators": {"18030502IND01": LIFE_EXPECTANCY},
        "dims": {"agg-23": {"1": MALE, "2": FEMALE}, "agg-2": LATEST},  # Pol, Period
    },
}


# --- pure mappings: records in, a table out -----------------------------------------------------------------------

def _selected(rec: dict, indicator: str | None, dims: dict) -> bool:
    """True for a record that was asked for: its indicator starts with `indicator` (when given) and its dimension
    columns equal `dims`."""
    return (indicator is None or str(rec.get("skrIndikator", "")).startswith(indicator)) and all(
        rec.get(key) == value for key, value in dims.items())


def by_unit(records, indicator=None, **dims) -> dict[str, float | None]:
    """{unit_id: value} of the records whose skrIndikator starts with `indicator` (when given) and whose dimension
    columns equal `dims` exactly (e.g. nPol="Ukupno"); when a unit has several, the last one wins."""
    return {rzs.unit_id(rec): rzs.value(rec) for rec in records if _selected(rec, indicator, dims)}


def flagged(records, indicator=None, **dims) -> dict[str, str]:
    """{unit_id: status code} of the records (picked as in by_unit) whose IDStatusPodatka is not "A", the office's
    code for a final figure; M is "no value can exist", O "not available"."""
    return {rzs.unit_id(rec): str(rec["IDStatusPodatka"]) for rec in records
            if _selected(rec, indicator, dims) and rec.get("IDStatusPodatka", "A") != "A"}


def sum_parts(table, parts) -> float | None:
    """The sum of the values of `parts` in `table`; None when one of them is None or missing."""
    values = [table.get(part) for part in parts]
    return sum(values) if all(v is not None for v in values) else None


def over_units(table: dict[str, float | None], *, summed: bool) -> dict[str, float | None]:
    """`table` (unit → value) over every unit of territory.units().

    Kosovo and Metohija has no statistics here: None. An aggregate (territory.aggregates()) keeps the office's own
    value; without one, a count (`summed=True`) is the sum of its parts, while a rate, a share or a wage stays None:
    those are never summed.
    """
    out = {unit: None if unit.startswith("9") else table.get(unit) for unit in territory.units()}
    for aggregate in territory.aggregates():
        if out[aggregate] is None and summed:
            out[aggregate] = sum_parts(out, territory.parts_of(aggregate))
    return out


def year_of(records) -> int:
    """The year an export pinned to one period describes: nVrTacka, the same on every record."""
    years = {str(rec.get("nVrTacka")) for rec in records}
    if len(years) != 1:
        raise RuntimeError(f"expected the records of exactly one year, got {sorted(years)}")
    return int(years.pop())


def population(records) -> tuple[list[int], dict[str, list[float | None] | None]]:
    """(pop_years, pop) from the population records of both sexes and all ages.

    pop_years lists the years the records hold. pop maps every unit to one list in that order, None where the
    office has nothing, or to None when it has nothing in any year. Belgrade is summed year by year.
    """
    years = sorted({int(rec["nVrTacka"]) for rec in records})
    per_year = [over_units(by_unit(records, POPULATION, nVrTacka=str(year)), summed=True) for year in years]
    pop = {}
    for unit in territory.units():
        series = [table[unit] for table in per_year]
        pop[unit] = series if any(v is not None for v in series) else None
    return years, pop


def share_65(records) -> dict[str, float | None]:
    """{unit: the share of its population aged 65 and over, 0..1} from one year's population records by age group;
    None when the unit's total or one of the five oldest groups is missing."""
    out = {}
    for unit, total in by_unit(records, POPULATION, nStarGrupa=TOTAL).items():
        aged = {group: by_unit(records, POPULATION, nStarGrupa=group).get(unit) for group in AGED_65}
        aged_65 = sum_parts(aged, AGED_65)
        out[unit] = aged_65 / total if aged_65 is not None and total else None
    return out


def employment(records) -> dict[str, dict]:
    """{unit: {"total": n, "by_nace": {letter: n}}} over all units from one year's registered-employment records.

    total is the office's own "Ukupno" row: the sections are rounded one by one and need not add up to it.
    by_nace has every NACE section of srb.INDUSTRIES. Belgrade is the sum of its parts, total by total and
    section by section.
    """
    totals = over_units(by_unit(records, EMPLOYMENT, nKD08=TOTAL), summed=True)
    by_section: dict[str, list[dict]] = {letter: [] for letter in NACE_LETTERS}
    for rec in records:
        letter = str(rec.get("nKD08", "")).split(" - ", 1)[0]  # "A - Poljoprivreda…" → "A"
        if letter in by_section:
            by_section[letter].append(rec)
    sections = {}
    for letter, rows in by_section.items():
        sections[letter] = over_units(by_unit(rows, EMPLOYMENT), summed=True)
    return {unit: {"total": totals[unit], "by_nace": {letter: sections[letter][unit] for letter in NACE_LETTERS}}
            for unit in territory.units()}


def life_expectancy(records) -> dict[str, dict]:
    """{unit: {"m": years, "f": years}} over all units from one year's records; life expectancy is a rate, so an
    aggregate without the office's own row has None."""
    men = over_units(by_unit(records, LIFE_EXPECTANCY, nPol=MALE), summed=False)
    women = over_units(by_unit(records, LIFE_EXPECTANCY, nPol=FEMALE), summed=False)
    return {unit: {"m": men[unit], "f": women[unit]} for unit in territory.units()}


def published_units(ds: rzs.Dataset) -> list[str]:
    """The units of territory.units() outside Kosovo and Metohija that the dataset's territory tree lists."""
    in_tree = {node.id for node in ds.dims["agg-102"]}
    return [unit for unit in territory.units() if not unit.startswith("9") and unit in in_tree]


# --- the source --------------------------------------------------------------------------------------------------

class RzsDatabase(Source):
    info = SourceInfo(
        id="rzs_db",
        title="Diseminaciona baza podataka",
        publisher="Republički zavod za statistiku",
        homepage="https://data.stat.gov.rs/",
        license="Slobodno korišćenje uz navođenje izvora (RZS)",
        description="Procene stanovništva po opštinama za svaku godinu, živorođeni i umrli, stopa prirodnog "
                    "priraštaja, prosečne neto i bruto zarade, zaposleni po opštini rada i delatnosti (KD2010) i "
                    "očekivano trajanje života. Za Kosovo i Metohiju nema podataka (polja su prazna). Grad Beograd nema svoj "
                    "red u tabelama zavoda: njegovi brojevi su zbir 17 gradskih opština, a zarade, stope i udeli "
                    "ostaju bez podataka.",
        used_for=["Stanovništvo i procene", "Rad i zarade", "BDP po oblastima"],
    )

    def fetch(self, force: bool = False) -> None:
        for name, picked in SELECTIONS.items():
            ds = rzs.load_dataset(picked["dataset"], force=force)
            selection = {
                "indicators": list(picked["indicators"]),
                **{dim: list(ids) for dim, ids in picked["dims"].items()},
                "agg-102": published_units(ds),
            }
            known = set(ds.indicators) | {node.id for nodes in ds.dims.values() for node in nodes}
            forgotten = [node_id for ids in selection.values() for node_id in ids if node_id not in known]
            if forgotten:
                raise RuntimeError(f"{self.id}: dataset {ds.subarea} no longer has {forgotten}; update SELECTIONS")
            rzs.export(ds, selection, f"{name}.json", force=force)

    def _records(self, rel_path: str) -> list[dict]:
        """The records of a cached export."""
        path = self.raw_dir / rel_path
        if not path.exists():
            raise FileNotFoundError(f"{self.id}: {rel_path} is not cached (run: uv run python -m pipeline fetch {self.id})")
        records = json.loads(path.read_text(encoding="utf-8"))
        if not records:
            raise RuntimeError(f"{self.id}: the office answered no records for {rel_path}; the ids in SELECTIONS "
                               f"may be out of date")
        return records

    def process(self) -> dict:
        tables = {name: self._records(f"{name}.json") for name in SELECTIONS}
        pop_years, pop = population(tables["pop_estimate"])
        year = {name: year_of(records) for name, records in tables.items() if name != "pop_estimate"}
        vital = tables["births_deaths"]
        return {
            "vintage": {
                "pop_estimate": f"Procene stanovništva po opštinama, {pop_years[0]}–{pop_years[-1]}",
                "births": f"Živorođeni, {year['births_deaths']}",
                "deaths": f"Umrli, {year['births_deaths']}",
                "natural_increase": f"Stopa prirodnog priraštaja na 1 000 stanovnika, {year['births_deaths']}",
                "wages": f"Prosečne neto i bruto zarade u dinarima mesečno, {year['wages']}",
                "employment": f"Zaposleni po opštini rada i delatnosti, {year['employment']}",
                "life_expectancy": f"Očekivano trajanje života živorođenih, {year['life_expectancy']}",
            },
            "pop_years": pop_years,
            "pop": pop,
            "pop_65": {"year": year["pop_65"], "by_unit": over_units(share_65(tables["pop_65"]), summed=False)},
            "births": {"year": year["births_deaths"], "by_unit": over_units(by_unit(vital, BIRTHS), summed=True)},
            "deaths": {"year": year["births_deaths"], "by_unit": over_units(by_unit(vital, DEATHS), summed=True)},
            "natural_increase": {"year": year["births_deaths"],
                                 "by_unit": over_units(by_unit(vital, NATURAL_INCREASE), summed=False)},
            "wages": {"year": year["wages"],
                      "net": over_units(by_unit(tables["wages"], NET), summed=False),
                      "gross": over_units(by_unit(tables["wages"], GROSS), summed=False)},
            "employment": {"year": year["employment"], "by_unit": employment(tables["employment"])},
            "life_expectancy": {"year": year["life_expectancy"],
                                "by_unit": life_expectancy(tables["life_expectancy"])},
            "status": {
                "pop_estimate": flagged(tables["pop_estimate"], POPULATION, nVrTacka=str(pop_years[-1])),
                "births": flagged(vital, BIRTHS),
                "deaths": flagged(vital, DEATHS),
                "natural_increase": flagged(vital, NATURAL_INCREASE),
                "wages": flagged(tables["wages"]),
                "employment": flagged(tables["employment"], EMPLOYMENT, nKD08=TOTAL),
                "life_expectancy": flagged(tables["life_expectancy"]),
            },
            "_files": list(dict.fromkeys([f"pages/{picked['dataset']}.html" for picked in SELECTIONS.values()]
                                         + [f"{name}.json" for name in SELECTIONS])),
        }
