"""Reading shapefiles without a GIS stack: pyshp behind two functions that speak this project's shapes.

``records`` yields ``(properties, parts)`` for every record: for a polygon, ``parts`` is a list of rings (outer
rings and holes alike, each a list of ``(lon, lat)``); for a line, a list of lines; for a point, ``[[(lon, lat)]]``.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterator

import shapefile  # pyshp

from .geo import Shape

MEMBERS = (".shp", ".shx", ".dbf")


def open_shapefile(path: Path, member_base: str | None = None) -> shapefile.Reader:
    """A pyshp Reader for a .shp file (with its .shx and .dbf beside it) or for a shapefile inside a zip.

    In a zip, the three members may sit at the top level (Geofabrik) or inside nested zips, one per projection
    (Eurostat). `member_base` names the shapefile without extension and with its path inside the zip, e.g.
    "gis_osm_places_free_1" or "LAU_RG_01M_2024_4326.shp.zip/LAU_RG_01M_2024_4326". Without it, the first complete
    shapefile found is used. Text is decoded as UTF-8.
    """
    path = Path(path)
    if path.suffix.lower() != ".zip":
        return shapefile.Reader(str(path.with_suffix("")), encoding="utf-8")
    with zipfile.ZipFile(path) as zf:
        for found_base, files in _shapefiles_in(zf, ""):
            if member_base is None or found_base == member_base:
                return _reader(files)
    raise FileNotFoundError(f"{path}: no shapefile {member_base!r} inside")


def shapefile_bases(path: Path) -> list[str]:
    """Every shapefile inside a zip, by member base (see open_shapefile)."""
    with zipfile.ZipFile(path) as zf:
        return [base for base, _ in _shapefiles_in(zf, "")]


def records(reader: shapefile.Reader) -> Iterator[tuple[dict, list]]:
    """(properties, parts) for every record that has geometry."""
    for shape, rec in zip(reader.shapes(), reader.records()):
        if shape.points:
            yield dict(rec.as_dict()), parts(shape)


def parts(shape) -> list:
    """A shape's geometry as lists of (lon, lat) points: rings for polygons, lines, one point for points."""
    pts = shape.points
    if not pts:
        return []
    if shape.shapeType in (shapefile.POINT, shapefile.POINTM, shapefile.POINTZ):
        return [[tuple(pts[0])]]
    out, start = [], 0
    for end in list(shape.parts[1:]) + [len(pts)]:
        out.append([tuple(p[:2]) for p in pts[start:end]])
        start = end
    return out


def to_shape(shape) -> Shape:
    """A polygon record as geo.Shape (a bag of rings; even-odd handles holes)."""
    return Shape(parts(shape))


def _shapefiles_in(zf: zipfile.ZipFile, prefix: str) -> Iterator[tuple[str, dict[str, bytes]]]:
    """(member base, {extension: bytes}) for each complete shapefile, descending into nested zips."""
    names = zf.namelist()
    bases = sorted({n[:-4] for n in names if n.lower().endswith(".shp")}
                   & {n[:-4] for n in names if n.lower().endswith(".shx")}
                   & {n[:-4] for n in names if n.lower().endswith(".dbf")})
    for base in bases:
        yield prefix + base, {ext: zf.read(base + ext) for ext in MEMBERS}
    for name in names:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(zf.read(name))) as nested:
                yield from _shapefiles_in(nested, prefix + name + "/")


def _reader(files: dict[str, bytes]) -> shapefile.Reader:
    return shapefile.Reader(
        shp=io.BytesIO(files[".shp"]), shx=io.BytesIO(files[".shx"]), dbf=io.BytesIO(files[".dbf"]), encoding="utf-8"
    )
