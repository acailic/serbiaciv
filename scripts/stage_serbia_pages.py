"""Stage the full app only when its data has the Serbia milestone's identity and shape.

This is an additional guard, not a replacement for `python -m pipeline check` or a browser smoke test.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.package import ASSETS, SOURCE_ZIP, write_source_archive
# Every file the app loads. It fetches a missing one and shows a note instead of the layer, so a file left out here
# publishes an app that looks whole and is not: the site layers, the Energy, Traffic and Culture advisors and the
# whole City View read the last five.
LENSES = ("density", "pop_change", "natural_increase", "age65", "education", "wages", "unemployment",
          "manufacturing", "commute", "orthodox", "serbs", "life_expectancy", "elevation", "relief", "land_cover")


def stage(web: Path, dest: Path) -> None:
    web, dest = Path(web), Path(dest)
    if dest.exists():
        raise ValueError(f"staging destination already exists: {dest}")
    if not (web / "index.html").is_file():
        raise ValueError("missing web/index.html")
    data = {}
    for name in ASSETS:
        path = web / "data" / name
        if not path.is_file():
            raise ValueError(f"missing Serbian build asset: {path}")
        try:
            data[name] = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    world = data["world.json"]
    districts = [s.get("fips") for s in world.get("states", [])]
    if (world.get("grid", {}).get("radius") != 5 or len(districts) != 30 or len(set(districts)) != 30
            or any(not isinstance(i, str) or not re.fullmatch(r"RS\d{3}", i) for i in districts)):
        raise ValueError("world is not the 5 km Serbian district map")
    if [s.get("fips") for s in data["states.json"]] != districts:
        raise ValueError("state IDs do not match the world")
    ids = [c.get("geoid") for c in world.get("counties", [])]
    if len(ids) != 197 or len(set(ids)) != 197 or any(not isinstance(i, str) or not re.fullmatch(r"\d{5}", i) for i in ids):
        raise ValueError("world must contain 197 distinct municipality IDs")
    lens_file, lens_values = data["lenses.json"], data["lens-values.json"]
    if lens_file.get("version") != 2 or [x.get("id") for x in lens_file.get("lenses", [])] != list(LENSES):
        raise ValueError("Serbian version 2 lens manifest is missing or incomplete")
    if lens_values.get("version") != 2 or lens_values.get("municipality_ids") != ids:
        raise ValueError("lens municipality IDs do not match the world")
    values = lens_values.get("values", {})
    if any(not isinstance(values.get(key), list) or len(values[key]) != len(ids) for key in LENSES[:12]):
        raise ValueError("municipality lens values are missing or incomplete")
    if not any(c.get("id") == "79014" and c.get("capital") for c in data["cities.json"]):
        raise ValueError("Serbian capital is missing")
    if data["nation.json"].get("nation", {}).get("fips") != "RS":
        raise ValueError("nation data is not Serbian")
    if not {"census", "rzs_db", "dem", "landcover"}.issubset({s.get("id") for s in data["sources.json"]}):
        raise ValueError("Serbian source metadata is incomplete")
    table = data["counties.json"]
    columns = table.get("columns", [])
    if "geoid" not in columns or [row[columns.index("geoid")] for row in table.get("rows", [])] != ids:
        raise ValueError("municipality table IDs do not match the world")

    # The site layers place their items on the map by cell index; a cell outside the grid draws nothing.
    cells = world["grid"]["cols"] * world["grid"]["rows"]

    def on_map(name, items):
        if not isinstance(items, list) or not items:
            raise ValueError(f"{name}: no sites to show")
        for item in items:
            cell = item.get("cell")
            if type(cell) is not int or not 0 <= cell < cells:
                raise ValueError(f"{name}: {item.get('name', item.get('id'))!r} is not on a hex of the map")

    on_map("resources.json", data["resources.json"].get("items"))
    on_map("wonders.json", data["wonders.json"].get("wonders"))
    infrastructure = data["infrastructure.json"]
    on_map("infrastructure.json", infrastructure.get("ports"))
    on_map("infrastructure.json", infrastructure.get("airports"))
    if not infrastructure.get("roads") or not infrastructure.get("rail"):
        raise ValueError("infrastructure.json: no roads or no rail lines")

    # The City View files hold a row for every city of cities.json, and no row for a city the map does not have.
    city_ids = {c.get("id") for c in data["cities.json"]}
    known = city_ids | set(ids)
    for name in ("citizens.json", "districts.json"):
        rows = data[name].get("cities")
        if not isinstance(rows, dict) or set(rows) != city_ids:
            raise ValueError(f"{name}: its cities are not exactly the cities of cities.json")
    district_rows = data["districts.json"].get("counties")
    if (not isinstance(district_rows, dict) or not district_rows
            or not set(district_rows) <= known):
        raise ValueError("districts.json: a municipality row names a unit the map does not have")

    def ignore(directory, names):
        path = Path(directory)
        if path == web:
            return [name for name in names if name in {"dev", "data"}]
        return [name for name in names if name.endswith(".test.js") or name == "__pycache__"]

    shutil.copytree(web, dest, ignore=ignore)
    (dest / "data").mkdir()
    for name in ASSETS:
        shutil.copy2(web / "data" / name, dest / "data" / name)
    write_source_archive(dest / SOURCE_ZIP)


if __name__ == "__main__":
    stage(ROOT / "web", ROOT / "dist" / "pages-app")
    print("Staged Serbian application in dist/pages-app")
