"""Serbia's boundaries, and the land around it: oblasti and regioni (Eurostat NUTS), municipalities (Eurostat LAU)
and the neighbouring countries (Natural Earth).

Each unit is ``{"id": …, "rings": …}`` with its rings in lon/lat; who owns a heks is decided by testing its centre
against them (the world builder), not here. The ids are the ones every other source joins on: NUTS codes for the
oblasti and regioni, the Statistical Office's 5-digit codes for the municipalities (GISCO writes them ``RS_70017``).
Kosovo and Metohija is not in these files; the kim source draws it.

The oblasti and regioni are read from GISCO's 1:1 M file, the finest it publishes. The 1:20 M file the project began
with draws a district border with a vertex every 8 km, about one hex: measured against a public copy of the Republic
Geodetic Authority's 2019 dump of the register of spatial units, it put 3.6 % of Serbia's hexes outside Kosovo and
Metohija in a neighbouring district and 24 on the wrong side of the state border; this file puts 0.25 % and 3.

A neighbouring country is kept only where it can be seen: the rings that touch the frame, the Republic's bounding
box grown by the map's margin.
"""

from __future__ import annotations

import math

from ..core import geo, srb, shp
from ..core.source import Source, SourceInfo
from ..data import country_names

NUTS = "NUTS_RG_01M_2024_4326_LEVL_{level}.geojson"  # same scale as the LAU file below, see the module docstring
LAU_ZIP = "ref-lau-2024-01m.shp.zip"
LAU_MEMBER = "LAU_RG_01M_2024_4326.shp.zip/LAU_RG_01M_2024_4326"  # the 4326 (lon/lat) of the three nested shapefiles
COUNTRIES_ZIP = "ne_10m_admin_0_countries.zip"
FILES = [NUTS.format(level=3), NUTS.format(level=2), LAU_ZIP, COUNTRIES_ZIP]

COUNTRY = "RS"  # CNTR_CODE of Serbia; Kosovo and Metohija's regions are filed under XK
GISCO_PREFIX = "RS_"
NO_ISO = "-99"  # what Natural Earth writes where ISO has no code
HOMELAND = ("SRB", "KOS")  # never a neighbour: the oblasti, the municipalities and the kim source draw them

KM_PER_DEGREE = 111.0


def frame_bbox() -> tuple[float, float, float, float]:
    """The map's frame: Serbia's bounding box grown by the margin, as (min lon, min lat, max lon, max lat)."""
    lon0, lat0, lon1, lat1 = srb.BBOX_LONLAT
    dlat = srb.MARGIN_KM / KM_PER_DEGREE
    dlon = srb.MARGIN_KM / (KM_PER_DEGREE * math.cos(math.radians(44.0)))  # a degree of longitude at Serbia's middle
    return lon0 - dlon, lat0 - dlat, lon1 + dlon, lat1 + dlat


def oblasti_from_geojson(features: list[dict]) -> list[dict]:
    """Serbia's regions of one NUTS level from a GISCO file's features: [{"id": "RS110", "rings": …}], ids sorted.
    The same function reads both files: the oblasti at level 3, the regioni at level 2."""
    serbia = [f for f in features if f["properties"].get("CNTR_CODE") == COUNTRY]
    return [
        {"id": f["properties"]["NUTS_ID"], "rings": geo.geojson_rings(f["geometry"])}
        for f in sorted(serbia, key=lambda f: f["properties"]["NUTS_ID"])
    ]


def municipalities_from_records(records) -> list[dict]:
    """Serbia's municipalities from LAU records (properties, rings) as shp.records yields them:
    [{"id": "70017", "rings": …}], ids sorted. Only the Serbian records; there are none for Kosovo and Metohija."""
    out = []
    for props, rings in records:
        gisco_id = props.get("GISCO_ID") or ""
        if gisco_id.startswith(GISCO_PREFIX):
            out.append({"id": gisco_id[len(GISCO_PREFIX):], "rings": _rounded(rings)})
    return sorted(out, key=lambda m: m["id"])


def countries_from_features(features, frame: tuple, names: dict) -> list[dict]:
    """Every country with a ring that touches the frame, Serbia and Kosovo excepted, keeping only the rings that
    touch: [{"iso": "HUN", "name_sr": "Mađarska", "rings": …}], in the file's order.

    `features` are the (properties, rings) records of Natural Earth's countries. A country that `names` has no
    Serbian name for raises KeyError naming it, rather than appearing on the map nameless or under an English name.
    """
    countries = []
    for props, rings in features:
        iso = props["ISO_A3"] if props["ISO_A3"] != NO_ISO else props["ADM0_A3"]
        if iso in HOMELAND:
            continue
        rings = _rounded(r for r in rings if geo.bbox_intersects(r, frame))
        if rings:
            countries.append({"iso": iso, "name_sr": names[iso], "rings": rings})
    return countries


def _rounded(rings) -> list[list[tuple[float, float]]]:
    """Shapefile rings at the precision geojson_rings keeps for GeoJSON ones (five decimals, about a metre)."""
    return [[(round(x, 5), round(y, 5)) for x, y in ring] for ring in rings]


class Boundaries(Source):
    info = SourceInfo(
        id="boundaries",
        title="Granice: oblasti, regioni, opštine i susedne države",
        publisher="Eurostat (GISCO), Natural Earth",
        homepage="https://ec.europa.eu/eurostat/web/gisco",
        license="© Evropska unija, 1995–2026, CC BY 4.0; Natural Earth: javni domen",
        description="NUTS 2024 (1:1 M) za 25 oblasti i 4 regiona, LAU 2024 (1:1 M) za 168 opština Srbije bez Kosova i "
                    "Metohije (koji donosi izvor kim) i Natural Earth 1:10m za petnaest susednih država koje dodiruju "
                    "okvir karte.",
        used_for=["Kojoj oblasti i opštini pripada heks", "Granice oblasti, regiona i opština na mapi", "Susedne države na mapi"],
    )

    def fetch(self, force=False):
        for level in (3, 2):
            self.download(srb.GISCO_NUTS_URL.format(level=level), NUTS.format(level=level), force=force, expect_binary=True)
        self.download(srb.GISCO_LAU_URL, LAU_ZIP, force=force, expect_binary=True)
        self.download(srb.NATURAL_EARTH.format(theme="cultural", name="admin_0_countries"), COUNTRIES_ZIP, force=force,
                      expect_binary=True)

    def process(self) -> dict:
        oblasti = oblasti_from_geojson(geo.load_geojson(self.raw_dir / NUTS.format(level=3)))
        regioni = oblasti_from_geojson(geo.load_geojson(self.raw_dir / NUTS.format(level=2)))
        municipalities = municipalities_from_records(shp.records(shp.open_shapefile(self.raw_dir / LAU_ZIP, LAU_MEMBER)))
        countries = countries_from_features(
            shp.records(shp.open_shapefile(self.raw_dir / COUNTRIES_ZIP)), frame_bbox(), country_names.SR
        )
        print(f"    {len(oblasti)} oblasti, {len(regioni)} regioni, {len(municipalities)} municipalities, "
              f"{len(countries)} countries")
        return {
            "vintage": {
                "oblasti": "Eurostat GISCO, NUTS 2024 (1:1 M)",
                "regioni": "Eurostat GISCO, NUTS 2024 (1:1 M)",
                "municipalities": "Eurostat GISCO, LAU 2024 (1:1 M)",
                "countries": "Natural Earth 1:10m",
            },
            "oblasti": oblasti,
            "regioni": regioni,
            "municipalities": municipalities,
            "countries": countries,
            "_files": list(FILES),
        }
