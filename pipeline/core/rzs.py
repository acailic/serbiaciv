"""The client for the Statistical Office's dissemination database (data.stat.gov.rs).

The office publishes a dataset as a "result page": an HTML page that embeds the dataset's
dimensions (territory, period, sex…) as jsTree nodes and its indicators as checkboxes. The page
itself shows a default selection only. The table asked for is a POST to Home/DisplayResult with
the selected node ids in `uriQuery`; the answer is a JSON list of flat records, one per cell:

    {"IDIndikator": "18030302IND01", "IDTer": "RS11 ", "nPol": "Muško", "God+Mes": "202300", "Vrednost": "3220916", …}

    ds = rzs.load_dataset("18010602")   # the result page, parsed; cached under pages/
    rzs.export(ds, {"indicators": ds.indicators, "agg-102": ["70017"], "agg-2": ["202500"]}, "example.json")

Ids and values arrive as the office writes them: "IDTer" padded with spaces, "Vrednost" a string.
value() and unit_id() clean a record. Every request that is not served from the cache waits
PAUSE seconds first: the office asks for at most one request a second.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from . import fetch
from .srb import RZS_EXPORT_URL, RZS_RESULT_URL

SOURCE_ID = "rzs_db"  # pages and exports are cached in data/raw/rzs_db/, the rzs_db source's folder
PAUSE = 1.1  # seconds

_TREE = re.compile(r"\$\('#(agg-\d+)'\)\.jstree\(\{\s*'core':\s*\{\s*'data'\s*:\s*(\[.*?\])\s*,\s*'check_callback'", re.S)
# the <label> of a checkbox: its control id ("cbAggT-102" for a dimension's box, "…IND01" for an indicator)
_LABEL = re.compile(r'<label\b[^>]*\bfor="([^"]+)"[^>]*>(.*?)</label>', re.S)
_TAG = re.compile(r"<[^>]+>")
_INDICATOR_ID = re.compile(r"\d+IND\d+$")


@dataclass(frozen=True)
class Node:
    """A node of a dimension tree: an id to select, the text the page shows, and its parent (None for a root)."""

    id: str
    text: str
    parent: str | None


@dataclass(frozen=True)
class Dataset:
    """One dataset of the database, as its result page describes it.

    dims:        "agg-102" → every node of that dimension's tree, parents before children
    labels:      "agg-102" → the title of the dimension's box on the page ("Teritorija - NSTJ")
    indicators:  the ids of the dataset's indicators ("18030302IND01")
    """

    subarea: str
    dims: dict[str, tuple[Node, ...]]
    labels: dict[str, str]
    indicators: tuple[str, ...]

    def find(self, dim: str, text: str) -> list[str]:
        """Ids of the nodes of dimension `dim` whose text contains `text`, case-insensitive; LookupError when none."""
        wanted = text.casefold()
        hits = [n.id for n in self.dims[dim] if wanted in n.text.casefold()]
        if not hits:
            raise LookupError(f"{self.subarea} {dim} ({self.labels.get(dim, '?')}) has no node containing {text!r}")
        return hits

    def children(self, dim: str, parent: str | None) -> list[str]:
        """Ids of the nodes of dimension `dim` directly under `parent` (None: the roots), in tree order."""
        return [n.id for n in self.dims[dim] if n.parent == parent]

    def leaves(self, dim: str) -> list[str]:
        """Ids of the nodes of dimension `dim` that have no children, in tree order."""
        parents = {n.parent for n in self.dims[dim]}
        return [n.id for n in self.dims[dim] if n.id not in parents]


def parse_dataset(html: str, subarea: str) -> Dataset:
    """The dimension trees, their titles and the indicators that the result page `html` of dataset `subarea` embeds."""
    dims = {}
    for m in _TREE.finditer(html):
        dims[m.group(1)] = tuple(_parents_first([_node(n) for n in json.loads(m.group(2))]))
    labels: dict[str, str] = {}
    indicators: list[str] = []
    for m in _LABEL.finditer(html):
        control, text = m.group(1), " ".join(_TAG.sub(" ", m.group(2)).split())
        if control.startswith("cbAggT-"):
            labels[f"agg-{control[len('cbAggT-'):]}"] = text
        elif _INDICATOR_ID.fullmatch(control):
            indicators.append(control)
    return Dataset(subarea, dims, labels, tuple(indicators))


def _node(rec: dict) -> Node:
    parent = rec.get("parent")
    return Node(str(rec["id"]), str(rec.get("text") or "").strip(), None if parent in ("#", "", None) else str(parent))


def _parents_first(nodes: list[Node]) -> list[Node]:
    """`nodes` in the page's order, except that a node listed before its parent comes after it."""
    ids = {n.id for n in nodes}
    out: list[Node] = []
    placed: set[str] = set()
    waiting = list(nodes)
    while waiting:
        moved = False
        rest = []
        for n in waiting:
            if n.parent in ids and n.parent not in placed:
                rest.append(n)  # its parent is still waiting: this node goes after it
            else:
                out.append(n)
                placed.add(n.id)
                moved = True
        if not moved:
            break  # a cycle: keep the page's order for what is left
        waiting = rest
    return out + waiting


def query(selection: dict[str, list[str]]) -> str:
    """The `uriQuery` of an export: the selected ids as `key=id,id&key=id`, keys in the order given."""
    return "&".join(f"{key}={','.join(ids)}" for key, ids in selection.items())


def value(rec: dict) -> float | None:
    """The record's Vrednost as a number; None when the office has none ("…", "-", empty, missing)."""
    raw = rec.get("Vrednost")
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).replace(" ", "").replace("\N{NO-BREAK SPACE}", ""))
    except ValueError:
        return None


def unit_id(rec: dict) -> str:
    """The record's territory id without the padding the office adds ("70017 " → "70017")."""
    return str(rec.get("IDTer", "")).strip()


def _pause(rel_path: str, force: bool) -> None:
    """Wait before a request that will really go out: the office asks for at most one a second."""
    if not fetch.OFFLINE and (force or not (fetch.RAW / SOURCE_ID / rel_path).exists()):
        time.sleep(PAUSE)


def load_dataset(subarea: str, *, force: bool = False) -> Dataset:
    """Dataset `subarea` of the database. Its result page is cached at data/raw/rzs_db/pages/<subarea>.html."""
    rel_path = f"pages/{subarea}.html"
    _pause(rel_path, force)
    page = fetch.download(SOURCE_ID, RZS_RESULT_URL.format(subarea=subarea), rel_path, force=force)
    return parse_dataset(page.read_text(encoding="utf-8", errors="replace"), subarea)


def export(ds: Dataset, selection: dict[str, list[str]], rel_path: str, *, force: bool = False) -> list[dict]:
    """The records the office answers to `selection` in dataset `ds`, cached at data/raw/rzs_db/<rel_path>.

    A body that is not a JSON list (an error page, an empty answer) raises UnexpectedContentError
    and is discarded, so that the next run asks again.
    """
    def read_records(path):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise fetch.UnexpectedContentError(f"{ds.subarea} → {rel_path}: the office's answer is not JSON ({exc})") from exc
        if not isinstance(records, list):
            raise fetch.UnexpectedContentError(
                f"{ds.subarea} → {rel_path}: the office's answer is not a list of records but {type(records).__name__}")
        return records

    _pause(rel_path, force)
    path = fetch.post(
        SOURCE_ID,
        RZS_EXPORT_URL,
        {
            "languageCode": "sr-Latn",
            "displayMode": "exportJSON",
            "subAreaId": ds.subarea,
            "resultDisplayType": "Title",
            "uriQuery": query(selection),
        },
        rel_path,
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": RZS_RESULT_URL.format(subarea=ds.subarea)},
        force=force,
        validate=read_records,
    )
    try:
        return read_records(path)
    except fetch.UnexpectedContentError:
        # Only an already-cached file can reach here: new responses are validated before replacement.
        fetch.discard(SOURCE_ID, rel_path)
        raise
