"""sources.places: fetching Serbia's extract and reading its named settlements."""

import unittest
from pathlib import Path
from unittest import mock

from pipeline.core import fetch, srb
from pipeline.sources import places


class FakeNetwork:
    """Stands in for fetch.download: records what it is asked for."""

    def __init__(self):
        self.downloaded = []  # (source id, url, rel_path, keyword arguments)

    def download(self, source_id, url, rel_path, **kwargs):
        self.downloaded.append((source_id, url, rel_path, kwargs))
        return Path(rel_path)


class FetchPlaces(unittest.TestCase):
    def test_downloads_the_serbia_extract_only(self):
        net = FakeNetwork()
        with mock.patch.object(fetch, "download", net.download):
            places.Places().fetch()
        self.assertEqual([(sid, url, rel) for sid, url, rel, _ in net.downloaded],
                         [("places", srb.GEOFABRIK_URL.format(region="serbia"), "serbia-latest-free.shp.zip")])
        self.assertTrue(net.downloaded[0][3]["expect_binary"])

    def test_processes_named_cities_towns_and_villages(self):
        rows = [
            ({"name": "Ниш", "fclass": "city", "population": "183164"}, [[(21.9, 43.3)]]),
            ({"name": "Без броја", "fclass": "village", "population": ""}, [[(20, 44)]]),
            ({"name": "Farm", "fclass": "farm"}, [[(20, 44)]]),
            ({"name": "", "fclass": "town"}, [[(20, 44)]]),
        ]
        self.assertEqual(places.places_from_records(rows), [
            {"name": "Ниш", "name_lat": "Niš", "fclass": "city", "population": 183164, "lon": 21.9, "lat": 43.3},
            {"name": "Без броја", "name_lat": "Bez broja", "fclass": "village", "population": None, "lon": 20, "lat": 44},
        ])


if __name__ == "__main__":
    unittest.main()
