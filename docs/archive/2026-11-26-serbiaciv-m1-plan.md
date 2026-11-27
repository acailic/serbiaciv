# serbiaciv M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Coordination:** Tasks 1–3 can proceed independently. Task 4 must work with the existing fetch-all-then-process pipeline; Task 4 defines the source-raster descriptor used by Task 5; Task 7 and Task 8 must agree on the versioned lens contract and loading behavior before implementation. Tasks 11–13 integrate and validate the results. Assign file ownership explicitly when work runs concurrently; the data-contract and `main.js` changes require one integration owner.

**Goal:** Milestone 1 of `docs/DESIGN.md`: the whole of Serbia (Kosovo and Metohija inside the frame) as a browsable Civ-style hex map built from Serbian and European public data, with about 90 cities, yields, 15 lenses, the okrug and city panels, the Almanac, and the interface in Serbian Latin and Cyrillic.

**Architecture:** Upstream's flow is kept: **source → interim JSON in `data/interim/` → builder → `web/data/*.json` → static site**. Sources are `Source` subclasses discovered automatically; builders are modules with `REQUIRES`, `PRODUCES` and `build()`. The web engine is upstream's, patched where its constants were sized for 25 km hexes and the USA, plus a new `web/js/i18n/` module that generates Cyrillic from Serbian Latin.

**Tech Stack:** Python ≥ 3.11 run through `uv`; standard library plus `rasterio`, `numpy`, `pyshp`, `openpyxl`. Plain ES modules and Canvas 2D, no framework, no build step. JavaScript tests with `node --test`.

## Global Constraints

Every task's requirements include all of these. Values are exact.

- **Grid:** pointy-top hexes, radius `5.0` km, odd-r layout (`pipeline/core/hexgrid.py`, unchanged). Albers equal-area with `lat1=42.5, lat2=45.5, lat0=44.0, lon0=21.0` (`pipeline/core/geo.py`, already changed). Margin `200.0` km.
- **Kosovo and Metohija is inside the frame.** Its hexes are owned by its five okruzi (`RS231`–`RS235`). Physical data there is real. Statistical fields there are `null`, never `0`.
- **Null means no data.** Never write `0` as a stand-in for "unknown". A real zero is written as `0`.
- **The UI is Serbian Latin in code and data; Cyrillic is generated.** No English UI strings. Every user-visible string follows `docs/GLOSSARY.md`.
- **JSON key names stay as upstream:** `fips` holds a NUTS-3 code (`"RS225"`), `geoid` holds an RZS 5-digit code (`"70017"`).
- **Industry keys are the 19 NACE section keys of `pipeline.core.srb.INDUSTRIES`.** Yields are `srb.YIELDS`.
- **Shared constants live in `pipeline/core/srb.py`** and nowhere else. Do not redefine a value that exists there; if a value is missing, add it there in your own commit and say so in your report.
- **Territory ids come from `pipeline/core/territory.py`** (backed by the committed `pipeline/data/rzs_territory.json`). Names shown to users are `territory.name(id)`.
- **Only touch the files your task owns** (listed under "Files"). Another task owns everything else and is editing it right now. In particular no task edits another task's test files.
- **Follow upstream's conventions:** a source is a `Source` subclass with `info = SourceInfo(...)`, `fetch()` and `process()` returning a dict that may carry `"vintage"` and `"_files"`; every download goes through `self.download(...)` (cached, with provenance). A builder declares `REQUIRES`, `PRODUCES` and `build()`, and may define `check(web_dir)`.
- **RZS servers return 403 to curl's default User-Agent.** All requests go through `pipeline.core.fetch`, which sends its own agent string. Make at most one request per second to `*.stat.gov.rs`.
- **Serbian text helpers:** `pipeline.core.srtext.to_latin`, `to_cyrillic`, `fold_key`, `okrug_name`.
- **Terrain accuracy:** the existing 10″ lattice is an experimental intermediate only. Final per-hex means, extrema and land-cover shares must be computed from source-resolution pixels or from an approach validated against them with explicit tolerances. Never call the maximum of coarse averages the source maximum. Source cache paths and provenance must remain reproducible offline.
- **Tests:** `uv run python -m unittest discover -s tests` must pass with pristine output before every commit. JavaScript: `node --test web/js/i18n/` (the folder is an ES-module package through `web/package.json`).
- **Commit often, on your task branch only**, with messages that say what and why. Do not push.
- **Upstream's US modules are gone** (commit `6a492d7`); read them with `git show 1fdbdf3:<path>` when a pattern is worth copying. Do not restore them.

## How the ten tasks fit together

Tasks 1–4 produce interims; Tasks 5–7 consume them and write `web/data`; Tasks 8–10 change the web app. Builders (Tasks 5–7) are written against the interim shapes written out in this plan and tested on small hand-made interims, so they do not wait for the sources. Real data meets the builders in Task 11.

| Task | Produces (interim or file) | Read by |
|---|---|---|
| 1 RZS database | `rzs_db` | Tasks 6, 7 |
| 2 Census 2022 | `census` | Tasks 6, 7 |
| 3 Boundaries | `boundaries`, `kim`, `gdp` | Tasks 5, 6 |
| 4 Geography sources | `dem`, `landcover`, `water`, `places` | Tasks 5, 6 |
| 5 World builder | `_world`, `world.json` | Tasks 6, 7 |
| 6 Yields, cities, okruzi | `_cities`, `cities.json`, `states.json`, `nation.json`, `kim_towns.json` | Task 7, the site |
| 7 Lenses, table, checker | `lenses.json`, `counties.json`, `sources.json`, `pipeline/check.py` | the site |
| 8 Engine + i18n | `web/js/i18n/*`, engine constants | the site |
| 9, 10 Translation | Serbian UI strings | the site |

---

### Task 1: RZS dissemination database client and source

**Files:**
- Create: `pipeline/core/rzs.py`
- Create: `pipeline/sources/rzs_db.py`
- Modify: `pipeline/core/fetch.py` — add one function, `post()`, at the end of the file; change nothing else in it
- Test: `tests/test_rzs.py`, `tests/test_rzs_db.py`

**Interfaces:**
- Consumes: `pipeline.core.fetch` (`download`, `_request`, `OFFLINE`, `USER_AGENT`, `read_manifest`, `manifest_path`, `OfflineError`, `atomic_write_text` usage as in `download`), `pipeline.core.territory` (`units`, `parts_of`, `GRAD_BEOGRAD`), `pipeline.core.srb` (`RZS_RESULT_URL`, `RZS_EXPORT_URL`, `RZS_DATASETS`).
- Produces:
  - `fetch.post(source_id, url, data: dict, rel_path, *, headers=None, timeout=300) -> Path` — a POST of a form, cached exactly like `download()` (same retries, manifest entry, `OFFLINE` rule).
  - `rzs.parse_dataset(html, subarea) -> Dataset`; `rzs.load_dataset(subarea) -> Dataset` (caches the page at `data/raw/rzs_db/pages/<subarea>.html`).
  - `Dataset.dims: dict[str, tuple[Node, ...]]` (every node of a tree, parents before children), `Dataset.labels: dict[str, str]` (agg id → the box's label, e.g. `"Teritorija - NSTJ"`), `Dataset.indicators: tuple[str, ...]`, `Dataset.subarea`, `Dataset.find(dim, text) -> list[str]` (ids of the nodes whose text contains `text`, case-insensitive; `LookupError` when none), `Dataset.children(dim, parent) -> list[str]`, `Dataset.leaves(dim) -> list[str]` (nodes without children).
  - `rzs.query(selection: dict[str, list[str]]) -> str` — `"indicators=a,b&agg-102=x,y&agg-2=…"`, keys in the order given.
  - `rzs.export(ds, selection, rel_path, *, force=False) -> list[dict]` — the POST described below, cached at `data/raw/rzs_db/<rel_path>`; sleeps 1.1 s before each request.
  - `rzs.value(rec) -> float | None`, `rzs.unit_id(rec) -> str`.
  - Source `rzs_db` (id `"rzs_db"`), `process()` → interim **`rzs_db`**:

```jsonc
{
  "vintage": {"pop_estimate": "…", "births": "…", "deaths": "…", "natural_increase": "…", "wages": "…", "employment": "…", "life_expectancy": "…"},  // Serbian Latin, human
  "pop_years": [1991, …, 2025],
  "pop": {"70017": [null, 8412, …], "…": null},                 // one list per 5-digit unit, same length as pop_years, both sexes; null when the office has nothing
  "pop_65": {"year": 2025, "by_unit": {"70017": 0.213}},        // share of the unit's population aged 65 and over, 0..1
  "births": {"year": 2025, "by_unit": {"70017": 87}},
  "deaths": {"year": 2025, "by_unit": {"70017": 131}},
  "natural_increase": {"year": 2025, "by_unit": {"70017": -6.2}},   // per 1,000 residents, as published
  "wages": {"year": 2025, "net": {"70017": 104512.0}, "gross": {"70017": 145610.0}},   // RSD per month
  "employment": {"year": 2025, "by_unit": {"70017": {"total": 3210.0, "by_nace": {"A": 412.0, "B": 0.0, "…": null}}}},   // registered employment, municipality of work; every srb.INDUSTRY NACE letter is a key
  "life_expectancy": {"year": 2025, "by_unit": {"70017": {"m": 72.0, "f": 77.5}}},
  "status": {"pop_estimate": {"70017": "A"}},                   // only entries whose status is not "A"
  "_files": ["…"]
}
```

  Every one of the 204 `territory.units()` ids is a key in each `by_unit` table (and in `pop`, `wages.net`, `wages.gross`). The 29 Kosovo ids (starting with `"9"`) have `null` everywhere. Aggregates (`territory.aggregates()`) use the office's own row when it publishes one; when it does not publish a row for `79014` (Grad Beograd), **counts** are the sum of `territory.parts_of("79014")` and rates, shares and wages stay `null`. Never sum a rate, a share or a wage.
  - `rzs_db.by_unit(records, indicator=None, **dims) -> dict[str, float | None]` — `{unit_id: value}` of the records whose `skrIndikator` starts with `indicator` (when given) and whose dimension columns equal `dims` exactly (e.g. `nPol="Ukupno"`).
  - `rzs_db.sum_parts(table, parts) -> float | None` — the sum of the parts' values, `None` if any is `None`.

**What the office's export looks like** (from saved responses, 2026-11-26). A result page `https://data.stat.gov.rs/Home/Result/<subarea>?languageCode=sr-Latn` embeds each dimension tree as `$('#agg-<n>').jstree({'core': {'data': [ {"id": "RS11", "text": "Beogradski region", "parent": "RS"}, … ], 'check_callback' …`. The same regex is in `scripts/refresh_territory.py`. A plain GET of the page shows the default selection only; the full table needs this POST to `https://data.stat.gov.rs/Home/DisplayResult`:

```
Content-Type: application/x-www-form-urlencoded
languageCode=sr-Latn&displayMode=exportJSON&subAreaId=<subarea>&resultDisplayType=Title&uriQuery=<rzs.query(...)>
```

with headers `X-Requested-With: XMLHttpRequest` and `Referer:` the result page. The body is a JSON list of flat records:

```json
{"IDIndikator": "18030302IND01", "skrIndikator": "Procene stanovništva, po starosti i po", "IDTer": "RS11 ", "nTer": "Beogradski region",
 "nStarGrupa": "Ukupno", "God+Mes": "202300", "nVrTacka": "2023", "nPol": "Muško", "Vrednost": "3220916", "IDStatusPodatka": "A",
 "nStatusPodatka": "Konačan podatak", "IDStatusPoverljivosti": "F", "IDJedinicaMere": "NR", "nJedinicaMere": "broj"}
```

`IDTer` arrives padded with spaces. `Vrednost` is a string with a decimal point; unavailable values are `"…"` or `"-"`. Dimension columns seen: `nPol` (`Muško`, `Žensko`, `Ukupno`), `nStarGrupa` (`0`, `1–4`, `5–9`, …, `85 i više`, `Ukupno`), `nKD08` (`"A - Poljoprivreda, šumarstvo i ribarstv…"`, …, `Ukupno`), `nModalitetRegZap`, `nDnevneMigracije`. Status strings: `Konačan podatak`, `Nedostaje vrednost - podaci ne mogu post…`, `Ne raspolaže se podatkom`. Dataset `180304` carries live births, deaths, natural increase and their rates in one table. Datasets and what they are: `srb.RZS_DATASETS`. The node ids to select are discovered from each dataset's trees; write the ones you use into a module-level table `SELECTIONS` in `rzs_db.py` with a comment naming the label each id came from.

- [ ] **Step 1: Write the failing tests for `fetch.post`**

```python
# tests/test_rzs.py
import http.server, json, tempfile, threading, unittest
from pathlib import Path
from unittest import mock

from pipeline.core import fetch, rzs


class PostTest(unittest.TestCase):
    def test_post_caches_and_records_provenance(self):
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, self.rfile.read(int(self.headers["Content-Length"])).decode(), self.headers.get("User-Agent")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'[{"Vrednost": "1"}]')

            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/Home/DisplayResult"
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fetch, "RAW", Path(tmp)):
                p = fetch.post("rzs_db", url, {"a": "1"}, "t.json", timeout=5)
                self.assertEqual(json.loads(p.read_text()), [{"Vrednost": "1"}])
                self.assertEqual(seen[0][2], fetch.USER_AGENT)
                self.assertIn("a=1", seen[0][1])
                fetch.post("rzs_db", url, {"a": "1"}, "t.json", timeout=5)
                self.assertEqual(len(seen), 1)  # the second call read the cache
                self.assertEqual(fetch.read_manifest("rzs_db")["t.json"]["bytes"], p.stat().st_size)
                fetch.OFFLINE = True
                try:
                    with self.assertRaises(fetch.OfflineError):
                        fetch.post("rzs_db", url, {"a": "1"}, "missing.json", timeout=5)
                finally:
                    fetch.OFFLINE = False
        finally:
            srv.shutdown()
```

- [ ] **Step 2: Run it and see it fail** — `uv run python -m unittest tests.test_rzs -v` → `AttributeError: module 'pipeline.core.fetch' has no attribute 'post'`.
- [ ] **Step 3: Add `fetch.post`** at the end of `pipeline/core/fetch.py`. It posts `urllib.parse.urlencode(data).encode("ascii")` with `_request(url, "POST", headers)` and reuses `_download_with` by passing an `attempt(tmp)` that writes the response body. Exported as a normal function; docstring in upstream's style.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Write the failing tests for the client**

```python
PAGE = """<script>$('#agg-102').jstree({'core': {'data': [{"id": "RS", "text": "REPUBLIKA SRBIJA", "parent": "#"},
{"id": "RS11", "text": "Beogradski region", "parent": "RS"}, {"id": "RS110", "text": "Beogradska oblast", "parent": "RS11"},
{"id": "70114", "text": "Vračar", "parent": "RS110"}], 'check_callback': true}});
$('#agg-2').jstree({'core': {'data': [{"id": "202400", "text": "2024", "parent": "#"},
{"id": "202500", "text": "2025", "parent": "#"}], 'check_callback': true}});</script>
<label style="font-weight:bold" for="cbAggT-102"><input type="checkbox" id="cbAggT-102">Teritorija - NSTJ</label>"""


class ParseDatasetTest(unittest.TestCase):
    def test_trees_labels_and_lookups(self):
        ds = rzs.parse_dataset(PAGE, "18010602")
        self.assertEqual(ds.subarea, "18010602")
        self.assertEqual(ds.labels["agg-102"], "Teritorija - NSTJ")
        self.assertEqual([n.text for n in ds.dims["agg-102"]], ["REPUBLIKA SRBIJA", "Beogradski region", "Beogradska oblast", "Vračar"])
        self.assertEqual(rzs.query({"indicators": ["1IND01"], "agg-102": ["70114"], "agg-2": ["202400", "202500"], "agg-23": ["0"]}),
                         "indicators=1IND01&agg-102=70114&agg-2=202400,202500&agg-23=0")
        self.assertEqual(ds.find("agg-102", "vračar"), ["70114"])
        self.assertEqual(ds.find("agg-102", "oblast"), ["RS110"])
        with self.assertRaises(LookupError):
            ds.find("agg-102", "Nema me")

    def test_children_and_leaves(self):
        ds = rzs.parse_dataset(PAGE, "18010602")
        self.assertEqual(ds.children("agg-102", "RS110"), ["70114"])
        self.assertEqual(ds.leaves("agg-102"), ["70114"])
        self.assertEqual(ds.leaves("agg-2"), ["202400", "202500"])


class ValueTest(unittest.TestCase):
    def test_values_and_ids(self):
        self.assertEqual(rzs.value({"Vrednost": "109462"}), 109462.0)
        self.assertEqual(rzs.value({"Vrednost": "73.86"}), 73.86)
        self.assertEqual(rzs.value({"Vrednost": "1 234"}), 1234.0)
        for bad in ("…", "-", "", None):
            self.assertIsNone(rzs.value({"Vrednost": bad}))
        self.assertIsNone(rzs.value({}))
        self.assertEqual(rzs.unit_id({"IDTer": "RS11 "}), "RS11")
```

- [ ] **Step 6: Run** → FAIL (`AttributeError`/`ImportError`), then write `pipeline/core/rzs.py` to pass.

  `export()` posts through `fetch.post("rzs_db", RZS_EXPORT_URL, {...}, rel_path, headers={"X-Requested-With": "XMLHttpRequest", "Referer": RZS_RESULT_URL.format(subarea=ds.subarea)})`, sleeps `time.sleep(1.1)` before any request that is not served from the cache, and returns `json.loads(path.read_text(encoding="utf-8"))`. A body that is not a JSON list raises `fetch.UnexpectedContentError` and the file is discarded with `fetch.discard`.

- [ ] **Step 7: Write the failing tests for the source's pure functions**

```python
# tests/test_rzs_db.py
import unittest

from pipeline.sources import rzs_db


def rec(unit, value, **dims):
    return {"IDTer": unit + " " * (5 - len(unit)), "skrIndikator": "Prosečne neto zarade", "Vrednost": value, **dims}


class ByUnitTest(unittest.TestCase):
    def test_filters_by_indicator_and_dimensions_and_strips_ids(self):
        rows = [rec("70017", "10", nPol="Ukupno"), rec("70246", "…", nPol="Ukupno"), rec("70017", "99", nPol="Muško"),
                {**rec("70017", "7", nPol="Ukupno"), "skrIndikator": "Prosečne bruto zarade"}]
        self.assertEqual(rzs_db.by_unit(rows, "Prosečne neto", nPol="Ukupno"), {"70017": 10.0, "70246": None})
        self.assertEqual(rzs_db.by_unit(rows, nPol="Ukupno"), {"70017": 7.0, "70246": None})  # the last record wins
        self.assertEqual(rzs_db.by_unit(rows, "Prosečne neto", nPol="Žensko"), {})


class SumPartsTest(unittest.TestCase):
    def test_counts_sum_and_a_missing_part_makes_none(self):
        self.assertEqual(rzs_db.sum_parts({"a": 1.0, "b": 2.0, "c": None}, ["a", "b"]), 3.0)
        self.assertIsNone(rzs_db.sum_parts({"a": 1.0, "b": None}, ["a", "b"]))
```

- [ ] **Step 8: Run** → FAIL, then write `pipeline/sources/rzs_db.py` until it passes. `info` fields: `id="rzs_db"`, `title="Diseminaciona baza podataka"`, `publisher="Republički zavod za statistiku"`, `homepage="https://data.stat.gov.rs/"`, `license="Slobodno korišćenje uz navođenje izvora (RZS)"`, `description` in Serbian Latin, `used_for=["Stanovništvo i procene", "Rad i zarade", "BDP po oblastima"]`.

  `fetch()` loads every needed dataset page and every export named in `SELECTIONS`; under `self.offline` it only checks the cache (as `cmd_fetch` already does by catching `OfflineError`).
  `process()` builds the interim above. Keep each mapping a small function so the shape is testable; add at least one test per mapping function with hand-written records.
- [ ] **Step 9: Run against the office's database** — `uv run python -m pipeline fetch rzs_db && uv run python -m pipeline process rzs_db` → ends with `done in …s`; then `uv run python -c "from pipeline.core.store import load_interim as l; d = l('rzs_db'); print(len(d['pop']), d['wages']['net'].get('70017'), d['employment']['by_unit']['70017'])"` → prints `204` and real numbers. If a number looks wrong (for example a Belgrade of fewer than a million), stop and report it in your report file rather than adjusting anything by hand.
- [ ] **Step 10: Run the whole suite, self-review, commit** (`git commit -m "RZS database: client, POST download and the rzs_db source"`).

---

### Task 2: Census 2022 source

**Files:**
- Create: `pipeline/core/census_xlsx.py`
- Create: `pipeline/sources/census.py`
- Test: `tests/test_census_xlsx.py`, `tests/test_census.py`

**Interfaces:**
- Consumes: `pipeline.core.fetch`, `pipeline.core.srtext.to_latin`, `pipeline.core.territory` (`nodes`, `children`, `find_unit`, `oblast_of`, `units`, `parts_of`, `GRAD_BEOGRAD`, `BEOGRAD_OBLAST`, `level`), `pipeline.core.srb` (`CENSUS_BASE`, `CENSUS_FILES`, `NACE_TO_KEY`).
- Produces:
  - `census_xlsx.read_rows(path) -> list[Row]`: one `Row` per spreadsheet row that has text in column A, as `dict(level=<indent 0..4>, name=<Cyrillic as in the file>, sex=<"m"|"f"|"t">, cells={column title: number | None})`. Column titles come from the header row of the block (the first row of the sheet). `"-"` is `0` (the office prints it for "none"); `"..."`, blank and non-numeric are `None`.
  - `census_xlsx.areas(rows) -> list[Area]`: the rows grouped into areas by walking the indent stack; `Area` is `dict(name, level, parent=<Area | None>, rows={"m": Row, "f": Row, "t": Row | None}, children=[Area])`. An area's first row carries its name; the following rows repeat the name or leave it blank and differ only in the sex column.
  - Source id `"census"`, `process()` → interim **`census`**:

```jsonc
{
  "vintage": "Popis stanovništva, domaćinstava i stanova 2022. u Republici Srbiji",
  "settlements": [
    {"id": "80438", "name": "Subotica", "unit": "80438", "oblast": "RS125", "urban": true,
     "population": 117933, "age": [21 ints] | null}          // id: the 6-digit settlement id, null when no match
  ],
  "units": {
    "70017": {
      "name": "Aleksandrovac", "oblast": "RS216", "kind": "opstina" | "grad" | "gradska_opstina" | "beograd",
      "population": 39451, "households": 13200,
      "age": {"m": [21], "f": [21], "t": [21]},                // 0, 1–4, 5–9, …, 80–84, 85 i više (21 groups)
      "education": {"total15": 33200, "none": 0, "incomplete_primary": 1200, "primary": 9800, "secondary": 14100, "higher": 8100, "unknown": 0},
      "ethnicity": {"total": 39451, "srbi": 37900, "albanci": 0, "…": 0},   // the 25 categories of the file, snake_case names, in file order
      "religion": {"total": 39451, "orthodox": 37000, "catholic": 120, "protestant": 30, "other_christian": 40, "muslim": 610,
                   "jewish": 0, "eastern": 0, "other": 50, "agnostic": 20, "nonbeliever": 300, "undeclared": 500, "unknown": 81},
      "activity": {"employed": 16800, "unemployed": 2200, "inactive": 13200, "total15": 32200},
      "industry": {"total": 16800, "A": 3100, "B": 80, "C": 3900, "…": 0, "unknown": 40},   // every NACE column of the file, then "unknown"
      "commute": {"total": 16800, "same_unit": 9800, "other_unit": 5200, "other_oblast": 1400, "abroad": 400},
      "migration": {"total": 39451, "same_settlement": 22000, "internal": 12000, "abroad": 3100}
    }
  },
  "_files": ["…"]
}
```

  A unit is in `units` when the census has its own row for it. Kosovo units are absent. The three ethnic categories that are not a nationality (`Ostali`, `Regionalna pripadnost`, `Nisu se izjasnili`, `Nepoznato`) are kept with the snake_case of their names. `kind`: `gradska_opstina` for `territory.is_city_municipality(id)`, `beograd` for `GRAD_BEOGRAD`, `grad` when the name starts with `Grad `, else `opstina`. A field the file does not give for that unit is `None`, not an empty dict.

**How the files are built** (verified 2026-11-26). Index: `https://popis2022.stat.gov.rs/sr-Latn/rezultati/excel/`. Each table is one sheet, Cyrillic titles, no code column. The hierarchy Region (indent 0) → Oblast (1) → Opština/Grad (2) → Gradska opština (3) → Naselje (4 in settlement tables) is carried only by the indent of column A's cell style (`cell.alignment.indent`) and by row order. Each area occupies three rows with `с`, `м`, `ж` in the second column; the name is only in the first. `г` marks an urban settlement. Settlement names repeat across Serbia (three `Бели Поток`), so the parent is part of the identity. Download each file with `self.download(f"{CENSUS_BASE}/{media_id}/{file}", file, expect_binary=True)`; the table list is `srb.CENSUS_FILES`. Column layouts, in order:

| Table | Columns after name and sex |
|---|---|
| `settlement_population` | `г` (urban marker), population, `u`, Latin name |
| `settlement_age_sex` | total, `0–4, 5–9 … 80–84, 85 и више` |
| `municipality_age_sex` | same, one row group per unit |
| `ethnicity` | total, `Срби, Албанци, Бошњаци, Бугари, Буњевци, Власи, Горанци, Југословени, Мађари, Македонци, Муслимани, Немци, Роми, Румуни, Руси, Русини, Словаци, Словенци, Украјинци, Хрвати, Црногорци, Остали, Регионална припадност, Нису се изјаснили, Непознато` |
| `religion` | total, then 13 columns: Christian all, Orthodox, Catholic, Protestant, Other Christian, Islamic, Jewish, Eastern religions, Other religions, Agnostics, Not believers, Did not declare, Unknown |
| `education` | total, Without educational attainment, Incomplete primary education, Primary education, Secondary All, Gymnasium, Secondary vocational (shorter than 4 years), Secondary vocational (4 years), Specialisation after secondary education, High education, Higher education, Unknown (these titles are English in the file) |
| `activity` | employed / unemployed / inactive, cross-tabulated by age; take the `Ukupno` age column |
| `industry` | total, one column per NACE section `A…X`, then Unknown |
| `commute` | same opština / other opština / other oblast / abroad |
| `migration` | same settlement since birth / internal / abroad |

Read the real headers; do not trust this table over the file. Where a header is not what this plan says, follow the file and list the difference in your report. `occupation`, `illiterate`, `municipality_households`, `settlement_households`, `migrants` are listed in `CENSUS_FILES` but are not needed in M1: do not fetch them.

**Attaching ids.** Transliterate names with `to_latin`. An area at indent 1 is an oblast: its id is the level-3 node whose `fold_key` equals the area's. Indent 2: `territory.find_unit(name, parent=oblast_id)`. Indent 3: `find_unit(name, parent=grad_id)`. A settlement (indent ≥ 2 in settlement tables) is matched to the 6-digit node with the same folded name whose parent chain contains its unit. Anything that does not match is reported in your report file with its name and parents; it is not guessed.

- [ ] **Step 1: Write the failing tests for the reader** with a workbook built by the test itself.

```python
# tests/test_census_xlsx.py
import tempfile, unittest
from pathlib import Path

from openpyxl import Workbook

from pipeline.core import census_xlsx


def workbook(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append(["", "Потација", "Ukupno", "Срби", "Роми"])
    ws.append(["Рашка област", "с", "100", "90", "10"]); ws.append(["", "м", "50", "45", "5"]); ws.append(["", "ж", "50", "45", "5"])
    ws.append(["Тутин", "с", "100", "90", "10"])
    ws.append(["Тутин", "с", "100", "90", "-"]); ws.cell(row=6, column=1).alignment = census_xlsx.indent(3)
    ws.append(["Насеље", "м", "...", "", "3"]); ws.cell(row=7, column=1).alignment = census_xlsx.indent(4)
    wb.save(path)


class ReadRowsTest(unittest.TestCase):
    def test_indent_sex_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.xlsx"
            workbook(p)
            rows = census_xlsx.read_rows(p)
        self.assertEqual([(r["level"], r["sex"]) for r in rows], [(0, "t"), (0, "m"), (0, "f"), (0, "t"), (3, "t"), (4, "m")])
        self.assertEqual(rows[0]["cells"], {"Ukupno": 100, "Срби": 90, "Роми": 10})
        self.assertEqual(rows[4]["cells"], {"Ukupno": 100, "Срби": 90, "Роми": 0})  # "-" is a real zero
        self.assertEqual(rows[5]["cells"], {"Ukupno": None, "Срби": None, "Роми": 3})  # "..." and blank are missing
        self.assertIsNone(rows[1]["name"])

    def test_areas_follow_the_indent_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.xlsx"
            workbook(p)
            areas = census_xlsx.areas(census_xlsx.read_rows(p))
        self.assertEqual(len(areas), 1)
        oblast = areas[0]
        self.assertEqual((oblast["name"], oblast["level"]), ("Рашка област", 0))
        self.assertEqual(oblast["rows"]["m"]["cells"]["Ukupno"], 50)
        self.assertEqual([a["name"] for a in oblast["children"]], ["Тутин"])
        grad = oblast["children"][0]
        self.assertEqual(grad["rows"]["t"]["cells"]["Роми"], 0)
```

- [ ] **Step 2: Run** → FAIL. **Step 3: implement** `census_xlsx.py` with `indent(level)` returning an `Alignment(indent=level)` and the two functions. Open workbooks with `openpyxl.load_workbook(path, read_only=False, data_only=True)`; close them. **Step 4: Run** → PASS.
- [ ] **Step 5: Write the failing tests for the source** on synthetic workbooks placed where `fetch()` would download them (patch `fetch.RAW`): build minimal versions of `ethnicity`, `religion`, `education`, `activity`, `industry`, `commute`, `migration`, `municipality_age_sex`, `settlement_population`, `settlement_age_sex` with the real column titles (copy them from the table above), two oblasti, one grad with a gradska opština pattern from the real tree (use `RS225` → `Grad Niš` `79022` → `Medijana` `71331`), and one settlement. Assert: `process()` returns ids `79022` and `71331` with `kind` `"grad"` and `"gradska_opstina"`; sums of `с` rows; the settlement has `id`, `unit`, `oblast`, `urban`.
- [ ] **Step 6: Run** → FAIL, **Step 7: implement** `pipeline/sources/census.py` until PASS. `info`: `id="census"`, `title="Popis stanovništva, domaćinstava i stanova 2022. u Republici Srbiji"`, `publisher="Republički zavod za statistiku"`, `homepage="https://popis2022.stat.gov.rs/"`, `license="Slobodno korišćenje uz navođenje izvora (RZS)"`.
- [ ] **Step 8: Run against the real files** — `uv run python -m pipeline fetch census && uv run python -m pipeline process census`, then `uv run python -c "from pipeline.core.store import load_interim as l; d = l('census'); u = d['units']; print(len(d['settlements']), len(u), u['70017']['population'], u.get('79014', {}).get('population'))"`. Expected: about 5,300 settlements, about 175 units, real numbers. Note in your report whether the census has its own row for `79014` and for the other aggregates, how many settlements matched a territory id, and every name that did not match.
- [ ] **Step 9: Whole suite, self-review, commit** (`git commit -m "Census 2022: xlsx reader with indent hierarchy and the census source"`).

---

### Task 3: Boundaries, the Kosovo and Metohija stitch, and GDP

**Files:**
- Create: `pipeline/core/jsonstat.py`
- Create: `pipeline/sources/boundaries.py`, `pipeline/sources/kim.py`, `pipeline/sources/gdp.py`
- Create: `pipeline/data/kim_stitch.csv`, `pipeline/data/kim_towns.csv`, `pipeline/data/country_names.py`
- Test: `tests/test_jsonstat.py`, `tests/test_boundaries.py`, `tests/test_kim.py`, `tests/test_gdp.py`, fixture `tests/fixtures/eurostat/nama_10r_3gdp.json` (a real response; fetch one for RS110, RS121, RS217 with `unit=MIO_EUR` and years 2022 and 2023 and commit it — it is about 3 kB)

**Interfaces:**
- Consumes: `pipeline.core.fetch`, `geo` (`geojson_rings`, `load_geojson`, `Shape`, `MapProjection`), `shp` (`open_shapefile`, `records`, `to_shape`, `shapefile_bases`), `territory`, `srtext`, `srb` (`GISCO_NUTS_URL`, `GISCO_LAU_URL`, `GEOBOUNDARIES_XKX_ADM2`, `NATURAL_EARTH`, `EUROSTAT_GDP_URL`, `BBOX_LONLAT`, `MARGIN_KM`, `KIM_OBLASTI`), `lattice` (for `frame_bbox()` only if you need it).
- Produces:
  - `jsonstat.parse(doc) -> list[dict]` — JSON-stat 2.0 (`id`, `size`, `dimension.<dim>.category.index {label: position}`, `value {flat_index: number}`, optional `status`) → one dict per cell: `{<dim>: <category label>, …, "value": number | None, "status": str | None}`. The flat index counts the last dimension fastest.
  - `country_names.SR: dict[str, str]` — ISO3 → Serbian Latin, for every country that can touch the frame: HUN, ROU, BGR, MKD, ALB, MNE, BIH, HRV, SVN, AUT, ITA, GRC.
  - Interim **`boundaries`**:

```jsonc
{
  "vintage": {"oblasti": "Eurostat GISCO, NUTS 2024 (1:20 M)", "regioni": "Eurostat GISCO, NUTS 2024 (1:20 M)", "municipalities": "Eurostat GISCO, LAU 2024 (1:1 M)", "countries": "Natural Earth 1:10m"},
  "oblasti":      [{"id": "RS110", "rings": [[[lon, lat], …], …]}, …],   // 25, ids sorted
  "regioni":      [{"id": "RS11", "rings": …}, …],                      // 4
  "municipalities": [{"id": "70017", "rings": …}, …],                   // 168
  "countries":    [{"iso": "HUN", "name_sr": "Mađarska", "rings": …}, …], // every Natural Earth country that touches the frame; Serbia and Kosovo excluded
  "_files": ["…"]
}
```

  The frame is Serbia's bounding box (`srb.BBOX_LONLAT`) grown by `srb.MARGIN_KM` converted to degrees (111 km per degree of latitude, 111 × cos(44°) per degree of longitude).
  - Interim **`kim`**:

```jsonc
{
  "vintage": "geoBoundaries XKX ADM2 (OpenStreetMap, januar 2023); podela Republičkog zavoda za statistiku",
  "oblasti": [{"id": "RS231", "rings": …}, …],          // 5: each the rings of its municipalities together
  "municipalities": [{"id": "90018", "rings": …}, …],   // 29: each the rings of its member polygons together
  "stitch": [{"polygon": "<shapeName in the file>", "unit": "90263", "basis": "isto ime"}],   // one row per polygon, 38
  "area_km2": 10888.0,                                  // the polygons' total, measured
  "towns": [{"name": "Priština", "lon": 21.1655, "lat": 42.6629}],   // the seat of each of the 29 municipalities
  "_files": ["…"]
}
```

  - Interim **`gdp`**:

```jsonc
{
  "vintage": "Eurostat, BDP po oblastima (nama_10r_3gdp), 2023 — privremeni podaci",
  "year": 2023, "unit": "MIO_EUR",
  "nuts3": {"RS110": 32418.65, …},      // the 25 Serbian ids
  "nuts2": {"RS11": 54000.0, "RS12": 15000.0, "RS21": 19000.0, "RS22": 17000.0},
  "provisional": ["RS110", …],          // ids whose Eurostat status is "p"
  "_files": ["…"]
}
```

  `year` is the latest year in which all 25 ids have a value (ask for 2019–2024). The vintage string ends with `— privremeni podaci` when any id is provisional.

**The stitch.** `pipeline/data/kim_stitch.csv` has the header `polygon,unit,basis` and one row for each of the 38 polygons of `geoBoundaries-XKX-ADM2.geojson`. `unit` is the RZS municipality the polygon belongs to; the 29 are, by okrug (from the office's own tree):

| Oblast | RZS municipalities |
|---|---|
| RS231 Kosovska | Glogovac, Kačanik, Kosovo Polje, Lipljan, Obilić, Podujevo, Priština, Štimlje, Štrpce, Uroševac |
| RS232 Kosovsko-mitrovačka | Kosovska Mitrovica, Leposavić, Srbica, Vučitrn, Zubin Potok, Zvečan |
| RS233 Kosovsko-pomoravska | Gnjilane, Kosovska Kamenica, Novo Brdo, Vitina |
| RS234 Pećka | Dečani, Đakovica, Istok, Klina, Peć |
| RS235 Prizrenska | Gora, Orahovac, Prizren, Suva Reka |

Rules, in order: a polygon with the same name as an RZS municipality (after `fold_key`) goes to it (`basis: isto ime`). North Mitrovica joins Kosovska Mitrovica (`pridružena: nastala 2013. iz Kosovske Mitrovice`). Dragaš, which covers Gora and part of Orahovac and which no source divides, goes whole to Gora (`pridružena: obuhvata Goru i deo Orahovca`). Every other polygon is one of the municipalities created since the office's list; it goes to the unit it was split from (`pridružena: nastala iz <unit>`): Mamuša → Prizren, Junik → Đakovica, Mališevo → Suva Reka, Hani i Elezit → Kačanik, Gračanica → Priština, Ranilug → Kosovska Kamenica, Parteš → Gnjilane, Klokot → Vitina. Take the 38 names from the file, not from this paragraph; if a name is not covered by a rule, stop and report it.

**Towns.** `pipeline/data/kim_towns.csv` has the header `name,osm_name,lon,lat` and 29 rows: the seat of each RZS municipality in Serbian Latin (`Priština`, `Gora` → the town `Dragaš`), the name the Kosovo OpenStreetMap extract gives the place (`Prishtinë`, `Dragash`), and its coordinates. Get the coordinates from the Kosovo extract's place layer (`https://download.geofabrik.de/europe/kosovo-latest-free.shp.zip`, layer `gis_osm_places_free_1`; download it into this source's own raw folder with `self.download`). `process()` checks each town lies inside its own municipality's rings and fails naming the town otherwise.

- [ ] **Step 1: Failing test for the JSON-stat reader** against the committed real fixture:

```python
# tests/test_jsonstat.py
import json, unittest
from pathlib import Path

from pipeline.core import jsonstat

FIXTURE = Path(__file__).parent / "fixtures" / "eurostat" / "nama_10r_3gdp.json"


class ParseTest(unittest.TestCase):
    def test_real_response(self):
        cells = jsonstat.parse(json.loads(FIXTURE.read_text(encoding="utf-8")))
        by = {(c["geo"], c["time"]): c for c in cells}
        self.assertEqual(by[("RS110", "2022")]["value"], 25637.62)
        self.assertEqual(by[("RS110", "2023")]["value"], 32418.65)
        self.assertEqual(by[("RS110", "2023")]["status"], "p")
        self.assertIsNone(by[("RS110", "2022")]["status"])
        self.assertEqual(by[("RS110", "2023")]["unit"], "MIO_EUR")
        self.assertEqual(len(cells), 6)

    def test_sparse_values_are_none(self):
        doc = {"version": "2.0", "id": ["a", "b"], "size": [2, 2],
               "dimension": {"a": {"category": {"index": {"x": 0, "y": 1}}}, "b": {"category": {"index": {"p": 0, "q": 1}}}},
               "value": {"0": 1.5, "3": 4.0}}
        cells = {(c["a"], c["b"]): c["value"] for c in jsonstat.parse(doc)}
        self.assertEqual(cells, {("x", "p"): 1.5, ("x", "q"): None, ("y", "p"): None, ("y", "q"): 4.0})
```

- [ ] **Step 2: Run** → FAIL. **Step 3: implement** `jsonstat.py`. **Step 4: Run** → PASS.
- [ ] **Step 5: Failing tests for the stitch and the town check.** Two groups. Against the committed CSV:

```python
# tests/test_kim.py
import unittest
from pathlib import Path

from pipeline.sources import kim

STITCH_CSV = Path(__file__).parent.parent / "pipeline" / "data" / "kim_stitch.csv"


class StitchTableTest(unittest.TestCase):
    def test_every_polygon_maps_into_a_kosovo_unit(self):
        table = kim.read_stitch(STITCH_CSV)  # {"<shapeName>": ("<unit id>", "<basis>")}
        self.assertEqual(len(table), 38)
        self.assertTrue(all(unit.startswith("9") for unit, _ in table.values()), sorted(table.values()))
        self.assertTrue(all(basis for _, basis in table.values()))

    def test_bad_rows_are_rejected_by_name(self):
        with self.assertRaises(RuntimeError) as ctx:
            kim.read_stitch_text("polygon,unit,basis\nNovo Nebo,70017,isto ime\n")
        self.assertIn("Novo Nebo", str(ctx.exception))
        with self.assertRaises(RuntimeError):
            kim.read_stitch_text("polygon,unit,basis\nNovo Nebo,nema,isto ime\n")
```

  And on synthetic GeoJSON built in the test (five polygons, two of them for one municipality, one oblast made of two municipalities): `dissolve(polygons, table, oblast_of)` returns, for each okrug, the rings of its municipalities' polygons together; the measured area (`geo.MapProjection(0, 0, 0)`, then `Shape.area_km2`) of what it returns equals the input area within 1 %; a polygon of the input that the table does not name raises `RuntimeError` naming it. `check_towns(towns, municipalities)` raises for a town outside its own municipality's rings and returns normally for one inside.
- [ ] **Step 6: Run** → FAIL, implement `kim.py` → PASS. The CSV is filled from the real file: Step 6a, `uv run python -m pipeline fetch kim`, then a one-off script that prints the 38 `shapeName` values; fill the CSV by the rules; say in your report which rule you used for each of the nine that needed one.
- [ ] **Step 7: Failing tests for boundaries**: NUTS GeoJSON filtered to `CNTR_CODE == "RS"` gives 25 level-3 and 4 level-2 features; a LAU shapefile read through `shp.open_shapefile(zip, "LAU_RG_01M_2024_4326.shp.zip/LAU_RG_01M_2024_4326")` yields records whose `GISCO_ID` is `RS_` + a 5-digit id; a country without a Serbian name raises `KeyError` naming it; Serbia and Kosovo are never in `countries`. Build tiny fixtures with `shp`'s writer as `tests/test_core_lattice_shp.py` does.
- [ ] **Step 8: Run** → FAIL, implement `boundaries.py` → PASS. Keep functions small and file-taking (`oblasti_from_geojson(features)`, `municipalities_from_records(records)`, `countries_from_features(features, frame, names)`).
- [ ] **Step 9: Failing test for `gdp`**: `pick_year(cells)` returns the latest year where all of `srb`'s 25 ids (the level-3 ids under `territory.nodes()` with level 3 that are not in `KIM_OBLASTI`) have a value; `vintage(year, provisional_ids)`.
- [ ] **Step 10: Run** → FAIL, implement `gdp.py` → PASS. `info`: `id="gdp"`, `title="BDP po oblastima (nama_10r_3gdp)"`, `publisher="Eurostat"`, `homepage="https://ec.europa.eu/eurostat/web/regions"`, `license="© Evropska unija, 1995–2026, CC BY 4.0"`.
- [ ] **Step 11: Run all three sources for real** — `uv run python -m pipeline fetch boundaries kim gdp && uv run python -m pipeline process boundaries kim gdp`, then print the counts: `25 4 168`, `5 29 38`, and the GDP year. Report the measured Kosovo area and the frame's country list.
- [ ] **Step 12: Whole suite, self-review, commit** (`git commit -m "Boundaries: Eurostat NUTS and LAU, Natural Earth countries, the Kosovo stitch and Eurostat GDP"`).

---

### Task 4: Geography sources — terrain, water and places

**Files:**
- Create: `pipeline/core/wikidata.py`, `pipeline/core/raster.py`
- Create: `pipeline/sources/copernicus_dem.py`, `pipeline/sources/worldcover.py`, `pipeline/sources/water.py`, `pipeline/sources/places.py`
- Test: `tests/test_wikidata.py`, `tests/test_raster.py`, `tests/test_dem_worldcover.py`, `tests/test_water.py`, `tests/test_places.py`

**Interfaces:**
- Consumes: the raw-cache manifest and `srb.BBOX_LONLAT` (optional cached territory boundary for narrower selection), `shp`, `geo` (`MapProjection`, `Shape`), `srtext.to_latin`, `srb` (`COPERNICUS_TILE_URL`, `WORLDCOVER_TILE_URL`, `GEOFABRIK_URL`, `RIVER_MIN_LENGTH_KM`, `LAKE_MIN_KM2`), `fetch`.
- Produces:
  - `wikidata.query(source, sparql, rel_path) -> list[dict]` — GET `https://query.wikidata.org/sparql?format=json&query=…` through `source.download`, cached; returns the `bindings` of the JSON.
  - `wikidata.river_lengths_in_serbia(source) -> dict[str, tuple[str, float]]` — `{folded Serbian label: (Q-id, length km)}` from

```sparql
SELECT ?item ?itemLabel ?len WHERE {
  ?item wdt:P31/wdt:P279* wd:Q4022 ; wdt:P2043 ?len ; wdt:P17 wd:Q403 .
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) IN ("sr", "sr-latn", "sr-ec"))
}
```

  - `raster.tile_names(kind, bbox) -> list[str]` — Copernicus `"N44_E020"` (1° tiles) for kind `"dem"`, WorldCover `"N42E021"` (3° tiles) for kind `"worldcover"`.
  - `raster.iter_windows(paths, bounds)`: yield bounded source-resolution raster windows with transform, nodata mask and source identity; iteration is deterministic and never loads an entire country raster into memory. Each source exposes cached tiles selected against the documented territory bounds and required buffer; a verified territory polygon may narrow selection when available.
  - Interim **`dem`** (source id `"dem"`): `{"vintage", "tiles": [{"id", "path", "sha256"}], "_files"}`. Paths are relative to the raw-cache root and validated against the manifest. Record nodata and transforms from the files.
  - Interim **`landcover`** (source id `"landcover"`): `{"vintage", "tiles": [{"id", "path", "sha256"}], "legend": {"10": "Tree cover", …}, "_files"}`. Use source-resolution classes; retain neither 10″ modes as representative proportions nor a mandatory base64 lattice. Fail clearly if a cached file is missing or its checksum differs.
  - Interim **`water`** (source id `"water"`):

```jsonc
{
  "vintage": "OpenStreetMap (Geofabrik: Srbija i Kosovo) i Vikipedijine dužine reka",
  "rivers": [{"name": "Дунав", "name_lat": "Dunav", "wikidata": "Q1653", "length_km": 2850.0, "mapped_km": 401.2, "lines": [[[lon, lat], …], …]}],
  "lakes":  [{"name": "Ђердапско језеро", "name_lat": "Đerdapsko jezero", "wikidata": null, "area_km2": 253.0, "rings": [[[lon, lat], …], …]}],
  "_files": ["…"]
}
```

  Rivers: the waterway lines of both extracts with `fclass == "river"` and a name, joined per name. `length_km` is Wikidata's when the folded name matches, else `null`; `mapped_km` is the length within the extracts. `wikidata` is `null` without a match. Lakes: named water polygons with a measured area of at least 1 km²; `rings` are all rings of the polygon; `wikidata` from the name match if there is one.
  - Interim **`places`** (source id `"places"`): `{"vintage", "places": [{"name": "Суботица", "name_lat": "Subotica", "fclass": "city", "population": 100000, "lon": 19.6679, "lat": 45.9406}], "_files"}` — points with `fclass` in `city`, `town`, `village` and a name, from the Serbia extract only (Kosovo's towns are Task 3's).

**Downloads** (all complete files through `self.download`, `expect_binary=True`): choose Copernicus 1° and WorldCover 3° tiles by footprint intersection with a verified cached territory polygon and documented buffer when available; otherwise use the bounding box and buffer. Fetch must work before boundary processing, including from a clean cache. Derive expected coverage rather than relying on a fixed count. Verify all needed tiles and fail clearly on gaps. Benchmark HTTP range/window reads as a separate optimization; use only when host support, provenance, replay and offline caching are verified, with full-tile fallback. Geofabrik `srb.GEOFABRIK_URL.format(region="serbia")` and `region="kosovo"`. Geofabrik's free shapefile zip holds layers `gis_osm_waterways_free_1` (lines: `fclass`, `name`), `gis_osm_water_a_free_1` (polygons: `fclass`, `name`), `gis_osm_places_free_1` (points: `fclass`, `name`, `population` when mapped). Record the zip's file date or the `README`-style metadata inside the zip in `vintage` so the extract can be told apart later.

- [ ] **Step 1: Raster tests:** derive tile footprints from a bounding-box fixture, then filter an irregular polygon without omitting intersecting tiles; include a boundary-touching case. Use `rasterio.io.MemoryFile` source rasters to verify window iteration, geotransforms, nodata masks, deterministic iteration, no overlap double-counting, coverage gaps, missing cache files and checksum errors. Test Wikidata with a recorded response and water/places with small shapefiles.
- [ ] **Step 2: Run** → FAIL. **Step 3: implement** the two helpers → PASS. **Step 4: failing tests for the four sources' `process()`** taking file paths (not the network): `process_files(paths: dict) -> dict`. **Step 5: implement** the four sources → PASS.
- [ ] **Step 6: Run for real** — `uv run python -m pipeline fetch dem landcover water places` (about 2.5 GB; report the sizes), then `process` each. Print: source dimensions and coverage gaps, the number of rivers kept at `srb.RIVER_MIN_LENGTH_KM`, the five longest with their Wikidata lengths, the number of lakes, and the number of places. Check source samples at Belgrade (`20.4606, 44.8125`) and Kopaonik's Pančićev vrh (`20.8156, 43.2725`), reporting source, pixel value, location and nodata handling. Validate expected ranges against the actual source rather than assuming a point value equals a whole-hex average. Record bytes transferred by source, selected tile count and coverage.
- [ ] **Step 7: Whole suite, self-review, commit** (`git commit -m "Geography: source rasters, OpenStreetMap water and places"`).

---

### Task 5: The world builder

**Files:**
- Create: `pipeline/build/world.py`
- Test: `tests/test_world_builder.py`

**Interfaces:**
- Consumes (interims): `boundaries`, `kim`, `dem`, `landcover`, `water` — shapes as in Tasks 3 and 4:

```jsonc
// boundaries: {"oblasti": [{"id", "rings"}], "regioni": [...], "municipalities": [{"id", "rings"}], "countries": [{"iso", "name_sr", "rings"}]}
// kim:         {"oblasti": [{"id", "rings"}], "municipalities": [{"id", "rings"}]}
// dem:         {"vintage", "tiles": [{"id", "path", "sha256"}]}
// landcover:   {"vintage", "tiles": [{"id", "path", "sha256"}], "legend": {...}}
// water:       {"rivers": [{"name", "name_lat", "length_km", "mapped_km", "lines"}], "lakes": [{"name", "name_lat", "area_km2", "rings"}]}
```

- Produces: builder `world` with `REQUIRES = ["boundaries", "kim", "dem", "landcover", "water"]`, `PRODUCES = ["_world", "world.json"]`; interim **`_world`**:

```jsonc
{
  "grid": {"radius": 5.0, "cols": …, "rows": …},
  "projection": {"min_x": …, "max_y": …, "margin": 200.0},
  "width": …, "height": …,
  "owner": [int], "county": [int], "county_samples": [[int × 7]],      // as upstream; states are 30 okruzi, counties 197 municipalities
  "states": ["RS110", …], "counties": ["70017", …],                    // same order as world.json
  "water": [int], "cover": [int], "pct": {"forest": [...], "crop": [...], "pasture": [...], "grass": [...], "shrub": [...], "wetland": [...], "developed": [...]},
  "cells_of_county": [[cell, …], …],                                     // per county index; may be empty
  "county_area_km2": [number | null]                                    // source polygons projected to equal-area; matches county order
}
```

  and **`world.json`**: upstream's shape (`version: 2`, `grid`, `width`, `height`, `margin`, `owner`, `county`, `elev`, `elev_max`, `water`, `relief`, `cover`, `pct`, `tables`, `states`, `counties`, `rivers`) plus `"projection": {"min_x", "max_y", "margin"}` and `"elev_range": [int | null]` (and null-safe elevation, relief and cover fields). `states` is `[{"fips": "RS225", "abbr": null, "name": "Nišavski okrug"}]` with `okrug_name(territory.name(id))`; `counties` is `[{"geoid": "70017", "name": "Aleksandrovac"}]`. `tables.water` keeps upstream's four ids (0 Land, 1 Ocean, 2 Coast, 3 Lake) with Serbian names and rules; `tables.relief` and `tables.cover` keep upstream's ids and keys, with Serbian names, colours and rule text.

- Constants from `srb`: `HEX_RADIUS_KM`, `MARGIN_KM`, `WATER`, `FOREIGN`, `LAND`, `LAKE`, `LAKE_MIN_KM2`, `FLAT`, `HILLS`, `MOUNTAINS`, `PEAKS`, `RELIEF_HILLS_RANGE_M`, `RELIEF_MOUNTAINS_RANGE_M`, `PEAKS_MEAN_M`, `URBAN_MIN_PCT`, `RIVER_MIN_LENGTH_KM`.
- Pure functions the tests call: `classify_relief(mean_m, range_m) -> int`, `cover_shares(class_counts: Counter) -> dict[str, int]`, `dominant_cover(shares: dict[str, int], mean_m: float) -> int`, `relief_table()`, `cover_table()`, `water_table()`, `build()`.

**Rules.**
1. **States:** the 25 okruzi of `boundaries.oblasti` and the 5 of `kim.oblasti`, sorted by name.
2. **Counties:** `boundaries.municipalities` (168) and `kim.municipalities` (29), sorted by id. Compute and retain each source polygon area in the equal-area projection, including holes and multipolygons; document geometry source, year and Kosovo stitch approximations. Supply it to `counties.json` and density lenses independently of hex ownership.
3. **Projection and grid:** exactly as upstream's `world.py` did (`git show 1fdbdf3:pipeline/build/world.py`, lines 260–273), with the okruzi's rings.
4. **Ownership:** the seven sample points (centre and six at 60 % of the radius) of every hex are located in, in order, the lakes (`area_km2 >= LAKE_MIN_KM2`), the okruzi, the countries. Upstream's majority rule decides between okrug and foreign; "sea" is anything in none. Serbia is landlocked, so **every non-lake water hex with at least one land neighbour becomes land with its land neighbours' majority owner** (upstream's sliver fix, relaxed from four neighbours to one). Hexes with no land neighbour at all stay `WATER` / `OCEAN`.
5. **Counties:** for owner ≥ 0, the seven points in the municipalities; the hex's county must lie in its okrug (each municipality's okrug is `territory.oblast_of(id)`); centre first, else the most common in-okrug sample, else any sample.
6. **Elevation, relief, range:** stream native-resolution raster windows. Assign each valid pixel by its centre projected into the hex and compute an area-weighted mean, source-pixel minimum and maximum; document the area weights, boundary and nodata rule. Compute range as max minus min and classify relief from those values. Ensure overlapping source tiles do not double-count. A Serbian hex without valid samples has `null` elevation, maximum, range and relief; the renderer uses a clearly documented unknown-data style and the checker reports it. Foreign cells have no source value. Compare results and classes with a full-resolution reference before accepting the build.
7. **Land cover:** stream native-resolution WorldCover pixels and aggregate area-weighted valid pixel areas by class inside each hex using the same documented centre-in-hex, boundary, nodata and overlap rules; class areas → `cover_shares`:

| `pct` key | WorldCover classes |
|---|---|
| `forest` | 10 |
| `shrub` | 20 |
| `pasture` | 30 |
| `crop` | 40 |
| `developed` | 50 |
| `wetland` | 90 |
| `grass` | none (always 0) |

  Shares are of the hex's valid sampled area, whole percent; report coverage and retain unknown separately from a real zero. `dominant_cover`: urban (9) when the developed share is at least `URBAN_MIN_PCT`; else the largest of forest (1 below 900 m mean elevation, 2 at or above: a drawing choice, since WorldCover has one tree-cover class — say so in the rule text), scrub (4), pasture (6), cropland (7), wetland (8), barren (10, from class 60); `null` when there are no valid samples. Cells with no valid cover samples have `null` shares and an unknown cover, not fabricated zeros; foreign cells are not presented as Serbian land data.
8. **Lakes:** a hex whose centre lies in a lake of at least `LAKE_MIN_KM2` is `WATER` with class `LAKE`; smaller lakes do not make water hexes.
9. **Rivers:** keep a river when `length_km or mapped_km` is at least `RIVER_MIN_LENGTH_KM`; rank by that number, 1 = longest, ties by name. Project, clip to the map with `geom.clip_polyline`, drop pieces shorter than 1 km, `geom.simplify(piece, 0.8)`, `pts` rounded to one decimal.
10. **Tables:** rule texts in Serbian Latin, each stating its numbers. For relief, for example: `"Razlika između najviše i najniže tačke u heksu: do 60 m ravnica, od 60 do 300 m brdovit teren, od 300 m planine. Vrhovi su heksovi čija je srednja visina najmanje 1.300 m."` Improve the wording if you can; keep every number. The cover table says that forest type is a drawing choice (rule 7). The water table says there is no sea on this map and which lakes make water hexes.

- [ ] **Step 1: Failing unit tests** for `classify_relief` (`(200, 30) → FLAT`, `(200, 60) → HILLS`, `(1200, 300) → MOUNTAINS`, `(1350, 400) → PEAKS`, `(100, 0) → FLAT`), `cover_shares` (`Counter({10: 5, 40: 3, 50: 2})` → forest 50, crop 30, developed 20, others 0; an empty counter → all null), `dominant_cover` (developed 30 → 9; forest 60 at 800 m → 1 and at 900 m → 2; barren only → 10; nothing → null), and that each table has the upstream ids with Serbian text.
- [ ] **Step 2: Run** → FAIL. **Step 3: implement** those → PASS.
- [ ] **Step 4: Failing end-to-end test on a tiny synthetic map.** Write the five interims into a temporary `INTERIM` (`mock.patch.object(store, "INTERIM", Path(tmp) / "interim")` and the same for `WEB_DATA`): two okruzi that are neighbouring squares of 0.6° near Novi Sad, one municipality each (one with two rings), one neighbouring country ring around them, one lake polygon of 0.05° × 0.1°, tiny source rasters with a known transform, nodata, mixed land-cover classes and elevations including a narrow peak that would disappear under averaging, and two rivers (one with `length_km: null, mapped_km: 30`, one with `length_km: 100`). Call `world.build()`, read `world.json` and the `_world` interim, and assert: `len(states) == 2` and their names; every hex inside the squares has `owner` in `(0, 1)`; the lake hexes are `owner -1` with `water == 3`; a hex east of the squares has `owner == -2`; `county` is `0` or `1` matching the squares; elevation increases to the east; the forest hex has `cover == 1` and the crop hex `cover == 7`; the urban corner has `cover == 9`; `rivers` has exactly one entry with `rank == 1`; `projection` and `elev_range` are present and `len(elev_range) == grid.cols * grid.rows`; `cells_of_county[0]` lists exactly the hexes with `county == 0`.
- [ ] **Step 5: Run** → FAIL. **Step 6: implement `build()`** by porting upstream's `world.py` (read `git show 1fdbdf3:pipeline/build/world.py`) to these rules. Helpers already live in `pipeline.core.geom` and `pipeline.core.geo`. **Step 7: Run** → PASS.
- [ ] **Step 8: Add `check(web_dir)`** to the builder: FAIL when a Serbian hex has `water != 0` while not a lake, NOTE with the counts of hexes without elevation or cover samples, PASS with the class shares. (Task 7's checker runs it.)
- [ ] **Step 9: Whole suite, self-review, commit** (`git commit -m "World builder: Serbia's grid, okruzi and municipalities, terrain and rivers"`).

---

### Task 6: Yields, cities, okruzi, the nation, Kosovo's towns

**Files:**
- Create: `pipeline/build/yields.py`, `pipeline/build/cities.py`, `pipeline/build/states.py`, `pipeline/build/kim_towns.py`, `pipeline/data/city_positions.csv`
- Test: `tests/test_yields.py`, `tests/test_cities.py`, `tests/test_states.py`, `tests/test_kim_towns.py`

**Interfaces:**
- Consumes (interims): `census`, `rzs_db`, `gdp`, `places`, `kim` (Tasks 1–4; shapes as written there), `_world` (Task 5). `city_positions.csv` (header `id,lon,lat`, empty at first) is a reviewed override when the automatic position of a city is wrong.
- Produces:
  - `yields.jobs_from_nace(by_nace: dict[str, float | None]) -> dict[str, int | None]` — the census `industry` row (keys `total`, `A` … `S`, `unknown`) → the 19 industry keys, rounded to whole jobs; `None` stays `None`; `total`, `unknown` and any letter that is not in `srb.NACE_TO_KEY` are ignored; a letter missing from the input gives `None`.
  - `yields.yields_of(jobs: dict, gdp: float | None) -> dict` — `food = agriculture`; `production = manufacturing + construction + mining`; `science = professional + information`; `culture = arts`; `gold = gdp`; a yield with any missing industry is `None`.
  - `yields.growth(series: list | None, years: list[int], start: int = 2021) -> tuple[float | None, list[int] | None]` — latest ÷ start − 1; `None` when either is missing or when the absolute value exceeds 0.25.
  - `yields.ranks(rows: list[dict], keys: list[str], value=lambda r, k: r.get(k)) -> None` — writes `r["ranks"][key]` for each row (1 = top, ties broken by population, `None` where the value is `None`).
  - `yields.peers(rows, n=5) -> None` — `r["peers"]`: the `n` other ids whose population is closest by ratio.
  - Builder `cities` (`REQUIRES = ["census", "rzs_db", "gdp", "places", "_world"]`, `PRODUCES = ["cities.json", "_cities"]`), builder `states` (`REQUIRES = ["census", "rzs_db", "gdp", "_world"]`, `PRODUCES = ["states.json", "nation.json"]`), builder `kim_towns` (`REQUIRES = ["kim", "_world"]`, `PRODUCES = ["kim_towns.json"]`).
  - **`cities.json`** — a list sorted by population, descending, of the units that are cities:

```jsonc
{
  "id": "79022", "name": "Niš", "full": "Niš (Nišavski okrug)",
  "states": ["RS225"], "metro": false, "capital": false,
  "x": 318.4, "y": 262.1, "cell": 5123,                       // x, y: the position of the unit's largest urban settlement
  "population": 260455, "employed": 101200,                     // population: the RZS estimate of the unit's latest year
  "yields": {"food": 820, "production": 23100, "gold": 4.2e9, "science": 13200, "culture": 4100},
  "jobs": {"agriculture": 820, "mining": 300, "…": null},
  "median_income": null, "median_rent": null, "home_value": null, "rent_burden": null,   // not published below region level
  "unemployment": 0.0987, "wage_net": 88210.0, "age65": 0.219,                             // new: RSD per month; share 65+
  "gdp": 4.2e9, "gdp_year": 2023, "gdp_by_industry": null, "gdp_undisclosed": null, "gdp_estimated": ["total"],
  "growth": -0.0131, "growth_years": [2021, 2025],
  "counties": ["71285", "71307", "71315", "71323", "71331"],    // territory.parts_of(id)
  "footprint": [5119, 5123, 5124, …],                           // Serbian land cells whose county is in counties; includes cell
  "pop_series": {"1991": 254100, "…": null, "2025": 260455},
  "ranks": {"population": 2, "gdp": 2, "gdp_per_capita": 5, "growth": 61, "food": 9, "production": 2, "gold": 2, "science": 2, "culture": 2},
  "peers": ["89010", "70645", "…"],
  "settlement_population": 178926                              // the urban settlement itself, Popis 2022
}
```

  - **A city is** a 5-digit unit that (a) is not in Kosovo, (b) is not a city municipality (`territory.is_city_municipality`: Belgrade's seventeen opštine and the 5-digit sub-units of the aggregates; only the aggregate can be a city, so Beograd, Niš and Novi Sad appear once each, as upstream's metros do), (c) has, in the census, an urban settlement of at least `srb.CITY_MIN_URBAN_POP` inside the unit or one of its parts, and (d) has an RZS population (latest `pop_years` entry) of at least `srb.CITY_MIN_POP`. `id` is the unit; aggregates use their own id (`79014` Beograd, `79022` Niš, `79049`, `79057`, `79065`, `89010`). `name` is `territory.name(id)` without a leading `"Grad "`. `capital` is true for `79014` only. `metro` is false.
  - **Position.** Among the unit's (or its parts') settlements that have an id in `census.settlements` and are urban, take the most populous. Find a place in `places` whose `fold_key(name_lat)` equals the settlement's folded name and whose cell (`grid.cell_at` of the projected point) has `_world.county` equal to the settlement's unit or one of its parts. If none matches, use `city_positions.csv`; if that has no row either, leave the city out and print its name. `cell` is the nearest Serbian land cell of the unit's territory to the position, moved to the nearest free cell of the same territory when another city holds it.
  - **Aggregates.** For `79014` the position is the centre of the Serbian land cell nearest to the centroid of the cells of `70246` (Stari grad, where the fortress is), so the capital's marker sits on the old town and not on a suburb. For the other aggregates (`79022`, `79049`, `79057`, `79065`, `89010`) the settlement is the most populous urban settlement among the parts.
  - **Counts** come from the census rows of `territory.parts_of(id)` summed (`population` of the census is kept only as a check; `employed`, `jobs`, the shares of `education`, `religion`, `ethnicity`, `commute` are sums); a unit with no census row for any part leaves the field `null`.
  - **GDP** is an estimate, marked as such: `gdp = gdp["nuts3"][oblast] × 1e6 × city_employment / okrug_employment`, where the employments are `rzs_db.employment.by_unit[unit]["total"]` summed over the city's parts and over all of the okrug's parts on the map (the units of `_world.counties` whose `territory.oblast_of` is the okrug); `None` when the okrug has no GDP or no employment. `gdp_estimated` is `["total"]` then.
  - **`unemployment`** = unemployed ÷ (employed + unemployed) from the census activity row, 4 decimals. **`age65`** = `rzs_db.pop_65.by_unit[id]` (`null` for an aggregate without its own row; do not average shares). **`wage_net`** = `rzs_db.wages.net[id]`.
  - **`_cities` interim:** `{"cities": <the same list>, "units": {"70017": {"is_city": false, "city": null, "why": "no urban settlement of 10,000+"}, "71331": {"is_city": false, "city": "79022", "why": "city municipality of 79022"}}, …}` for every non-Kosovo unit. `city` is the id of the city the municipality belongs to in the final `cities.json` — itself when it is a city, its aggregate's id when the aggregate is a city (one left out for lack of a position makes its parts `null`), else `null` — and is what Task 7's table reads. `why` says, in a short English phrase for the developer-facing checker, why a unit that is not a city is not one.
  - **`states.json`** — one row per okrug in `_world.states` order, each with `fips`, `abbr: null`, `name`, `population`, `employed`, `yields`, `jobs`, `median_income`/`median_rent`/`home_value`/`rent_burden` (`null`), `unemployment`, `wage_net`, `age65`, `gdp`, `gdp_year`, `gdp_by_industry: null`, `gdp_undisclosed: null`, `gdp_estimated: null`, `growth`, `growth_years`, `ranks`, `label`, `land`, `energy: null`. Sums are over the okrug's units on the map (those in `_world.counties`); `population` is the sum of the units' RZS estimates; `age65` is Σ(population × share) ÷ Σ population over the units with both; `wage_net` is the employment-weighted mean of the units' wages (weights: registered employment); `gdp` is `gdp.nuts3[fips] × 1e6`. Kosovo's five okruzi have `null` everywhere except `fips`, `abbr`, `name`, `label`, `land`. `label` is `{x, y, angle: 0, size}` at the centroid of the okrug's cells, `size = clamp(3.2 × sqrt(cells), 3, 22)`. `land` is the mean of `pct` over the okrug's cells with `cover > 0`, as 0..1 fractions, or `null`. Ranks are among the 25 okruzi with data.
  - **`nation.json`**: `{"vintage": "Procene RZS 2025 · Popis 2022", "year": <latest pop year>, "gdp_vintage": <gdp.vintage>, "nation": <the same shape as an okrug, summed over the 25 okruzi>, "yields": srb.YIELDS, "industries": srb.INDUSTRY_NAMES}`.
  - **`kim_towns.json`**: `{"version": 1, "vintage": <kim.vintage>, "sources": ["kim"], "towns": [{"name": "Priština", "x": …, "y": …, "cell": <nearest Serbian land cell>}]}`.

- [ ] **Step 1: Failing tests for the yields helpers** (numbers chosen to expose each rule):

```python
# tests/test_yields.py
import unittest

from pipeline.build import yields


class JobsTest(unittest.TestCase):
    def test_nace_letters_map_to_keys_and_unknowns_are_dropped(self):
        jobs = yields.jobs_from_nace({"A": 10.4, "C": 20.6, "Z": 99.0, "total": 30.0, "unknown": 5.0, "F": None})
        self.assertEqual(jobs["agriculture"], 10)
        self.assertEqual(jobs["manufacturing"], 21)
        self.assertIsNone(jobs["construction"])
        self.assertEqual(len(jobs), 19)
        self.assertNotIn("Z", jobs)


class YieldsTest(unittest.TestCase):
    def test_formulas_and_missing_values(self):
        jobs = {k: 1.0 for k in ("agriculture", "manufacturing", "construction", "mining", "professional", "information", "arts")}
        y = yields.yields_of(jobs, 1e9)
        self.assertEqual((y["food"], y["production"], y["science"], y["culture"], y["gold"]), (1.0, 3.0, 2.0, 1.0, 1e9))
        jobs["construction"] = None
        self.assertIsNone(yields.yields_of(jobs, 1e9)["production"])
        self.assertIsNone(yields.yields_of(jobs, None)["gold"])


class GrowthTest(unittest.TestCase):
    def test_growth(self):
        self.assertEqual(yields.growth([100, 102, 98], [2023, 2024, 2025], start=2023), (-0.02, [2023, 2025]))
        self.assertEqual(yields.growth(None, [2025], start=2021), (None, None))
        self.assertEqual(yields.growth([100, None], [2021, 2025]), (None, None))
        self.assertEqual(yields.growth([100, 200], [2021, 2025]), (None, None))  # more than 25 %: not believed


class RankTest(unittest.TestCase):
    def test_ranks_and_peers(self):
        rows = [{"id": "a", "population": 300, "gdp": 10.0}, {"id": "b", "population": 200, "gdp": 10.0},
                {"id": "c", "population": 100, "gdp": None}, {"id": "d", "population": 400, "gdp": 5.0}]
        yields.ranks(rows, ["population", "gdp"])
        self.assertEqual([r["ranks"]["gdp"] for r in rows], [1, 2, None, 3])  # the tie goes to the larger population
        self.assertEqual([r["ranks"]["population"] for r in rows], [2, 3, 4, 1])
        yields.peers(rows, n=2)
        self.assertEqual(rows[1]["peers"], ["a", "c"])
```

- [ ] **Step 2: Run** → FAIL. **Step 3: implement `yields.py`** → PASS.
- [ ] **Step 4: Failing tests for the city rules** on a hand-made world (patch `store.INTERIM`): four units in one okrug — an aggregate `79014`-like with two parts, a plain unit above both thresholds, a unit whose only urban settlement is too small, a Kosovo unit — plus a `places` entry that matches one settlement by name and cell and one that matches nothing. Assert: the three rules of "is a city"; the aggregate's counts are the sum of its parts; GDP is the okrug GDP times the employment share and `gdp_estimated == ["total"]`; a city without a position is left out and printed; `cell` is unique; `peers` has five entries only when that many cities exist.
- [ ] **Step 5: Run** → FAIL. **Step 6: implement `cities.py`** → PASS.
- [ ] **Step 7: Failing tests for okruzi and the nation**: an okrug's `age65` is population-weighted, `wage_net` employment-weighted, `gdp` in euros; a Kosovo okrug is all `null` with a `label` and `land`; the nation equals the sum over the 25; `kim_towns.json` has 29 towns with distinct cells and a Serbian-land cell each.
- [ ] **Step 8: Run** → FAIL. **Step 9: implement `states.py` and `kim_towns.py`** → PASS.
- [ ] **Step 10: Whole suite, self-review, commit** (`git commit -m "Cities, okruzi and the nation from Popis, RZS and Eurostat; Kosovo's towns"`).

---

### Task 7: Lenses, the municipalities table, the catalog and the checker

**Files:**
- Create: `pipeline/build/lenses.py`, `pipeline/build/counties.py`, `pipeline/build/catalog.py`
- Coordinate with Task 8: versioned manifest, `lens-values.json`, lazy loading and adapter; update `docs/DATA_CONTRACTS.md` together.
- Create: `pipeline/check.py`
- Test: `tests/test_lenses.py`, `tests/test_counties_table.py`, `tests/test_check.py`, `tests/test_builder_checks.py`

**Interfaces:**
- Consumes (interims): `_world`, `_cities`, `census`, `rzs_db`, and `web/data/world.json` for the cover table. Their shapes are the Interfaces sections of Tasks 1, 2, 5 and 6 of this plan. `catalog.py` is upstream's (`git show 1fdbdf3:pipeline/build/catalog.py`) unchanged.
- Produces:
  - Builder `lenses` (`REQUIRES = ["_world", "world.json", "_cities", "census", "rzs_db"]`, `PRODUCES = ["lenses.json", "lens-values.json"]`; it needs `world.json` for the cover table's colours), builder `counties` (`REQUIRES = ["_world", "_cities", "census", "rzs_db"]`, `PRODUCES = ["counties.json"]`; land shares come from `_world.pct`), builder `catalog` (`RUN_LAST = True`, `PRODUCES = ["sources.json"]`).
  - **Versioned lens contract:** `lenses.json` is a small manifest `{version: 2, vintage, groups, lenses: [{id, group, name, icon, emoji, unit, format, scale, domain, ramp, higher_is, source, description, note, value_source}]}` in the fifteen-lens order below. For the twelve municipal lenses `value_source` is `{kind: "municipality", file: "lens-values.json", key: <lens id>}`. `lens-values.json` is `{version: 2, municipality_ids: [geoid, …], values: {<lens id>: [number | null, …]}}`; its ID list must exactly match `world.json.counties` in length and order, validated by the checker. A value is stored once per municipality. Resolve a cell using `world.county[cell]`; invalid indices, foreign cells, water and absent statistics resolve to `null`. For physical lenses use `{kind: "world", field: "elev" | "relief" | "cover"}` and reuse those per-cell arrays. An adapter materializes a per-cell view only on lens activation for existing rendering consumers; preserve `null` and keep municipality values for domains and Explorer, including municipalities owning zero hexes. `domain` is the 2nd–98th percentile of valid municipality values; physical lens domains follow valid hex values. "Latest" means the last year of `rzs_db.pop_years`.

  The manifest and data are independent assets: fetch the manifest when needed for the lens UI and `lens-values.json` once on activation of a municipal lens, cached by `loadData()`. Update `docs/DATA_CONTRACTS.md`, all relevant consumers and the checker in the same change. Tests compare indexed lookups and materialized arrays against the original per-cell semantics, including Kosovo, foreign land, water, missing statistics, valid zero and zero-hex municipalities.

| id | group | name | unit | format | scale | higher_is | source |
|---|---|---|---|---|---|---|---|
| `density` | `people` | Gustina naseljenosti | `stanovnika / km²` | `int` | `log` | neutral | `rzs_db` |
| `pop_change` | `people` | Promena broja stanovnika | `%` | `pct` | `linear` | neutral | `rzs_db` |
| `natural_increase` | `people` | Prirodni priraštaj | `na 1.000 stanovnika` | `float` | `linear` | neutral | `rzs_db` |
| `age65` | `people` | Stariji od 65 godina | `%` | `pct` | `linear` | neutral | `rzs_db` |
| `education` | `work` | Visoko obrazovanje | `%` | `pct` | `linear` | good | `census` |
| `wages` | `work` | Prosečna neto zarada | `RSD` | `rsd` | `log` | good | `rzs_db` |
| `unemployment` | `work` | Stopa nezaposlenosti | `%` | `pct` | `linear` | bad | `census` |
| `manufacturing` | `work` | Prerađivačka industrija | `%` | `pct` | `linear` | neutral | `census` |
| `commute` | `work` | Rad u drugoj opštini | `%` | `pct` | `linear` | neutral | `census` |
| `orthodox` | `identity` | Pravoslavni | `%` | `pct` | `linear` | neutral | `census` |
| `serbs` | `identity` | Srbi | `%` | `pct` | `linear` | neutral | `census` |
| `life_expectancy` | `life` | Očekivano trajanje života | `godine` | `float` | `linear` | good | `rzs_db` |
| `elevation` | `land` | Nadmorska visina | `m` | `int` | `linear` | neutral | `dem` |
| `relief` | `land` | Reljef | — | `category` | `linear` | neutral | `dem` |
| `land_cover` | `land` | Zemljišni pokrivač | — | `category` | `linear` | neutral | `landcover` |

  Groups in order: `people` Stanovništvo, `work` Rad i zarade, `identity` Identitet, `life` Kvalitet života, `land` Zemljište. Formulas: `density` = latest RZS population ÷ municipality polygon area in km² (equal-area projection, source and vintage recorded); null if area is unavailable or nonpositive; `pop_change` = pop[latest] ÷ pop[2015] − 1, a ten-year change whose base year is `srb.LENS_CHANGE_YEARS = (2015, None)` (this task adds that constant next to `srb.GROWTH_YEARS`, which is the 2021 base of the `growth` field of cities and okruzi); `education` = `education.higher / education.total15`; `unemployment` = unemployed ÷ (employed + unemployed); `manufacturing` = `industry.C / industry.total`; `commute` = `(other_unit + other_oblast) / commute.total`; `orthodox` = `religion.orthodox / religion.total`; `serbs` = `ethnicity.srbi / ethnicity.total`; `life_expectancy` = the mean of `m` and `f` (say so in `note`). Every lens has a `note` stating its year and source in Serbian Latin; the year comes from the interim (`pop_years`, the table's own `year`), never typed. `relief` categories: `flat` Ravnica, `hills` Brdovito, `mountains` Planine, `peaks` Vrhovi. `land_cover` categories are the cover ids 1, 2, 4, 6, 7, 8, 9, 10 with the colours of `world.json`'s `tables.cover`. A new format `rsd` joins the lens formats.
  - **`counties.json`** keeps upstream's column-oriented shape (`vintage`, `fields`, `columns`, `rows`), one row per municipality in `_world.counties` order: `["geoid", "name", "state", "population", "land_km2", "density", "age65", "education", "wage_net", "unemployment", "manufacturing", "commute", "orthodox", "serbs", "life_expectancy", "natural_increase", "forest", "crop", "pasture", "developed", "city", "cell"]`. `state` is the okrug id; `wage_net` has format `rsd`; `city` is the cities.json id of the city the municipality belongs to (itself when it is one), else `null`; `cell` is the municipality's first cell in `cells_of_county`, or `null` if it owns none; keep such rows in the Explorer and provide a documented selection fallback. Kosovo rows carry only `geoid`, `name`, `state`, `land_km2`, the land shares and `cell`.
  - **`pipeline/check.py`**: upstream's design (`Report`, `need_keys`, `check_cells`, per-file `check_*` functions, `builder_checks()`, `run()`, `main()`; read `git show 1fdbdf3:pipeline/check.py`) rewritten for these files: ids `^RS\d{3}$` for `fips`, `^\d{5}$` for `geoid`; 30 okruzi, 197 municipalities; `median_*` fields may be `null`; `wage_net` and `age65` are numbers or `null`; `elev_range` is a per-cell array of non-negative ints or null and `projection` an object `{min_x, max_y, margin}` whose margin equals `margin`; nation.json carries non-empty strings `vintage` and `gdp_vintage` and an integer `year`; every okrug and city carries `gdp_year` (int or `null`) and `growth_years` (two ints or `null`); every lens carries non-empty `source`, `description` and `note`; Kosovo's five okruzi are `null` in every numeric field (only `fips`, `name`, `label`, `land` are set, `abbr` and `energy` are `null`) and a municipalities row whose `geoid` starts with `"9"` is `null` except `geoid`, `name`, `state`, `land_km2`, the land shares and `cell`, while any `null` population elsewhere is a failure; lens ids are exactly the fifteen; ranks are permutations. Data-quality lines: cities on water, cities sharing a cell, per-lens share of `null` among Serbian hexes (WARN above 5 %), and a `WARN` naming every 5-digit unit that is in one of `census.units`, `rzs_db.pop` or `_world.counties` but not in all three (new city municipalities keep being created, so a difference is not a failure — but it must be named). `REQUIRED = ["world.json", "cities.json", "states.json", "nation.json", "lenses.json", "lens-values.json", "sources.json", "counties.json"]`. Validate schema versions, aligned municipality IDs and all references; distinguish expected Kosovo missing values from missing values elsewhere.

- [ ] **Step 1: Lens tests:** `unit_values(...)` with hand-made units, IDs and domain; adapter equivalence for every fixture cell including valid zero, Kosovo null, foreign/water, no-owned-cell unit, bad/misaligned IDs and physical world fields. Verify the manifest and deferred values fetch separately.
- [ ] **Step 2: Run** → FAIL. **Step 3: implement `lenses.py`** → PASS.
- [ ] **Step 4: Failing tests for `counties.json`** on the same fixture: column order, `fields[j].key == columns[j]`, a Kosovo row's nulls.
- [ ] **Step 5: implement `counties.py`** → PASS.
- [ ] **Step 6: Failing tests for the checker** in the style of upstream's `tests/test_check.py` (a `dataset()` helper that builds a tiny valid set of the seven files in a temporary folder): each check passes on the valid set, and each rule fails when its condition is broken (one test per rule).
- [ ] **Step 7: implement `check.py`** → PASS. Also restore `tests/test_builder_checks.py` from upstream (`git show 1fdbdf3:tests/test_builder_checks.py`) adapted to your `dataset()`.
- [ ] **Step 8: Whole suite, self-review, commit** (`git commit -m "Fifteen lenses, the municipalities table, the source catalog and the data checker"`).

---

### Task 8: Engine patches and the i18n module

**Files:**
- Create: `web/js/i18n/transliterate.js`, `web/js/i18n/index.js`, `web/js/i18n/boot.js`, `web/js/i18n/transliterate.test.js`, `web/js/i18n/index.test.js`, `web/css/i18n.css`, `web/js/ext/towns/index.js`
- Modify: `web/js/camera.js`, `web/js/main.js`, `web/js/world.js`, `web/js/format.js`, `web/js/app/search.js`, `web/js/app/urlstate.js`, `web/js/render/map.js`, `web/js/render/banners.js`, `web/js/render/art/terrain.js`, `web/js/render/art/city.js`, `web/js/ui/topbar.js`, `web/js/ext/advisors/core/frame.js`, `web/js/ext/advisors/core/data.js`, `web/js/ext/advisors/views/commerce.js`, `energy.js`, `culture.js`, `military.js`, `web/css/style.css` (styles for the script button only)
- Modify, in `web/js/ui/yieldReport.js`: only lines 9–13
- Not yours: `web/index.html` and every other file under `web/js/ui/` and `web/js/app/` (Task 9), everything under `web/js/ext/` except the advisor files' constant lines listed below and your new folder `web/js/ext/towns/` (Task 10). In the advisor files touch constants only.

**Interfaces:**
- Produces:
  - `transliterate.js`: `PROTECTED` (the same strings as `pipeline.core.srtext.PROTECTED`, in double quotes), `toCyrillic(text)`, `toLatin(text)`, `fold(text)` — behaviour identical to `srtext.py` (digraphs, capital digraphs in all-caps words, protected names as whole words, other scripts untouched).
  - `index.js`: `initialScript({ hash, stored, language }) -> "lat" | "cyr"` (the hash's `script=` wins, then the stored value, then `"cyr"` when `language` matches `/^sr(-[A-Za-z]{2})?$/i` and is not `sr-Latn`, else `"lat"`); `getScript()`; `script(text)` (`toCyrillic` when the script is Cyrillic, else the text unchanged); `setScript(s)` (stores the choice, rewrites the hash through `history.replaceState`, then `location.reload()`: the app restores its view from the hash); `installScriptToggle(button)` (the button shows `Ћир` in Latin mode and `Lat` in Cyrillic mode, and carries `data-no-translit`); `watchDom()` (when the script is Cyrillic: a `MutationObserver` over `document` that transliterates text nodes and the `title`, `aria-label`, `alt` and `placeholder` attributes of everything added or changed, skipping subtrees with `data-no-translit` and the elements `script`, `style`, `code`, `kbd`, `pre`, `textarea`, and never the value of an `input`; it remembers each node's Latin source in a `WeakMap` and ignores the mutations it causes itself).
  - `boot.js`: sets `document.documentElement.dataset.script` from `initialScript(...)` before the app draws, so Cyrillic mode never flashes Latin.
  - `format.js`: `compact(n)` (`hilj.`, `mil.`, `mlrd`, `bil.`; decimal comma), `int(n)` (`1.234.567`), `eur(n)` (`compact` + `" €"`), `rsd(n)` (`int` + `" RSD"`), `pct(x, d)` (`12,3 %`), `yieldValue(y, v)` (`y.unit === "eur"` → `eur`), `popShort(n)` (`1,7 mil.`, `250 hilj.`), `esc` unchanged.
  - A toggle switch changes script by reloading, not by redrawing in place.
  - **Kosovo's towns on the map.** `web/js/ext/towns/index.js` exports `drawTowns(app, towns)`, which registers one static layer through `app.registerStaticLayer` (`id: "kim-towns"`, `z: 65`, `minRpx: 8`) drawing a small town marker with its name beside it (`script(name)`) at each town's `x, y` of `kim_towns.json` (`{"towns": [{"name", "x", "y", "cell"}]}`), hit-testable with the tooltip `Naselje bez statističkih podataka`. `main.js` calls `app.loadData("kim_towns")` after the first frame and, when the file exists, `drawTowns`. `initSearch` gets the towns as a third list: entries of `kind: "town"`, labelled `naselje`, and picking one frames the town's cell. Nothing happens when the file is missing.

**Loading and lens integration (coordinate with Task 7):** implement the versioned manifest and adapter specified in Task 7. First render needs only world, initial city markers and essential summaries; load lens manifest and municipal values on demand, and restore a shared city/lens URL only after its required data arrives. Cache promises; expose loading and retryable failure states. Remove US-only eager layers. Preserve search and Kosovo town availability. Test normal activation, direct-link reload, error/retry and script toggle.

**Engine constants.** Apply the constants below and make the loading/contract changes described above; avoid unrelated restructuring.

| File | Change |
|---|---|
| `web/js/camera.js` (line 20) | `this.maxScale = 6` → `30` |
| `web/js/main.js` (line 443) | `Math.max(cam.scale, 0.8)` → `Math.max(cam.scale, 4)` |
| `web/js/main.js` (line 490) | `Math.min(2.2, …)` → `Math.min(11, …)` |
| `web/js/main.js` (`stateFromHash`, ~597–607) | accept `RS\d{3}` case-insensitively; drop the `padStart`; a name still matches `states[i].name` |
| `web/js/main.js` (share file name, ~789) | `united-states-` → `srbija-` |
| `web/js/main.js`, `app/search.js` | the search key is `fold()` from `i18n/index.js`; `sub: "State"` → `"okrug"`; the placeholders are `"Pretraga"` and `"Pretraga gradova i okruga"` |
| `web/js/app/urlstate.js` | parse and format `script=cyr`; write it only when the script is Cyrillic |
| `web/js/render/art/terrain.js` (~375–382) | `ALBERS`: `p1 = 42.5 * RAD, p2 = 45.5 * RAD, p0 = 44.0 * RAD`, `lon0: 21`; delete `SHIPPED_PROJ` and its use: use `raw.projection` or `null` |
| `web/js/render/art/terrain.js` (`onPlateau`, `inGreatBasin`, `pivotCountry`) | each returns `false` |
| `web/js/render/art/terrain.js` (~437, 511, 514, 438) | `FIELD_T = 256` → `51`; the field-size constants multiplied by 0.2; the pattern cap `8` px/km → `40` |
| `web/js/render/art/terrain.js` (~678–679) | `snowy`: `desert` never applies; `elev > 1700 || emax > 2000`; `alpine`: `rel === 3 || (rel === 2 && emax > 1900)` |
| `web/js/render/art/terrain.js` (~774–779) | `low` is always `false`, so no dune and no cactus is ever drawn |
| `web/js/render/art/city.js` (~51–54, 95–98, 57) | `cityIsDot`: `2.5e5` → `6e4`, `1e5` → `3e4`; `CITY_CLASSES` minimums `1.5e5, 4e5, 1.5e6, 5e6` → `2e4, 8e4, 3e5, 1e6`; `SPILL_MIN_POP` → `1.2e6` |
| `web/js/render/banners.js` (`popFloor`, ~560) | replaced by a rank: the banner list is `cities` sorted by population, so a city's index is its rank; banners are drawn for index < `Rpx < 6 ? 25 : Rpx < 10 ? 40 : Rpx < 16 ? 60 : Rpx < 24 ? 90 : Infinity`; `showYields` stays `Rpx > 24` |
| `web/js/ui/yieldReport.js` (lines 11–12) | `METRO_MIN = 60000`, `BIG_METRO_MIN = 150000` |
| `web/js/ext/advisors/core/frame.js` (54), `core/data.js` (268), `views/commerce.js` (135), `energy.js` (210), `culture.js` (112), `military.js` (143) | each px-per-km zoom cap multiplied by 5 |
| `web/js/world.js` (label fit, ~297–308) | the `150` km cap → `30`; a label smaller than `3` is not drawn |
| `web/js/render/map.js`, `render/banners.js` | where a state name or a city name is put on the canvas, wrap it: `script(name)` |
| `web/js/ui/topbar.js` | `Turn <b>…</b> · …` → `Godina <b>…</b> · …`; append the script button (`id="btn-script"`) to `.tb-buttons` through `installScriptToggle` |
| `web/js/main.js` (strings at ~533, 536) | the words `state`/`states` → `okrug`/`okruzi`, in Serbian |

- [ ] **Step 1: Failing tests for the transliterator** — the same cases as `tests/test_srtext.py` (copy its `GLOSSARY` and `HARD_CASES` dictionaries), plus `PROTECTED` listing the twenty names.

```js
// web/js/i18n/transliterate.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { toCyrillic, toLatin, fold, PROTECTED } from "./transliterate.js";

test("Serbian Latin becomes Cyrillic, digraphs and all", () => {
  assert.equal(toCyrillic("Ljubljana"), "Љубљана");
  assert.equal(toCyrillic("injekcija"), "ињекција");
  assert.equal(toCyrillic("Njujork"), "Њујорк");
  assert.equal(toCyrillic("Đerdap"), "Ђердап");
  assert.equal(toCyrillic("LJUBAV"), "ЉУБАВ");
  assert.equal(toCyrillic("123 € (5 km)"), "123 € (5 км)");
});

test("protected names stay Latin and Serbian acronyms do not", () => {
  assert.equal(toCyrillic("Izvor: Eurostat, NACE i OpenStreetMap."), "Извор: Eurostat, NACE и OpenStreetMap.");
  assert.equal(toCyrillic("RZS i BDP"), "РЗС и БДП");
  assert.equal(toCyrillic("MESA"), "МЕСА");
  assert.equal(PROTECTED.length, 20);
});

test("Latin comes back exactly, including capital digraphs", () => {
  for (const latin of ["Ljubljana", "injekcija", "Njujork", "Đerdap", "LJUBAV", "Niš", "Kosovsko-mitrovačka"]) {
    assert.equal(toLatin(toCyrillic(latin)), latin);
  }
  assert.equal(toLatin("ЉУБАВ"), "LJUBAV");
});

test("both scripts fold to one search key", () => {
  assert.equal(fold("Niš"), "nis");
  assert.equal(fold("Ниш"), "nis");
  assert.equal(fold("Đerdap"), "djerdap");
  assert.equal(fold("Kosovsko-mitrovačka"), "kosovsko mitrovacka");
});
```

- [ ] **Step 2: Run** `node --test web/js/i18n/` → FAIL (module not found). **Step 3: write `transliterate.js`** → PASS, and `uv run python -m unittest tests.test_srtext` still passes (it compares the two protected lists).
- [ ] **Step 4: Failing tests for `initialScript`, `script`, `format.js`** (`compact(6549901) === "6,5 mil."`, `compact(250000) === "250 hilj."`, `int(1234567) === "1.234.567"`, `eur(8.2e10) === "82 mlrd €"`, `rsd(109462) === "109.462 RSD"`, `pct(0.123) === "12,3 %"`, `popShort(1700000) === "1,7 mil."`). **Step 5: implement** `index.js`, `boot.js`, `format.js` → PASS.
- [ ] **Step 6: Apply the engine constants** from the table, then the towns layer. After each file run `node --check <file>`. When all are done, serve the still-US data and look at it once: `uv run python -m pipeline serve --port 8765` in one terminal, then `NODE_PATH=$HOME/.nvm/versions/node/v22.23.2/lib/node_modules node scripts/look.mjs http://127.0.0.1:8765/ /tmp/look.png` — `scripts/look.mjs` is in the repo: it opens the page in a headless Chromium, waits for the map, saves a screenshot and prints the console errors as JSON. Assert the list is empty and the screenshot shows a map.
- [ ] **Step 7: Whole suite (Python and JS), self-review, commit** (`git commit -m "Engine constants for a 5 km Serbia; Serbian scripts and number formats"`).

---

### Task 9: Translation A — the core interface and the Almanac

**Files:**
- Modify: `web/index.html`, `web/js/ui/pedia.js`, `ui/lenses.js`, `ui/tooltip.js`, `ui/infoPanel.js`, `ui/statePanel.js`, `ui/cityPanel.js`, `ui/minimap.js`, `web/js/ui/yieldReport.js` (everything except lines 9–13), `web/js/app/help.js`, `web/js/app/share.js`
- Not yours: `web/js/ui/topbar.js`, `web/js/main.js`, `web/js/format.js`, `web/js/app/search.js`, `web/js/app/urlstate.js`, everything under `web/js/ext/` and `web/js/render/` (Tasks 8 and 10).

**Interfaces:**
- Consumes: `docs/GLOSSARY.md` (binding), the transliteration rules in `pipeline/core/srtext.py` (the website transliterates automatically, so you write Serbian Latin only).
- Produces: every user-visible string in the owned files in Serbian Latin; no English sentence left. In `web/index.html`, exactly one added line: `<script type="module" src="js/i18n/boot.js"></script>` right after the stylesheet link (Task 8 provides `boot.js`). Element ids, class names, `aria-controls` values and data keys stay as they are.

**What to change.**
- `web/index.html`: `<title>` (`serbiaciv — Srbija kao strateška igra`), the description and social-card texts, the brand (`SRBIJA`), the search placeholder and aria labels (`Pretraga gradova i okruga`), the buttons (`Podeli`, `Pomoć`, `Almanah` with `title="Šta svaki broj znači i odakle dolazi"`), the loading line (`Kartografisanje zemlje…`), the canvas `aria-label` (`Heksagonalna mapa Republike Srbije`).
- `ui/pedia.js` (the Almanac): rewrite the prose for Serbia. Sections: Kako čitati mapu (the five yields and what each really is; that Gold is an estimate for cities, marked ≈), Teritorija (okrug and opština as the office uses them; that Kosovo and Metohija is drawn as part of Serbia after the office's codes and that the office publishes no figures for it, in the office's own wording, and that some international publishers file the territory under a separate code), Izvori (built from `sources.json`, as upstream), Rečnik (the glossary's game words). No sentence about the USA, ACS, BEA or Canada may remain. Names of publishers that `PROTECTED` lists stay in Latin.
- `ui/tooltip.js` line 45 and `ui/cityPanel.js` line 35 are matched by regular expressions in `web/js/ext/cityView/index.js` (lines ~69 and ~291), which Task 10 owns. Keep those two strings' structure such that a regex looking for the same words still matches: change the wording, then tell Task 10's owner through your report file exactly what the new strings are (Task 10 reads the report). Prefer strings whose Serbian wording is unambiguous: `"Država"`-like labels become `"Okrug"`.
- `ui/yieldReport.js`: the report headings and sentences (`Najveći gradovi po…`), never lines 9–13.
- `app/share.js`: `SITE_URL = ""` until the site is hosted; the dialog texts; the file-name stem `srbija`.
- `app/help.js`: the rows (`Pomeranje`, `Istraživanje`, `Paneli`…) and the footer (`Svaki broj se može pratiti do javnog izvora: otvorite Almanah. Veza u adresnoj traci uvek ponovo otvara ovaj prikaz. Izvorni kod: <a href="serbiaciv-source.zip" download>serbiaciv-source.zip</a> (MIT; pokrenite ga sa uv, pogledajte README).`).

**How.** For each file: list its user-visible strings (template literals and strings that reach `innerHTML`, `textContent`, `title`, `aria-label`, `alt`, `placeholder`), translate each with the glossary, keep HTML structure and escaping (`esc()` calls stay around data), keep code identifiers. Where a Serbian sentence mentions a protected name (Eurostat, OpenStreetMap, …), wrap that name in `<span data-no-translit>…</span>` when the string is HTML. Run `node --check` on each file.

- [ ] **Step 1:** Translate `web/index.html` and `app/help.js`; run `node --check web/js/app/help.js`; serve the site (`uv run python -m pipeline serve --port 8765`) and look at it with `NODE_PATH=$HOME/.nvm/versions/node/v22.23.2/lib/node_modules node scripts/look.mjs http://127.0.0.1:8765/ /tmp/look.png`; confirm the top bar and help dialog read in Serbian.
- [ ] **Step 2:** Translate `ui/tooltip.js`, `ui/infoPanel.js`, `ui/statePanel.js`, `ui/cityPanel.js`, `ui/minimap.js`, `ui/lenses.js`; `node --check` each.
- [ ] **Step 3:** Translate `ui/yieldReport.js` (not lines 9–13) and `app/share.js`.
- [ ] **Step 4:** Rewrite `ui/pedia.js` for Serbia.
- [ ] **Step 5:** Grep your files for leftover English: `grep -nE "\b(the|and|of|to|in|is|are|by|for|with|from|this|that|city|state|county)\b" <your files>` and deal with every hit that is UI text (code identifiers and `data-no-translit` names are fine).
- [ ] **Step 6:** Whole suite, self-review, commit (`git commit -m "Core interface in Serbian Latin; the Almanac for Serbia"`). In your report file, write the section "Strings Task 10 must know about" with the new `tooltip.js:45` and `cityPanel.js:35` strings.

---

### Task 10: Translation B — extensions and site names

**Files:**
- Modify: `web/js/ext/index.js`, everything under `web/js/ext/cityView/`, `web/js/ext/advisors/` and `web/js/ext/layers/`, and the strings of `web/js/render/art/sites.js` (lines ~65–84)
- Not yours: `web/js/ext/advisors/core/frame.js`, `core/data.js` (lines 54 and 268 only are Task 8's: touch nothing else in those two files), `views/commerce.js` line 135, `energy.js` line 210, `culture.js` line 112, `military.js` line 143; the folder `web/js/ext/towns/` (Task 8's); everything outside `web/js/ext/` except `render/art/sites.js`.

**Interfaces:**
- Consumes: `docs/GLOSSARY.md`; the report file of Task 9 (`.superpowers/sdd/task-9-report.md`), which names the new strings that `ext/cityView/index.js` matches with regular expressions at lines ~69 and ~291. If that report is not there when you reach that step, use the word `Okrug` for a state-level label and say so in your own report.
- Produces: every user-visible string in the owned files in Serbian Latin. Strings a user can see in M1 without optional data files must be finished; the dashboard interiors of the advisors, which M3 rewrites for Serbian data, may keep English only where it is not reachable in M1 — list every such place in your report file under "Left English for M3".

**What a user sees in M1** (this is the bar): the advisors button and roster (Ekonomija, Stanovništvo, Prosperitet i stanovanje, Znanje, Zemljište, Vojni, Trgovina, Kultura, Istraživač), the notices shown when a data file is missing (`military.js` ~37–40, `commerce.js` ~19–22, `culture.js` ~208, `cityView/citizens.js` ~127, `cityView/districts.js` ~177, `views/people.js` ~64, `cityView/screen.js` ~154), the map-menu toggle labels in `ext/layers/index.js`, the layer tooltips in `ext/layers/tips.js`, the City View's frame (screen.js ~70, 140–229), the site name plates in `render/art/sites.js`.

- [ ] **Step 1:** `ext/index.js`, `ext/layers/` (all strings), `ext/advisors/index.js` roster and empty states.
- [ ] **Step 2:** `ext/advisors/views/*` — every label, heading, note and source sentence that is not behind missing data; the M3-deferred list goes in your report.
- [ ] **Step 3:** `ext/cityView/*` — frame, notices, panel headings; update the two regular expressions to Task 9's strings.
- [ ] **Step 4:** `render/art/sites.js` strings.
- [ ] **Step 5:** `node --check` on every changed file; the leftover-English grep from Task 9 Step 5 over your files.
- [ ] **Step 6:** Whole suite, self-review, commit (`git commit -m "Extensions in Serbian Latin: advisors roster, layers, City View"`).

---

### Task 11: Integration on real data

Runs after Tasks 1–10 are merged into `main`.

**Files:** integration changes as needed; create `scripts/report_data_size.py` and `docs/DATA_BASELINE.md` for repeatable measurements. Coordinate file ownership. No new product features.

- [ ] **Step 1:** `uv run python -m pipeline all` from a clean cache. Record every download's size. It must reach `check` without an exception.
- [ ] **Step 2:** `uv run python -m pipeline check` → no `FAIL`. Deal with every `WARN` (fix or write it into `docs/STATUS.md` as known).
- [ ] **Step 3:** The seams to test first, because they join two tasks: (a) `census` ids against `rzs_db` ids — every non-Kosovo 5-digit id has a census row or is listed as missing; (b) city positions — print each city's name and position source (match, override, none) and check the twenty-five largest on a map; (c) Belgrade's aggregate — its population is about 1.69 million in 2025, not a few hundred thousand; (d) `kim_towns` all land inside Serbia; (e) the checker's rules against the real files.
- [ ] **Step 4:** Serve and look: `uv run python -m pipeline serve` and the headless script. The home view shows all of Serbia with Kosovo and Metohija, thirty okrug names, twenty-five banners, the neighbours muted. Capture `docs/images/m1-home.png`.
- [ ] **Step 5:** The relief cut-offs. Render the elevation and relief lenses and compare with a physical map of Serbia: Vojvodina flat, Šumadija hilly, the main ranges mountains. If a cut-off is wrong, change it in `srb.py` only, rebuild, and note the change.
- [ ] **Step 6: Data and accuracy report.** Record download bytes per source, selected tiles and coverage, cache hits, interim disk use, raw and gzip bytes per published asset, first-frame and on-demand browser transfer, build time and peak memory. Compare representative flat, mountain, border and mixed-cover hexes with independently computed native-resolution reference statistics and categories; document tolerances, discrepancies and nodata. Check polygon area and density for small and border municipalities. Have the report emit deterministic raw/gzip sizes and source-cache totals; record browser measurements, conditions and reference device in `docs/DATA_BASELINE.md`. Establish budgets only from this real baseline, then add a CI regression check and an explicit review process for justified increases.
- [ ] **Step 7:** Commit (`git commit -m "Milestone 1 on real data"`) and push only when the user has authorized publication.

---

### Task 12: The trailer

**Files:**
- Modify: `web/dev/trailer/storyboard.js`, `web/dev/trailer/main.js`, `web/dev/trailer/stage.js`, `web/dev/trailer.html`
- Create: `scripts/render_trailer.mjs`, `web/dev/trailer/storyboard.test.js`
- Not yours: `score.js`, `mp4.js`, `overlays.js`.

- [ ] **Step 1:** Storyboard for Serbia: title `Srbija`, eight shots with upstream's shot ids in order — (1) the Pannonian plain from the north, caption with the country's area and population; (2) Belgrade at the confluence, its population and `prestonica`; (3) the `pop_change` lens sweeping over the map, caption with the national change; (4) Novi Sad, its share of students or its wage; (5) Kopaonik and the Iron Gates, the wonders of the relief lens; (6) Niš and the Morava corridor; (7) the fifteen lenses flashing by name; (8) the end card. Every caption is a function of `web/data/*.json` read by the stage; write no number by hand. Camera keys in Serbia's map km.
- [ ] **Step 2:** Captions' numbers are computed: `storyboard.test.js` loads the fixture data folder `web/data` of the real build (skip when absent) and asserts that each caption's number equals the value in the data.
- [ ] **Step 3:** Audio. `main.js` encodes AAC in the browser, which this machine's Chromium cannot. Change it so that the page offers exporting the rendered score as WAV (`scoreToWav()` returning a `Blob`), and write `scripts/render_trailer.mjs`: Playwright opens `/dev/trailer.html`, runs the render, saves the video track and the WAV, then calls `ffmpeg -y -i video.mp4 -i score.wav -c:v copy -c:a aac -b:a 192k -shortest out.mp4`. Also try the browser's own AAC first and fall back only when `AudioEncoder.isConfigSupported` says no.
- [ ] **Step 4:** Run it; `ffprobe` reports `h264` video and `aac` audio, 1920×1080, 30 fps, 30 s. Save as `docs/trailer.mp4` only if under 20 MB, else say so.
- [ ] **Step 5:** Commit (`git commit -m "Serbia trailer: storyboard, score export and ffmpeg mux"`).

---

### Task 13: Browser smoke test, docs, and the English guard

**Files:**
- Create: `tests/browser/smoke.mjs`, `tests/test_no_english_ui.py`, `web/js/i18n/allowlist.txt`, `docs/STATUS.md`
- Modify: `README.md` (rewrite for Serbia, keeping the credit to Karpathy and upstream's data terms), `docs/DATA_CONTRACTS.md` (rewrite for the Serbian files: every shape in this plan), `pyproject.toml` only if a script entry is needed.

- [ ] **Step 1:** `smoke.mjs` against `uv run python -m pipeline serve --port 8765`: loads `/`, waits for the loading overlay to hide, asserts no console errors, the canvas is not blank (the standard deviation of sampled pixels above a threshold), Beograd's banner is found by its name and clicking it opens `#city-panel` with `Beograd`, the lens `#lens-quick` buttons switch two lenses without errors, `#btn-script` exists, clicking it reloads with `script=cyr` in the hash and after the reload `document.documentElement.dataset.script === "cyr"` and the page text contains `Београд`, clicking it again returns to Latin and `Beograd`. Exit code 1 on any failure.
- [ ] **Step 2:** `tests/test_no_english_ui.py`: for every shipped `.js` under `web/js` and `.mjs`/`.html` (not `web/dev/`, not `*.test.js`), extract string literals and text nodes with two or more consecutive ASCII lower-case words from the list `the of and to in is are by for with from this that city state county`, and fail listing file and line — unless the line is in `web/js/i18n/allowlist.txt` (one exact line of text per entry, with a comment saying why). Lines inside `data-no-translit` markup and code identifiers are not sentences: the test must look at string literals only.
- [ ] **Step 3:** Docs: `README.md` (what it is, how to run `uv run python -m pipeline serve`, how to rebuild, the credits and licences including upstream's data terms), `docs/DATA_CONTRACTS.md`, `docs/STATUS.md` (done / left ledger, starting with M1's acceptance list).
- [ ] **Step 4:** Whole suite: Python, `node --test web/js/i18n/ web/dev/trailer/`, the browser smoke test. Commit (`git commit -m "Browser smoke test, English guard, docs for milestone 1"`).

---

## M1 acceptance (checked by the controller at the end of Task 13)

In addition: indexed lens values and missing values equal reference per-cell semantics; lazy deep links and failure/retry work; terrain reference and geometry checks pass; the real-data size report and baseline budgets are recorded.

From the spec, section 9: `uv run python -m pipeline all` builds everything and `check` reports no FAIL; the home view shows all of Serbia including Kosovo and Metohija, 30 labelled okruzi and 25 banners; Beograd is marked as capital; every lens states its source and caveat; `beograd`, `beograd` and `београд` find Beograd; toggling script changes map labels, panels, tooltips and search, and toggling back restores Latin exactly.
