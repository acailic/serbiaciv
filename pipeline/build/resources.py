"""Resources layer: Serbia's real power plants, mines and the oil refinery, placed on the hex map.

Like strategic resources on a Civ tile, but only meaningful sites, with the figure that a public source publishes for
each one. The sites are curated in pipeline/data/resources_sites.csv (one reviewable row per site: id, name, type,
lon, lat, value, unit, year, detail, source); docs/SITES.md says where every figure and coordinate comes from.

Rules, published inside the file (types[].description and summary.note):
  * power plants (EPS and others) from 100 MW; wind farms from 50 MW; solar plants from 5 MW;
  * the EPS plants carry the net output capacity of the EPS Technical Report 2024, plants outside EPS the capacity
    their operator publishes; mines and the refinery carry a yearly quantity (USGS Minerals Yearbook, NIS);
  * a figure nobody publishes is null, never 0: totals are sums of the mapped sites, not national capacity.

Writes web/data/resources.json in the upstream usaciv shape: {types, items, summary}. `state` is the okrug id
("RS110"), `cbsa` the id of the city whose opštine contain the hex (the frontend reads `it.cbsa === city.id`).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.store import load_interim, write_web
from .sites import DATA, Placer, land_cells, read_sites, number

REQUIRES = ["_world", "_cities"]
PRODUCES = ["resources.json"]

CSV = "resources_sites.csv"
MIN_MW = 100      # thermal, gas and hydro plants below this are not mapped
MIN_WIND_MW = 50
MIN_SOLAR_MW = 5

ENERGY, MINERAL = "energy", "mineral"


def _type(id, name, category, emoji, color, unit, description, source):
    return {"id": id, "name": name, "category": category, "emoji": emoji, "icon": f"r-{id}", "color": color,
            "unit": unit, "description": description, "source": source}


TYPES = [
    _type("coal_plant", "Termoelektrana na lignit", ENERGY, "⚡", "#6f6f6f", "MW",
          f"Elektrane EPS na lignit iz kolubarskog i kostolačkog basena, od {MIN_MW} MW neto snage. Lignit pokriva "
          "oko polovine proizvodnje struje u Srbiji; svaka je na svom mestu uz površinski kop koji je snabdeva.",
          "eps_technical_report_2024"),
    _type("gas_plant", "Gasna elektrana (TE-TO)", ENERGY, "🔥", "#c9856a", "MW",
          f"Gasno-parne elektrane-toplane na prirodni gas, od {MIN_MW} MW: kombinovana proizvodnja struje i topline za "
          "Novi Sad (EPS) i Pančevo (Gazprom energoholding Srbija).",
          "nis_teto_pancevo"),
    _type("hydro", "Hidroelektrana", ENERGY, "💧", "#3b7dd8", "MW",
          f"Hidroelektrane EPS od {MIN_MW} MW neto snage: Đerdap 1 i 2 na Dunavu, Bajina Bašta na Drini, Zvornik na "
          "Drini i kaskada Vlasina (Vrla 1–4). Neto snaga iz Tehničkog godišnjaka EPS 2024.",
          "eps_technical_report_2024"),
    _type("pumped_storage", "Reverzibilna hidroelektrana", ENERGY, "🔄", "#6aa6e8", "MW",
          "Pumpno-akumulacione hidroelektrane: RHE Bajina Bašta (gornja akumulacija Zaovine na Tari) crpi vodu u "
          "akumulaciju kad ima viška struje i proizvodi u špicu. Nema drugih u Srbiji.",
          "eps_technical_report_2024"),
    _type("wind", "Vetropark", ENERGY, "🌬️", "#8fb4c2", "MW",
          f"Vetroparkovi od {MIN_WIND_MW} MW instalisane snage: Čibuk 1 i Kovačica na Banatu (poslovni) i VE Kostolac "
          "(EPS). Instalisana snaga operatora, ne neto.",
          "wind_parks_wikipedia"),
    _type("solar", "Solarna elektrana", ENERGY, "☀️", "#e3c14b", "MW",
          f"Solarne elektrane od {MIN_SOLAR_MW} MW instalisane snage. Prikazana je prva elektrana EPS-a na bivšem "
          "rudarskom odlagalištu (Petka, Kostolac); većina solarnih elektrana u Srbiji je u prometu preko "
          "podsticaja i nema objavljen kapacitet po lokaciji.",
          "se_petka_2025"),
    _type("coal_mine", "Rudnik lignita", MINERAL, "⛏️", "#3d3d3d", "t/god",
          "Površinski kopovi lignita EPS-a (MB Kolubara kod Vreoca, kop Drmno kod Kostolca) i podzemni kop Ibarskih "
          "rudnika (Baljevac): godišnja proizvodnja uglja, gde je objavljena.",
          "eps_technical_report_2024"),
    _type("copper", "Rudnik bakra", MINERAL, "🟠", "#c47a3a", "t/god",
          "Rudnici Zijin Copper u boranskom basenu (Veliki Krivelj, Majdanpek, Jama, Čukaru Peki): sadržaj bakra u "
          "koncentratu godišnje, procene USGS.",
          "usgs_minerals_yearbook_2024"),
    _type("lead_zinc", "Rudnik olova i cinka", MINERAL, "⚪", "#8a93a6", "t/god",
          "Rudnici olovo-cinkove rude (Mineco: Rudnik, Veliki Majdan; Farmakom: Lece): koncentrat godišnje po USGS; "
          "za Lece je objavljena samo količina rude, pa je vrednost null.",
          "usgs_minerals_yearbook_2024"),
    _type("oil", "Rafinerija nafte", MINERAL, "🛢️", "#2f2f2f", "t/god",
          "Rafinerija nafte Pančevo (NIS): projektovani kapacitet prerade 4,8 miliona tona godišnje; naftna polja u "
          "Banatu nemaju objavljen kapacitet po polju, pa nisu prikazana.",
          "nis_refinery_pancevo"),
]
RANK = {t["id"]: i for i, t in enumerate(TYPES)}
NOT_ADDITIVE: frozenset[str] = frozenset()

SUMMARY_NOTE = (
    "Zbirovi su zbirovi prikazanih lokacija, ne ukupni kapaciteti Srbije: elektrane EPS-a su neto snage iz Tehničkog "
    f"godišnjaka EPS za 2024. godinu, elektrane van EPS-a instalisana snaga operatora; prikazane su elektrane od "
    f"{MIN_MW} MW, vetroparkovi od {MIN_WIND_MW} MW i solarne elektrane od {MIN_SOLAR_MW} MW. Rudnici i rafinerija su "
    "godišnje količine (USGS 2024, NIS). Prazna vrednost znači da podatak nije objavljen."
)


def _tidy(name: str) -> str:
    return " ".join(name.split())


def items_from(rows: list[dict], placer: Placer) -> tuple[list[dict], list[str], list[str]]:
    """One item per CSV row, placed on Serbian land; rows whose type is unknown or whose figure is below the type's
    threshold are reported (and skipped) so the build cannot publish a site the rule text does not describe.
    The third list names the sites that had to move to the nearest Serbian land hex."""
    by_id = {t["id"]: t for t in TYPES}
    out, skipped, moved = [], [], []
    for row in rows:
        t = by_id.get(row["type"])
        value = number(row["value"])
        if t is None:
            skipped.append(f"{row['id']}: unknown type {row['type']}")
            continue
        if value is not None and (
                (t["id"] in ("coal_plant", "gas_plant", "hydro", "pumped_storage") and value < MIN_MW)
                or (t["id"] == "wind" and value < MIN_WIND_MW) or (t["id"] == "solar" and value < MIN_SOLAR_MW)):
            skipped.append(f"{row['id']}: {value} {t['unit']} below the {t['id']} threshold")
            continue
        pos = placer.place(float(row["lon"]), float(row["lat"]), okrug=row.get("okrug") or None)
        if pos.get("moved_to_land"):
            moved.append(row["name"])
        out.append({"type": t["id"], "name": _tidy(row["name"]), "x": pos["x"], "y": pos["y"], "cell": pos["cell"],
                    "value": value, "detail": _tidy(row["detail"]), "state": pos["state"], "cbsa": pos["cbsa"]})
    return out, skipped, moved


def summarize(items: list[dict], types: list[dict]) -> dict:
    """National and per-okrug {type: {count, value, unit}} over the mapped items; null values add nothing."""
    def blank(t):
        return {"count": 0, "value": None if t["id"] in NOT_ADDITIVE else 0, "unit": t["unit"]}

    by_id = {t["id"]: t for t in types}
    national = {t["id"]: blank(t) for t in types}
    states: dict[str, dict] = {}
    for it in items:
        t = by_id[it["type"]]
        rows = [national[t["id"]]]
        if it["state"]:
            rows.append(states.setdefault(it["state"], {}).setdefault(t["id"], blank(t)))
        for row in rows:
            row["count"] += 1
            if row["value"] is not None and it["value"] is not None:
                row["value"] += it["value"]
    for row in [*national.values(), *(r for st in states.values() for r in st.values())]:
        if row["value"] is not None:
            row["value"] = round(row["value"], 2)
    return {"note": SUMMARY_NOTE, "national": national, "states": dict(sorted(states.items()))}


def build() -> None:
    placer = Placer(load_interim("_world"), load_interim("_cities")["cities"])
    items, skipped, moved = items_from(read_sites(CSV), placer)
    if skipped:
        raise ValueError("resources_sites.csv: " + "; ".join(skipped))
    present = {it["type"] for it in items}
    types = [t for t in TYPES if t["id"] in present]
    write_web("resources.json", {"types": types, "items": items, "summary": summarize(items, types)})
    counts = Counter(it["type"] for it in items)
    print(f"    resources.json: {len(items)} sites: " + ", ".join(f"{t['id']} {counts[t['id']]}" for t in types))
    print(f"    moved to the nearest Serbian land hex: {', '.join(moved) if moved else 'none'}")


def _listed(names: list, limit: int = 8) -> str:
    """A sample of names for a report line, with the count of the rest."""
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def check(web_dir) -> list[tuple[str, str]]:
    """The published file read on its own (pipeline check runs it): the shape in the module docstring, only types from
    the catalog above, a number or null for every figure, every site on a Serbian land hex. One (level, message) per
    line; the report prefixes each with the builder's name."""
    path = Path(web_dir) / "resources.json"
    if not path.exists():
        return [("NOTE", "not built — run: python -m pipeline build resources")]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [("FAIL", f"invalid JSON ({exc})")]
    types, items = (doc.get("types"), doc.get("items")) if isinstance(doc, dict) else (None, None)
    if not (isinstance(types, list) and isinstance(items, list) and isinstance(doc.get("summary"), dict)):
        return [("FAIL", "expected {types, items, summary}: two lists and an object")]
    out: list[tuple[str, str]] = []
    ids = [t.get("id") if isinstance(t, dict) else None for t in types]
    if len(set(ids)) != len(ids):
        out.append(("FAIL", "a type is listed twice"))
    catalog = {t["id"] for t in TYPES}
    if set(ids) - catalog:
        out.append(("FAIL", f"types not in this module's catalog: {_listed(sorted(map(str, set(ids) - catalog)))}"))
    if not types:
        out.append(("NOTE", "no types: the CSV mapped no site"))
    land = land_cells(path.parent)
    known = set(ids)
    bad, off = [], []
    for it in items:
        if not isinstance(it, dict) or it.get("type") not in known:
            bad.append(repr(it.get("name") if isinstance(it, dict) else it))
            continue
        value = it.get("value")
        if value is not None and not (isinstance(value, (int, float)) and not isinstance(value, bool)):
            bad.append(f"{it.get('name')!r} (figure {value!r})")
        if land is not None:
            cell = it.get("cell")
            if type(cell) is not int or not 0 <= cell < len(land) or not land[cell]:
                off.append(f"{it.get('name')} (cell {cell!r})")
    if bad:
        out.append(("FAIL", f"sites not of a known type with a number or null for the figure: {_listed(bad)}"))
    if off:
        out.append(("WARN", f"sites not on a Serbian land hex: {_listed(off)}"))
    if not bad and not off:
        out.append(("PASS", f"{len(types)} types, {len(items)} sites" + (", all on Serbian land" if land is not None else "")))
    return out
