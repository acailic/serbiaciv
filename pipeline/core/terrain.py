"""Select and verify native terrain tiles for the Serbian map.

The 0.1-degree buffer exceeds a 5 km hex radius in both directions over Serbia. A tile touching the buffered
territory is included, so hexes along borders are not silently clipped. Raw cache paths remain relative to RAW.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import bounds as window_bounds

from . import fetch, raster, store
from .geo import Shape
from .geom import clip_segment

BUFFER_DEGREES = 0.1


def _intersects(rings, left, bottom, right, top):
    shape = Shape(rings)
    x0, y0, x1, y1 = shape.bbox
    if x1 < left or x0 > right or y1 < bottom or y0 > top:
        return False
    if any(left <= x <= right and bottom <= y <= top for ring in rings for x, y in ring):
        return True
    if any(shape.contains(x, y) for x, y in ((left, bottom), (left, top), (right, bottom), (right, top))):
        return True
    for ring in rings:
        for a, b in zip(ring, ring[1:] + ring[:1]):
            if clip_segment((a[0] - left, a[1] - bottom), (b[0] - left, b[1] - bottom), right - left, top - bottom):
                return True
    return False


def required_tiles(kind, features, buffer_deg=BUFFER_DEGREES):
    if not features or buffer_deg < 0:
        raise ValueError("terrain tile selection needs territory features and a nonnegative buffer")
    side, _ = raster.TILES[kind]
    points = [p for feature in features for ring in feature["rings"] for p in ring]
    if not points:
        raise ValueError("territory has no polygon points")
    west, south = min(p[0] for p in points) - buffer_deg, min(p[1] for p in points) - buffer_deg
    east, north = max(p[0] for p in points) + buffer_deg, max(p[1] for p in points) + buffer_deg
    west, south = math.nextafter(west, -math.inf), math.nextafter(south, -math.inf)
    result = []
    for tile in raster.tile_names(kind, (west, south, east, north)):
        lat, lon = ((int(tile[1:3]), int(tile[5:8])) if kind == "dem" else (int(tile[1:3]), int(tile[4:7])))
        if any(_intersects(f["rings"], lon - buffer_deg, lat - buffer_deg,
                           lon + side + buffer_deg, lat + side + buffer_deg) for f in features):
            result.append(tile)
    return result


def territory_features():
    """Use processed boundaries when available; on a clean build read the already-fetched raw sources."""
    features = []
    for name in ("boundaries", "kim"):
        try:
            data = store.load_interim(name)
        except FileNotFoundError:
            if name == "boundaries":
                from ..sources.boundaries import Boundaries
                data = Boundaries().process()
            else:
                from ..sources.kim import Kim
                data = Kim().process()
        features.extend(data["oblasti"])
    return features


def verified_tiles(source_id, tile_files):
    manifest = fetch.read_manifest(source_id)
    result = []
    for tile, filename in sorted(tile_files.items()):
        path = fetch.RAW / source_id / filename
        info = manifest.get(filename)
        if not info or not path.is_file():
            raise FileNotFoundError(f"missing cached {source_id} tile {filename}; fetch it before processing")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != info.get("sha256") or path.stat().st_size != info.get("bytes"):
            raise ValueError(f"checksum or size mismatch for {source_id}/{filename}")
        result.append({"id": tile, "path": (Path(source_id) / filename).as_posix(), "sha256": info["sha256"]})
    if not result:
        raise ValueError(f"no {source_id} tiles cover the territory")
    return result


def cell_indices(lon, lat, grid, proj):
    """Vectorized projection and cube rounding, matching HexGrid.cell_at for every pixel centre."""
    a = proj._albers
    lon, lat = np.deg2rad(lon), np.deg2rad(lat)
    rho = 6371.0088 * np.sqrt(a.c - 2 * a.n * np.sin(lat)) / a.n
    theta = a.n * (lon - a.lon0)
    x = rho * np.sin(theta) - proj.min_x + proj.margin
    y = proj.max_y - (a.rho0 - rho * np.cos(theta)) + proj.margin
    q = (np.sqrt(3) / 3 * x - y / 3) / grid.radius
    r = (2 / 3 * y) / grid.radius
    cy = -q - r
    rx, ry, rz = np.floor(q + .5), np.floor(cy + .5), np.floor(r + .5)
    dx, dy, dz = np.abs(rx - q), np.abs(ry - cy), np.abs(rz - r)
    fix_x = (dx > dy) & (dx > dz)
    fix_z = ~fix_x & (dy <= dz)
    rx = np.where(fix_x, -ry - rz, rx).astype(np.int64)
    rz = np.where(fix_z, -rx - ry, rz).astype(np.int64)
    col = rx + (rz - (rz & 1)) // 2
    valid = (col >= 0) & (col < grid.cols) & (rz >= 0) & (rz < grid.rows)
    return np.where(valid, rz * grid.cols + col, -1)


def aggregate_tiles(tiles, grid, proj, owner, water, kind, bounds=None):
    """Stream native WGS84 pixels into land hexes, weighted by spherical pixel area.

    Pixel centres select one hex. Raster nodata is excluded; overlapping tile footprints are rejected so source
    pixels cannot be counted twice. The area weight is dlon * (sin(north) - sin(south)); the common earth-radius
    factor cancels in means and class shares. Optional bounds limit work to the buffered territory.
    """
    if kind not in ("dem", "landcover"):
        raise ValueError(f"unknown terrain kind {kind}")
    if len(owner) != grid.size or len(water) != grid.size:
        raise ValueError("terrain grid ownership arrays have wrong length")
    sizes = grid.size
    areas, totals = np.zeros(sizes), np.zeros(sizes)
    counts = np.zeros(sizes, dtype=np.int64)
    lows, highs = np.full(sizes, np.inf), np.full(sizes, -np.inf)
    categories = {}
    land = (np.asarray(owner) >= 0) & (np.asarray(water) == 0)
    footprints = []
    cache_root = fetch.RAW.resolve()
    for tile in tiles:
        path = (cache_root / tile["path"]).resolve()
        if not path.is_relative_to(cache_root) or not path.is_file():
            raise FileNotFoundError(f"missing or unsafe terrain tile {tile['path']}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != tile["sha256"]:
            raise ValueError(f"checksum mismatch for {tile['path']}")
        with rasterio.open(path) as src:
            transform = src.transform
            if src.crs is None or src.crs.to_epsg() != 4326 or transform.b or transform.d or transform.a <= 0 or transform.e >= 0:
                raise ValueError(f"unsupported raster projection or transform: {tile['path']}")
            left, bottom, right, top = src.bounds
            for prev in footprints:
                if min(right, prev[2]) - max(left, prev[0]) > 1e-10 and min(top, prev[3]) - max(bottom, prev[1]) > 1e-10:
                    raise ValueError(f"overlap between terrain tiles at {tile['path']}")
            footprints.append((left, bottom, right, top))
            for _, window in src.block_windows(1):
                if bounds:
                    w, s, e, n = window_bounds(window, transform)
                    if e <= bounds[0] or w >= bounds[2] or n <= bounds[1] or s >= bounds[3]:
                        continue
                raster_data = src.read(1, window=window, masked=True)
                valid = ~np.ma.getmaskarray(raster_data)
                valid &= np.isfinite(raster_data.data)
                if not valid.any():
                    continue
                rows = np.arange(int(window.row_off), int(window.row_off + window.height))
                cols = np.arange(int(window.col_off), int(window.col_off + window.width))
                lat = transform.f + (rows + .5) * transform.e
                lon = transform.c + (cols + .5) * transform.a
                indices = cell_indices(lon[None, :], lat[:, None], grid, proj)
                valid &= indices >= 0
                valid &= land[np.maximum(indices, 0)]
                if bounds:
                    valid &= (lat[:, None] >= bounds[1]) & (lat[:, None] <= bounds[3])
                    valid &= (lon[None, :] >= bounds[0]) & (lon[None, :] <= bounds[2])
                if not valid.any():
                    continue
                row, col = np.nonzero(valid)
                idx = indices[row, col]
                values = np.asarray(raster_data.data)[row, col]
                lat_rad = np.deg2rad(lat[row])
                half_step = np.deg2rad(-transform.e / 2)
                weight = np.deg2rad(transform.a) * (np.sin(lat_rad + half_step) - np.sin(lat_rad - half_step))
                areas += np.bincount(idx, weights=weight, minlength=sizes)
                counts += np.bincount(idx, minlength=sizes)
                if kind == "dem":
                    totals += np.bincount(idx, weights=weight * values, minlength=sizes)
                    np.minimum.at(lows, idx, values)
                    np.maximum.at(highs, idx, values)
                else:
                    for value in np.unique(values):
                        selected = values == value
                        cat = categories.setdefault(int(value), np.zeros(sizes))
                        cat += np.bincount(idx[selected], weights=weight[selected], minlength=sizes)
    if kind == "dem":
        return {"count": counts, "area": areas, "weighted_sum": totals, "min": lows, "max": highs}
    classes = [{code: values[i] for code, values in categories.items() if values[i] > 0} for i in range(sizes)]
    return {"count": counts, "area": areas, "classes": classes}
