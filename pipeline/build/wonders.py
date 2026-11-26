"""Wonders layer: Serbia's national parks, other protected areas, UNESCO World Heritage, research universities and
hand-picked landmarks, placed on the hex map.

The sites are curated in pipeline/data/wonders_sites.csv (one reviewable row per site: id, name, short, kind, rule,
lon, lat, value, unit, year, listed_as, note); docs/SITES.md says where every figure and coordinate comes from. The
rules are published inside the file (rules[].text) in the upstream shape, with the upstream rule ids and kinds where
the frontend keys on them:

  * national_park  – the five national parks of the Republic of Serbia, ranked by the area of their founding act;
  * park_unit      – other protected areas (nature parks, a special reserve, a natural monument), ranked by area;
  * research_university – the four largest state universities by enrolled students (RZS, 2024/25);
  * unesco_site    – Serbia's five UNESCO World Heritage properties, by component; curated, listed alphabetically;
  * landmark       – hand-picked fortresses, archaeological sites and monasteries; curated, alphabetical.

Serbia publishes no visitor count per park on one page and no research spending per university, so those metrics are
null, never 0. Kosovo and Metohija is in the frame: its sites have real coordinates and their okrug as `state`, and
`state_note` says that no statistics are published for them.

Writes web/data/wonders.json in the upstream usaciv shape:
{version, vintage, sources, rules, national, wonders}.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..core.store import load_interim, write_web
from ..core.territory import in_kosovo
from .sites import DATA, Placer, land_cells, read_sites, number, source_ids

REQUIRES = ["_world", "_cities"]
PRODUCES = ["wonders.json"]

CSV = "wonders_sites.csv"
KIM_NOTE = "Kosovo i Metohija: statistika nije objavljena (prazno); fizičke i geografske činjenice su stvarne."
UNIVERSITY_YEAR = "2024/25"
UNIVERSITY_SOURCE = "rzs_G20251236"

RULES = [
    {"id": "national_park", "kind": "natural", "kinds": ["natural"], "year": None,
     "text": "Svih pet nacionalnih parkova Republike Srbije (Đerdap, Fruška gora, Kopaonik, Tara, Šar-planina), "
             "poredani po površini iz akta o proglašenja. Srbija ne objavljuje broj posetilaca po parku na jednom "
             "mestu, pa je taj podatak prazan. Šar-planina je proglašen zakonom Republike Srbije i leži na Kosovu i "
             "Metohiji."},
    {"id": "park_unit", "kind": "natural", "kinds": ["natural"], "year": None,
     "text": "Zaštićene površine koje nisu nacionalni parkovi, poredane po površini: parkovi prirode Golija-Studenica "
             "i Deliblatska peščara, specijalni rezervat prirode Uvac i Đavolja varoš kao znamenito prirodno mesto "
             "(prikazana zbog poznatosti, iako je mala). Za Deliblatsku peščaru površina po aktu o proglašenju nije "
             "bila u izvoru, pa je prazna."},
    {"id": "research_university", "kind": "university", "kinds": ["university"], "year": UNIVERSITY_YEAR,
     "text": f"Četiri najveća državna univerziteta (Beograd, Novi Sad, Niš, Kragujevac) po broju upisanih studenata "
             f"u školskoj {UNIVERSITY_YEAR}. godini (RZS, saopštenje br. 36). Novčani istraživački izdaci po "
             "univerzitetu se u Srbiji ne objavljuju, pa su prazni."},
    {"id": "unesco_site", "kind": "landmark", "kinds": ["landmark"], "curated": True,
     "text": "Svih pet dobara Republike Srbije na UNESCO-ovoj Listi svetske baštine (1979–2016), prikazana po "
             "komponentama: srednjovekovni spomenici na Kosovu i Metohiji su četiri crkve i manastira, stećci su "
             "zajednička nominacija sa Bosnom i Hercegovinom, Crnom Gorom i Hrvatskom (tri lokaliteta u Srbiji). "
             "Poredani abecedno, ne po podacima; za dobra na Kosovu i Metohiji statistika nije objavljena."},
    {"id": "landmark", "kind": "landmark", "kinds": ["landmark"], "curated": True,
     "text": "Ručni izbor projekta, ne po podacima: {landmarks} najpoznatijih tvrđava, arheoloških lokaliteta i "
             "manastira (kulturna dobra od izuzetnog značaja), raširenih po celoj zemlji. Poredani abecedno; "
             "koordinate su objavljene geografske oznake Wikipedije na engleskom jeziku. Nijedno ne ponavlja mesto "
             "koje je već izabrao nacionalni park ili UNESCO."},
]
CURATED = {r["id"] for r in RULES if r.get("curated")}
AREA_UNIT = "km2"


def _metrics(row: dict, value: float | None) -> dict:
    rule = row["rule"]
    if rule in ("national_park", "park_unit"):
        return {"visits": None, "year": None, "area_km2": value, "unit_type": row["listed_as"] or None,
                "designated": int(row["year"]) if row["year"] else None}
    if rule == "research_university":
        return {"rd_usd": None, "federal_usd": None, "enrollment": int(value) if value is not None else None,
                "enrollment_year": row["year"] or None}
    if rule == "unesco_site":
        return {"visits": None, "inscribed": int(row["year"]) if row["year"] else None}
    return {"visits": None}


def build_wonders(rows: list[dict], placer: Placer) -> tuple[list[dict], list[str]]:
    by_rule: dict[str, list[dict]] = {r["id"]: [] for r in RULES}
    for row in rows:
        if row["rule"] not in by_rule:
            raise ValueError(f"{CSV}: {row['id']} has unknown rule {row['rule']!r}")
        by_rule[row["rule"]].append(row)
    out: list[dict] = []
    moved: list[str] = []
    taken: set[int] = set()
    for rule in RULES:
        group = by_rule[rule["id"]]
        if rule["id"] in ("national_park", "park_unit"):
            group = sorted(group, key=lambda r: (-(number(r["value"]) or -1.0), r["name"]))
        elif rule["id"] == "research_university":
            group = sorted(group, key=lambda r: (-(number(r["value"]) or -1.0), r["name"]))
        else:
            group = sorted(group, key=lambda r: r["name"])
        for rank, row in enumerate(group, start=1):
            pos = placer.place(float(row["lon"]), float(row["lat"]), avoid=frozenset(taken), okrug=row.get("okrug") or None)
            if pos.get("moved_to_land"):
                moved.append(row["name"])
            taken.add(pos["cell"])
            w = {"id": row["id"], "name": row["name"], "short": row["short"], "kind": row["kind"], "rule": rule["id"],
                 "rank": rank, "metrics": _metrics(row, number(row["value"])), **{k: pos[k] for k in ("x", "y", "cell", "county", "cbsa", "state")},
                 "cells": None, "curated": rule["id"] in CURATED}
            if row["listed_as"]:
                w["listed_as"] = row["listed_as"]
            if pos["state"] and in_kosovo(pos["state"]):
                w["state_note"] = KIM_NOTE
            if row["note"]:
                w["note"] = row["note"]
            out.append(w)
    return out, moved


def build() -> None:
    placer = Placer(load_interim("_world"), load_interim("_cities")["cities"])
    rows = read_sites(CSV)
    wonders, moved = build_wonders(rows, placer)
    rules = []
    for r in RULES:
        r = dict(r)
        if "{landmarks}" in r["text"]:
            r["text"] = r["text"].format(landmarks=sum(1 for w in wonders if w["rule"] == "landmark"))
        rules.append(r)
    national = {
        "park_visits": None, "park_visits_year": None,
        "national_parks": sum(1 for w in wonders if w["rule"] == "national_park"),
        "unesco_sites": 5, "unesco_components": sum(1 for w in wonders if w["rule"] == "unesco_site"),
        "state_university_enrollment": 175789, "enrollment_year": UNIVERSITY_YEAR,
    }
    doc = {
        "version": 1,
        "vintage": {"parks": "Vikipedija na srpskom jeziku, infokutije zaštićenih površina (površina i godina "
                             "proglašenja), provereno novembar 2026; Golija: engleska Vikipedija",
                    "unesco": "UNESCO WHC, Lista svetske baštine – Srbija, provereno novembar 2026",
                    "universities": f"RZS saopštenje G20251236 (29. 8. 2025), školska {UNIVERSITY_YEAR}",
                    "landmarks": "ručni izbor projekta, novembar 2026; koordinate sa engleske Vikipedije"},
        "sources": ["wikipedia_sr_protected_areas", "wikipedia_en_coordinates", "unesco_whc_rs", UNIVERSITY_SOURCE,
                    "project_curated_landmarks"],
        "rules": rules,
        "national": national,
        "wonders": wonders,
    }
    write_web("wonders.json", doc)
    kinds = {}
    for w in wonders:
        kinds[w["rule"]] = kinds.get(w["rule"], 0) + 1
    print(f"    wonders.json: {len(wonders)} wonders: {kinds}")
    print(f"    moved to another hex: {', '.join(moved) if moved else 'none'}")


def _listed(names: list, limit: int = 8) -> str:
    """A sample of names for a report line, with the count of the rest."""
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def check(web_dir) -> list[tuple[str, str]]:
    """The published file read on its own (pipeline check runs it): version 1; exactly this module's rules, in its
    order; sources that are in sources.json; every wonder with a name, of a rule and kind defined here, on a Serbian
    land hex; ids unique. One (level, message) per line; the report prefixes each with the builder's name."""
    path = Path(web_dir) / "wonders.json"
    if not path.exists():
        return [("NOTE", "not built — run: python -m pipeline build wonders")]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [("FAIL", f"invalid JSON ({exc})")]
    rules, wonders = (doc.get("rules"), doc.get("wonders")) if isinstance(doc, dict) else (None, None)
    if not (isinstance(doc, dict) and doc.get("version") == 1 and isinstance(rules, list) and rules and isinstance(wonders, list)):
        return [("FAIL", "expected version 1 with a non-empty list of rules and a list of wonders")]
    out: list[tuple[str, str]] = []
    rule_ids = [r.get("id") if isinstance(r, dict) else None for r in rules]
    mine = [r["id"] for r in RULES]
    if len(set(rule_ids)) != len(rule_ids):
        out.append(("FAIL", "a rule is listed twice"))
    if rule_ids != mine:
        out.append(("FAIL", f"rules differ from this module's list and order: {', '.join(map(str, rule_ids))}"))
    sources = doc.get("sources")
    cited = {s for s in sources if isinstance(s, str)} if isinstance(sources, list) else set()
    known_sources = source_ids(path.parent)
    if not cited:
        out.append(("FAIL", "no sources cited"))
    elif known_sources is not None and cited - known_sources:
        out.append(("FAIL", f"sources not in sources.json: {', '.join(sorted(cited - known_sources))}"))
    kinds = {r["kind"] for r in RULES}
    land = land_cells(path.parent)
    bad, off, ids = [], [], []
    for w in wonders:
        if not isinstance(w, dict):
            bad.append(repr(w))
            continue
        ids.append(w.get("id"))
        if (w.get("rule") not in mine or w.get("kind") not in kinds
                or not (isinstance(w.get("name"), str) and w["name"].strip())):
            bad.append(f"{w.get('id') or w.get('name')} (rule {w.get('rule')!r}, kind {w.get('kind')!r})")
            continue
        if land is not None:
            cell = w.get("cell")
            if type(cell) is not int or not 0 <= cell < len(land) or not land[cell]:
                off.append(f"{w.get('name')} (cell {cell!r})")
    twice = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    if twice:
        out.append(("FAIL", f"wonders listed twice: {_listed(twice)}"))
    if bad:
        out.append(("FAIL", f"wonders without a name or of a rule or kind this module does not define: {_listed(bad)}"))
    if off:
        out.append(("WARN", f"wonders not on a Serbian land hex: {_listed(off)}"))
    used: dict[str, int] = {}
    for w in wonders:
        if isinstance(w, dict) and w.get("rule") in mine:
            used[w["rule"]] = used.get(w["rule"], 0) + 1
    empty = [rid for rid in mine if not used.get(rid)]
    if empty:
        out.append(("NOTE", f"rules with no wonder: {', '.join(empty)}"))
    if not bad and not twice and not off:
        out.append(("PASS", f"{len(wonders)} wonders: " + (", ".join(f"{rid} {n}" for rid, n in used.items()) or "none")
                          + (", all on Serbian land" if land is not None else "")))
    return out
