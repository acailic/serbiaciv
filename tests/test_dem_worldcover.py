"""sources.copernicus_dem and sources.worldcover: fetching the tiles and warping them onto the lattice."""

import unittest
from pathlib import Path
from unittest import mock

from pipeline.core import fetch, raster, srb
from pipeline.sources import copernicus_dem, worldcover


def dem_url(tile: str) -> str:
    """Copernicus names a 1° tile by degrees and minutes: "N44_E020" is the key N44_00_E020_00."""
    ns, ew = tile.split("_")
    return srb.COPERNICUS_TILE_URL.format(ns=f"{ns}_00", ew=f"{ew}_00")


def worldcover_url(tile: str) -> str:
    return srb.WORLDCOVER_TILE_URL.format(tile=tile)


class FakeNetwork:
    """Stands in for the two things a source's fetch() touches: fetch.url_exists and fetch.download."""

    def __init__(self, existing=()):
        self.existing = set(existing)
        self.checked = []  # urls url_exists was asked about
        self.downloaded = []  # (source id, url, rel_path, keyword arguments)

    def url_exists(self, url):
        self.checked.append(url)
        return url in self.existing

    def download(self, source_id, url, rel_path, **kwargs):
        self.downloaded.append((source_id, url, rel_path, kwargs))
        return Path(rel_path)


def with_network(test: unittest.TestCase, net: FakeNetwork, offline: bool = False) -> None:
    for patcher in (mock.patch.object(fetch, "url_exists", net.url_exists), mock.patch.object(fetch, "download", net.download),
                    mock.patch.object(fetch, "OFFLINE", offline)):
        patcher.start()
        test.addCleanup(patcher.stop)


DEM_TILES = raster.tile_names("dem", srb.BBOX_LONLAT)
WORLDCOVER_TILES = raster.tile_names("worldcover", srb.BBOX_LONLAT)


class FetchCopernicus(unittest.TestCase):
    def test_downloads_every_tile_of_the_box_except_the_one_that_does_not_exist(self):
        net = FakeNetwork({dem_url(t) for t in DEM_TILES} - {dem_url("N41_E018")})
        with_network(self, net)
        copernicus_dem.CopernicusDEM().fetch()
        urls = [url for _, url, _, _ in net.downloaded]
        self.assertEqual(len(urls), 35)
        self.assertEqual(sorted(net.checked), sorted(dem_url(t) for t in DEM_TILES))  # asked about all 36
        self.assertEqual((net.downloaded[0][0], net.downloaded[0][1]), ("dem", dem_url("N41_E019")))
        self.assertEqual(net.downloaded[0][2], "Copernicus_DSM_COG_10_N41_00_E019_00_DEM.tif")  # the remote file's name
        self.assertTrue(all(kw["expect_binary"] for *_, kw in net.downloaded))

    def test_offline_asks_the_server_nothing_and_checks_only_the_tiles_fetched_before(self):
        net = FakeNetwork()
        with_network(self, net, offline=True)
        earlier = "Copernicus_DSM_COG_10_N41_00_E019_00_DEM.tif"  # in the manifest: download() checks the cache
        with mock.patch.object(fetch, "read_manifest", return_value={earlier: {}}):
            copernicus_dem.CopernicusDEM().fetch()
        self.assertEqual(net.checked, [])  # --offline forbids discovery requests
        self.assertEqual([rel for _, _, rel, _ in net.downloaded], [earlier])


class FetchWorldCover(unittest.TestCase):
    def test_downloads_the_six_tiles_of_the_box(self):
        net = FakeNetwork(worldcover_url(t) for t in WORLDCOVER_TILES)
        with_network(self, net)
        worldcover.WorldCover().fetch()
        self.assertEqual(len(WORLDCOVER_TILES), 6)
        self.assertEqual([(sid, url, rel) for sid, url, rel, _ in net.downloaded],
                         [("landcover", worldcover_url(t), f"ESA_WorldCover_10m_2021_v200_{t}_Map.tif") for t in WORLDCOVER_TILES])
        self.assertTrue(all(kw["expect_binary"] for *_, kw in net.downloaded))
        self.assertEqual(net.checked, [])  # every tile exists: nothing to probe


if __name__ == "__main__":
    unittest.main()
