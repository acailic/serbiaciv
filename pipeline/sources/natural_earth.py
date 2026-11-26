"""Natural Earth 1:10m roads and railroads: the line work the map's roads and railways are drawn from.

A separate source from the boundaries (which take the countries file), so the map's land and water do not depend on
these two large files. Every feature with a line that touches the frame is kept, in every neighbouring country too:
who owns a heks is decided by the world builder (owner codes), not here. The builder samples the lines onto hex links;
this module only reads the shapefiles and rounds the coordinates.

Natural Earth's 1:10m roads carry a ``type`` (Motorway, Major Highway, Secondary Highway, Beltway, …) and a
``scalerank``; its railroads carry a ``scalerank`` and, for Serbia, no owner. Names are kept as Natural Earth writes
them (Serbian roads carry their Latin or Cyrillic name; the builder converts them).
"""

from __future__ import annotations

from ..core import srb, shp
from ..core.geo import bbox_intersects
from ..core.source import Source, SourceInfo
from .boundaries import frame_bbox

ROADS_ZIP = "ne_10m_roads.zip"
RAIL_ZIP = "ne_10m_railroads.zip"
FILES = [ROADS_ZIP, RAIL_ZIP]
FERRY_TYPES = {"Ferry Route", "Ferry"}  # Natural Earth's ferry lines are not roads


def _rounded(line):
    return [(round(x, 4), round(y, 4)) for x, y in line]


def roads_from_records(records, frame):
    """[{level, type, name, expressway, scalerank, sov_a3, lines}] for every road feature with a line in `frame`."""
    out = []
    for props, lines in records:
        if (props.get("type") or "") in FERRY_TYPES or (props.get("featurecla") or "") in FERRY_TYPES:
            continue
        kept = [_rounded(ln) for ln in lines if bbox_intersects(ln, frame)]
        if not kept:
            continue
        name = str(props.get("name") or "").strip() or None
        out.append({
            "level": str(props.get("level") or "").strip() or None,
            "type": str(props.get("type") or "").strip() or None,
            "name": name,
            # Natural Earth's route labels for Serbia: the European road (E75) and the state road number or old M/A number
            "label": str(props.get("label") or "").strip() or None,
            "label2": str(props.get("label2") or "").strip() or None,
            "expressway": 1 if props.get("expressway") in (1, "1", 1.0) else 0,
            "scalerank": int(props["scalerank"]) if props.get("scalerank") not in (None, "") else None,
            "sov_a3": str(props.get("sov_a3") or "").strip() or None,
            "lines": kept,
        })
    return out


def rail_from_records(records, frame):
    """[{scalerank, sov_a3, lines}] for every railroad feature with a line in `frame`."""
    out = []
    for props, lines in records:
        kept = [_rounded(ln) for ln in lines if bbox_intersects(ln, frame)]
        if not kept:
            continue
        out.append({
            "scalerank": int(props["scalerank"]) if props.get("scalerank") not in (None, "") else None,
            "sov_a3": str(props.get("sov_a3") or "").strip() or None,
            "lines": kept,
        })
    return out


class NaturalEarthRoads(Source):
    info = SourceInfo(
        id="natural_earth_roads",
        title="Natural Earth 1:10m: putevi i pruge",
        publisher="Natural Earth",
        homepage="https://www.naturalearthdata.com/downloads/10m-cultural-vectors/roads/",
        license="Javno dobro (public domain)",
        description="Auto-putevi, magistralni putevi i pruge kao linijski crtež 1:10m za Srbiju i susede. Služe kao "
                    "naknadna umetnost na mapi (put ili pruga između centara heksa), ne kao statistika: položaj je "
                    "stariji, bez podataka o saobraćaju, a pruge su prikazane nepotpuno.",
        used_for=["Putevi na mapi", "Pruge na mapi"],
    )

    def fetch(self, force=False):
        for name in ("roads", "railroads"):
            self.download(srb.NATURAL_EARTH.format(theme="cultural", name=name), f"ne_10m_{name}.zip", force=force,
                          expect_binary=True)

    def process(self) -> dict:
        frame = frame_bbox()
        roads_reader = shp.open_shapefile(self.raw_dir / ROADS_ZIP)
        try:
            roads = roads_from_records(shp.records(roads_reader), frame)
        finally:
            roads_reader.close()
        rail_reader = shp.open_shapefile(self.raw_dir / RAIL_ZIP)
        try:
            rail = rail_from_records(shp.records(rail_reader), frame)
        finally:
            rail_reader.close()
        print(f"    {len(roads)} road features, {len(rail)} rail features in the map frame")
        return {
            "vintage": "Natural Earth 1:10m (naciscdn.org)",
            "roads": roads,
            "rail": rail,
            "_files": list(FILES),
        }
