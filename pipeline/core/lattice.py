"""The square lon/lat lattice on which the terrain sources publish rasters as compact interim JSON.

A "source knows nothing about hexes" (upstream's rule), so the elevation and land-cover sources do not compute
per-hex values. They resample their rasters onto this one lattice; the world builder samples the lattice inside
each hex. The lattice is 10 arc-seconds (about 222 m east–west × 310 m north–south at Serbia's latitude) over Serbia's bounding box with
a small buffer, so every Serbian hex is covered and nothing outside it is stored twice.

Both sides go through this module: the sources encode with ``Lattice.encode``, the builder decodes with
``Lattice.decode`` and reads with ``Lattice.value``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import numpy as np

LON_MIN, LON_MAX = 18.6, 23.4
LAT_MIN, LAT_MAX = 41.6, 46.4
STEP_DEG = 1 / 360  # 10 arc-seconds
ELEV_NODATA: np.int16 = np.int16(-32768)
CLASS_NODATA: np.uint8 = np.uint8(0)


@dataclass(frozen=True)
class Lattice:
    """``cell(c, r)`` has its centre at lon_min + (c + 0.5) · step, lat_min + (rows − r − 0.5) · step: row 0 is north."""

    lon_min: float
    lat_min: float
    step_deg: float
    cols: int
    rows: int

    @classmethod
    def serbia(cls) -> "Lattice":
        return cls(LON_MIN, LAT_MIN, STEP_DEG, round((LON_MAX - LON_MIN) / STEP_DEG), round((LAT_MAX - LAT_MIN) / STEP_DEG))

    @classmethod
    def from_dict(cls, d: dict) -> "Lattice":
        return cls(float(d["lon_min"]), float(d["lat_min"]), float(d["step_deg"]), int(d["cols"]), int(d["rows"]))

    def to_dict(self) -> dict:
        return {"lon_min": self.lon_min, "lat_min": self.lat_min, "step_deg": self.step_deg, "cols": self.cols, "rows": self.rows}

    @property
    def shape(self) -> tuple[int, int]:
        return self.rows, self.cols

    def cell(self, lon: float, lat: float) -> tuple[int, int] | None:
        """The (col, row) whose cell contains the point, or None when it is outside the lattice."""
        c = int(np.floor((lon - self.lon_min) / self.step_deg))
        r = int(np.floor((self.lat_min + self.rows * self.step_deg - lat) / self.step_deg))
        return (c, r) if 0 <= c < self.cols and 0 <= r < self.rows else None

    def centre(self, col: int, row: int) -> tuple[float, float]:
        return (self.lon_min + (col + 0.5) * self.step_deg, self.lat_min + (self.rows - row - 0.5) * self.step_deg)

    @staticmethod
    def encode(arr: np.ndarray) -> str:
        """Base64 of the array's little-endian bytes, row-major from the north."""
        return base64.b64encode(np.ascontiguousarray(arr).astype(arr.dtype.newbyteorder("<")).tobytes()).decode("ascii")

    @staticmethod
    def decode(text: str, dtype: Any, shape: tuple[int, int]) -> np.ndarray:
        raw = np.frombuffer(base64.b64decode(text), dtype=np.dtype(dtype).newbyteorder("<"))
        if raw.size != shape[0] * shape[1]:
            raise ValueError(f"lattice data holds {raw.size} values, expected {shape[0] * shape[1]}")
        return raw.reshape(shape)

    def value(self, arr: np.ndarray, lon: float, lat: float, nodata: Any) -> Any:
        """The lattice value at a point (nearest cell), or `nodata` outside the lattice."""
        pos = self.cell(lon, lat)
        return nodata if pos is None else arr[pos[1], pos[0]]


SERBIA = Lattice.serbia()
