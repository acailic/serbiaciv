"""ESA WorldCover: Serbia's land cover on the shared lattice, as the publisher's classes."""

from __future__ import annotations

from ..core import raster, srb, terrain
from ..core.source import Source, SourceInfo


def tile_file(tile: str) -> str:
    """The tile as ESA stores it, under the same name it has in its address."""
    return srb.WORLDCOVER_TILE_URL.format(tile=tile).rsplit("/", 1)[1]


class WorldCover(Source):
    info = SourceInfo(
        id="landcover",
        title="ESA WorldCover 2021, pokrov zemljišta (10 m)",
        publisher="ESA, Evropska svemirska agencija",
        homepage="https://esa-worldcover.org/",
        license="CC BY 4.0",
        description="Pokrov zemljišta Srbije na 10 m (šume, njive, livade i pašnjaci, gradsko zemljište, vode), "
                    "obrađen iz izvornih piksela za svaki heks.",
        used_for=["Teren"],
    )

    def fetch(self, force: bool = False) -> None:
        """Download the six 3° tiles that touch Serbia's bounding box (the lattice lies inside them)."""
        for tile in raster.tile_names("worldcover", srb.BBOX_LONLAT):
            url = srb.WORLDCOVER_TILE_URL.format(tile=tile)
            self.download(url, tile_file(tile), force=force, expect_binary=True)

    def process(self) -> dict:
        selected = terrain.required_tiles("worldcover", terrain.territory_features())
        files = {tile: tile_file(tile) for tile in selected}
        tiles = terrain.verified_tiles(self.id, files)
        legend = {"10": "Tree cover", "20": "Shrubland", "30": "Grassland", "40": "Cropland",
                  "50": "Built-up", "60": "Bare/sparse vegetation", "70": "Snow and ice",
                  "80": "Permanent water", "90": "Herbaceous wetland", "95": "Mangroves", "100": "Moss and lichen"}
        return {"vintage": "ESA WorldCover 2021 v200", "tiles": tiles, "legend": legend, "_files": list(files.values())}
