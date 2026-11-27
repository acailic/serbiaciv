# Contributing to serbiaciv

Thanks for helping improve the atlas. Issues and pull requests are welcome in English or Serbian (Latin or Cyrillic).

## Reporting problems

- **Data errors** (a wrong population, a misplaced town, a bad district boundary, a missing landmark): open a [data error report](https://github.com/acailic/serbiaciv/issues/new?template=data-error.yml). Please include a link to the map view (the address bar keeps the view and script) and, if you can, a source for the correct value.
- **Bugs** in the interface or the pipeline: open a [bug report](https://github.com/acailic/serbiaciv/issues/new?template=bug-report.yml).

## Development setup

You need [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer. Node.js and `rg` are only needed for the JavaScript tests.

```bash
uv sync --frozen
uv run python -m pipeline serve          # http://127.0.0.1:8765
```

## Before opening a pull request

```bash
uv run python -m unittest discover -s tests
node --test $(rg --files web -g '*.test.js')
uv run python -m pipeline check          # when you touched data or builders
```

`pipeline check` must not report failures. If it reports new warnings, explain them in the pull request.

## Changing data

- Keep each dataset's attribution and licence terms; add new sources to `web/data/sources.json` with their vintage.
- Document the shape and meaning of new fields in [`docs/DATA_CONTRACTS.md`](docs/DATA_CONTRACTS.md).
- Represent missing values as missing, never as zero. This matters in particular for Kosovo and Metohija, where RZS does not publish the statistical series.
- User-facing text needs both Serbian Latin and Cyrillic; check terms against [`docs/GLOSSARY.md`](docs/GLOSSARY.md).

## Scope

serbiaciv is a data visualisation, not a playable game or a simulation. Proposals that keep every number traceable to a public source fit best; see [`docs/DESIGN.md`](docs/DESIGN.md) for the binding design decisions.

By contributing you agree that your code is released under the [MIT licence](LICENSE).
