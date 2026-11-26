"""Lenses: per-hex map overlays built from the municipalities' statistics and from the land itself.

The office and the census publish per municipality, and nothing is known about where inside a municipality its
people are, so a statistical lens gives every hex of a municipality that municipality's value. Nothing is
interpolated and no municipality is split. Kosovo and Metohija is on the map but has no statistics, so its hexes
are null there, as are foreign land and water. The three land lenses are read hex by hex from world.json, where
the world builder keeps elevation, relief and the cover table, so they do cover Kosovo.

Whose figures stand for a municipality is pipeline.core.territory.data_unit's decision, made per source and, in
rzs_db, per table: the census of 2022 has Grad Novi Sad and not its two city municipalities.

`domain` is the 2nd–98th percentile of what the lens shows: of the municipalities' values for a statistical lens,
of the hexes' for elevation. counties.py goes through the same unit_values, so the table and the lenses never
disagree about a municipality.
"""

from __future__ import annotations

import json
import math
import re

from ..core import srb, territory
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "_cities", "census", "rzs_db", "world.json"]
PRODUCES = ["lenses.json", "lens-values.json"]

HEX_AREA_KM2 = 1.5 * math.sqrt(3) * srb.HEX_RADIUS_KM**2  # 64.95 km², an area of last resort (see land_area)
COVER_SHOWN = [1, 2, 4, 6, 7, 8, 9, 10]  # the classes of world.json's cover table that land_cover shows

GROUPS = [
    {"id": "people", "name": "Stanovništvo"},
    {"id": "work", "name": "Rad i zarade"},
    {"id": "identity", "name": "Identitet"},
    {"id": "life", "name": "Kvalitet života"},
    {"id": "land", "name": "Zemljište"},
]


def _lens(lid, group, name, unit, fmt, scale, higher_is, source, emoji, ramp, key=None) -> dict:
    """A lens's fixed part. `key` is the name of its value in unit_values (the counties.json column) where that
    differs from the lens id."""
    return {"id": lid, "key": key or lid, "group": group, "name": name, "unit": unit, "format": fmt, "scale": scale,
            "higher_is": higher_is, "source": source, "emoji": emoji, "ramp": ramp}


DIVERGING = ["#123c6b", "#2f6fae", "#a8cbe6", "#f5e6c4", "#e6a24a", "#a63d12"]  # a change: fewer at one end, more at the other

# The twelve statistical lenses, in the order the site lists them. None of this depends on the data.
UNIT_LENSES = [
    _lens("density", "people", "Gustina naseljenosti", "stanovnika / km²", "int", "log", "neutral", "rzs_db", "👥",
          ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]),
    _lens("pop_change", "people", "Promena broja stanovnika", "%", "pct", "linear", "neutral", "rzs_db", "📈", DIVERGING),
    _lens("natural_increase", "people", "Prirodni priraštaj", "na 1.000 stanovnika", "float", "linear", "neutral", "rzs_db", "👶",
          DIVERGING),
    _lens("age65", "people", "Stariji od 65 godina", "%", "pct", "linear", "neutral", "rzs_db", "👴",
          ["#00224e", "#35456c", "#666970", "#948e77", "#c8b866", "#fee838"]),
    _lens("education", "work", "Visoko obrazovanje", "%", "pct", "linear", "good", "census", "🎓",
          ["#08203e", "#0f4c81", "#2a7fc1", "#5fa8e0", "#a6d1f2", "#eaf5ff"]),
    _lens("wages", "work", "Prosečna neto zarada", "RSD", "rsd", "log", "good", "rzs_db", "💵",
          ["#3a1c0b", "#7a4413", "#b8781f", "#e3b23c", "#f6e27f", "#fffbe0"], key="wage_net"),
    _lens("unemployment", "work", "Stopa nezaposlenosti", "%", "pct", "linear", "bad", "census", "🙋",
          ["#1a0505", "#4a0f0f", "#80201a", "#b8452b", "#e07b54", "#f9c9a8"]),
    _lens("manufacturing", "work", "Prerađivačka industrija", "%", "pct", "linear", "neutral", "census", "⚙️",
          ["#121826", "#1f334d", "#35536f", "#5f7f98", "#9db4c6", "#e3edf4"]),
    _lens("commute", "work", "Rad u drugoj opštini", "%", "pct", "linear", "neutral", "census", "🚗",
          ["#2b0b1e", "#5e1742", "#93275f", "#c84f7c", "#ea8fa8", "#fbd9e1"]),
    _lens("orthodox", "identity", "Pravoslavni", "%", "pct", "linear", "neutral", "census", "☦️",
          ["#031c1a", "#0d4f49", "#1f857b", "#43b3a3", "#8dd9c9", "#e2f7ef"]),
    _lens("serbs", "identity", "Srbi", "%", "pct", "linear", "neutral", "census", "🇷🇸",
          ["#03051a", "#152a5c", "#24478f", "#3f6cbf", "#86a9e3", "#e6eefb"]),
    _lens("life_expectancy", "life", "Očekivano trajanje života", "godine", "float", "linear", "good", "rzs_db", "⏳",
          ["#0b2013", "#14401f", "#1f6b33", "#3a9450", "#7fc07a", "#d5efcd"]),
]

# The land lenses, read from world.json hex by hex. land_cover takes its ramp from its categories (see land_lenses).
ELEVATION = _lens("elevation", "land", "Nadmorska visina", "m", "int", "linear", "neutral", "dem", "⛰️",
                  ["#12261a", "#274a26", "#5d6b2f", "#9c8a52", "#c9b98a", "#f3efe4"])
RELIEF_CATEGORIES = [
    {"id": "flat", "name": "Ravnica", "color": "#6f9e4a"},
    {"id": "hills", "name": "Brdovito", "color": "#c2a24f"},
    {"id": "mountains", "name": "Planine", "color": "#8d6e63"},
    {"id": "peaks", "name": "Vrhovi", "color": "#efe9df"},
]
RELIEF = _lens("relief", "land", "Reljef", "", "category", "linear", "neutral", "dem", "🏔️",
               [c["color"] for c in RELIEF_CATEGORIES])
LAND_COVER = _lens("land_cover", "land", "Zemljišni pokrivač", "", "category", "linear", "neutral", "landcover", "🌿", [])

VALUE_KEYS = ["population", "land_km2", "density", "age65", "education", "wage_net", "unemployment", "manufacturing",
              "commute", "orthodox", "serbs", "life_expectancy", "natural_increase", "pop_change"]

# ---------------------------------------------------------------- the figures of one municipality


def ratio(rec: dict | None, num: list[str], den: list[str]) -> float | None:
    """Sum of a record's `num` fields ÷ sum of its `den` fields; None when a field is missing or nothing is divided."""
    if not isinstance(rec, dict) or any(rec.get(k) is None for k in num + den):
        return None
    total = sum(rec[k] for k in den)
    return sum(rec[k] for k in num) / total if total else None


def census_values(rec: dict | None) -> dict[str, float | None]:
    """The six census lenses from one census.units record, as fractions of 1."""
    rec = rec or {}
    return {
        "education": ratio(rec.get("education"), ["higher"], ["total15"]),
        "unemployment": ratio(rec.get("activity"), ["unemployed"], ["employed", "unemployed"]),
        "manufacturing": ratio(rec.get("industry"), ["C"], ["total"]),  # NACE section C
        "commute": ratio(rec.get("commute"), ["other_unit", "other_oblast"], ["total"]),
        "orthodox": ratio(rec.get("religion"), ["orthodox"], ["total"]),
        "serbs": ratio(rec.get("ethnicity"), ["srbi"], ["total"]),
    }


def change(series: list | None, years: list[int], base: int) -> float | None:
    """The last of a unit's series against its value in `base`: latest ÷ base − 1. None when either is missing."""
    if not series or base not in years:
        return None
    first, last = series[years.index(base)], series[-1]
    return last / first - 1 if first and last is not None else None


def _by_unit(rzs: dict, table: str) -> dict | None:
    return (rzs.get(table) or {}).get("by_unit")


def _value(rows: dict | None, unit: str):
    """The value that stands for a unit in one rzs_db table ({unit: value}); None when the office has nothing."""
    return territory.row_for(rows or {}, unit)


def rzs_values(rzs: dict, geoid: str) -> dict[str, float | None]:
    """What the rzs_db interim gives for one municipality: its estimates as the office publishes them."""
    series = _value(rzs.get("pop"), geoid)
    life = _value(_by_unit(rzs, "life_expectancy"), geoid)
    has_both = bool(life) and life.get("m") is not None and life.get("f") is not None
    return {
        "population": series[-1] if series else None,
        "pop_change": change(series, rzs.get("pop_years") or [], srb.LENS_CHANGE_YEARS[0]),
        "age65": _value(_by_unit(rzs, "pop_65"), geoid),
        "wage_net": _value((rzs.get("wages") or {}).get("net"), geoid),
        "natural_increase": _value(_by_unit(rzs, "natural_increase"), geoid),
        "life_expectancy": (life["m"] + life["f"]) / 2 if has_both else None,
    }


def land_area(world: dict, index: int) -> float | None:
    """km² of the municipality at `index` of _world.counties: its polygon's area in the equal-area projection. An
    interim from before the world builder measured polygons has no such array; then whole hexes × the hex area."""
    if "county_area_km2" in world:
        return world["county_area_km2"][index]
    return len(world["cells_of_county"][index]) * HEX_AREA_KM2


def unit_values(geoid: str, world: dict, census: dict, rzs: dict) -> dict[str, float | None]:
    """Every number the unit lenses and counties.json show for one municipality, unrounded.

    None wherever a term is missing, and for everything statistical in Kosovo and Metohija: the sources have
    nothing for it, and the site must show nothing."""
    values = dict.fromkeys(VALUE_KEYS)
    if geoid not in world["counties"]:
        return values
    values["land_km2"] = land_area(world, world["counties"].index(geoid))
    if territory.in_kosovo(geoid):
        return values
    units = census.get("units") or {}
    row = units.get(territory.data_unit(geoid, lambda u: isinstance(units.get(u), dict)))
    values.update(rzs_values(rzs, geoid))
    values.update(census_values(row))
    area = values["land_km2"]
    values["density"] = values["population"] / area if values["population"] is not None and area and area > 0 else None
    return values


# ---------------------------------------------------------------- hexes and colours


def spread(values: list, owner: list, county: list) -> list:
    """Per hex, the value of the municipality that owns it (`values` in _world.counties order): None on water and
    foreign land, and wherever the municipality has no value."""
    return [values[k] if o >= 0 and k >= 0 else None for o, k in zip(owner, county)]


def percentile_domain(values: list, log: bool = False) -> list | None:
    """[2nd, 98th percentile] of the values that exist, only the positive ones on a log scale.

    Nearest-rank: the value at rank ceil(p × n / 100), so each end is a value something on the map has. None when
    no value is left."""
    vals = sorted(v for v in values if v is not None and (v > 0 or not log))
    if not vals:
        return None
    n = len(vals)
    return [vals[-(-2 * n // 100) - 1], vals[-(-98 * n // 100) - 1]]


def round_value(fmt: str, v) -> float | int | None:
    """A number the way its format shows it: shares to 4 decimals, kilometres and other decimals to 1, whole numbers whole."""
    if v is None:
        return None
    if fmt == "pct":
        return round(v, 4)
    return round(v, 1) if fmt in ("float", "km2") else int(round(v))


# ---------------------------------------------------------------- what the lenses say

RZS = "Republičkog zavoda za statistiku"  # in the genitive, as the notes use it
NO_KOSOVO = " Za Kosovo i Metohiju nema podataka."
DOMAIN_OF_OPSTINE = " Boje obuhvataju od 2. do 98. percentila opština; vrednosti izvan tog opsega prikazuju se krajnjim bojama."
DOMAIN_OF_HEKSEVI = " Boje obuhvataju od 2. do 98. percentila hekseva; vrednosti izvan tog opsega prikazuju se krajnjim bojama."


def _edition(interim: str) -> str | None:
    """The edition a source interim names for its data (its payload's vintage); None without an interim or a vintage."""
    try:
        vintage = load_interim_payload(interim).get("vintage")
    except FileNotFoundError:
        return None
    return vintage.strip() or None if isinstance(vintage, str) else None


def year_in(text: str) -> str | None:
    """The first four-digit year in a text."""
    found = re.search(r"\d{4}", text)
    return found.group() if found else None


def _source(name: str, edition: str | None) -> str:
    """'Copernicus GLO-30, izdanje 2021' – or the edition alone when it already names the source."""
    if not edition:
        return name
    return edition if name.lower() in edition.lower() else f"{name}, izdanje {edition}"


def _km2(area: float) -> str:
    return f"{area:.2f}".replace(".", ",")  # the site writes a decimal comma


def _years(rzs: dict, census: dict, world: dict) -> dict:
    """What the notes and the vintage cite. No year is typed into a text: each comes from the interim that owns it."""
    return {
        "base": srb.LENS_CHANGE_YEARS[0], "latest": rzs["pop_years"][-1],
        "pop_65": rzs["pop_65"]["year"], "wages": rzs["wages"]["year"],
        "natural_increase": rzs["natural_increase"]["year"], "life_expectancy": rzs["life_expectancy"]["year"],
        "census": census["vintage"], "dem": _edition("dem"), "landcover": _edition("landcover"),
        "area_note": "" if "county_area_km2" in world else (
            " Interim _world nema površine opština, pa je površina opštine broj njenih hekseva × "
            f"{_km2(HEX_AREA_KM2)} km²."),
    }


def vintage_text(rzs: dict, census: dict) -> str:
    """The vintage of lenses.json and counties.json: the latest estimate and the census, as their interims name them."""
    latest = rzs["pop_years"][-1]
    year = year_in(census["vintage"])
    return f"Procene RZS {latest} · Popis {year}" if year else f"Procene RZS {latest} · {census['vintage']}"


def _notes(w: dict) -> dict[str, str]:
    """Every lens's note: the caveat the legend always shows, naming the year and the source it was computed from."""
    popis = f"{w['census']}, Republički zavod za statistiku"
    dem = _source("Copernicus GLO-30", w["dem"])
    worldcover = _source("ESA WorldCover", w["landcover"])
    return {
        "density": f"Procena broja stanovnika {RZS} za {w['latest']}. godinu, podeljena površinom opštine.{NO_KOSOVO}",
        "pop_change": f"Procena broja stanovnika {RZS}: {w['latest']}. godina prema {w['base']}. godini.{NO_KOSOVO}",
        "natural_increase": f"Prirodni priraštaj na 1.000 stanovnika po podacima {RZS} za {w['natural_increase']}. godinu.{NO_KOSOVO}",
        "age65": f"Udeo stanovništva starog 65 i više godina u proceni {RZS} za {w['pop_65']}. godinu.{NO_KOSOVO}",
        "education": f"Udeo stanovništva starog 15 i više godina sa završenim visokim obrazovanjem. Izvor: {popis}.{NO_KOSOVO}",
        "wages": f"Prosečna neto zarada po podacima {RZS} za {w['wages']}. godinu.{NO_KOSOVO}",
        "unemployment": f"Udeo nezaposlenih u aktivnom stanovništvu. Izvor: {popis}.{NO_KOSOVO}",
        "manufacturing": f"Udeo zaposlenih u prerađivačkoj industriji. Izvor: {popis}.{NO_KOSOVO}",
        "commute": f"Udeo zaposlenih koji rade u drugoj opštini ili u drugom okrugu. Izvor: {popis}.{NO_KOSOVO}",
        "orthodox": f"Udeo pravoslavnih u ukupnom stanovništvu. Izvor: {popis}.{NO_KOSOVO}",
        "serbs": f"Udeo Srba u ukupnom stanovništvu. Izvor: {popis}.{NO_KOSOVO}",
        "life_expectancy": f"Očekivano trajanje života pri rođenju za {w['life_expectancy']}. godinu po podacima {RZS}: "
                           f"sredina vrednosti za muškarce i za žene.{NO_KOSOVO}",
        "elevation": f"Nadmorska visina heksa. Izvor: {dem}.",
        "relief": f"Reljef heksa. Izvor: {dem}.",
        "land_cover": f"Zemljišni pokrivač heksa. Izvor: {worldcover}.",
    }


def _descriptions(w: dict) -> dict[str, str]:
    """What each lens measures; the years in them come from the interims, like the years in the notes."""
    return {
        "density": "Procenjeni broj stanovnika opštine po km²: najnovija procena podeljena površinom opštine." + w["area_note"],
        "pop_change": f"Koliko se procenjeni broj stanovnika opštine promenio od {w['base']}. do {w['latest']}. godine, "
                      f"u odnosu na {w['base']}. godinu.",
        "natural_increase": "Prirodni priraštaj opštine na 1.000 stanovnika (živorođeni minus umrli), kako ga objavljuje zavod.",
        "age65": "Udeo stanovništva opštine starog 65 i više godina.",
        "education": "Udeo stanovništva starog 15 i više godina sa završenim visokim obrazovanjem.",
        "wages": "Prosečna neto zarada u opštini, u dinarima mesečno.",
        "unemployment": "Stopa nezaposlenosti: udeo nezaposlenih u aktivnom stanovništvu (zaposleni i nezaposleni).",
        "manufacturing": "Udeo zaposlenih u prerađivačkoj industriji (NACE odeljak C) u svim zaposlenima opštine.",
        "commute": "Udeo zaposlenih koji rade u drugoj opštini ili u drugom okrugu, u svim zaposlenima.",
        "orthodox": "Udeo pravoslavnih u ukupnom stanovništvu opštine.",
        "serbs": "Udeo Srba u ukupnom stanovništvu opštine.",
        "life_expectancy": "Očekivano trajanje života pri rođenju, u godinama: sredina vrednosti za muškarce i za žene.",
        "elevation": "Srednja nadmorska visina heksa u metrima, iz digitalnog modela reljefa.",
        "relief": "Oblik reljefa heksa, prema razlici najviše i najniže tačke i srednjoj nadmorskoj visini.",
        "land_cover": "Zemljišni pokrivač koji zauzima najveći deo heksa.",
    }


# ---------------------------------------------------------------- the builder


def _world_json() -> dict:
    path = WEB_DATA / "world.json"
    if not path.exists():
        raise FileNotFoundError("web/data/world.json missing – run: uv run python -m pipeline build world")
    return json.loads(path.read_text())


def _emit(meta: dict, values: list, domain: list | None, description: str, note: str, categories: list | None = None) -> dict:
    """One lens as lenses.json carries it, its keys in the order the contract lists them."""
    lens = {
        "id": meta["id"], "group": meta["group"], "name": meta["name"], "icon": f"l-{meta['id']}", "emoji": meta["emoji"],
        "unit": meta["unit"], "format": meta["format"], "scale": meta["scale"], "domain": domain, "ramp": meta["ramp"],
        "higher_is": meta["higher_is"], "source": meta["source"], "description": description, "note": note,
    }
    if categories is not None:
        lens["categories"] = categories
    lens["values"] = values
    return lens


def land_lenses(owner: list, world_json: dict, when: dict) -> list[dict]:
    """elevation, relief and land_cover: read hex by hex from world.json, so they cover Kosovo and Metohija too."""
    mine = [o >= 0 for o in owner]

    def per_hex(cells: list, value) -> list:
        """value(hex) wherever the hex is Serbia's; None elsewhere."""
        return [value(v) if ok and v is not None else None for ok, v in zip(mine, cells)]

    table = {entry["id"]: entry for entry in world_json["tables"]["cover"]}
    missing = [i for i in COVER_SHOWN if i not in table]
    if missing:
        raise ValueError(f"world.json tables.cover has no class {missing}: the land_cover lens cannot be built")
    index = {cover_id: k for k, cover_id in enumerate(COVER_SHOWN)}
    categories = [{"id": table[i]["key"], "name": table[i]["name"], "color": table[i]["color"]} for i in COVER_SHOWN]

    elevation = per_hex(world_json["elev"], lambda e: int(round(e)))
    relief = per_hex(world_json["relief"], int)
    cover = per_hex(world_json["cover"], index.get)
    notes, descriptions = _notes(when), _descriptions(when)
    return [
        _emit(ELEVATION, elevation, percentile_domain(elevation), descriptions["elevation"] + DOMAIN_OF_HEKSEVI, notes["elevation"]),
        _emit(RELIEF, relief, [0, len(RELIEF_CATEGORIES) - 1], descriptions["relief"], notes["relief"], RELIEF_CATEGORIES),
        _emit({**LAND_COVER, "ramp": [c["color"] for c in categories]}, cover, [0, len(COVER_SHOWN) - 1],
              descriptions["land_cover"], notes["land_cover"], categories),
    ]


def build() -> None:
    world, census, rzs = load_interim("_world"), load_interim("census"), load_interim("rzs_db")
    world_json = _world_json()
    when = _years(rzs, census, world)
    notes, descriptions = _notes(when), _descriptions(when)
    geoids = world["counties"]
    rows = [unit_values(geoid, world, census, rzs) for geoid in geoids]
    owner, county = world["owner"], world["county"]

    lenses, indexed_values = [], {}
    for meta in UNIT_LENSES:
        per_opstina = [round_value(meta["format"], row[meta["key"]]) for row in rows]
        indexed_values[meta["id"]] = per_opstina
        lens = _emit(meta, [], percentile_domain(per_opstina, meta["scale"] == "log"),
                     descriptions[meta["id"]] + " Svaki heks nosi vrednost svoje opštine." + DOMAIN_OF_OPSTINE,
                     notes[meta["id"]])
        del lens["values"]
        lens["value_source"] = {"kind": "municipality", "file": "lens-values.json", "key": meta["id"]}
        lenses.append(lens)
    for lens, field in zip(land_lenses(owner, world_json, when), ("elev", "relief", "cover")):
        del lens["values"]
        source = {"kind": "world", "field": field}
        if field == "cover":
            source["categoryValues"] = {str(code): i for i, code in enumerate(COVER_SHOWN)}
        lens["value_source"] = source
        lenses.append(lens)

    if "county_area_km2" not in world:
        print(f"    _world has no county_area_km2: areas are whole hexes × {_km2(HEX_AREA_KM2)} km²")
    for interim, which in (("dem", "elevation and relief"), ("landcover", "land_cover")):
        if not when[interim]:
            print(f"    ! interim {interim} names no vintage: the {which} note names no year")
    without = [g for g, row in zip(geoids, rows) if row["population"] is None and not territory.in_kosovo(g)]
    print(f"    {len(geoids)} municipalities, {len(without)} outside Kosovo and Metohija without a population estimate"
          + (f": {', '.join(without)}" if without else ""))
    write_web("lenses.json", {"version": 2, "vintage": vintage_text(rzs, census), "groups": GROUPS, "lenses": lenses})
    write_web("lens-values.json", {"version": 2, "municipality_ids": geoids, "values": indexed_values})
