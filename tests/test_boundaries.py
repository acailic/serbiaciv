"""Boundaries: Serbia's oblasti, regioni and municipalities from Eurostat, the neighbouring countries from Natural Earth."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import shapefile

from pipeline.core import geo, shp
from pipeline.data import country_names
from pipeline.sources import boundaries

FRAME = (16.295, 39.998, 25.705, 48.002)  # Serbia's bounding box grown by the 200 km margin


def _square(lon0, lat0, lon1, lat1):
    """A closed square ring in lon/lat."""
    return [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]


def _tuples(rings):
    return [[tuple(p) for p in ring] for ring in rings]


def _nuts_feature(nuts_id, country, ring):
    """A feature as GISCO's NUTS GeoJSON writes it: one MultiPolygon with a single part."""
    return {"type": "Feature", "properties": {"NUTS_ID": nuts_id, "CNTR_CODE": country},
            "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]}}


class FrameTest(unittest.TestCase):
    def test_serbias_bounding_box_grown_by_the_margin(self):
        # 200 km is 1.80 degrees of latitude at 111 km each, and 2.50 of longitude at 111 km × cos 44°
        self.assertEqual(tuple(round(v, 3) for v in boundaries.frame_bbox()), FRAME)


class OblastiTest(unittest.TestCase):
    def test_only_serbias_regions_come_out_with_sorted_ids(self):
        level3 = [
            _nuts_feature("RS217", "RS", _square(20.5, 43.2, 21.0, 43.8)),
            _nuts_feature("HU11", "HU", _square(19.0, 46.3, 20.0, 46.8)),
            _nuts_feature("RS110", "RS", _square(20.2, 44.5, 20.7, 45.2)),
            _nuts_feature("RS121", "RS", _square(19.3, 45.5, 19.6, 45.9)),
        ]
        out = boundaries.oblasti_from_geojson(level3)
        self.assertEqual([o["id"] for o in out], ["RS110", "RS121", "RS217"])
        self.assertEqual(out[2]["rings"], _tuples([_square(20.5, 43.2, 21.0, 43.8)]))

    def test_the_same_function_reads_the_regions_of_level_2(self):
        level2 = [_nuts_feature("RS22", "RS", _square(21.5, 43.2, 22.3, 44.2)), _nuts_feature("RS11", "RS", _square(20.2, 44.5, 20.7, 45.2))]
        self.assertEqual([r["id"] for r in boundaries.oblasti_from_geojson(level2)], ["RS11", "RS22"])


class MunicipalitiesTest(unittest.TestCase):
    def _lau_zip(self, rows) -> Path:
        """A municipal file as Eurostat ships it: one nested zip per projection."""
        bufs = {ext: io.BytesIO() for ext in shp.MEMBERS}
        w = shapefile.Writer(shp=bufs[".shp"], shx=bufs[".shx"], dbf=bufs[".dbf"], shapeType=shapefile.POLYGON)
        for field in ("GISCO_ID", "CNTR_CODE", "LAU_NAME"):
            w.field(field, "C")
        for rings, gisco_id, country, name in rows:
            w.poly([[(float(x), float(y)) for x, y in ring] for ring in rings])
            w.record(gisco_id, country, name)
        w.close()
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zf:
            for ext in shp.MEMBERS:
                zf.writestr("LAU_RG_01M_2024_4326" + ext, bufs[ext].getvalue())
        path = Path(self.tmp.name) / "ref-lau-2024-01m.shp.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("LAU_RG_01M_2024_4326.shp.zip", inner.getvalue())
        return path

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_ids_are_the_office_codes_of_the_serbian_records(self):
        path = self._lau_zip([
            ([_square(21.9, 42.4, 22.0, 42.6)], "RS_70432", "RS", "Vranje"),
            ([_square(20.9, 43.4, 21.0, 43.6)], "HU_31587", "HU", "Pécs"),
            ([_square(21.0, 43.4, 21.1, 43.5)], "RS_70017", "RS", "Aleksandrovac"),
        ])
        reader = shp.open_shapefile(path, "LAU_RG_01M_2024_4326.shp.zip/LAU_RG_01M_2024_4326")
        out = boundaries.municipalities_from_records(shp.records(reader))
        self.assertEqual([m["id"] for m in out], ["70017", "70432"])  # sorted, "RS_" removed, other countries left out
        self.assertEqual(out[1]["rings"], _tuples([_square(21.9, 42.4, 22.0, 42.6)]))

    def test_a_municipality_keeps_all_its_rings(self):
        rings = [_square(20.3, 43.0, 20.5, 43.2), _square(20.8, 43.0, 20.9, 43.1)]  # a mainland and an island
        out = boundaries.municipalities_from_records([({"GISCO_ID": "RS_70000"}, rings)])
        self.assertEqual(out, [{"id": "70000", "rings": _tuples(rings)}])


class CountriesTest(unittest.TestCase):
    def _countries_zip(self, rows) -> Path:
        bufs = {ext: io.BytesIO() for ext in shp.MEMBERS}
        w = shapefile.Writer(shp=bufs[".shp"], shx=bufs[".shx"], dbf=bufs[".dbf"], shapeType=shapefile.POLYGON)
        for field in ("ADMIN", "ISO_A3", "ADM0_A3"):
            w.field(field, "C")
        for rings, admin, iso, adm0 in rows:
            w.poly([[(float(x), float(y)) for x, y in ring] for ring in rings])
            w.record(admin, iso, adm0)
        w.close()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "ne_10m_admin_0_countries.zip"
        with zipfile.ZipFile(path, "w") as zf:
            for ext in shp.MEMBERS:
                zf.writestr("ne_10m_admin_0_countries" + ext, bufs[ext].getvalue())
        return path

    def _countries(self, rows, names=None):
        reader = shp.open_shapefile(self._countries_zip(rows))
        return boundaries.countries_from_features(shp.records(reader), FRAME, country_names.SR if names is None else names)

    def test_a_country_touching_the_frame_comes_out_in_serbian(self):
        hungary = _square(19.0, 46.3, 20.0, 46.8)
        out = self._countries([([hungary], "Hungary", "HUN", "HUN")])
        self.assertEqual(out, [{"iso": "HUN", "name_sr": "Mađarska", "rings": _tuples([hungary])}])

    def test_a_country_outside_the_frame_is_left_out(self):
        france = _square(2.0, 48.5, 2.5, 49.0)
        self.assertEqual(self._countries([([france], "France", "-99", "FRA")]), [])

    def test_only_the_rings_that_touch_the_frame_are_kept(self):
        rome, salento = _square(12.4, 41.7, 12.7, 42.0), _square(18.3, 40.0, 18.6, 40.4)
        out = self._countries([([rome, salento], "Italy", "ITA", "ITA")])
        self.assertEqual(out[0]["rings"], _tuples([salento]))

    def test_a_country_without_a_serbian_name_is_named(self):
        slovakia = _square(18.7, 47.9, 18.8, 48.0)  # south of the frame's north edge
        with self.assertRaises(KeyError) as ctx:
            self._countries([([slovakia], "Slovakia", "SVK", "SVK")], names={"HUN": "Mađarska"})
        self.assertIn("SVK", str(ctx.exception))

    def test_serbia_and_kosovo_are_never_countries(self):
        serbia, kosovo, hungary = _square(20.2, 44.5, 20.7, 45.2), _square(20.9, 42.5, 21.1, 42.8), _square(19.0, 46.3, 20.0, 46.8)
        rows = [([serbia], "Republic of Serbia", "SRB", "SRB"), ([kosovo], "Kosovo", "-99", "KOS"), ([hungary], "Hungary", "HUN", "HUN")]
        names = dict(country_names.SR, SRB="Srbija", KOS="Kosovo")  # a Serbian name would not make them neighbours
        self.assertEqual([c["iso"] for c in self._countries(rows, names)], ["HUN"])


class CountryNamesTest(unittest.TestCase):
    def test_every_country_the_frame_reaches_has_its_serbian_latin_name(self):
        self.assertEqual(country_names.SR, {
            "ALB": "Albanija", "AUT": "Austrija", "BIH": "Bosna i Hercegovina", "BGR": "Bugarska", "HRV": "Hrvatska",
            "GRC": "Grčka", "HUN": "Mađarska", "ITA": "Italija", "MNE": "Crna Gora", "MKD": "Severna Makedonija",
            "ROU": "Rumunija", "SVK": "Slovačka", "SVN": "Slovenija", "TUR": "Turska", "UKR": "Ukrajina",
        })


if __name__ == "__main__":
    unittest.main()
