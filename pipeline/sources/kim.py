"""Kosovo and Metohija: the 5 oblasti and 29 municipalities the Statistical Office counts, with boundaries.

Eurostat's NUTS and LAU files end at the administrative line: they hold Serbia's 25 oblasti and 168 municipalities
north of it and nothing under RS23. South of it geoBoundaries draws the 38 municipalities Kosovo administers today,
from OpenStreetMap. Which of those polygons make which of the office's 29 municipalities is a hand-checked table,
pipeline/data/kim_stitch.csv, with the reason in its ``basis`` column (the Almanac quotes it). A municipality is the
rings of its polygons together and an oblast the rings of its municipalities; no shared edge is removed, geo.Shape's
even-odd rule takes the rings as they are.

pipeline/data/kim_towns.csv holds each municipality's seat. Its coordinates were taken from the place layer of the
Kosovo OpenStreetMap extract that fetch() downloads for the record; process() reads the table, not the extract, and
fails naming the town when a seat is not inside its own municipality.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from ..core import geo, srb, territory
from ..core.source import Source, SourceInfo
from ..core.srtext import fold_key

DATA = Path(__file__).resolve().parents[1] / "data"
STITCH_CSV = DATA / "kim_stitch.csv"
TOWNS_CSV = DATA / "kim_towns.csv"
GEOBOUNDARIES = "geoBoundaries-XKX-ADM2.geojson"
KOSOVO_EXTRACT = "kosovo-latest-free.shp.zip"

# geoBoundaries names every polygon "Municipality of <name>", in Albanian or English. The name a row of the stitch
# table refers to is what follows; "isto ime" holds only when that is the municipality's own name.
PREFIX = "Municipality of "
SAME_NAME = "isto ime"

# Gora's seat is the town of Dragaš; every other seat is named after its municipality.
SEAT_DIFFERS = {"Dragaš": "Gora"}

VINTAGE = "geoBoundaries XKX ADM2 (OpenStreetMap, januar 2023); podela Republičkog zavoda za statistiku"

_PROJECT = geo.MapProjection(0, 0, 0)  # the equal-area projection with no shift and no margin: x, y are km


# --- the stitch table ------------------------------------------------------------------------------------------


def read_stitch(path) -> dict[str, tuple[str, str]]:
    """{"<shapeName>": ("<unit id>", "<basis>")} from the stitch table at `path` (see read_stitch_text)."""
    return read_stitch_text(Path(path).read_text(encoding="utf-8"))


def read_stitch_text(text: str) -> dict[str, tuple[str, str]]:
    """{"<shapeName>": ("<unit id>", "<basis>")} from the text of kim_stitch.csv.

    A row that cannot be right is refused by naming its polygon: a unit that is not a municipality of Kosovo and
    Metohija, no basis, a polygon twice, or ``isto ime`` when the polygon's name is not the unit's.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ["polygon", "unit", "basis"]:
        found = ",".join(reader.fieldnames or [])
        raise RuntimeError(f"the stitch table must start with the header polygon,unit,basis, not {found!r}")
    table: dict[str, tuple[str, str]] = {}
    for row in reader:
        polygon, unit, basis = row["polygon"], row["unit"], (row["basis"] or "").strip()
        if not (territory.is_unit(unit) and territory.in_kosovo(unit)):
            raise RuntimeError(f"{polygon!r}: {unit!r} is not a municipality of Kosovo and Metohija")
        if polygon in table:
            raise RuntimeError(f"{polygon!r} is in the stitch table twice")
        if not basis:
            raise RuntimeError(f"{polygon!r}: no basis")
        if basis == SAME_NAME and fold_key(polygon.removeprefix(PREFIX)) != fold_key(territory.name(unit)):
            raise RuntimeError(f"{polygon!r} is not the name of {territory.name(unit)}, so its basis is not {SAME_NAME!r}")
        table[polygon] = (unit, basis)
    return table


# --- polygons → municipalities → oblasti -----------------------------------------------------------------------


def municipalities(polygons: list[dict], table: dict) -> dict[str, list]:
    """For each RZS municipality, the lon/lat rings of its polygons together: {unit id: rings}, in id order."""
    return _rings_by(polygons, table, lambda unit: unit)


def dissolve(polygons: list[dict], table: dict, oblast_of) -> dict[str, list]:
    """For each okrug, the rings of its municipalities' polygons together: {okrug id: rings}, in id order.
    `oblast_of` gives a unit's okrug (territory.oblast_of)."""
    return _rings_by(polygons, table, oblast_of)


def _rings_by(polygons: list[dict], table: dict, key_of) -> dict[str, list]:
    """The rings of the polygons (GeoJSON features with a `shapeName`), grouped by the key of each one's unit."""
    grouped: dict[str, list] = {}
    for polygon in polygons:
        name = polygon["properties"]["shapeName"]
        if name not in table:
            raise RuntimeError(f"the stitch table has no row for the polygon {name!r}")
        grouped.setdefault(key_of(table[name][0]), []).extend(geo.geojson_rings(polygon["geometry"]))
    return dict(sorted(grouped.items()))


def _projected(rings) -> list[list[tuple[float, float]]]:
    return [[_PROJECT(x, y) for x, y in ring] for ring in rings]


def area_km2(rings) -> float:
    """The area of lon/lat rings in km². The projection is equal-area, so the planar area is the true area."""
    return geo.Shape(_projected(rings)).area_km2()


# --- the seats --------------------------------------------------------------------------------------------------


def read_towns(path) -> list[dict]:
    """The seats from kim_towns.csv: [{"name": "Priština", "unit": "90263", "lon": …, "lat": …}], in the table's order."""
    with open(path, encoding="utf-8", newline="") as f:
        towns = [
            {"name": row["name"], "unit": _seat_unit(row["name"]), "lon": float(row["lon"]), "lat": float(row["lat"])}
            for row in csv.DictReader(f)
        ]
    return towns


def _seat_unit(name: str) -> str:
    """The municipality a seat belongs to: the one it is named after (Dragaš is the seat of Gora)."""
    wanted = fold_key(SEAT_DIFFERS.get(name, name))
    for okrug in srb.KIM_OBLASTI:
        for unit in territory.children(okrug):
            if fold_key(territory.name(unit)) == wanted:
                return unit
    raise RuntimeError(f"{name!r} is the seat of no municipality of Kosovo and Metohija")


def check_towns(towns: list[dict], municipalities: dict) -> None:
    """Fail, naming the town, when a seat does not lie inside its own municipality's rings."""
    for town in towns:
        rings = municipalities.get(town["unit"])
        inside = rings is not None and geo.Shape(_projected(rings)).contains(*_PROJECT(town["lon"], town["lat"]))
        if not inside:
            raise RuntimeError(f"{town['name']!r} does not lie inside its municipality {town['unit']}")


# --- the source -------------------------------------------------------------------------------------------------


class Kim(Source):
    info = SourceInfo(
        id="kim",
        title="Granice opština Kosova i Metohije (geoBoundaries)",
        publisher="geoBoundaries, OpenStreetMap",
        homepage="https://www.geoboundaries.org/",
        license="geoBoundaries: CC BY-SA 2.0 (podaci iz OpenStreetMap); © OpenStreetMap contributors",
        description="Granice 38 opština po današnjoj podeli Kosova (geoBoundaries, iz OpenStreetMap), ručno sparene sa "
                    "29 opština i 5 oblasti po podeli Republičkog zavoda za statistiku: tabela kim_stitch.csv navodi "
                    "razlog za svaku od njih. Sedišta opština su preuzeta sa OpenStreetMap karte Kosova.",
        used_for=["Granice opština i okruga Kosova i Metohije na mapi", "Sedišta opština Kosova i Metohije"],
    )

    def fetch(self, force=False):
        self.download(srb.GEOBOUNDARIES_XKX_ADM2, GEOBOUNDARIES, force=force, expect_binary=True)
        self.download(srb.GEOFABRIK_URL.format(region="kosovo"), KOSOVO_EXTRACT, force=force, expect_binary=True)

    def process(self) -> dict:
        polygons = geo.load_geojson(self.raw_dir / GEOBOUNDARIES)
        table = read_stitch(STITCH_CSV)
        units = municipalities(polygons, table)
        oblasti = dissolve(polygons, table, territory.oblast_of)
        towns = read_towns(TOWNS_CSV)
        check_towns(towns, units)
        area = round(sum(area_km2(geo.geojson_rings(p["geometry"])) for p in polygons), 1)
        print(f"    {len(oblasti)} oblasti, {len(units)} municipalities, {len(towns)} seats, {area:,.1f} km²")
        return {
            "vintage": VINTAGE,
            "oblasti": [{"id": okrug, "rings": rings} for okrug, rings in oblasti.items()],
            "municipalities": [{"id": unit, "rings": rings} for unit, rings in units.items()],
            "stitch": [{"polygon": polygon, "unit": unit, "basis": basis} for polygon, (unit, basis) in table.items()],
            "area_km2": area,
            "towns": [{"name": t["name"], "lon": t["lon"], "lat": t["lat"]} for t in towns],
            "_files": [GEOBOUNDARIES, KOSOVO_EXTRACT],
        }
