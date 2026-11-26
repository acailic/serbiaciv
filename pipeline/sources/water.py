"""OpenStreetMap water: the rivers and lakes of Serbia and of Kosovo and Metohija, from Geofabrik's shapefiles."""

from __future__ import annotations

from itertools import chain
from math import hypot

from ..core import shp, srb, wikidata
from ..core.geo import Albers, Shape
from ..core.srtext import fold_key, to_latin
from ..core.source import Source, SourceInfo

EXTRACTS = ("serbia", "kosovo")  # the two Geofabrik extracts that together cover the whole country


def extract_file(region: str) -> str:
    """The extract as Geofabrik stores it, under the name of its address."""
    return srb.GEOFABRIK_URL.format(region=region).rsplit("/", 1)[1]


def water_from_records(river_records, lake_records, lengths):
    """Join named OSM rivers and retain named lakes, deduplicating overlapping extracts."""
    projection = Albers()
    rivers, lakes, seen_rivers, seen_lakes = {}, [], set(), set()
    for props, lines in river_records:
        name, ident = props.get("name"), props.get("osm_id")
        if props.get("fclass") != "river" or not name or not lines:
            continue
        # Extracts can clip the same OSM way differently. Keep distinct pieces and drop exact duplicates.
        geometry = tuple(tuple(tuple(point) for point in line) for line in lines)
        signature = (ident, geometry)
        if ident and signature in seen_rivers:
            continue
        if ident:
            seen_rivers.add(signature)
        key = fold_key(name)
        if not key:
            continue
        qid, length = lengths.get(key, (None, None))
        entry = rivers.setdefault(key, {"name": name, "name_lat": to_latin(name), "wikidata": qid,
                                        "length_km": length, "mapped_km": 0.0, "lines": []})
        for line in lines:
            points = [projection(*point) for point in line]
            entry["mapped_km"] += sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
            entry["lines"].append(line)
    for props, rings in lake_records:
        name, ident = props.get("name"), props.get("osm_id")
        if not name or not rings:
            continue
        signature = (ident, tuple(tuple(tuple(point) for point in ring) for ring in rings))
        if ident and signature in seen_lakes:
            continue
        if ident:
            seen_lakes.add(signature)
        area = Shape([[projection(*p) for p in ring] for ring in rings]).area_km2()
        if area >= srb.LAKE_MIN_KM2:
            lakes.append({"name": name, "name_lat": to_latin(name), "wikidata": None,
                          "area_km2": round(area, 2), "rings": rings})
    return {"rivers": [r for r in rivers.values() if (r["length_km"] or r["mapped_km"]) >= srb.RIVER_MIN_LENGTH_KM],
            "lakes": lakes}


class Water(Source):
    info = SourceInfo(
        id="water",
        title="Reke i jezera Srbije (OpenStreetMap)",
        publisher="OpenStreetMap (Geofabrik) i Wikidata",
        homepage="https://download.geofabrik.de/europe.html",
        license="Open Database License (ODbL) 1.0; Wikidata: CC0 1.0",
        description="Tokovi reka i obrisi jezera sa mapa OpenStreetMap-a, sa dužinom reke iz Wikidate kad je poznata.",
        used_for=["Reke", "Jezera"],
    )

    def fetch(self, force: bool = False) -> None:
        """Download both extracts and Wikidata's answer to the river-length query (which --force asks again too)."""
        for region in EXTRACTS:
            self.download(srb.GEOFABRIK_URL.format(region=region), extract_file(region), force=force, expect_binary=True)
        if force:
            self.discard(wikidata.RIVER_LENGTHS_FILE)
        wikidata.query(self, wikidata.RIVER_LENGTHS_SPARQL, wikidata.RIVER_LENGTHS_FILE)

    def process(self) -> dict:
        files = [extract_file(region) for region in EXTRACTS]
        readers = [shp.open_shapefile(self.raw_dir / file, layer) for file in files
                   for layer in ("gis_osm_waterways_free_1", "gis_osm_water_a_free_1")]
        try:
            rivers = chain.from_iterable(shp.records(r) for r in readers[::2])
            lakes = chain.from_iterable(shp.records(r) for r in readers[1::2])
            lengths = wikidata.river_lengths(wikidata.read_bindings(self.raw_dir / wikidata.RIVER_LENGTHS_FILE))
            result = water_from_records(rivers, lakes, lengths)
        finally:
            for reader in readers:
                reader.close()
        return {"vintage": "OpenStreetMap (Geofabrik: Srbija i Kosovo) i Wikidata", **result,
                "_files": files + [wikidata.RIVER_LENGTHS_FILE]}
