"""web/data/districts.json — the economic districts (kvartovi) of every city, from Popis 2022 (RZS).

Upstream usaciv derives its districts from BLS QCEW (jobs by NAICS at the county of work) and names a city's
type after its strongest district. Serbia's census publishes, for every opština, the employed residents by NACE
section A–S (srb.INDUSTRIES: the 19 sections used everywhere in this project); the RZS registered-employment table
by municipality of work and NACE exists too, but the census is the source the rest of the city screen already
uses, so the districts are built from it:

  * emp — the city's employed residents (the census's industry total, summed over its opštine);
  * each district reads one to three NACE sections (catalog.naics holds the section letters); its location
    quotient is the city's share of jobs in them divided by the Republic's share (Serbia without KiM);
  * a district qualifies with a quotient of at least 1.25 and at least 500 jobs or 1% of the city's jobs
    (upstream's 1,000 jobs scaled to Serbia's 2.4 million employed), ranked by the jobs above the national
    norm, at most 5 per city;
  * sub-industries, wages, pay and the year-on-year change are not published at this level: every sub, avg_pay,
    oty_pct, suppressed and lower_bound field is null, never a guess;
  * the city type (badge) is the strongest district's badge, or a listed district's with a quotient of at
    least 6 and at least 3% of the city's jobs; «Prestonica» goes to Belgrade alone (no okrug seats are on file).
"""
from __future__ import annotations

import json

from ..core import srb, store, territory
from ..sources.census import Census
from .citizens import walk_cells

REQUIRES = ["census", "_cities", "cities.json"]
PRODUCES = ["districts.json"]

VINTAGE = "Popis stanovništva, domaćinstava i stanova 2022. u Republici Srbiji — zaposleni po prebivalištu i delatnosti"
YEAR = 2022
SOURCES = ["census"]

MIN_LQ = 1.25
MIN_JOBS = 500
MIN_SHARE = 0.01
SPECIALTY_LQ = None  # no sub-industries at the NACE section level
SPECIALTY_JOBS = None
SPECIALTY_SHARE = None
MAX_PER_CITY = 5
TOP_INDUSTRIES = 8
HARBOR_NEEDS_WATER = False  # the logistics district reads road, rail, air and water transport alike
BADGE_LQ = 6.0
BADGE_SHARE = 0.03
COLLEGE_SHARE = None  # no IPEDS equivalent: the knowledge badge comes from the campus district alone

RULE_TEXT = (
    "Kvart se pojavljuje kada zaposleni u njegovim delatnostima imaju lokacioni količnik (udeo tih delatnosti u "
    "zaposlenima grada podeljen nacionalnim udelom) najmanje 1,25 i najmanje 500 zaposlenih ili 1 % zaposlenih "
    "grada. Kvartovi se ređaju po broju zaposlenih iznad nacionalnog proseka (zaposleni umanjeni za količnik); "
    "najviše 5 po gradu. Tip grada nosi ime najjačeg kvarta, odnosno navedenog kvarta s količnikom najmanje 6 i "
    "udeom najmanje 3 % zaposlenih grada kad postoji; «Prestonica» pripada samo Beogradu. Podaci su Popis 2022: "
    "zaposleni po prebivalištu i NACE odeljku A–S, pa se poddelatnosti, zarade i promena u odnosu na prethodnu "
    "godinu ne objavljuju (null)."
)
COUNTY_NOTE = "Kvartovi opština računaju se istim pravilom, bez grada."
CATALOG = [
    {"id": "campus", "name": "Kampus", "icon": "d-campus", "color": "#4a7bd0", "naics": ["M", "P", "J"],
     "badge": {"id": "scientific", "label": "Grad znanja", "labels": {"M": "Naučni grad", "P": "Univerzitetski grad", "J": "Grad tehnologije"}},
     "description": "Nauka, obrazovanje i tehnologija: stručne, naučne i tehničke delatnosti (M), obrazovanje (P) i informisanje i komunikacije (J).",
     "caveat": None},
    {"id": "commercial_hub", "name": "Poslovni centar", "icon": "d-commercial-hub", "color": "#d0a23a", "naics": ["K", "L"],
     "badge": {"id": "commercial", "label": "Finansijski centar", "labels": {"K": "Finansijski centar", "L": "Centar nekretnina"}},
     "description": "Finansije i osiguranje (K) i poslovanje nekretninama (L).",
     "caveat": None},
    {"id": "industrial_zone", "name": "Industrijska zona", "icon": "d-industrial-zone", "color": "#c2643a", "naics": ["B", "C"],
     "badge": {"id": "industrial", "label": "Industrijski grad", "labels": {"B": "Rudarski grad", "C": "Industrijski grad"}},
     "description": "Rudarstvo i vađenje (B) i prerađivačka industrija (C).",
     "caveat": None},
    {"id": "harbor", "name": "Logistički čvor", "icon": "d-harbor", "color": "#2f8fb0", "naics": ["H"],
     "badge": {"id": "logistics", "label": "Logistički čvor", "labels": {"H": "Logistički čvor"}},
     "description": "Saobraćaj i skladištenje (H): drumski, železnički, vazdušni i vodni prevoz, skladištenje i pomoćne usluge u saobraćaju. Umesto američkog okruga luke, jer Popis ne izdvaja vodni saobraćaj iz odeljka H.",
     "caveat": "Ne traži položaj uz vodu: obuhvata sav saobraćaj i skladištenje."},
    {"id": "theater_square", "name": "Kulturni trg", "icon": "d-theater-square", "color": "#a15bc4", "naics": ["R"],
     "badge": {"id": "cultural", "label": "Grad kulture", "labels": {"R": "Grad kulture"}},
     "description": "Umetnost, zabava i rekreacija (R): pozorišta, muzika, film, sport i rekreacija.",
     "caveat": "Izdavaštvo i emitovanje ne izdvajaju se iz odeljka J (informisanje i komunikacije), pa ovde ulazi samo odeljak R."},
    {"id": "entertainment_complex", "name": "Turistički kompleks", "icon": "d-entertainment-complex", "color": "#d0508a", "naics": ["I"],
     "badge": {"id": "entertainment", "label": "Turistički grad", "labels": {"I": "Turistički grad"}},
     "description": "Ugostiteljstvo (I): smeštaj i ishrana.",
     "caveat": None},
    {"id": "aerodrome", "name": "Aerodrom", "icon": "d-aerodrome", "color": "#6a8fb8", "naics": [],
     "badge": {"id": "aviation", "label": "Vazdušna luka", "labels": {}},
     "description": "Vazdušni saobraćaj i usluge na aerodromima (NACE 51).",
     "caveat": "Ne izračunava se: Popis po opštinama objavljuje samo odeljke delatnosti, a vazdušni saobraćaj je deo odeljka H, zajedno sa Logističkim čvorom."},
    {"id": "government_plaza", "name": "Upravni trg", "icon": "d-government-plaza", "color": "#8a9a5b", "naics": ["O"],
     "badge": {"id": "governmental", "label": "Grad uprave", "labels": {"O": "Grad uprave"}},
     "description": "Državna uprava i odbrana; obavezno socijalno osiguranje (O).",
     "caveat": "Odbrana je u istom odeljku sa upravom, pa se vojni kvart (Logor) ne može izdvojiti."},
    {"id": "encampment", "name": "Vojni logor", "icon": "d-encampment", "color": "#8a4a3a", "naics": [],
     "badge": {"id": "militaristic", "label": "Garnizon", "labels": {}},
     "description": "Odbrana (NACE 84.2).",
     "caveat": "Ne izračunava se: Popis ne objavljuje odbranu odvojeno od državne uprave (odeljak O)."},
    {"id": "aqueduct", "name": "Energetika i komunalije", "icon": "d-aqueduct", "color": "#3aa0a0", "naics": ["D", "E"],
     "badge": {"id": "utility", "label": "Komunalni grad", "labels": {"D": "Energetski grad", "E": "Komunalni grad"}},
     "description": "Snabdevanje električnom energijom, gasom i parom (D) i snabdevanje vodom te uklanjanje i obrada otpada (E).",
     "caveat": None},
    {"id": "agriculture", "name": "Poljoprivreda", "icon": "i-agriculture", "color": "#6c9a3a", "naics": ["A"],
     "badge": {"id": "agrarian", "label": "Poljoprivredni grad", "labels": {"A": "Poljoprivredni grad"}},
     "description": "Poljoprivreda, šumarstvo i ribarstvo (A).",
     "caveat": None},
    {"id": "construction", "name": "Građevinarstvo", "icon": "i-construction", "color": "#e0b020", "naics": ["F"],
     "badge": {"id": "construction", "label": "Građevinski grad", "labels": {"F": "Građevinski grad"}},
     "description": "Građevinarstvo (F).",
     "caveat": None},
]
BY_ID = {c["id"]: c for c in CATALOG}
CAPITAL_BADGE = {"id": "capital", "label": "Prestonica", "district": None, "text": "sedište države", "basis": "capital"}
DEFAULT_BADGE = {"id": "diversified", "label": "Raznovrsna privreda", "district": None, "text": "Nijedna grana privrede se ne ističe.", "basis": "census"}
NO_DATA_BADGE = {"id": "nodata", "label": "Nema podataka", "district": None, "text": "Popis 2022 nije sproveden.", "basis": "census"}


def lq(emp, total, nat_emp, nat_total):
    """The location quotient of a group of industries: the city's share of jobs in them ÷ the national share."""
    if not emp or not total or not nat_emp or not nat_total:
        return None
    return (emp / total) / (nat_emp / nat_total)


def excess(emp, q):
    """The jobs the city has in an industry above the national norm."""
    return emp * (1 - 1 / q) if q and q > 1 else 0.0


def section_jobs(industry: dict | None) -> dict | None:
    """{NACE section: employed} from a census industry row (the letters A–S the project uses); None without a row
    or when a section is not published."""
    if not industry or industry.get("total") is None:
        return None
    out = {}
    for key, nace, _ in srb.INDUSTRIES:
        v = industry.get(nace)
        if v is None:
            return None
        out[nace] = v
    out["total"] = industry["total"]
    return out


def evaluate(jobs: dict | None, national: dict) -> list:
    """The districts of one city (or opština) from {section: employed} (+ 'total'), ranked by strength, at most
    MAX_PER_CITY. Entries without NACE sections (Aerodrom, Vojni logor) are never evaluated."""
    if not jobs or not jobs.get("total"):
        return []
    total = jobs["total"]
    out = []
    for cat in CATALOG:
        if not cat["naics"]:
            continue
        emp = sum(jobs.get(n, 0) for n in cat["naics"])
        q = lq(emp, total, sum(national.get(n, 0) for n in cat["naics"]), national["total"])
        if q is None or q < MIN_LQ:
            continue
        share = emp / total
        if emp < MIN_JOBS and share < MIN_SHARE:
            continue
        out.append({
            "id": cat["id"], "lq": round(q, 2), "emp": emp, "share": round(share, 4),
            "avg_pay": None, "sub": None, "sub_lq": None, "sub_emp": None, "sub_lower_bound": None,
            "via": "broad", "strength": round(excess(emp, q)),
            "suppressed": None, "lower_bound": None,
        })
    out.sort(key=lambda d: (-d["strength"], d["id"]))
    return out[:MAX_PER_CITY]


def badge_district(dists: list) -> dict | None:
    """The district the city type is named after: a listed one with a quotient of at least BADGE_LQ and BADGE_SHARE
    of the jobs, the strongest such; otherwise the strongest district."""
    if not dists:
        return None
    extreme = [d for d in dists if d["lq"] >= BADGE_LQ and d["share"] >= BADGE_SHARE]
    pick = extreme or dists
    return max(pick, key=lambda d: d["strength"])


def _sections_text(sections: list) -> str:
    """The NACE sections of a district in a sentence: «obrazovanje», «rudarstvo i prerađivačka industrija»."""
    names = [srb.INDUSTRY_NAMES[srb.NACE_TO_KEY[n]].lower() for n in sections]
    return names[0] if len(names) == 1 else "; ".join(names)


def badge_for(district: dict | None, capital: bool) -> dict:
    """The city's type badge: «Prestonica» for the capital when its administration district qualifies, else the
    district's catalog badge, else the diversified default."""
    if not district:
        return dict(DEFAULT_BADGE)
    if district["id"] == "government_plaza" and capital:
        return dict(CAPITAL_BADGE, district=district["id"])
    entry = BY_ID[district["id"]]
    return {"id": entry["badge"]["id"], "label": entry["badge"]["label"], "district": district["id"],
            "text": f"{_sections_text(entry['naics'])}: ×{district['lq']:.1f} nacionalnog udela zaposlenih".replace(".", ","),
            "basis": "census"}


def top_industries(jobs: dict | None, national: dict) -> list:
    """The TOP_INDUSTRIES sections with the highest location quotient, each with at least MIN_JOBS jobs."""
    if not jobs or not jobs.get("total"):
        return []
    out = []
    for key, nace, _ in srb.INDUSTRIES:
        emp = jobs.get(nace)
        if emp is None:
            continue
        q = lq(emp, jobs["total"], national.get(nace), national["total"])
        if q is None or emp < MIN_JOBS:
            continue
        out.append({"naics": nace, "emp": emp, "lq": round(q, 2), "avg_pay": None, "oty_pct": None, "suppressed": None, "lower_bound": None})
    out.sort(key=lambda t: (-t["lq"], t["naics"]))
    return out[:TOP_INDUSTRIES]


def city_record(jobs: dict | None, counties: list, national: dict, capital: bool) -> dict | None:
    """One city: employed, its opštine, the most specialised sections, its districts and its type."""
    if not jobs:
        return None
    dists = evaluate(jobs, national)
    return {
        "emp": jobs["total"], "avg_pay": None, "counties": [len(counties), len(counties)],
        "top": top_industries(jobs, national), "districts": dists,
        "badge": badge_for(badge_district(dists), capital),
    }


def make_doc(national: dict, cities: dict, counties: dict) -> dict:
    """The file: rule, catalog, the national totals and every city's and opština's record."""
    industries = {nace: {"title": name, "us_emp": national[nace]} for key, nace, name in srb.INDUSTRIES}
    return {
        "version": 1, "vintage": VINTAGE, "year": YEAR, "sources": SOURCES,
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_share": MIN_SHARE, "specialty_lq": SPECIALTY_LQ,
                 "specialty_jobs": SPECIALTY_JOBS, "specialty_share": SPECIALTY_SHARE, "max_per_city": MAX_PER_CITY,
                 "harbor_needs_water": HARBOR_NEEDS_WATER, "badge_lq": BADGE_LQ, "badge_share": BADGE_SHARE,
                 "college_share": COLLEGE_SHARE, "county_note": COUNTY_NOTE, "text": RULE_TEXT},
        "catalog": [{**c, "own": None, "sub": None} for c in CATALOG],
        "industries": industries,
        "national": {"emp": national["total"], "avg_pay": None},
        "cities": cities, "counties": counties,
    }


def build() -> None:
    from .cities import unit_row


    census_units = store.load_interim("census")["units"]
    cities = json.loads((store.WEB_DATA / "cities.json").read_text(encoding="utf-8"))
    if isinstance(cities, dict):
        cities = cities["cities"]
    # The Republic row of the industry workbook: Serbia without KiM (the census was not taken there).
    _, rep = walk_cells(Census(), "industry")
    national = {}
    for (key, nace, _), fragment in zip(srb.INDUSTRIES, srb.CENSUS_NACE_FRAGMENTS):
        hits = [v for k, v in rep.items() if fragment in k]
        if len(hits) != 1:
            raise ValueError(f"industry workbook: section {nace}: {len(hits)} matches")
        national[nace] = hits[0]
    national["total"] = rep["Укупно Total"]
    def city_jobs(parts) -> dict | None:
        rows = [section_jobs((unit_row(census_units, u) or {}).get("industry")) for u in parts]
        rows = [r for r in rows if r is not None]
        if not rows:
            return None
        return {nace: sum(r[nace] for r in rows) for nace in national}

    out_cities = {}
    for c in cities:
        parts = c.get("counties") or []
        out_cities[c["id"]] = city_record(city_jobs(parts), parts, national, bool(c.get("capital")))
    out_counties = {}
    for ident, row in census_units.items():
        jobs = section_jobs(row.get("industry"))
        if not jobs:
            continue
        out_counties[ident] = {"emp": jobs["total"], "districts": [[d["id"], d["lq"], d["emp"]] for d in evaluate(jobs, national)]}
    doc = make_doc(national, out_cities, out_counties)
    store.write_web("districts.json", doc)
    with_districts = sum(1 for c in out_cities.values() if c and c["districts"])
    print(f"    districts: {len(out_cities)} cities ({with_districts} with a district), {len(out_counties)} opštine; "
          f"national employed {national['total']:,}")


def check(web_dir) -> list:
    path = web_dir / "districts.json"
    if not path.exists():
        return [("NOTE", "districts.json: not built — run: python -m pipeline build districts")]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [("FAIL", f"districts.json: invalid JSON ({exc})")]
    if not isinstance(doc, dict) or doc.get("version") != 1:
        return [("FAIL", f"districts.json: version {doc.get('version') if isinstance(doc, dict) else doc!r}, expected 1")]
    out = []
    ids = {c["id"] for c in doc.get("catalog", [])}
    if ids != set(BY_ID):
        out.append(("FAIL", f"districts.json: catalog ids differ from pipeline/build/districts.py"))
    try:
        cities = json.loads((web_dir / "cities.json").read_text(encoding="utf-8"))
        city_ids = {c["id"] for c in (cities["cities"] if isinstance(cities, dict) else cities)}
    except (OSError, ValueError, KeyError, TypeError):
        city_ids = None
    bad = []
    for cid, c in doc.get("cities", {}).items():
        if c is None:
            continue
        if not isinstance(c.get("emp"), int) or c["emp"] <= 0 or len(c.get("districts", ())) > MAX_PER_CITY:
            bad.append(cid)
            continue
        for d in c["districts"]:
            if d["id"] not in ids or not d["emp"] > 0 or d["lq"] < MIN_LQ:
                bad.append(cid)
                break
        if any(t["naics"] not in doc.get("industries", {}) for t in c["top"]):
            bad.append(cid)
        b = c.get("badge")
        if not isinstance(b, dict) or not b.get("label"):
            bad.append(cid)
    if bad:
        out.append(("FAIL", f"districts.json: malformed city records: {sorted(set(bad))[:8]}"))
    if city_ids is not None:
        stray = sorted(cid for cid in doc["cities"] if cid not in city_ids)
        absent = sorted(cid for cid in city_ids if cid not in doc["cities"])
        if stray:
            out.append(("FAIL", f"districts.json: city ids not in cities.json: {stray[:8]}"))
        if absent:
            out.append(("FAIL", f"districts.json: cities missing from the file: {absent[:8]}"))
    # The opštine table feeds the district overlay: a unit of Kosovo and Metohija never carries one, a key is a unit
    # of the territory tree, and every district qualifies under the rule the cities are held to.
    units = set(territory.units())
    bad_counties = []
    for gid, c in doc.get("counties", {}).items():
        if gid not in units or territory.in_kosovo(gid):
            bad_counties.append(gid)
            continue
        try:
            well_formed = (isinstance(c, dict) and isinstance(c.get("emp"), int) and c["emp"] > 0
                           and isinstance(c.get("districts"), list) and len(c["districts"]) <= MAX_PER_CITY
                           and all(len(d) == 3 and d[0] in ids and isinstance(d[1], (int, float)) and d[1] >= MIN_LQ
                                   and isinstance(d[2], int) and d[2] > 0 for d in c["districts"]))
        except (TypeError, ValueError, KeyError):
            well_formed = False
        if not well_formed:
            bad_counties.append(gid)
    if bad_counties:
        out.append(("FAIL", f"districts.json: opštine outside the tree, in Kosovo and Metohija, or malformed: "
                            f"{sorted(bad_counties)[:8]}"))
    if out:
        return out
    none = sorted(cid for cid, c in doc["cities"].items() if c is None)
    out.append(("PASS", f"districts.json: {len(doc['cities'])} cities, {len(doc['counties'])} opštine, {len(none)} cities without data"))
    if none:
        out.append(("NOTE", f"districts.json: cities without a census row (null): {none[:12]}"))
    return out
