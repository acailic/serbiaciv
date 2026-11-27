"""web/data/citizens.json — the citizen mix of every city, from Popis 2022 (RZS).

The file keeps upstream usaciv's shape (version, vintage, year, sources, figures, rows, groups, rule, national,
cities). The rows are the same five: workforce (employed by ISCO-08 major group), age (the census's five-year
brackets put into four generations), commute (where the employed work: the census's daily-migration table, not
the means of travel), education (population 15+ by schooling) and nativity (the census's migratorna obeležja:
born in the settlement or moved in from elsewhere). Every group key and label is Serbian wherever the census has
no equivalent of the American category; the upstream keys stay where the concepts are the same.

Sources (all Popis 2022, by municipality of residence):
  * interim census.json — age (18 brackets) and the daily-migration counts per unit (sources/census.py);
  * the raw workbooks, read here through sources/census.Census._walk: occupation (table 25), education (table 3),
    migration (table 13). The Republic row of each workbook is the national row (Serbia without KiM: the census
    was not taken there).
A city's figures are the sum over the census rows that stand for its opštine (build/cities.unit_row: Grad Novi
Sad's row stands for its two city municipalities, Belgrade's 17 opštine each have their own). A city without a
row (KiM) gets null, never a zero.
"""
from __future__ import annotations

import json

from ..core import srb, store
from ..sources.census import Census, _group
from ..core import census_xlsx

REQUIRES = ["census", "_cities", "cities.json"]
PRODUCES = ["citizens.json"]

VINTAGE = "Popis stanovništva, domaćinstava i stanova 2022. u Republici Srbiji"
YEAR = 2022
SOURCES = ["census"]

FIGURES = {"workforce": 20, "age": 10, "commute": 10}
SPECIALIST_HIGH = 1.5
SPECIALIST_LOW = 0.67
MIN_SHARE = 0.01
MAX_HIGH = 4
MAX_LOW = 2

# The census columns a group reads (the workbooks label every column in Cyrillic and English; the labels are
# matched after hyphenation artefacts and spaces are removed). Several columns add up; None: not published.
OCCUPATION = {  # ISCO-08 major groups
    "executive": ("руководиоци, функционери и законодавци",),
    "engineer": ("стручњаци и уметници", "Инжињери, стручни сарадници и техничари"),
    "scholar": None,  # nastavnici: Popis po opštinama objavljuje samo glavne grupe, ne i podgrupe
    "healer": None,  # zdravstveni radnici: not published separately at municipality level
    # (vojnička i nepoznata zanimanja, ISCO 0 and 9-unknown, are left out of the icons; the rule text says so)
    "service": ("услужна и трговачка занимања", "једноставна занимања"),
    "clerk": ("админис тративни службеници",),
    "farmer": ("шумари, рибари",),
    "builder": ("занатлије и сродни",),
    "maker": ("руковаоци машинама",),
}
AGE_BINS = {"child": (0, 3), "young": (3, 6), "midlife": (6, 11), "elder": (11, 18)}  # 0–14, 15–29, 30–54, 55+
EDUCATION = {  # population 15+
    "less_than_hs": ("Без школске спреме", "Непотпуно основно образовање"),
    "primary": ("Основно образовање Primary",),
    "high_school": ("Secondary education › свега",),
    "bachelors": ("Више образовање High education",),
    "graduate": ("Високо образовање Higher education",),
}
COMMUTE = {  # daily migrants by place of work (interim keys)
    "same_municipality": "same_unit", "other_municipality": "other_unit", "other_area": "other_oblast", "abroad": "abroad"}
NATIVITY = {  # migratorna obeležja
    "same_settlement": ("Lives in the same settlement",),
    "elsewhere_serbia": ("within the Republic of Serbia, of which: › свега",),
    "former_yugoslavia": ("from the former SFRY republics",),
    "other_country": ("from other countries",),
}

GROUPS = {
    "workforce": [
        {"key": "executive", "label": "Rukovodioci", "icon": "c-executive", "lines": "ISCO-08 glavna grupa 1: rukovodioci, funkcioneri i zakonodavci"},
        {"key": "engineer", "label": "Stručnjaci i tehničari", "icon": "c-engineer", "lines": "ISCO-08 glavne grupe 2 i 3: stručnjaci i umetnici; inženjeri, stručni saradnici i tehničari"},
        {"key": "scholar", "label": "Nastavnici i predavači", "icon": "c-scholar", "lines": "ISCO-08 podgrupa 2.3 (nastavnici): Popis po opštinama je ne objavljuje posebno — nema podataka"},
        {"key": "healer", "label": "Zdravstveni radnici", "icon": "c-healer", "lines": "ISCO-08 podgrupa 2.2 (zdravstveni radnici): Popis po opštinama je ne objavljuje posebno — nema podataka"},
        {"key": "service", "label": "Uslužna i trgovinska zanimanja", "icon": "c-service", "lines": "ISCO-08 glavne grupe 5 (uslužna i trgovinska zanimanja) i 9 (jednostavna zanimanja)"},
        {"key": "clerk", "label": "Administrativni službenici", "icon": "c-clerk", "lines": "ISCO-08 glavna grupa 4: administrativni službenici"},
        {"key": "farmer", "label": "Poljoprivrednici, šumari i ribari", "icon": "c-farmer", "lines": "ISCO-08 glavna grupa 6: poljoprivrednici, šumari, ribari i srodni"},
        {"key": "builder", "label": "Zanatlije i srodna zanimanja", "icon": "c-builder", "lines": "ISCO-08 glavna grupa 7: zanatlije i srodni radnici"},
        {"key": "maker", "label": "Rukovaoci mašinama, monteri i vozači", "icon": "c-maker", "lines": "ISCO-08 glavna grupa 8: rukovaoci mašinama i postrojenjima, monteri i vozači"},
    ],
    "age": [
        {"key": "child", "label": "Dete (do 14)", "icon": "c-child", "lines": "Popis 2022: starost 0–4, 5–9 i 10–14 godina"},
        {"key": "young", "label": "Mladi (15–29)", "icon": "c-young", "lines": "Popis 2022: starost 15–19, 20–24 i 25–29 godina"},
        {"key": "midlife", "label": "Zrele godine (30–54)", "icon": "c-midlife", "lines": "Popis 2022: starost 30–34 do 50–54 godina"},
        {"key": "elder", "label": "Stariji (55 i više)", "icon": "c-elder", "lines": "Popis 2022: starost 55–59 do 85 i više godina"},
    ],
    "commute": [
        {"key": "home_settlement", "label": "U naselju u kom stanuju", "icon": "c-work_home", "lines": "Zaposleni koji rade u naselju stanovanja: ukupno zaposlenih (tabela 25) umanjeno za dnevne migrante"},
        {"key": "same_municipality", "label": "U drugom naselju iste opštine", "icon": "c-work_municipality", "lines": "Dnevne migracije: rade u okviru iste opštine"},
        {"key": "other_municipality", "label": "U drugoj opštini", "icon": "c-work_area", "lines": "Dnevne migracije: rade u drugoj opštini"},
        {"key": "other_area", "label": "U drugom okrugu", "icon": "c-work_okrug", "lines": "Dnevne migracije: rade u drugoj oblasti (okrugu)"},
        {"key": "abroad", "label": "U inostranstvu", "icon": "c-work_abroad", "lines": "Dnevne migracije: rade u stranoj državi"},
    ],
    "education": [
        {"key": "less_than_hs", "label": "Bez završene osnovne škole", "icon": "c-edu0", "lines": "Popis 2022: bez školske spreme i s nepotpunom osnovnom školom (15 i više godina)"},
        {"key": "primary", "label": "Osnovna škola", "icon": "c-primary", "lines": "Popis 2022: osnovno obrazovanje (15 i više godina)"},
        {"key": "high_school", "label": "Srednja škola", "icon": "c-edu1", "lines": "Popis 2022: srednje obrazovanje, svega (15 i više godina)"},
        {"key": "bachelors", "label": "Viša škola", "icon": "c-edu3", "lines": "Popis 2022: više obrazovanje (15 i više godina)"},
        {"key": "graduate", "label": "Fakultet, master i doktorat", "icon": "c-edu4", "lines": "Popis 2022: visoko obrazovanje (15 i više godina)"},
    ],
    "nativity": [
        {"key": "same_settlement", "label": "Od rođenja u istom naselju", "icon": "c-local", "lines": "Popis 2022: od rođenja stanuju u istom naselju"},
        {"key": "elsewhere_serbia", "label": "Doseljeni iz drugog mesta u Srbiji", "icon": "c-newcomer", "lines": "Popis 2022: doseljeno stanovništvo sa područja Republike Srbije, svega"},
        {"key": "former_yugoslavia", "label": "Doseljeni iz bivših jugoslovenskih republika", "icon": "c-yugoslavia", "lines": "Popis 2022: doseljeni iz bivših republika SFRJ"},
        {"key": "other_country", "label": "Doseljeni iz drugih država", "icon": "c-immigrant", "lines": "Popis 2022: doseljeni iz drugih država"},
    ],
}
ROWS = {
    "workforce": "Zaposleni po glavnim grupama zanimanja",
    "age": "Stanovništvo po starosti",
    "commute": "Gde zaposleni rade",
    "education": "Stanovništvo 15+ po školskoj spremi",
    "nativity": "Stanovništvo prema poreklu doseljenja",
}
RULE_TEXT = (
    "Figure se zaokružuju metodom najvećeg ostataka tako da svaki red tačno zbraja ikone. Specijalista je "
    "kategorija čiji je udeo najmanje 1,5× odnosno najviše 0,67× nacionalnog udela (kategorije ispod 1 % i ovde "
    "i nacionalno se preskaču); navodi se najviše 4 nad- i 2 pod-reprezentovane. Popis 2022 (RZS) je potpuna "
    "enumeracija, pa redovi nemaju grešku uzorka. "
    "Zanimanja: Popis po opštinama objavljuje samo ISCO-08 glavne grupe (tabela 25); stručnjaci (grupa 2) i "
    "tehničari (grupa 3) prikazani su zajedno, a nastavnici i zdravstveni radnici nemaju posebno objavljenih "
    "podataka (null). Jednostavna zanimanja (grupa 9) pribrojana su uslužnim i trgovinskim zanimanjima; vojna "
    "zanimanja i nepoznata zanimanja (u Srbiji 19.563 odnosno 20.561) nisu prikazana kao posebne grupe, pa "
    "udeli ne iznose ukupno 100 %. Starost: popisne petogodišnje grupe složene su u četiri generacije (0–14, "
    "15–29, 30–54, 55 i više). Gde zaposleni rade: dnevne migracije (tabela «Dnevne migracije aktivnog "
    "stanovništva koje obavlja zanimanje»); oni koji rade u naselju stanovanja dobijeni su kao razlika ukupno "
    "zaposlenih i dnevnih migranata. Školska sprema: bez škole i nepotpuna osnovna škola zajedno; više i visoko "
    "obrazovanje posebno; nepoznata sprema nije prikazana. Poreklo doseljenja: migratorna obeležja (tabela 13); "
    "nepoznata opština i nepoznata država doseljenja nisu prikazani. Nacionalni red je Republika Srbija bez "
    "Kosova i Metohije (popis tamo nije sproveden); gradovima na KiM nema podataka, pa je ceo red null."
)


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if not ch.isspace() and ch != "-")


def pick(cells: dict, fragment: str):
    """The value of the one census column whose label contains `fragment` (after normalisation); None when the
    table has no such column, an error when it has more than one."""
    if cells is None:
        return None
    want = _norm(fragment)
    exact = [v for k, v in cells.items() if _norm(k) == want]
    if len(exact) == 1:
        return exact[0]
    hits = [v for k, v in cells.items() if want in _norm(k)]
    if len(hits) > 1:
        raise ValueError(f"census column {fragment!r}: found {len(hits)} matches")
    return hits[0] if hits else None


def _add(values):
    """The sum of published values; None when any of them is not published (a sum of part of a group is no data,
    never a smaller number)."""
    return sum(values) if values and all(v is not None for v in values) else None


def _sum_counts(parts: list[dict], keys) -> dict | None:
    """{key: sum} over a city's census rows; None for a key any row lacks, None for all when there is no row."""
    if not parts:
        return None
    return {k: (None if any(p.get(k) is None for p in parts) else sum(p[k] for p in parts)) for k in keys}


def largest_remainder(values: dict, n: int) -> dict:
    """Hamilton's method: n icons split by the shares, ties go to the larger count, then to the earlier key."""
    total = sum(max(v or 0, 0) for v in values.values())
    out = {k: 0 for k in values}
    if not total or n <= 0:
        return out
    exact = {k: max(v or 0, 0) * n / total for k, v in values.items()}
    for k, v in exact.items():
        out[k] = int(v)
    left = n - sum(out.values())
    order = sorted(values, key=lambda k: (-(exact[k] - int(exact[k])), -(values[k] or 0), list(values).index(k)))
    for k in order[:left]:
        out[k] += 1
    return out


def _shares(counts: dict, total):
    if not total:
        return {k: None for k in counts}
    return {k: (None if v is None else round(v / total, 3)) for k, v in counts.items()}


def row(counts: dict, total, figures: int | None = None) -> dict:
    """One row of a city: total, counts and shares (None where the census published nothing); with the rounded
    figures for the rows drawn as icons."""
    out = {"total": total, "counts": dict(counts), "shares": _shares(counts, total)}
    if figures is not None:
        out["figures"] = largest_remainder(counts, figures)
    return out


def specialists(r: dict, nat: dict) -> list:
    """The categories furthest from the national share: ratio = city share ÷ national share, skipping categories
    under min_share on both sides; up to max_high over- and max_low under-represented ones, by ratio."""
    hi, lo = [], []
    for name, parts in GROUPS.items():
        if not r.get(name) or not nat.get(name):
            continue
        for g in parts:
            k = g["key"]
            s, ns = r[name]["shares"].get(k), nat[name]["shares"].get(k)
            if s is None or ns is None or ns <= 0 or (s < MIN_SHARE and ns < MIN_SHARE):
                continue
            ratio = s / ns
            item = {"row": name, "key": k, "share": round(s, 3), "national": round(ns, 3), "ratio": round(ratio, 2)}
            if ratio >= SPECIALIST_HIGH:
                hi.append(item)
            elif ratio <= SPECIALIST_LOW:
                lo.append(item)
    hi = sorted(hi, key=lambda i: -i["ratio"])[:MAX_HIGH]
    lo = sorted(lo, key=lambda i: i["ratio"])[:MAX_LOW]
    return hi + lo


def full_row(rec: dict, nat: dict) -> dict | None:
    """A city's record: the five rows, its specialists and reliability; None without a single census row."""
    if all(rec.get(name) is None for name in ROWS):
        return None
    return {**{name: rec.get(name) for name in ROWS}, "specialists": specialists(rec, nat), "reliable": True}


def walk_cells(source: Census, key: str):
    """({unit id: the total row's cells}, the Republic row's cells) of one census workbook: the national figures.

    Also used by build/districts.py for the industry workbook."""
    walk = source._walk(key)
    units = {ident: area["rows"].get("t", {}).get("cells") if area["rows"].get("t") else None for ident, area in walk.units.items()}
    units = {k: v for k, v in units.items() if v}
    first = _group(census_xlsx.read_rows(source.raw_dir / srb.CENSUS_FILES[key][1]))[0]
    if "РЕПУБЛИКА СРБИЈА" not in first["name"].upper():
        raise ValueError(f"census workbook {key!r} does not start with the Republic row")
    return units, first["rows"]["t"]["cells"]


def occupation_cells(cells) -> dict | None:
    """{kind: employed} from one occupation row: None where the census does not publish the group."""
    if cells is None:
        return None
    return {k: (_add([pick(cells, f) for f in frags]) if frags else None) for k, frags in OCCUPATION.items()}


def education_cells(cells) -> dict | None:
    if cells is None:
        return None
    return {k: _add([pick(cells, f) for f in frags]) for k, frags in EDUCATION.items()}


def nativity_cells(cells) -> dict | None:
    if cells is None:
        return None
    return {k: _add([pick(cells, f) for f in frags]) for k, frags in NATIVITY.items()}


def age_counts(age: list | None) -> dict | None:
    """The four generations from the census's 18 five-year brackets (Popis: 0–4 … 85 and over)."""
    if not age or len(age) != 18:
        return None
    return {k: sum(age[a:b]) for k, (a, b) in AGE_BINS.items()}


def commute_counts(commute: dict | None, employed) -> dict | None:
    """Where the employed work. The census counts only the daily migrants (those working outside their
    settlement); the rest are derived as employed minus daily migrants. No daily-migration row → None."""
    if commute is None or commute.get("total") is None:
        return None
    home = employed - commute["total"] if employed is not None else None
    if home is not None and home < 0:
        home = None
    out = {"home_settlement": home}
    for k, ck in COMMUTE.items():
        out[k] = commute.get(ck)
    return out


def city_records(cities: list[dict], census_units: dict, occ: dict, edu: dict, mig: dict) -> dict:
    """{city id: the five rows} of every city: the census rows that stand for its opštine (build/cities.unit_row),
    added up. A row is None when no part has one; a part that has none is left out only where another part's
    row stands for it (Grad Novi Sad's row for its two city municipalities), which is what unit_row decides."""
    from .cities import unit_row

    out = {}
    for c in cities:
        parts = c.get("counties") or []
        interim = [r for r in (unit_row(census_units, u) for u in parts) if r]
        occ_cells = [x for x in (unit_row(occ, u) for u in parts) if x is not None]
        edu_cells = [x for x in (unit_row(edu, u) for u in parts) if x is not None]
        mig_cells = [x for x in (unit_row(mig, u) for u in parts) if x is not None]
        age_rows = [r["age"]["t"] for r in interim if r.get("age") and r["age"].get("t")]
        commute_rows = [r["commute"] for r in interim if r.get("commute")]
        employed = _total(occ_cells)
        commute = _sum_counts(commute_rows, ("total", "same_unit", "other_unit", "other_oblast", "abroad"))
        counts = {
            "workforce": _sum_counts([occupation_cells(x) for x in occ_cells], OCCUPATION),
            "age": age_counts([sum(a[i] for a in age_rows) for i in range(18)]) if age_rows else None,
            "commute": commute_counts(commute, employed),
            "education": _sum_counts([education_cells(x) for x in edu_cells], EDUCATION),
            "nativity": _sum_counts([nativity_cells(x) for x in mig_cells], NATIVITY),
        }
        totals = {"workforce": employed, "commute": employed, "age": sum(counts["age"].values()) if counts["age"] else None,
                  "education": _total(edu_cells), "nativity": _total(mig_cells)}
        out[c["id"]] = {name: (row(counts[name], totals[name], FIGURES.get(name)) if counts[name] is not None else None)
                        for name in ROWS}
    return out


def _total(cells: list) -> int | None:
    """The census total of the parts' rows (the first, «Укупно», column); None without rows or with one missing."""
    values = [pick(x, "Укупно Total") for x in cells]
    return sum(values) if values and all(v is not None for v in values) else None


def national_row(occ_rep: dict, edu_rep: dict, mig_rep: dict, commute_rep: dict, age_rep: dict) -> dict:
    """The Republic row of each workbook: Serbia without Kosovo and Metohija (the census was not taken there)."""
    employed = pick(occ_rep, "Укупно Total")
    age = [v for k, v in age_rep.items() if k.startswith("Старост / Age ›")]
    commute = {"total": pick(commute_rep, "› укупно total"), "same_unit": pick(commute_rep, "within the same municipality"),
               "other_unit": pick(commute_rep, "in another municipality"), "other_oblast": pick(commute_rep, "in another area"),
               "abroad": pick(commute_rep, "in the foreign country")}
    counts = {
        "workforce": occupation_cells(occ_rep),
        "age": age_counts(age),
        "commute": commute_counts(commute, employed),
        "education": education_cells(edu_rep),
        "nativity": nativity_cells(mig_rep),
    }
    totals = {"workforce": employed, "commute": employed, "age": sum(age) if len(age) == 18 else None,
              "education": pick(edu_rep, "Укупно Total"), "nativity": pick(mig_rep, "Укупно Total")}
    rec = {name: (row(counts[name], totals[name], FIGURES.get(name)) if counts[name] is not None else None) for name in ROWS}
    rec["specialists"] = []
    return rec


def make_doc(nat: dict, recs: dict) -> dict:
    """The file: the national row and every city's record (null where the census has nothing)."""
    return {
        "version": 1, "vintage": VINTAGE, "year": YEAR, "sources": SOURCES,
        "figures": FIGURES, "rows": ROWS, "groups": GROUPS,
        "rule": {"specialist_high": SPECIALIST_HIGH, "specialist_low": SPECIALIST_LOW, "min_share": MIN_SHARE,
                 "max_high": MAX_HIGH, "max_low": MAX_LOW, "text": RULE_TEXT},
        "national": nat,
        "cities": {cid: full_row(rec, nat) for cid, rec in recs.items()},
    }


def build() -> None:
    census_units = store.load_interim("census")["units"]
    cities = json.loads((store.WEB_DATA / "cities.json").read_text(encoding="utf-8"))
    if isinstance(cities, dict):
        cities = cities["cities"]
    source = Census()
    occ, occ_rep = walk_cells(source, "occupation")
    edu, edu_rep = walk_cells(source, "education")
    mig, mig_rep = walk_cells(source, "migration")
    _, comm_rep = walk_cells(source, "commute")
    _, age_rep = walk_cells(source, "municipality_age_sex")
    nat = national_row(occ_rep, edu_rep, mig_rep, comm_rep, age_rep)
    recs = city_records(cities, census_units, occ, edu, mig)
    doc = make_doc(nat, recs)
    store.write_web("citizens.json", doc)
    missing = [cid for cid, r in doc["cities"].items() if r is None]
    print(f"    citizens: {len(doc['cities'])} cities, {len(missing)} without a census row{' (' + ', '.join(missing) + ')' if missing else ''}")


def check(web_dir) -> list:
    path = web_dir / "citizens.json"
    if not path.exists():
        return [("NOTE", "citizens.json: not built — run: python -m pipeline build citizens")]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [("FAIL", f"citizens.json: invalid JSON ({exc})")]
    if not isinstance(doc, dict) or doc.get("version") != 1:
        return [("FAIL", f"citizens.json: version {doc.get('version') if isinstance(doc, dict) else doc!r}, expected 1")]
    if doc.get("figures") != FIGURES:
        return [("FAIL", f"citizens.json: figures {doc.get('figures')!r}, expected {FIGURES!r}")]
    for name, parts in GROUPS.items():
        got = (doc.get("groups") or {}).get(name) or []
        if [g.get("key") for g in got] != [g["key"] for g in parts]:
            return [("FAIL", f"citizens.json: groups[{name}] keys differ from pipeline/build/citizens.py")]
        for g in got:
            if not g.get("label") or not g.get("lines"):
                return [("FAIL", f"citizens.json: group {name}/{g.get('key')} lacks a label or lines")]
    if not isinstance(doc.get("national"), dict) or not isinstance(doc.get("cities"), dict):
        return [("FAIL", "citizens.json: national or cities is not an object")]
    try:
        cities = json.loads((web_dir / "cities.json").read_text(encoding="utf-8"))
        city_ids = [c["id"] for c in (cities["cities"] if isinstance(cities, dict) else cities)]
    except (OSError, ValueError, KeyError, TypeError):
        city_ids = None
    out = []
    if city_ids is not None:
        known = set(city_ids)
        stray = sorted(cid for cid in doc["cities"] if cid not in known)
        absent = sorted(cid for cid in city_ids if cid not in doc["cities"])
        if stray:
            out.append(("FAIL", f"citizens.json: city ids not in cities.json: {stray[:8]}"))
        if absent:
            out.append(("FAIL", f"citizens.json: cities missing from the file: {absent[:8]}"))
    bad = []
    for cid, r in doc["cities"].items():
        if r is None:
            continue
        if r.get("reliable") is not True or not isinstance(r.get("specialists"), list):
            bad.append(cid)
    if bad:
        out.append(("FAIL", f"citizens.json: reliable/specialists malformed for {sorted(bad)[:8]}"))
    if out:
        return out
    none = sorted(cid for cid, r in doc["cities"].items() if r is None)
    out.append(("PASS", f"citizens.json: {len(doc['cities'])} cities, {len(none)} without a census row"))
    if none:
        out.append(("NOTE", f"citizens.json: cities without a census row (null): {none[:12]}"))
    return out
