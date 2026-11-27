"""Counties: one row per municipality on the map for the Explorer table (column-oriented).

The statistics are the numbers behind the lenses: lenses.unit_values computes them once for both files, so the
table and the lenses cannot disagree. The area and the density come from the world builder's polygon areas, the
land shares are the mean of the hex shares (_world.pct) over the municipality's hexes that have land-cover samples,
and `city` is the cities.json id of the city the municipality belongs to.

A municipality that holds no hex (one smaller than a hex) keeps its figures, but its `cell` and its land shares are
null: nothing on the map can be pointed at.
"""

from __future__ import annotations

from ..core import territory
from ..core.store import load_interim, write_web
from .lenses import round_value, unit_values, vintage_text

REQUIRES = ["_world", "_cities", "census", "rzs_db"]
PRODUCES = ["counties.json"]

LAND = {"forest": "Šuma", "crop": "Njive", "pasture": "Livade i pašnjaci", "developed": "Gradsko"}  # column → label; keys of _world.pct


def _field(key, label, fmt, unit, higher_is, source, description):
    return {"key": key, "label": label, "format": fmt, "unit": unit, "higher_is": higher_is, "source": source,
            "description": description}


def fields() -> list[dict]:
    """One entry per column, in column order."""
    popis = "po popisu stanovništva"
    return [
        _field("geoid", "Šifra", "text", None, "neutral", "rzs_db",
               "Petocifrena šifra opštine po nomenklaturi teritorijalnih jedinica Republičkog zavoda za statistiku."),
        _field("name", "Opština", "text", None, "neutral", "rzs_db", "Naziv opštine, odnosno grada."),
        _field("state", "Okrug", "text", None, "neutral", "rzs_db",
               "Okrug kome opština pripada, kao šifra (na primer RS216)."),
        _field("population", "Stanovništvo", "int", "stanovnika", "neutral", "rzs_db",
               "Procenjeni broj stanovnika opštine u poslednjoj godini procene."),
        _field("land_km2", "Površina", "km2", "km²", "neutral", "boundaries",
               "Površina opštine unutar njene granice, u izjednačenoj projekciji."),
        _field("density", "Gustina naseljenosti", "float", "stanovnika / km²", "neutral", "rzs_db",
               "Procenjeni broj stanovnika podeljen površinom opštine."),
        _field("age65", "Stariji od 65 godina", "pct", "stanovništva", "neutral", "rzs_db",
               "Udeo stanovništva starog 65 i više godina u proceni za poslednju godinu."),
        _field("education", "Visoko obrazovanje", "pct", "stanovništva", "good", "census",
               f"Udeo stanovništva starog 15 i više godina sa završenim visokim obrazovanjem, {popis}."),
        _field("wage_net", "Prosečna neto zarada", "rsd", "RSD", "good", "rzs_db",
               "Prosečna neto zarada u opštini u poslednjoj godini, u dinarima mesečno."),
        _field("unemployment", "Stopa nezaposlenosti", "pct", "aktivnog stanovništva", "bad", "census",
               f"Udeo nezaposlenih u aktivnom stanovništvu (zaposleni i nezaposleni), {popis}."),
        _field("manufacturing", "Prerađivačka industrija", "pct", "zaposlenih", "neutral", "census",
               f"Udeo zaposlenih u prerađivačkoj industriji (NACE odeljak C) u svim zaposlenima, {popis}."),
        _field("commute", "Rad u drugoj opštini", "pct", "zaposlenih", "neutral", "census",
               f"Udeo zaposlenih koji rade u drugoj opštini ili u drugom okrugu, {popis}."),
        _field("orthodox", "Pravoslavni", "pct", "stanovništva", "neutral", "census",
               f"Udeo pravoslavnih u ukupnom stanovništvu, {popis}."),
        _field("serbs", "Srbi", "pct", "stanovništva", "neutral", "census",
               f"Udeo Srba u ukupnom stanovništvu, {popis}."),
        _field("life_expectancy", "Očekivano trajanje života", "float", "godine", "good", "rzs_db",
               "Očekivano trajanje života pri rođenju: sredina vrednosti za muškarce i za žene."),
        _field("natural_increase", "Prirodni priraštaj", "float", "na 1.000 stanovnika", "neutral", "rzs_db",
               "Prirodni priraštaj na 1.000 stanovnika (živorođeni minus umrli) za poslednju godinu, kako ga objavljuje zavod."),
        _field("forest", "Šuma", "pct", "površine", "neutral", "landcover",
               "Udeo površine opštine pod šumom: srednja vrednost njenih hekseva."),
        _field("crop", "Njive", "pct", "površine", "neutral", "landcover",
               "Udeo površine opštine pod njivama: srednja vrednost njenih hekseva."),
        _field("pasture", "Livade i pašnjaci", "pct", "površine", "neutral", "landcover",
               "Udeo površine opštine pod livadama i pašnjacima: srednja vrednost njenih hekseva."),
        _field("developed", "Gradsko", "pct", "površine", "neutral", "landcover",
               "Udeo površine opštine sa gradskim zemljištem: srednja vrednost njenih hekseva."),
        _field("city", "Grad", "text", None, "neutral", "census",
               "Grad kome opština pripada: ona sama kada je grad, inače grad čija je gradska opština. Bez vrednosti "
               "kada ne pripada nijednom gradu."),
        _field("cell", "Heks", "int", None, "neutral", "boundaries",
               "Prvi heks opštine na mapi. Bez vrednosti za opštinu manju od heksa, koja nijedan heks ne drži."),
    ]


def land_shares(world: dict, cells: list) -> dict[str, float | None]:
    """Mean share of each land class over a municipality's hexes that have land-cover samples, as fractions of 1.
    None for a municipality with no such hex: that is no data, not 0."""
    sampled = [cell for cell in cells if world["cover"][cell] > 0]
    return {key: round(sum(world["pct"][key][cell] for cell in sampled) / len(sampled) / 100, 4) if sampled else None
            for key in LAND}


def record(geoid: str, cells: list, world: dict, cities: dict, census: dict, rzs: dict) -> dict:
    """One municipality's row as {column: value}, before rounding."""
    units = cities.get("units") or {}
    return {
        "geoid": geoid, "name": territory.name(geoid), "state": territory.oblast_of(geoid),
        **unit_values(geoid, world, census, rzs),
        **land_shares(world, cells),
        "city": (units.get(geoid) or {}).get("city"),
        "cell": cells[0] if cells else None,
    }


def build() -> None:
    world, cities, census, rzs = (load_interim(name) for name in REQUIRES)
    fs = fields()
    columns = [field["key"] for field in fs]
    fmt = {field["key"]: field["format"] for field in fs}
    records = [record(geoid, cells, world, cities, census, rzs) for geoid, cells in zip(world["counties"], world["cells_of_county"], strict=True)]
    rows = [[values[column] if fmt[column] == "text" else round_value(fmt[column], values[column]) for column in columns]
            for values in records]
    print(f"    {len(rows)} municipalities, {sum(1 for v in records if v['city'])} belonging to a city, "
          f"{sum(1 for v in records if v['forest'] is None)} without land shares")
    write_web("counties.json", {"vintage": vintage_text(rzs, census), "fields": fs, "columns": columns, "rows": rows})
