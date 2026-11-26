#!/usr/bin/env python3
"""Refresh pipeline/data/rzs_territory.json: the Statistical Office of Serbia's territory tree with codes.

Every source and builder joins on these ids, so the file is committed and refreshed only on purpose:

    uv run python scripts/refresh_territory.py

The dissemination database (data.stat.gov.rs) embeds each dataset's "Teritorija" tree as jsTree nodes in its
result page. Datasets show the tree to different depths, so several pages are merged. Nodes are kept as the
office names them (Serbian Latin); nothing here is typed by hand.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.core import fetch  # noqa: E402
from pipeline.core.store import atomic_write_text  # noqa: E402

SOURCE_ID = "rzs_territory"
# Datasets whose territory trees together reach every level: oblasti incl. Kosovo and Metohija, municipalities,
# city aggregates, settlements.
DATASETS = ["3104020101", "18010602", "1300021101", "18060401", "240205", "2403040403", "18050202", "180304", "18030504", "18030301", "09020404"]
TREE = re.compile(r"\$\('#(agg-\d+)'\)\.jstree\(\{\s*'core':\s*\{\s*'data'\s*:\s*(\[.*?\])\s*,\s*'check_callback'", re.S)


def page(subarea: str) -> str:
    path = fetch.download(SOURCE_ID, f"https://data.stat.gov.rs/Home/Result/{subarea}?languageCode=sr-Latn", f"{subarea}.html", expect_binary=False)
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    nodes: dict[str, dict] = {}
    conflicts: list[str] = []
    for subarea in DATASETS:
        html = page(subarea)
        found = 0
        for m in TREE.finditer(html):
            if m.group(1) != "agg-102":
                continue
            for n in json.loads(m.group(2)):
                nid, text, parent = str(n.get("id")), str(n.get("text") or "").strip(), n.get("parent")
                if parent in ("#", "", None):
                    parent = None
                else:
                    parent = str(parent)
                rec = {"name": text, "parent": parent}
                old = nodes.get(nid)
                if old and old["name"] != text:
                    conflicts.append(f"{nid}: {old} vs {rec} (dataset {subarea})")
                    continue
                if old and parent is None:
                    continue  # a shallower tree shows this node as a root; the deeper tree's parent stands
                nodes[nid] = rec
                found += 1
        print(f"  {subarea}: {found} territory nodes")
        fetch.time.sleep(1.1)
    if conflicts:
        print("\n".join(conflicts[:20]))
        sys.exit("conflicting definitions between datasets; resolve before committing")

    depth: dict[str, int] = {}

    def level(nid: str) -> int:
        if nid not in depth:
            parent = nodes[nid]["parent"]
            depth[nid] = 0 if parent is None else level(parent) + 1
        return depth[nid]

    for nid in nodes:
        nodes[nid]["level"] = level(nid)
    children: dict[str | None, list[str]] = {}
    for nid, rec in nodes.items():
        children.setdefault(rec["parent"], []).append(nid)
    for nid, rec in nodes.items():
        rec["children"] = len(children.get(nid, ()))

    out = {
        "source": "Republicki zavod za statistiku, Diseminaciona baza podataka (data.stat.gov.rs), stablo teritorije",
        "retrieved": date.today().isoformat(),
        "datasets": DATASETS,
        "levels": {0: "Republika Srbija", 1: "Srbija - Sever / Jug", 2: "region (NUTS-2)", 3: "oblast (NUTS-3)",
                   4: "opstina / grad", 5: "gradska opstina", 6: "naselje"},
        "nodes": dict(sorted(nodes.items())),
    }
    dest = ROOT / "pipeline" / "data" / "rzs_territory.json"
    atomic_write_text(dest, json.dumps(out, ensure_ascii=False, indent=1, sort_keys=False) + "\n")
    by_level: dict[int, int] = {}
    for rec in nodes.values():
        by_level[rec["level"]] = by_level.get(rec["level"], 0) + 1
    print(f"wrote {dest.relative_to(ROOT)}: {len(nodes)} nodes; per level: {dict(sorted(by_level.items()))}")


if __name__ == "__main__":
    main()
