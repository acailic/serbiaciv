"""sources.water: fetching the extracts, and joining OSM rivers and lakes into the interim."""

import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest import mock

from pipeline.core import fetch, srb, wikidata
from pipeline.sources import water

RESPONSE = Path(__file__).parent / "fixtures" / "wikidata_river_lengths.json"  # recorded from the endpoint


class FakeNetwork:
    """Stands in for the two things a source's fetch() touches: fetch.url_exists and fetch.download."""

    def __init__(self):
        self.downloaded = []  # (source id, url, rel_path, keyword arguments)

    def download(self, source_id, url, rel_path, **kwargs):
        self.downloaded.append((source_id, url, rel_path, kwargs))
        return RESPONSE  # what a download returns: the path of the file it saved


def use_network(test: unittest.TestCase, net: FakeNetwork) -> None:
    for target, replacement in (("download", net.download), ("url_exists", lambda url: True)):
        patcher = mock.patch.object(fetch, target, replacement)
        patcher.start()
        test.addCleanup(patcher.stop)


class FetchWater(unittest.TestCase):
    def test_downloads_both_extracts_and_the_river_lengths(self):
        net = FakeNetwork()
        use_network(self, net)
        water.Water().fetch()
        self.assertEqual([(sid, url, rel) for sid, url, rel, _ in net.downloaded], [
            ("water", srb.GEOFABRIK_URL.format(region="serbia"), "serbia-latest-free.shp.zip"),
            ("water", srb.GEOFABRIK_URL.format(region="kosovo"), "kosovo-latest-free.shp.zip"),
            ("water", mock.ANY, "river_lengths.json"),
        ])
        sparql = urlsplit(net.downloaded[2][1])
        self.assertEqual((sparql.scheme, sparql.netloc, sparql.path), ("https", "query.wikidata.org", "/sparql"))
        self.assertEqual(parse_qs(sparql.query), {"format": ["json"], "query": [wikidata.RIVER_LENGTHS_SPARQL]})
        self.assertTrue(all(kw["expect_binary"] for *_, kw in net.downloaded))

    def test_force_asks_wikidata_again_too(self):
        net = FakeNetwork()
        use_network(self, net)
        with mock.patch.object(water.Water, "discard", autospec=True) as discard:
            water.Water().fetch(force=True)
        self.assertEqual([kw["force"] for *_, kw in net.downloaded], [True, True, False])  # the extracts anew
        self.assertEqual(discard.call_args.args[1], "river_lengths.json")  # … and the saved answer forgotten, so it is asked again
        self.assertEqual(len(net.downloaded), 3)

    def test_processes_named_water_and_deduplicates_shared_extracts(self):
        river = ({"osm_id": "1", "fclass": "river", "name": "Дунав"}, [[(20.0, 44.0), (21.0, 44.0)]])
        clipped = ({"osm_id": "1", "fclass": "river", "name": "Дунав"}, [[(21.0, 44.0), (21.1, 44.0)]])
        lake = ({"osm_id": "2", "name": "Језеро"}, [[(20, 44), (20.2, 44), (20.2, 44.2), (20, 44.2), (20, 44)]])
        result = water.water_from_records([river, river, clipped], [lake, lake], {"dunav": ("Q1653", 2850.0)})
        self.assertEqual(len(result["rivers"]), 1)
        self.assertEqual(len(result["rivers"][0]["lines"]), 2)
        self.assertEqual((result["rivers"][0]["name_lat"], result["rivers"][0]["wikidata"]), ("Dunav", "Q1653"))
        self.assertEqual(len(result["lakes"]), 1)
        self.assertGreater(result["lakes"][0]["area_km2"], srb.LAKE_MIN_KM2)


if __name__ == "__main__":
    unittest.main()
