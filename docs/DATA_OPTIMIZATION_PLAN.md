# Data volume and size: review and proposed plan

Snapshot: 2026-11-26. This is a proposal for implementation, not a description of a completed Serbia build. The existing `web/data` files are upstream US data; the separate `pages/` site is an outline preview. The updated design and M1 implementation plan are the product references. Preserve the 5 km hex grid, Kosovo and Metohija coverage, Serbian scripts, provenance, source vintages and explicit missing values.

## What is planned

- M1: 5 km hexes (about 1,360 land hexes; about 10,800 cells including margin), boundaries, terrain, roughly 90 cities, 15 lenses, search and panels. The data model targets 30 districts and 197 municipalities; counts need validation against real joins.
- M2: city details and optional resources, infrastructure, parks and earthquake layers. M3: Explorer and advisors. M4: trailer.
- Geography: the spec estimates 35 Copernicus GLO-30 tiles at 1.5 GB and nine WorldCover tiles at 477 MB, plus other sources. These are planning estimates, not measured downloads. The M1 plan separately estimates 2.5 GB for geography; reconcile both after a real run.
- The earlier M1 design proposed a 1,728 × 1,728, 10-arc-second intermediate raster lattice and per-cell expansion of municipality lenses. The updated M1 plan uses source-resolution aggregation and municipality-indexed lenses; it retains the planned 1991–2025 population series.

## Baseline measurements

| Item | Measured size | Interpretation |
|---|---:|---|
| Existing `web/data/*.json` | 5,896,113 bytes | 15 upstream US files; not a forecast of Serbia size |
| Same JSON, independently gzip-compressed locally | 1,224,507 bytes | Illustrative compression; actual transfer depends on server and headers |
| Existing first-frame JSON set | 2,857,077 bytes raw; 573,727 bytes gzip | Seven upstream files in `web/js/main.js`; not a measured browser transfer |
| Existing optional layers fetched after first frame | 570,756 bytes raw; 130,119 bytes gzip | Infrastructure, military, wonders, trade; some are outside Serbia's scope |
| Current `pages/` | approximately 76 KiB on disk | Separate geographic preview, not the eventual map |
| Existing `data/raw/` at review time | approximately 223 MiB | Local ignored cache, subject to change; not committed or served |

The lattice contains 2,985,984 cells: an `int16` DEM is about 5.70 MiB and a `uint8` cover array 2.85 MiB before metadata. Base64 expands these to about 7.59 MiB and 3.80 MiB respectively before JSON overhead; compression may reduce them. They are local interims, not browser payloads.

## Priority changes

### 1. Store municipality lenses once per municipality

The M1 plan duplicates each of 12 administrative indicators across the entire approximately 10,800-cell grid. The updated plan stores each lens as a 197-element municipality array, keyed by the same municipality order as the world map, and resolve a cell through its existing municipality index. This changes the conceptual count from about 129,600 per-cell slots to about 2,364 municipality slots for those 12 lenses, plus the already-required cell-to-municipality mapping. This is an illustrative slot count, not a promised byte or transfer reduction: JSON nulls, compression and metadata affect the actual result. Keep elevation, relief and land cover per hex, preferably referencing the world data already holding them.

This changes the planned `lenses.json` contract and its browser consumers; implement it with schema versioning, contract documentation and tests comparing every rendered value, missing value, legend and domain to the old representation. Keep `null` for unavailable values. If a municipality owns no hex, preserve its Explorer row and handle map selection separately.

### 2. Load layers when needed

Keep only the world, initial city markers, essential nation/state summary and minimal source metadata on the first-frame path. Load lens values when a lens opens, and city details, Explorer tables, resources and later layers when requested. Preserve map links that open directly into a lens or city by loading the necessary data during URL restoration; provide visible loading and error states. The inherited renderer already supports cached `loadData()`, but currently blocks the first frame on seven JSON files and eagerly loads four optional layers afterwards. Remove unused US-only layers from the Serbia build, not merely from the display.

First measure the actual Serbia build: splitting a small file can cost more requests than it saves. Compare cold and warm loads with real compression and a constrained mobile connection.

### 3. Reduce raster downloads carefully

Select tiles by intersection with the actual territory polygon plus an explicitly justified buffer, instead of blindly downloading the whole rectangular bounding box. Evaluate HTTP range reads from cloud-optimized GeoTIFFs using bounded windows, where the host and file layout support them; preserve reproducibility by recording object version or immutable URL, validator/checksum when available, windows and processing parameters. Benchmark real transferred bytes and request counts against complete tile downloads: many small reads can cost more or be less reliable. Keep cached, whole-tile and offline fallbacks, retries and provenance; do not assume a clipped response has the full source file's checksum.

Only retain the source fields and geographic area required by M1; fetch M2 sources when their features are built. The census task already excludes five tables that M1 does not need. Population history from 1991 is explicitly planned for city series, so retain it unless the product requirement changes; fetching only 2015, 2021 and latest is an optional scope change, not a free optimization.

### 4. Preserve terrain meaning during aggregation

The proposed DEM interim uses 10-arc-second averages. Taking a maximum or range of those averages does **not** recover the maximum or range of the original 30 m elevations, and will tend to smooth peaks and relief. Similarly, taking a mode at each lattice cell and counting those modes does not preserve original 10 m land-cover proportions. Before adopting the current scheme, compare its per-hex mean, maximum, range, cover shares and resulting classes with a full-resolution reference for a representative sample of flat, mountainous, border and mixed-cover hexes. Record tolerances and mismatches, including Kopaonik and Vojvodina.

Possible implementations include streaming source raster windows into per-hex aggregators or retaining suitable sufficient statistics (such as per-class counts and min/max as well as means). These are alternatives to benchmark, not proven equivalent until pixel weighting, nodata and boundary rules are specified and tested. Avoid changing source resolution or simplifying geometries solely to hit a size target.

### 5. Keep geometry fit for purpose

Use source polygons for accurate joins, area and boundary checks, then simplify only display geometry in projected units with a measured visual error at the maximum zoom. Preserve shared edges and test for gaps, overlaps, enclaves and Kosovo coverage. Compare computed municipality area against authoritative polygon area: the planned cell-count × 64.95 km² approximation can distort density, especially for small municipalities and borders. Store authoritative area when available and label its source; do not trade accuracy for smaller files.

### 6. Measure and enforce budgets

Add a repeatable report for each build: raw download bytes by source, cache hit rate, interim disk size, each output's raw and gzip bytes, and first-frame vs on-demand assets. Record build time, browser transfer, parse time and peak memory on a repeatable reference device. Keep attribution, checksums and vintages in the report. Set budgets from the first valid Serbia build and enforce regression thresholds in CI, with a documented way to accept a justified increase. Do not put raw/interim files or generated source rasters into Git history.

## Plan inconsistencies to resolve before implementation

- The spec says nine WorldCover tiles; Task 4 lists `N39/N42/N45 × E018/E021`, which is six, while its test says nine. Derive expected tiles from the actual bounds and verify coverage; do not hard-code either count.
- The Task 4 reference calls coordinates `20.4606, 44.8125` Novi Sad; those are near Belgrade. Correct the fixture and verify the expected elevation against the same aggregation method.
- The lattice docstring's approximate east–west and north–south lengths are reversed for Serbia's latitude; 10 arc-seconds is roughly 220–230 m east–west and 309 m north–south.
- The README/spec contain historical deployment statements that predate the separate GitHub Pages preview. Update them when the product documentation is reconciled.

## Suggested order

1. Fix the inconsistencies and write accuracy and payload benchmarks using small, representative fixtures.
2. Build boundaries and a first real Serbia world; record baseline coverage and sizes.
3. Implement municipality-indexed lenses and on-demand loading with equivalence and deep-link tests.
4. Benchmark selective raster reads and accurate per-hex aggregation against full-tile reference results; choose based on actual size, speed and error.
5. Add budgets to CI and repeat measurements as M2/M3 data is added.
