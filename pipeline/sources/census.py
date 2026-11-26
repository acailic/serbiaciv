"""Read the 2022 census workbooks and join their rows to the RZS territory tree."""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..core import census_xlsx, fetch, srb, territory
from ..core.source import Source, SourceInfo
from ..core.srtext import fold_key, to_latin

TABLES = ("settlement_population", "settlement_age_sex", "municipality_age_sex", "ethnicity", "religion",
          "education", "activity", "industry", "commute", "migration")
# Labels the census uses where the territory tree uses a different name.
ALIASES = {("beogradska oblast grad beograd", "RS110"): "79014", ("novi sad", "RS123"): "89010",
           ("palilula", "RS110"): "70203", ("palilula", "79022"): "71323"}

@dataclass
class Walk:
    units: dict
    settlements: list
    counts: Counter
    unmatched: list


def _group(rows):
    groups = []
    for row in rows:
        name = row["name"]
        if name is not None and not (groups and name == groups[-1]["name"] and row["sex"] in ("m", "f")):
            groups.append({"name": name, "level": row["level"], "rows": {}})
        if groups:
            groups[-1]["rows"][row["sex"] or "t"] = row
    return groups


def _age(area, sex="t"):
    row = area["rows"].get(sex) if area else None
    if not row:
        return None
    return [v for k, v in row["cells"].items() if k.startswith("Старост / Age ›")]


def _values(area):
    row = area["rows"].get("t") if area else None
    return row["cells"] if row else None


def _find(cells, fragment):
    matches = [v for k, v in cells.items() if fragment in k]
    if len(matches) != 1:
        raise ValueError(f"census column {fragment!r}: found {len(matches)} matches")
    return matches[0]


def _sum(a, b):
    return a + b if a is not None and b is not None else None


class Census(Source):
    info = SourceInfo(id="census", title="Popis stanovništva, domaćinstava i stanova 2022. u Republici Srbiji",
                      publisher="Republički zavod za statistiku", homepage="https://popis2022.stat.gov.rs/",
                      license="Slobodno korišćenje uz navođenje izvora (RZS)",
                      description="Podaci Popisa 2022 po opštinama i naseljima.", used_for=["Stanovništvo"])

    def fetch(self, force=False):
        for key in TABLES:
            media, filename = srb.CENSUS_FILES[key]
            if force or not (fetch.RAW / self.id / filename).exists():
                if not self.offline:
                    time.sleep(1.0)
            self.download(f"{srb.CENSUS_BASE}/{media}/{filename}", filename, force=force, expect_binary=True)

    def _walk(self, key):
        groups = _group(census_xlsx.read_rows(self.raw_dir / srb.CENSUS_FILES[key][1]))
        nodes = territory.nodes()
        oblast_names = {fold_key(v["name"]): k for k, v in nodes.items() if k.startswith("RS") and v["level"] == 3}
        upper = {fold_key(v["name"]) for k, v in nodes.items() if k.startswith("RS") and v["level"] < 3}
        unit_index = defaultdict(list)
        settlement_index = defaultdict(list)
        for ident, item in nodes.items():
            if territory.is_unit(ident):
                unit_index[(item["parent"], fold_key(item["name"]))].append(ident)
            elif territory.is_settlement(ident):
                settlement_index[(item["parent"], fold_key(item["name"]))].append(ident)
        units, settlements, counts, unmatched, aliases_seen = {}, [], Counter(), [], Counter()
        oblast = current = aggregate = None
        is_settlement = key.startswith("settlement_")
        for area in groups:
            name, level = area["name"], area["level"]
            folded = fold_key(name)
            if level == 7 or folded in ("gradska", "ostala") or folded.startswith("naselje "):
                continue
            if folded == "region kosovo i metohija":
                oblast = current = aggregate = None
                continue
            if folded in upper:
                counts["upper"] += 1
                oblast = current = aggregate = None
                continue
            belgrade = folded == "beogradska oblast grad beograd"
            if belgrade or folded in oblast_names:
                oblast = "RS110" if belgrade else oblast_names[folded]
                counts["oblast"] += 1
                current = aggregate = None
                if not belgrade:
                    continue
            if is_settlement and level >= 4:
                if current is None:
                    unmatched.append((name, oblast, current)); counts["unmatched"] += 1
                    continue
                hits = settlement_index.get((current, folded), [])
                if len(hits) > 1:
                    raise ValueError(f"{name}: ambiguous settlement under {current}")
                ident = hits[0] if hits else None
                counts["exact" if ident else "unmatched"] += 1
                if not ident:
                    unmatched.append((name, oblast, current))
                settlements.append({"id": ident, "name": to_latin(" ".join(name.split())), "unit": current,
                                    "oblast": oblast, "urban": area["rows"].get("t", {}).get("urban", False), "area": area})
                continue
            alias_parent = aggregate if (folded, aggregate) in ALIASES else oblast
            alias_key = (folded, alias_parent)
            ident = ALIASES.get(alias_key)
            if ident:
                aliases_seen[alias_key] += 1
                counts["alias"] += 1
            else:
                hits = unit_index.get((aggregate, folded), []) if aggregate else []
                if not hits:
                    hits = unit_index.get((oblast, folded), [])
                if len(hits) > 1:
                    raise ValueError(f"{name}: ambiguous unit under {oblast}")
                ident = hits[0] if hits else None
                if ident:
                    counts["exact"] += 1
            if ident:
                if ident in units:
                    raise ValueError(f"{name} under {alias_parent}: duplicate census row")
                units[ident] = area
                current = ident
                if not territory.is_city_municipality(ident):
                    aggregate = ident if territory.parts_of(ident) != [ident] else None
            elif not belgrade:
                unmatched.append((name, oblast, aggregate)); counts["unmatched"] += 1
        for alias, ident in ALIASES.items():
            if aliases_seen[alias] != 1:
                label = {"novi sad": "Нови Сад", "palilula": "Палилула", "beogradska oblast grad beograd": "Београдска област"}[alias[0]]
                raise ValueError(f"{label} under {alias[1]}: expected one alias row, found {aliases_seen[alias]}")
        return Walk(units, settlements, counts, unmatched)

    def process(self):
        walks = {key: self._walk(key) for key in TABLES}
        for key, walk in walks.items():
            print(f"    {key}: {dict(walk.counts)}; unmatched {len(walk.unmatched)}")
            for row in walk.unmatched:
                print(f"      unmatched: {row}")
        age_units = walks["municipality_age_sex"].units
        all_ids = set().union(*(w.units.keys() for key, w in walks.items() if not key.startswith("settlement_")))
        ethnic_keys = ("srbi albanci bosnjaci bugari bunjevci vlasi goranci jugosloveni madjari makedonci muslimani nemci "
                       "romi rumuni rusi rusini slovaci slovenci ukrajinci hrvati crnogorci ostali regionalna_pripadnost "
                       "nisu_se_izjasnili nepoznato").split()
        religion_keys = "total christian orthodox catholic protestant other_christian muslim jewish eastern other agnostic nonbeliever undeclared unknown".split()
        ethnic_headers = ("Serbs", "Albanians", "Bosniaks", "Bulgarians", "Bunjevci", "Vlachs", "Goranci", "Yugoslavs",
                          "Hungarians", "Macedonians", "Muslims", "Germans", "Roma people", "Romanians", "Russians", "Ruthenians",
                          "Slovaks", "Slovenians", "Ukrainians", "Croats", "Montenegrins", "Other", "Regional affiliation",
                          "Did not declare", "Unknown")
        religion_headers = ("Total", "Christian", "Orthodox", "Catholic", "Protestant", "Other Christian", "Islam", "Judaism",
                            "Eastern religions", "Otherreligions", "Agnostics", "Not believers", "Did not declare", "Unknown")
        nace_fragments = ["Agriculture, forestry", "Mining and quarrying", "Manufacturing", "Electricity, gas", "Water supply",
                          "Construction", "Wholesale and retail", "Transportation and storage", "Accommodation and food",
                          "Information and communication", "Financial and insurance", "Real estate", "Professional, scientific",
                          "Administrative and support", "Public administration", "Education", "Human health", "Arts, entertainment",
                          "Other service activities", "Activities of households", "Activities of extraterritorial"]
        units = {}
        for ident in sorted(all_ids):
            age_area = age_units.get(ident)
            age_cells = _values(age_area)
            age = {sex: _age(age_area, sex) for sex in ("m", "f", "t")} if age_area else None
            if age and any(a is not None and len(a) != 18 for a in age.values()):
                raise ValueError(f"{ident}: expected 18 census age groups")
            node_name = territory.name(ident)
            kind = ("beograd" if ident == territory.GRAD_BEOGRAD else "gradska_opstina" if territory.is_city_municipality(ident)
                    else "grad" if node_name.startswith("Grad ") else "opstina")
            unit = {"name": node_name, "oblast": territory.oblast_of(ident), "kind": kind,
                    "population": _find(age_cells, "Укупно Total") if age_cells else None,
                    "households": None, "age": age}
            for table in ("education", "religion", "ethnicity", "activity", "industry", "commute", "migration"):
                cells = _values(walks[table].units.get(ident))
                if cells is None:
                    unit[table] = None
                    continue
                vals = list(cells.values())
                if table == "ethnicity":
                    if len(vals) != len(ethnic_keys) + 1 or not all(expected in actual for expected, actual in zip(ethnic_headers, list(cells)[1:])):
                        raise ValueError(f"{ident}: unexpected ethnicity columns")
                    unit[table] = dict(zip(["total", *ethnic_keys], vals))
                elif table == "religion":
                    if len(vals) != len(religion_keys) or not all(expected in actual for expected, actual in zip(religion_headers, cells)):
                        raise ValueError(f"{ident}: unexpected religion columns")
                    unit[table] = {k: v for k, v in zip(religion_keys, vals) if k != "christian"}
                elif table == "education":
                    unit[table] = {"total15": _find(cells, "Укупно Total"), "none": _find(cells, "Without educational attainment"),
                                   "incomplete_primary": _find(cells, "Incomplete primary education"),
                                   "primary": _find(cells, "Основно образовање Primary"),
                                   "secondary": _find(cells, "Secondary education › свега"),
                                   "higher": _sum(_find(cells, "Више образовање High"), _find(cells, "Високо образовање Higher")),
                                   "unknown": _find(cells, "Непознато Unknown")}
                elif table == "activity":
                    total, children = _find(cells, "Укупно Total"), _find(cells, "children less than 15 years")
                    unit[table] = {"employed": _find(cells, "perform occupation"), "unemployed": _find(cells, "unemployed"),
                                   "inactive": _find(cells, "Economically inactive › свега"),
                                   "total15": total - children if total is not None and children is not None else None}
                elif table == "industry":
                    out = {"total": _find(cells, "Укупно Total")}
                    for code, fragment in zip("ABCDEFGHIJKLMNOPQRSTU", nace_fragments):
                        hits = [v for k, v in cells.items() if fragment in k]
                        if len(hits) > 1:
                            raise ValueError(f"{ident}: ambiguous industry {code}")
                        out[code] = hits[0] if hits else None
                    out["unknown"] = _find(cells, "Непознато Unknown")
                    unit[table] = out
                elif table == "commute":
                    unit[table] = {"total": _find(cells, "› укупно total"), "same_unit": _find(cells, "within the same municipality"),
                                   "other_unit": _find(cells, "in another municipality"), "other_oblast": _find(cells, "in another area"),
                                   "abroad": _find(cells, "in the foreign country")}
                else:
                    unit[table] = {"total": _find(cells, "Укупно Total"), "same_settlement": _find(cells, "Lives in the same settlement"),
                                   "internal": _find(cells, "within the Republic of Serbia, of which: › свега"),
                                   "abroad": _find(cells, "from abroad, of which: › свега")}
            units[ident] = unit
        age_by_settlement = {(s["unit"], fold_key(s["name"])): _age(s["area"]) for s in walks["settlement_age_sex"].settlements}
        settlements = []
        for s in walks["settlement_population"].settlements:
            area = s.pop("area")
            cells = _values(area)
            settlements.append({**s, "population": _find(cells, "Укупно Total") if cells else None,
                                "age": age_by_settlement.get((s["unit"], fold_key(s["name"])) )})
        return {"vintage": self.info.title, "settlements": settlements, "units": units,
                "_files": [srb.CENSUS_FILES[key][1] for key in TABLES]}
