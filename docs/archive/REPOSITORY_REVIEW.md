# Repository review and next steps

Snapshot: 2026-11-26. SerbiaCiv is a foundation for a Serbia port of usaciv, not yet a complete data-driven map. The upstream renderer and US JSON remain under `web/`; the public `pages/` atlas is a separate geographic preview. Its hex pattern is decorative, its city list is illustrative, and it contains no terrain or statistical data. The outline uses the Natural Earth 1:10m Admin 0 Countries dataset (version 5.1.1, public domain); Serbia and Kosovo geometries are rendered together without an internal border. It is a small-scale overview, not an authoritative boundary dataset.

## Findings

- `pipeline/sources/` and `pipeline/build/` have registries but no source or builder implementations. The checked-in `web/data/` still describes the United States. Shipping it as Serbia would be misleading.
- `python -m pipeline check` raises an import error because `pipeline/check.py` does not exist; the inherited quick-start and pipeline documentation therefore describe capabilities that are not currently present.
- The Python suite passes (96 tests, one skipped), providing useful coverage of the foundations, but there is no Serbia end-to-end data or browser test yet.
- The existing design and M1 implementation plan are ambitious and valuable; some README material still describes upstream behaviour and should be revisited as work lands.

## Recommended sequence

1. **Make the data path honest and reproducible.** Implement boundary source and validation with licensing and provenance, a stable Kosovo stitch, and fixture-based tests. Establish an offline small-data build and make `pipeline check` report actionable failures.
2. **Build a thin vertical slice.** Generate Serbia's 5 km grid and a minimal `world.json`, adapt projection and camera, and render a navigable Serbia map. Validate coverage, inspect the terrain against a physical reference, and add a browser smoke test. Replace the preview only when this slice is ready.
3. **Add real terrain and cities.** Ingest documented elevation, land cover and census/place data; preserve missing values and record vintages. Test source-to-tile joins and attribution. Add Serbian Latin/Cyrillic rendering and search before enabling panels.
4. **Add statistics in small, verifiable layers.** Start with one well-documented indicator, provenance and missing-data treatment; then add lenses, yields, city and district panels. Verify Kosovo and Metohija missing-statistics behaviour explicitly.
5. **Harden and release.** Automate Python, JS, data-contract and browser checks; test mobile and keyboard access; make README commands reflect reality; build the trailer only after its data is stable.

The detailed product decisions and acceptance criteria live in `docs/DESIGN.md`. The untracked M1 implementation plan may need reconciliation with the repository before work starts.
