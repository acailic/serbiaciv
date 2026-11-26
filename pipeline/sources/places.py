"""OpenStreetMap places: the named settlements of Serbia, from Geofabrik's shapefile of its extract."""

from __future__ import annotations

from ..core import shp, srb
from ..core.srtext import to_latin
from ..core.source import Source, SourceInfo

SERBIA = "serbia-latest-free.shp.zip"  # Geofabrik names its extract of Serbia; Kosovo and Metohija is Task 3's


def places_from_records(records):
    """Read named settlements, retaining an unknown population as null."""
    out = []
    for props, parts in records:
        name, kind = props.get("name"), props.get("fclass")
        if not name or not str(name).strip() or kind not in {"city", "town", "village"} or not parts or not parts[0]:
            continue
        try:
            population = int(props.get("population"))
            if population < 0:
                population = None
        except (TypeError, ValueError):
            population = None
        lon, lat = parts[0][0]
        out.append({"name": name, "name_lat": to_latin(name), "fclass": kind,
                    "population": population, "lon": lon, "lat": lat})
    return out


class Places(Source):
    info = SourceInfo(
        id="places",
        title="Naselja Srbije (OpenStreetMap)",
        publisher="OpenStreetMap (Geofabrik)",
        homepage="https://download.geofabrik.de/europe.html",
        license="Open Database License (ODbL) 1.0",
        description="Gradovi, varoši i sela sa mape OpenStreetMap-a, sa brojem stanovnika kad je unet. Obuhvata Srbiju "
                    "bez Kosova i Metohije.",
        used_for=["Naselja"],
    )

    def fetch(self, force: bool = False) -> None:
        self.download(srb.GEOFABRIK_URL.format(region="serbia"), SERBIA, force=force, expect_binary=True)

    def process(self) -> dict:
        reader = shp.open_shapefile(self.raw_dir / SERBIA, "gis_osm_places_free_1")
        try:
            places = places_from_records(shp.records(reader))
        finally:
            reader.close()
        return {"vintage": "OpenStreetMap (Geofabrik: Srbija)", "places": places, "_files": [SERBIA]}
