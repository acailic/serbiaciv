"""GeoTIFFs onto the lattice: tile names, the lattice's affine transform and one reprojection helper.

The terrain sources (Copernicus elevation, ESA WorldCover) publish rasters cut into tiles of whole degrees. A source
knows nothing about hexes, so each one only warps its tiles onto ``core.lattice.SERBIA``; the world builder samples
that lattice inside each hex.
"""

from __future__ import annotations

import math

import rasterio
import rasterio.warp
import numpy as np
from rasterio.enums import Resampling
from rasterio.transform import Affine, from_origin

from .lattice import Lattice

# kind → (tile side in degrees, how a tile is named by its south-west corner)
TILES = {"dem": (1, "N{lat:02d}_E{lon:03d}"), "worldcover": (3, "N{lat:02d}E{lon:03d}")}


def tile_names(kind: str, bbox: tuple[float, float, float, float]) -> list[str]:
    """Names of the tiles of `kind` that touch `bbox` (min lon, min lat, max lon, max lat), south to north, west to east.

    Both products tile north and east of Greenwich only, which is all Serbia needs.
    """
    if kind not in TILES:
        raise ValueError(f"unknown tile kind {kind!r}")
    side, fmt = TILES[kind]
    lon_min, lat_min, lon_max, lat_max = bbox
    lats = range(int(lat_min // side) * side, int(lat_max // side) * side + 1, side)
    lons = range(int(lon_min // side) * side, int(lon_max // side) * side + 1, side)
    return [fmt.format(lat=lat, lon=lon) for lat in lats for lon in lons]


def lattice_transform(lat_: Lattice) -> Affine:
    """The lattice as a rasterio transform: its north-west corner is the origin and row 0 is the north."""
    return from_origin(lat_.lon_min, lat_.lat_min + lat_.rows * lat_.step_deg, lat_.step_deg, lat_.step_deg)


def resample(path, lat_: Lattice, *, resampling: Resampling, dtype, nodata, dst: np.ndarray | None = None) -> np.ndarray:
    """Warp one GeoTIFF onto the lattice; `nodata` is the lattice's void value (one that compares equal to itself).

    The returned array is the whole lattice. With ``dst`` (the lattice as earlier tiles left it) only the cells this
    tile holds are written, so a tile's nodata never overwrites another tile's value, and the result does not depend
    on the order the tiles were warped in. Cells no tile covers stay ``nodata``. The tile's own voids are the ones
    its file declares (``src.nodata``).
    """
    fresh = np.full(lat_.shape, nodata, dtype=dtype)
    with rasterio.open(path) as src:
        rasterio.warp.reproject(
            rasterio.band(src, 1), fresh, dst_transform=lattice_transform(lat_), dst_crs=src.crs,
            src_nodata=src.nodata, dst_nodata=nodata, resampling=resampling,
        )
        rows, cols = cells_inside(lat_, src.bounds)
    # The warp reaches one cell beyond the tile's west and north edges and writes an edge value there. Those cells
    # are the neighbours', so everything outside the tile's own cells is dropped before merging.
    inside = np.zeros(lat_.shape, dtype=bool)
    inside[rows, cols] = True
    fresh[~inside] = nodata
    if dst is None:
        return fresh
    np.copyto(dst, fresh, where=fresh != nodata)
    return dst


def cells_inside(lat_: Lattice, bounds: tuple[float, float, float, float]) -> tuple[slice, slice]:
    """The lattice cells whose centres lie inside `bounds` (left, bottom, right, top), as (rows, cols) slices."""
    left, bottom, right, top = bounds
    north = lat_.lat_min + lat_.rows * lat_.step_deg

    def span(from_edge: float, to_edge: float, size: int) -> slice:
        """Cells counted from the lattice's edge whose centres lie between the two bounds (in cells)."""
        first, end = (math.ceil(v - 0.5) for v in (from_edge, to_edge))  # a centre sits half a cell inside its cell
        return slice(max(0, first), min(size, end))

    rows = span((north - top) / lat_.step_deg, (north - bottom) / lat_.step_deg, lat_.rows)  # row 0 is the north
    cols = span((left - lat_.lon_min) / lat_.step_deg, (right - lat_.lon_min) / lat_.step_deg, lat_.cols)
    return rows, cols
