# serbiaciv: Serbia as a strategy game, built from real data

**Status:** approved on 2026-11-26. The atlas built from this design is published at <https://acailic.github.io/serbiaciv/>. Historical planning notes are in [`docs/archive/`](archive/).
**Base:** fork of [usaciv](https://karpathy.ai/usaciv) by Andrej Karpathy (MIT), imported as commit `1fdbdf3`.

## 1. Purpose

The same experience as usaciv, for the Republic of Serbia: the real country drawn like a 4X strategy map, with hex terrain, city banners with yields, lenses, a City View and an Almanac that traces every number to a public source. It stays a visualizer, not a game.

The repo exists so that this can be browsed, shared and later grown. A 30-second trailer is part of the first delivery.

## 2. Binding decisions

| # | Decision | Made by | Date |
|---|---|---|---|
| D1 | Kosovo and Metohija is **inside** the frame, as part of Serbia. | User ("HAVE KOSOVO INSIDE") | 2026-11-26 |
| D2 | The UI is in **Serbian, Latin and Cyrillic script**. There is no English UI. | User ("DO SERB LAT AND CYR") | 2026-11-26 |
| D3 | Approach: fork the engine, replace the pipeline, patch about seven renderer constants. All four milestones. Repo `~/Documents/github/serbiaciv`. | Presented as default; user raised no objection | 2026-11-26 |
| D4 | The repository is **public** on GitHub (`acailic/serbiaciv`). This overrides the "private until asked" default for this repo only. | User ("make public repo") | 2026-11-26 |

Everything below follows from these. Section 14 lists choices that were left open on purpose.

## 3. Architecture

Upstream's flow is kept: **source → interim → builder → web/data**.

```
pipeline/
  core/      fetch.py  cached downloads with a provenance manifest (url, sha256, bytes, date)
             source.py  Source base class
             geo.py     Albers projection (new constants), hexgrid.py, store.py
             rzs.py     client for the RZS dissemination database
  sources/   one module per Serbian data source; fetch() then process() → data/interim/<id>.json
  build/     builders that put interim data on the hex grid → web/data/*.json
  check.py   validates web/data against docs/DATA_CONTRACTS.md; exit 1 on FAIL
web/         upstream engine (ES modules + Canvas 2D, no framework, no build step) + patches + i18n
tests/       unittest suite
```

**Kept from upstream unchanged:** the renderer, the terrain and city art, the camera, the lens dock, the City View framework, the extension API, the URL state, sharing, the minimap, the trailer maker.

**Replaced:** every `pipeline/sources/*.py` and `pipeline/build/*.py` that reads a US publisher; the US-specific copy in the web app.

**New modules:**

| Module | What it does | Depends on |
|---|---|---|
| `pipeline/core/rzs.py` | Queries `data.stat.gov.rs` and returns flat records with `None` for unavailable values. | network |
| `pipeline/sources/census.py` | Popis 2022 Excel files: hierarchy by cell indent, three rows per area (с/м/ж). | `openpyxl` |
| `pipeline/sources/rzs_db.py` | Population estimates, births and deaths, migration, wages, employment by NACE, life expectancy, land use. | `core/rzs.py` |
| `pipeline/sources/boundaries.py` | Eurostat GISCO NUTS (districts, regions) and LAU (municipalities); Natural Earth countries. | `shapely` |
| `pipeline/sources/kim.py` | Kosovo and Metohija stitch (section 5). | `boundaries`, lookup table |
| `pipeline/sources/copernicus_dem.py`, `worldcover.py` | Elevation and land cover per hex. | `rasterio` |
| `pipeline/sources/osm_poi.py` | Power plants, mines, ports, lakes, rivers, place nodes. | Overpass API |
| `pipeline/sources/wikidata.py` | UNESCO sites, national parks, universities, river lengths. | Wikidata SPARQL |
| `web/js/i18n/` | Script state, transliteration, number formatting, search folding. | none |

**Dependencies and storage.** The implementation uses `rasterio`, `numpy`, `pyshp` and `openpyxl`; add other libraries only when needed and record them in `pyproject.toml`. The expected raw download is roughly 2–2.5 GB but is unverified for the final selection. Downloads and interims stay out of git. Measure the actual amounts and use only M1 inputs; retain required population history and source provenance.

## 4. The map

- **Grid:** pointy-top hexes, 5 km from centre to vertex (flat-to-flat 8.66 km, area 64.95 km²). About 1,360 land tiles, against about 4,900 for the USA. The total grid (90 × 120 = 10,800 cells with a 200 km margin) is the same size as upstream's 10,530, so every cache and zoom assumption in the engine holds.
- **Projection:** Albers equal-area, standard parallels 42.5° and 45.5°, central meridian 21.0°, latitude of origin 44.0°.
- **Elevation:** Copernicus GLO-10. (Status 2026-11-27: the plan named GLO-30, but the tiles the pipeline downloads are the 1-arc-second `Copernicus_DSM_COG_10` COGs, 3600 × 3600 pixels a degree, so every label now says GLO-10, 10 m, as the data is.) Each hex stores mean, maximum and range in metres, derived using a documented pixel-inclusion and nodata rule and checked against source-resolution samples. Do not infer source-pixel extrema from averages of coarser cells.
- **Relief classes** use the elevation range inside the hex (maximum minus minimum), because upstream's standard-deviation rule was calibrated on 25 km hexes and on a 9 km elevation grid: flat under 60 m, hills 60–300 m, mountains over 300 m, and "peaks" when the mean is at least 1,300 m. The four numbers live in one constants block and the rule text is written into `world.json`. The range itself is stored per hex as a new field, `elev_range`, and `DATA_CONTRACTS.md` gains it.
- **Land cover:** ESA WorldCover 2021. Tree cover → forest, shrubland → shrub, grassland → pasture ("livade i pašnjaci"), cropland → crop, built-up → developed, wetland → wetland.
- **Water:** a hex is a lake tile when its centre lies inside a lake or reservoir polygon of at least 40 km². In practice only the Iron Gates reservoir qualifies at this hex size. Smaller lakes and narrow reservoirs stay land with their river drawn through, which is how upstream already treats narrow reservoirs; it has no art for a lake on a land tile. Serbia is landlocked, so there is no ocean and no bathymetry.
- **Rivers:** OpenStreetMap river relations linked to Wikidata, with a Wikidata length of at least 50 km, ranked by length.

**Renderer patches.** Each is a constant or a rule in one file; none changes behaviour for data that upstream handles.

| File | Change |
|---|---|
| `web/js/camera.js` | `maxScale` 6 → 30 px/km, so max zoom reaches 150 px hexes as upstream does. |
| `web/js/main.js` | Absolute px/km caps scaled ×5; `#state=` accepts a NUTS-3 code. |
| `web/js/ext/advisors/core/frame.js` and advisor views | Per-view zoom caps scaled ×5. |
| `web/js/render/art/terrain.js` | New projection constants; US-only art rules removed (pivot circles, mesas, dunes, cacti); field size and pattern cap scaled; summit art re-scaled to Serbia's 28–2,169 m. |
| `web/js/world.js` | Hillshade gain and label sizes in km. |
| `web/js/render/banners.js`, `render/art/city.js`, `ui/yieldReport.js` | Population cut-offs replaced by rank-based ones (section 8). |
| `web/js/app/search.js`, `main.js` | Search folding keeps diacritics and Cyrillic (section 6). |
| `web/js/format.js` | Serbian number and currency formats. |
| `web/index.html`, `ui/*`, `app/*`, `ext/*` | All user-visible text in Serbian Latin. |

**Industry taxonomy.** Upstream's 20 NAICS-derived keys are replaced by 19 NACE section keys, because NACE sections are what Serbia publishes: `agriculture` (A), `mining` (B), `manufacturing` (C), `energy` (D), `water_waste` (E), `construction` (F), `trade` (G), `transport` (H), `accommodation` (I), `information` (J), `finance` (K), `real_estate` (L), `professional` (M), `admin` (N), `public_admin` (O), `education` (P), `health` (Q), `arts` (R), `other` (S). The icon tables in `ext/cityView/model.js` and `ui/infoPanel.js` are updated to match.

## 5. Kosovo and Metohija

**What is shown.** The territory is drawn inside Serbia, owned by its five districts, exactly as the Statistical Office of the Republic of Serbia (RZS) codes it: region RS23, oblasts RS231–RS235, and 29 municipalities with codes 90018–90352. Natural Earth's "Kosovo" country polygon is not drawn as a neighbour.

**Physical data is real; statistical data is absent.** Terrain, rivers, lakes, roads, railways, airports, power plants, mines, national parks and UNESCO sites appear there like anywhere else, because those come from physical and infrastructure sources. Population, GDP, jobs, wages and administrative statistical lenses are `null` there; physical lenses remain available, because RZS publishes no figures for the territory and this site takes its figures from RZS. The Almanac states this in RZS's own wording ("od 1999. godine bez podataka za AP Kosovo i Metohiju") and also says that some international publishers file the territory under a separate code.

**Towns.** Upstream's gate rejects a city without population, so Kosovo's towns (Priština, Prizren, Peć, Kosovska Mitrovica, Gnjilane, Uroševac, Đakovica, Podujevo and the rest) are a separate small file, `kim_towns.json`, drawn by a static layer as named town markers without banners. They are searchable. Names come from OpenStreetMap `name:sr-Latn` tags.

**Geometry, and why it is stitched.** RZS publishes codes and names for these units but no geometry, and no open publisher draws Serbia's five districts. They are built from the 38 Kosovo municipal polygons in geoBoundaries `XKX ADM2` (OpenStreetMap, ODbL, total 10,888 km²):

1. Each of the 38 polygons is assigned to one of RZS's 29 municipalities in a reviewed table, `pipeline/data/kim_stitch.csv`: polygon name → RZS code → basis ("same name" or "split from", with the year).
2. Municipalities are grouped into the five oblasts by RZS codes RS231–RS235.
3. A check asserts the grouped polygons cover the outer ring with no gap and no overlap, within 1% of area.

Known approximations, each recorded as a row in the table with its basis:

- About nine of the 38 polygons have no RZS counterpart because the municipality was created later (North Mitrovica and the likes of Mamuša, Junik and Gračanica). Each is attached to the unit it was split from. The exact list is taken from the 38 names in the file, not from memory.
- North Mitrovica and South Mitrovica are two polygons for the one RZS unit, Kosovska Mitrovica.
- Dragaš covers Gora plus part of Orahovac, and no source draws the line between them. It is attached whole to Gora.

Because of these, opština borders inside Kosovo and Metohija can differ from Serbia's statutory ones by a few tiles. Okrug borders are not affected.

## 6. Language and scripts

**Serbian Latin is the authoring base.** Every user-visible string in code and every text field in `web/data/*.json` is written in Serbian Latin. There is no English fallback.

**Cyrillic is a presentation layer.** Serbian is bi-scriptual with a deterministic letter mapping, so nothing is translated twice. A `web/js/i18n/` module converts at display time:

- **DOM:** the app writes Latin. One pass converts text nodes and the `title`, `aria-label`, `alt` and `placeholder` attributes to Cyrillic. A `MutationObserver` applies the same pass to anything inserted later. The original Latin text is kept per text node, so switching back restores it rather than reverse-transliterating.
- **Canvas:** map labels, banners and plaques call `script(text)` where they draw. Switching script reloads the page: the URL hash carries both the view and the script, so the same map comes back in the other script.
- **Search:** both sides are folded to one key (Cyrillic to Latin, then diacritics stripped), so `beograd`, `beograd` and `београд` all find Beograd.
- **Numbers:** `Intl.NumberFormat("sr-Latn-RS")`: decimal comma, dot thousands separator, `hilj.` / `mil.` / `mlrd` / `bil.` for compact values. GDP in € ("82 mlrd €"), wages in RSD.

**Exceptions stay Latin in both scripts:** names of foreign publishers and products (Eurostat, Copernicus, ESA WorldCover, OpenStreetMap, Natural Earth, USGS, Wikidata, UNESCO, NACE, GitHub) are marked `data-no-translit` and skipped. Acronyms of Serbian names follow the script (RZS → РЗС, BDP → БДП).

**Toggle.** A `Ћир / Lat` switch in the top bar. The choice is stored in `localStorage` and in the URL hash (`script=cyr`), so a shared link carries it. A first visit starts in Cyrillic when the browser language is `sr` and not `sr-Latn`; every other first visit starts in Latin.

**Fonts.** Upstream's stacks (`Palatino Linotype, Palatino, Book Antiqua, Georgia, serif` and the system sans stack) fall back to system fonts that cover Cyrillic on Windows, macOS and Linux. No font is bundled.

**Vocabulary.** This glossary is binding for consistency; wording can be changed on review.

| Concept | Serbian Latin | Serbian Cyrillic | Note |
|---|---|---|---|
| yield | prinos | принос | |
| Food / Production / Gold / Science / Culture | Hrana / Proizvodnja / Zlato / Nauka / Kultura | Храна / Производња / Злато / Наука / Култура | |
| lens | sočivo | сочиво | |
| tile | heks | хекс | |
| city, capital | grad, prestonica | град, престоница | |
| citizens | građani | грађани | |
| district of a city | kvart | кварт | deliberately not "okrug" |
| wonder | čudo | чудо | |
| advisor | savetnik | саветник | |
| Almanac | Almanah | Алманах | |
| resource, improvement | resurs, poboljšanje | ресурс, побољшање | |
| state-level unit | okrug | округ | RZS and Eurostat call the same 25 areas "oblast"; the Almanac says so |
| county-level unit | opština | општина | a "grad" unit is shown as "grad" |
| settlement | naselje | насеље | |
| region | region | регион | |
| no data | nema podataka | нема података | |
| source | izvor | извор | |

**Translation procedure.** Upstream's roughly 1,000 user-visible strings are rewritten in place, file by file, by parallel workers that each get this glossary. A test scans the shipped JavaScript and HTML for leftover English UI sentences against an allowlist of code words, and fails if it finds one.

## 7. Data sources

All were reached without a key or account on 2026-11-26. "Verified" means a file or response was fetched and parsed.

| Source | Publisher · licence | What it gives | Level | Status |
|---|---|---|---|---|
| Popis 2022 Excel index, `popis2022.stat.gov.rs/sr-Latn/rezultati/excel/` | RZS · reuse with attribution | Population, age and sex, education, ethnicity, religion, economic activity, industry, occupation, commute, migration, households, dwellings | settlement, municipality | Verified, 65 of 66 files |
| RZS database JSON export, `data.stat.gov.rs` | RZS · reuse with attribution | Population estimates 1991–2025, births and deaths, migration, wages, employment by municipality × NACE, life expectancy, land use | municipality | Verified |
| `nama_10r_3gdp`, `nama_10r_2gdp` | Eurostat · CC BY 4.0 | GDP by district (2022 final, 2023 provisional) and by region | NUTS-3, NUTS-2 | Verified |
| GISCO NUTS 2024 `NUTS_RG_20M_2024_4326_LEVL_3` / `LEVL_2` | Eurostat · CC BY 4.0 | 25 districts and 4 regions, names in Serbian Cyrillic | district, region | Verified |
| GISCO LAU 2024 `ref-lau-2024-01m.shp.zip` | Eurostat · CC BY 4.0 | 168 municipal polygons carrying RZS 5-digit codes, 77,481 km² | municipality | Verified |
| geoBoundaries `XKX ADM2` | geoBoundaries · ODbL | Kosovo's 38 municipal polygons | municipality | Verified |
| Natural Earth 10m | Public domain | Neighbouring countries, roads, railroads | — | Verified |
| Copernicus GLO-10, AWS Open Data | Copernicus · free with attribution | Elevation, 24 tiles, 1.0 GB (measured) | 10 m | Verified |
| ESA WorldCover 2021, AWS Open Data | ESA · CC BY 4.0 | Land cover; tile count and download size must be measured for the selected territory | 10 m | Source verified; coverage and transfer pending |
| OpenStreetMap via Overpass | OSM · ODbL | Power plants (358 with capacity in the region), mines, ports, lakes, rivers, place nodes | site | Verified |
| WRI Global Power Plant Database | WRI · CC BY 4.0 | Cross-check for plants over 100 MW | plant | Verified, 12 Serbia rows |
| OurAirports | Public domain | Airports and runways | airport | Verified |
| Wikidata SPARQL | CC0 | UNESCO sites, national parks, universities, river lengths | site | Verified |
| USGS earthquake catalog | Public domain | 994 events M ≥ 3.5 since 1970 in the region | event | Verified |

**Data size and accuracy.** Select only required inputs and territory coverage, cache with provenance, and measure raw download, interim, output and browser-transfer sizes. Municipality statistics are stored once per municipality, not repeated for every hex; cell values are resolved via the municipality index. Physical lenses reuse per-hex world fields. Load optional data on demand, including when restoring deep links, with visible loading and failure states. Record a real Serbia baseline before setting budgets; do not weaken geography, missing-value semantics or provenance merely to meet a size target. See [`archive/DATA_OPTIMIZATION_PLAN.md`](archive/DATA_OPTIMIZATION_PLAN.md) and the [M1 plan](archive/2026-11-26-serbiaciv-m1-plan.md).

**Fetch rule.** RZS's servers return `403` to curl's default user agent and `200` to a descriptive one. The fetcher always sends `serbiaciv/<version> (…)` and makes at most one request per second to RZS.

**Gaps, and the substitute used:** no income, rent or home value below region level (wages and census housing stand in); no GDP below district level (a city's Gold is its district's GDP scaled by its share of jobs, marked ≈ with the rule printed); no registered-unemployed count by municipality (census 2022 unemployed); no inter-city trade flows (the trade layer is not shipped); no visitor numbers for parks (ranked by area); no open military statistics (no military advisor).

## 8. Data model

| Upstream concept | Serbia | Count |
|---|---|---|
| nation | Republika Srbija; totals are over the territory RZS publishes for | 1 |
| states | okruzi, identified by NUTS-3 code (`RS110` … `RS235`), no abbreviations | 30 (25 with data, 5 without) |
| counties | opštine, identified by RZS 5-digit code | 168 with geometry from LAU, plus 29 in Kosovo and Metohija |
| cities | a municipality that contains an urban settlement of 10,000 or more, with 2025 population of at least 25,000 | about 90 |
| regions | NUTS-2, used as a grouping column in the Explorer | 5 |

- **Cities are municipality-based**, as upstream's metros are, because jobs, wages and yearly estimates exist per municipality and not per settlement. The marker sits on the urban settlement; the panel shows both the urban settlement (Popis 2022) and the territory (2025 estimate). Belgrade is the sum of its 17 city municipalities, because RZS publishes no aggregate code for it.
- **Banners are rank-based**, so they cannot go stale: at the home view the 25 most populous cities carry a banner; more appear as the view zooms, through upstream's existing tiers re-based on rank.
- **Yields:** Gold is GDP. Food is NACE A, Production is B + C + F, Science is J + M, Culture is R, all from Popis 2022 residents' employment. Districts and city-type badges use 2025 registered employment by workplace, which is what upstream's QCEW-based logic expects.
- **Municipal area:** compute population density with documented source-polygon area (in an equal-area projection), not a count of whole 5 km hexes; keep zero-hex municipalities in the Explorer.
- **JSON key names stay as upstream** (`fips` holds the NUTS-3 code, `geoid` the RZS code). Renaming them would touch the whole engine for no visible gain; `DATA_CONTRACTS.md` documents what they hold.

## 9. Features by milestone

This spec is the umbrella. The implementation plan is written one milestone at a time, M1 first, and each milestone is accepted on its own before the next is planned.

**M1: the map.** Terrain, rivers, lakes, districts and municipalities, about 90 cities with yields, the okrug panel, the city panel, the Almanac, search, share links, the minimap, the script toggle, and these lenses:

| Lens | Serbian | Source |
|---|---|---|
| Population density | Gustina naseljenosti | RZS 2025 estimate |
| Population change | Promena broja stanovnika | RZS estimates; census 2011→2022 if the estimate series is not on current boundaries |
| Natural increase | Prirodni priraštaj | RZS 2025 |
| Share aged 65+ | Udeo starijih od 65 godina | RZS 2025 |
| Higher education | Visoko obrazovanje | Popis 2022 |
| Average net wage | Prosečna neto zarada | RZS 2025 |
| Unemployment | Stopa nezaposlenosti | Popis 2022 |
| Orthodox share | Pravoslavni | Popis 2022 |
| Serb share | Srbi | Popis 2022 |
| Manufacturing share | Prerađivačka industrija | Popis 2022 |
| Commuting | Rad u drugoj opštini | Popis 2022 |
| Life expectancy | Očekivano trajanje života | RZS 2024 |
| Elevation, relief, land cover | Nadmorska visina, reljef, zemljišni pokrivač | per hex |

A five-second draft trailer render proves the video path.

*Acceptance:* `uv run python -m pipeline all` builds everything and `check` reports no FAIL. The home view shows all of Serbia including Kosovo and Metohija, 30 labelled okruzi and 25 banners. Beograd is marked as capital. Every lens states its source and caveat. Typing `beograd`, `beograd` or `београд` finds Beograd. Toggling script changes map labels, panels, tooltips and search; toggling back restores Latin exactly.

**M2: what the cities do.** City View with citizens (age and sex figures, education, activity, commute, origin), city districts and type badges, power plants and mines as resources, roads, railways, airports and river ports, wonders (UNESCO sites, national parks by area, universities), the earthquake layer.

*Acceptance:* Bor, Kragujevac, Novi Sad and Obrenovac each get a badge that their employment data supports; every wonder names the rule that selected it; the Iron Gates, Kopaonik, Tara and Fruška Gora appear as parks, and so does Šar-planina inside Kosovo and Metohija (its boundary comes from OpenStreetMap's protected-area polygon, because Wikidata lacks it).

**M3: slicing the data.** The Explorer over opštine, okruzi and gradovi, plus four advisors: Economy, People, Energy & Resources, Culture.

*Acceptance:* every column the Explorer lists is defined in the Almanac; selecting rows highlights the map both ways.

**M4: the trailer** (section 10).

*Acceptance:* see section 10.

**Out of scope, deliberately:**

- Playing: turns, AI opponents, combat, saving. This is a visualizer.
- Military advisor, troop and defence-spending panels. No open statistics exist; installations are not drawn either.
- Trade flows between cities. Nothing is published.
- Income, rent and home-value lenses, and poverty, broadband and veterans lenses. Not published below region level.
- An English UI.
- Treating the existing GitHub Pages outline preview as the completed M1 map. Replace it only when M1 is ready and verified.

## 10. Trailer

Upstream's trailer maker is reused with a Serbian storyboard: the Pannonian plain, Belgrade at the confluence, the depopulation lens, Novi Sad, Kopaonik and the Iron Gates, the end card.

- **Captions are computed, never typed.** Each caption is a function of the built data files, so a number on screen cannot go stale.
- **Video** is encoded in the browser with WebCodecs H.264, served over HTTP by `pipeline serve`.
- **Audio** is muxed with the system `ffmpeg`. This machine's Chromium encodes H.264 but has no AAC encoder. The user's installed browsers (snap Chromium and Firefox) are open-source builds and probably behave the same, but that is untested. The page exports the synthesized score as WAV; `ffmpeg` writes the final MP4.
- **Score:** upstream's code-synthesized score engine is kept as it is.

*Acceptance:* `ffprobe` reports H.264 video and AAC audio, 1920×1080, 30 fps, 30 seconds; every caption's numbers match `web/data`.

## 11. Error handling

- **Downloads** are cached with a provenance record. A failed fetch is retried three times with backoff, then the build stops with the source id and URL in the message. `--offline` never touches the network.
- **Missing data stays missing.** RZS status codes `M` and `O` and the symbols `…` and `-` all become `null`. Nothing is ever filled with zero. Lens legends carry a "nema podataka" swatch.
- **Territory changes.** A municipality code present in a table but absent from the boundary file, or the reverse, is a `WARN` naming the code; the build continues, because new city municipalities keep being created.
- **The stitch table.** If a Kosovo polygon has no row, or the area check in section 5 fails, the build stops with the offending names.
- **Vintages are mixed by design.** A city shows a 2025 population, 2022 jobs and a 2023 district GDP. So every file records the vintage of each field group, the Almanac prints it next to the figure, and `check` fails if a vintage string is missing or empty.
- **Old browser.** No WebCodecs means the trailer page explains that in Serbian and stops; the map itself needs nothing newer than upstream did.

## 12. Testing

In addition to functional tests, compare indexed and expanded lens values for every fixture cell (including missing, water and foreign cells); test lazy loading and deep-link restoration. Compare per-hex terrain statistics and classes against source-resolution reference samples in flat, mountain, border and mixed-cover areas. Record tolerances, nodata handling and results. Record compressed and uncompressed asset sizes and real browser transfer for a reproducible Serbia build; set regression budgets only after that baseline exists.

- **Kept:** upstream's about 70 country-neutral tests (fetch, store, hexgrid, builder plumbing).
- **Unit:** one test file per source module, on small slices of the real files; one per builder. The RZS client is tested against recorded responses so tests never hit the network.
- **i18n:** Latin → Cyrillic → Latin round-trips on a corpus that includes every glossary term, the protected names, and the known hard cases (Ljubljana, injekcija, Njujork, gde).
- **Gate:** `pipeline check` validates every file against `DATA_CONTRACTS.md` and prints a data-quality report; any FAIL exits 1.
- **Browser:** a headless Chromium test loads the site, asserts the canvas is not blank, opens Beograd's panel, switches two lenses, toggles script and compares a label before and after.
- **Trailer:** a five-second render is checked with `ffprobe` in M1 and again in M4.
- **Terrain look:** M1 is not accepted until a side-by-side with a physical reference map reads correctly to a human reviewer: Vojvodina flat, Šumadija hilly, the main ranges mountainous.

## 13. Repository and licence

- `~/Documents/github/serbiaciv`, published as the public repository `acailic/serbiaciv` (decision D4). Raw downloads, caches, worktrees and agent scratch files stay out of git.
- Commit history starts from the pristine upstream import, so every change is a clean diff against Karpathy's code.
- Upstream's `LICENSE` (MIT, Andrej Karpathy) stays; this project's additions are MIT too. The README credits usaciv and says it is a fork.
- Code is MIT. Data keeps each publisher's licence, listed in the Almanac. OpenStreetMap-derived tables (geoBoundaries, Overpass results) are offered under ODbL.

## 14. Open choices

These do not block the plan. Each is one isolated module either way.

| Choice | Current default | Alternative |
|---|---|---|
| Figures inside Kosovo and Metohija | None, as RZS publishes | Fill from the Kosovo Agency of Statistics census 2024, labelled with its publisher. That source sits behind a web form and its licence is unstated. |
| Trailer music | Upstream's score | A Serbian-flavoured motif written for the same synth engine. |
| Site name | `serbiaciv`, in line with chinaciv and argenciv | `srbijaciv` |

## 15. Not yet verified, and how M1 settles it

| Question | Check in M1 |
|---|---|
| Do settlement coordinates join cleanly to the census? | Join Popis names to OpenStreetMap place nodes inside the matching LAU polygon; review every city by hand; fall back to a reviewed CSV for failures. |
| Is the RZS estimate series on current municipal boundaries back to 2011? | Compare 2022 estimates with Popis 2022 per municipality; if they disagree by more than 1%, use census 2011→2022. |
| Which municipalities belong to which of the five Kosovo districts? | RZS tree where published, otherwise the Serbian regulation on administrative districts, cited in the stitch table. |
| Which of the 38 Kosovo polygons map to which RZS unit? | Read the 38 names from the file and fill `kim_stitch.csv` from them; the area check then proves nothing is left out. |
| Serbian names for Kosovo's towns | OpenStreetMap `name:sr-Latn`; if a town lacks it, transliterate `name:sr`; if both are missing, a reviewed CSV. |
| Does Cyrillic render correctly in the canvas labels, banners and plaques, not just in the DOM? | A probe page that draws every map label in both scripts and compares against Latin, run on the first M1 build. |
| Do upstream's exact relief cut-offs look right? | The side-by-side review in section 12; the numbers are then fixed. |
| Belgrade airport's official passenger count | Airport's activity report; if unreachable, the figure is omitted rather than approximated. |
| A university enrolment source | RZS database; otherwise universities are ranked by founding year and the rule says so. |
| Flood hazard licence (JRC) | Read the licence; include the layer only if reuse is permitted. |
