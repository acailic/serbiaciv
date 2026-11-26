"""JSON-stat 2.0, the format of Eurostat's statistics API.

A dataset is a cube described sparsely: ``id`` and ``size`` name the dimensions and their lengths, each dimension's
``category.index`` maps a category id to its position, and ``value`` (with the optional ``status``) is keyed by the
flat index, which counts the last dimension fastest. A missing key is a cell without data. ``parse`` returns one dict
per cell of the cube, so sources can work with plain rows and never see an index.
"""

from __future__ import annotations

import math


def parse(doc: dict) -> list[dict]:
    """Every cell of a JSON-stat 2.0 dataset, in flat-index order:
    ``{<dim>: <category id>, …, "value": number | None, "status": str | None}``.

    A cell the dataset holds no value for gets ``value=None`` (no data is never a number); a value published
    without a status gets ``status=None``.
    """
    dims, sizes = doc["id"], doc["size"]
    categories = [_by_position(doc["dimension"][d]["category"]["index"]) for d in dims]
    values, statuses = doc["value"], doc.get("status") or {}
    cells = []
    for flat in range(math.prod(sizes)):
        cell = {d: cats[pos] for d, cats, pos in zip(dims, categories, _positions(flat, sizes))}
        cell["value"] = values.get(str(flat))
        cell["status"] = statuses.get(str(flat))
        cells.append(cell)
    return cells


def _by_position(index: dict) -> list:
    """The category ids of one dimension, in index position (Eurostat sorts them, it does not echo the request)."""
    return sorted(index, key=index.__getitem__)


def _positions(flat: int, sizes: list) -> list[int]:
    """The category position of each dimension for a flat index; the last dimension counts fastest."""
    out = []
    for size in reversed(sizes):
        flat, pos = divmod(flat, size)
        out.append(pos)
    return out[::-1]
