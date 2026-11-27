"""Copernicus GLO-10: Serbia's elevation on the shared lattice, as whole metres.

The tiles are the 1-arc-second `Copernicus_DSM_COG_10` COGs (3600 × 3600 pixels a degree), i.e. the 10 m product;
the port labelled them GLO-30 until a review measured the pixels.
"""

from __future__ import annotations

from ..core import fetch, raster, srb, terrain
from ..core.source import Source, SourceInfo


def tile_url(tile: str) -> str:
    """Where Copernicus keeps `tile` ("N44_E020"): its keys are written in degrees and minutes ("N44_00_E020_00")."""
    ns, ew = tile.split("_")
    return srb.COPERNICUS_TILE_URL.format(ns=f"{ns}_00", ew=f"{ew}_00")


class CopernicusDEM(Source):
    info = SourceInfo(
        id="dem",
        title="Copernicus GLO-10, digitalni model reliefa (10 m)",
        publisher="Copernicus, program Evropske unije",
        homepage="https://spacedata.copernicus.eu/c/copernicus-dem/",
        license="Besplatno korišćenje uz navođenje izvora (Copernicus)",
        description="Nadmorska visina Srbije na 10 m; izvorni pikseli koriste se za teren svakog heksa.",
        used_for=["Teren"],
    )

    def fetch(self, force: bool = False) -> None:
        """Download the tiles that touch Serbia's bounding box (the lattice lies inside them).

        The model has no tile for the box's south-west corner (N41_E018), so every tile is probed first. Under
        --offline the server cannot be asked which tiles exist: only the tiles the manifest recorded as fetched are
        then checked against the cache.
        """
        fetched_before = fetch.read_manifest(self.id) if self.offline else ()
        for tile in raster.tile_names("dem", srb.BBOX_LONLAT):
            url = tile_url(tile)
            rel_path = url.rsplit("/", 1)[1]  # the file keeps the name Copernicus gave it
            if not self.offline and not fetch.url_exists(url):
                continue
            if self.offline and rel_path not in fetched_before:
                continue
            self.download(url, rel_path, force=force, expect_binary=True)

    def process(self) -> dict:
        selected = terrain.required_tiles("dem", terrain.territory_features())
        files = {tile: tile_url(tile).rsplit("/", 1)[1] for tile in selected}
        tiles = terrain.verified_tiles(self.id, files)
        return {"vintage": "Copernicus DEM GLO-10", "tiles": tiles, "_files": list(files.values())}
