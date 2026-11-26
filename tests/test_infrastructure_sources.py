"""The infrastructure sources' parsers on tiny synthetic inputs: Natural Earth records, the AUL port chart, the
OurAirports CSV, Eurostat's JSON-stat and the Morava airport's statistics table. No network."""

import io
import re
import unittest
import zipfile

from pipeline.build import infrastructure as infra
from pipeline.sources import natural_earth, transport_hubs
from pipeline.sources.natural_earth import rail_from_records, roads_from_records
from pipeline.sources.transport_hubs import (airports_from_csv, passengers_from_html, passengers_from_jsonstat,
                                             ports_from_pptx)

FRAME = (19.0, 44.0, 21.0, 46.0)  # lon/lat bbox of the synthetic map
CYRILLIC = re.compile(r"[А-Яа-яЂђЈјЉљЊњЋћЏџ]")


class NaturalEarthRecordsTest(unittest.TestCase):
    def test_roads_keep_frame_features_with_their_labels_and_drop_ferries(self):
        records = [
            ({"type": "Major Highway", "level": "E", "label": "E75", "label2": "1", "expressway": 1, "scalerank": 3,
              "sov_a3": "SRB", "name": None}, [[(20.0, 45.0), (20.1234567, 45.1)]]),
            ({"type": "Ferry Route", "level": None, "label": None, "label2": None, "expressway": 0, "scalerank": 5,
              "sov_a3": "SRB", "name": "Ferry"}, [[(20.0, 45.0), (20.1, 45.0)]]),
            ({"type": "Major Highway", "level": "E", "label": "E60", "label2": None, "expressway": 1, "scalerank": 3,
              "sov_a3": "HUN", "name": None}, [[(19.0, 47.0), (20.0, 47.5)]]),  # outside the frame
            ({"type": "Road", "level": "E", "label": "E761", "label2": "5", "expressway": None, "scalerank": None,
              "sov_a3": "", "name": "Друмски пут"}, [[(20.5, 44.5), (20.6, 44.6)]]),
        ]
        roads = roads_from_records(records, FRAME)
        self.assertEqual([r["label"] for r in roads], ["E75", "E761"])
        self.assertEqual((roads[0]["label2"], roads[0]["expressway"], roads[0]["scalerank"]), ("1", 1, 3))
        self.assertEqual(roads[0]["lines"], [[(20.0, 45.0), (20.1235, 45.1)]])  # rounded, the out-of-frame part kept as given
        self.assertEqual((roads[1]["expressway"], roads[1]["scalerank"], roads[1]["name"]), (0, None, "Друмски пут"))
        self.assertEqual(infra.road_class(roads[0]), 0)
        self.assertIsNone(infra.road_class(roads[1]))  # unknown rank: not guessed

    def test_rail_keeps_frame_features_with_their_rank(self):
        records = [({"scalerank": 4, "sov_a3": "SRB"}, [[(20.0, 45.0), (20.2, 45.0)]]),
                   ({"scalerank": 12, "sov_a3": "SRB"}, [[(19.5, 44.5), (19.6, 44.5)]]),
                   ({"scalerank": None, "sov_a3": "SRB"}, [[(20.0, 44.0), (20.1, 44.0)]]),
                   ({"scalerank": 4, "sov_a3": "HUN"}, [[(19.0, 47.0), (20.0, 47.5)]])]
        rail = rail_from_records(records, FRAME)
        self.assertEqual([r["scalerank"] for r in rail], [4, 12, None])
        self.assertEqual([infra.rail_tier(r["scalerank"]) for r in rail], [0, None, None])

    def test_source_metadata_is_serbian_latin(self):
        for source_cls in (natural_earth.NaturalEarthRoads, transport_hubs.RiverPorts, transport_hubs.Airports,
                           transport_hubs.AirportTraffic):
            info = source_cls.info
            for text in (info.title, info.publisher, info.description, *info.used_for):
                self.assertFalse(CYRILLIC.search(text), f"{info.id}: {text}")
            self.assertTrue(info.homepage.startswith("http"), info.id)


def chart_xml(series):
    ns = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    body = ""
    for year, names, values in series:
        cats = "".join(f'<c:pt idx="{i}"><c:v>{n}</c:v></c:pt>' for i, n in enumerate(names))
        vals = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values) if v is not None)
        body += (f'<c:ser><c:tx><c:strRef><c:strCache><c:pt idx="0"><c:v>{year}</c:v></c:pt></c:strCache></c:strRef></c:tx>'
                 f'<c:cat><c:strRef><c:strCache>{cats}</c:strCache></c:strRef></c:cat>'
                 f'<c:val><c:numRef><c:numCache>{vals}</c:numCache></c:numRef></c:val></c:ser>')
    return f'<?xml version="1.0"?><c:chartSpace xmlns:c="{ns}"><c:chart><c:plotArea>{body}</c:plotArea></c:chart></c:chartSpace>'


def pptx(*charts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        for i, xml in enumerate(charts, start=1):
            zf.writestr(f"ppt/charts/chart{i}.xml", xml)
    return buf.getvalue()


NAMES = ["Бачка Паланка", "Панчево", "Смедерево", "Шабац"]


class RiverPortsTest(unittest.TestCase):
    def test_latest_year_series_in_latin_and_whole_tonnes(self):
        data = pptx(chart_xml([("2024", ["БЕОГРАД", "НОВИ САД"], [None, 52861.0])]),  # another chart: no port areas
                    chart_xml([("2024", NAMES, [442858.69, 2240229.94, 2847814.0, None]),
                               ("2025", NAMES, [360798.4, 1464110.95, 3075540.46, 146776.17])]))
        year, ports = ports_from_pptx(data)
        self.assertEqual(year, 2025)
        self.assertEqual(ports, [{"name": "Bačka Palanka", "tons": 360798}, {"name": "Pančevo", "tons": 1464111},
                                 {"name": "Smederevo", "tons": 3075540}, {"name": "Šabac", "tons": 146776}])
        self.assertFalse(any(CYRILLIC.search(p["name"]) for p in ports))

    def test_missing_chart_is_an_error_not_invented_ports(self):
        with self.assertRaises(ValueError):
            ports_from_pptx(pptx(chart_xml([("2025", ["БЕОГРАД"], [1.0])])))


AIRPORTS_CSV = "\n".join([
    '"id","ident","type","name","latitude_deg","longitude_deg","iso_country","icao_code","municipality","scheduled_service"',
     '4611,"LYBT","medium_airport","Batajnica",44.935299,20.2575,"RS","LYBT","Zemun","no"',
     '4610,"LYBE","large_airport","Belgrade Nikola Tesla",44.818401,20.309099,"RS","LYBE","Belgrade","yes"',
     '1,"LYXX","small_airport","Sportski",44.0,20.0,"RS","LYXX","Anywhere","no"',
     '2,"LHBP","large_airport","Budapest",47.4,19.2,"HU","LHBP","Budapest","yes"',
     '3,"RS-0009","closed_airport","Stari",44.0,20.0,"RS","","Anywhere","no"',
     '4,"LYKV","medium_airport","Morava",43.817519,20.586662,"RS","LYKV","Kraljevo","yes"'])


class AirportsTest(unittest.TestCase):
    def test_large_and_medium_serbian_airports_only(self):
        airports = airports_from_csv(AIRPORTS_CSV + "\n")
        self.assertEqual([a["icao"] for a in airports], ["LYBE", "LYBT", "LYKV"])  # sorted by ICAO
        be = airports[0]
        self.assertEqual((be["type"], be["lon"], be["lat"], be["municipality"], be["scheduled"]),
                         ("large_airport", 20.309099, 44.818401, "Belgrade", True))
        self.assertEqual(airports[1]["scheduled"], False)  # Batajnica: no scheduled service

    def test_jsonstat_series_for_serbian_airports(self):
        data = {"version": "2.0", "class": "dataset", "id": ["freq", "unit", "tra_meas", "rep_airp", "schedule", "tra_cov", "time"],
                "size": [1, 1, 1, 3, 1, 1, 2],
                "dimension": {
                    "freq": {"category": {"index": {"A": 0}}}, "unit": {"category": {"index": {"PAS": 0}}},
                    "tra_meas": {"category": {"index": {"PAS_CRD": 0}}},
                    "rep_airp": {"category": {"index": {"HU_LHBP": 0, "RS_LYBE": 1, "RS_LYNI": 2}}},
                    "schedule": {"category": {"index": {"TOTAL": 0}}}, "tra_cov": {"category": {"index": {"TOTAL": 0}}},
                    "time": {"category": {"index": {"2024": 0, "2025": 1}}}},
                "value": {"0": 5000000, "1": 5200000, "2": 8367395, "3": 8913522, "4": 357313}}
        traffic = passengers_from_jsonstat(data)
        self.assertEqual(traffic, {"LYBE": {2024: 8367395, 2025: 8913522}, "LYNI": {2024: 357313, 2025: None}})

    def test_html_table_of_passengers(self):
        html = ('<html><table><tr><th>GODINA</th><td>2023</td><td>2024</td><td>2025</td></tr>'
                '<tr><td>BROJ PUTNIKA</td><td>13.862</td><td>13.781</td><td>14.713</td></tr>'
                '<tr><td>BROJ AVIONA</td><td>620</td><td>602</td><td>598</td></tr></table></html>')
        self.assertEqual(passengers_from_html(html), {2023: 13862, 2024: 13781, 2025: 14713})
        self.assertEqual(passengers_from_html("<html><p>nema tabele</p></html>", ), {})
        self.assertEqual(passengers_from_html('<table><tr><th>GODINA</th><td>2025</td></tr><tr><td>BROJ PUTNIKA</td><td>-</td></tr></table>'), {})


if __name__ == "__main__":
    unittest.main()
