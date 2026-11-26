"""Wikidata through its public SPARQL endpoint: a query, its saved answer, and what the water source reads from it.

Answers are cached like every download (core.fetch): the manifest of the source that asked is their provenance.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
from pathlib import Path

from .srtext import fold_key

ENDPOINT = "https://query.wikidata.org/sparql"
RATE_LIMIT_RETRIES = 3  # more attempts when the endpoint answers 429 (Too Many Requests)
RATE_LIMIT_WAIT_S = 60.0  # … without a Retry-After header: it then allows one request a minute
RIVER_LENGTHS_FILE = "river_lengths.json"  # the saved answer of RIVER_LENGTHS_SPARQL

# Every river Wikidata places in Serbia (Q403), that is a river (Q4022) and has a length (P2043), with its label in
# Serbian in either script. The length is read as kilometres: so it was in every statement on 2026-11-26, when all of
# them carried the unit "kilometre" (Q828224). The query does not read the unit.
RIVER_LENGTHS_SPARQL = """SELECT ?item ?itemLabel ?len WHERE {
  ?item wdt:P31/wdt:P279* wd:Q4022 ; wdt:P2043 ?len ; wdt:P17 wd:Q403 .
  ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) IN ("sr", "sr-latn", "sr-ec"))
}"""


def query(source, sparql: str, rel_path: str) -> list[dict]:
    """Run `sparql` on Wikidata's endpoint; the answer is cached as data/raw/<source id>/<rel_path>. Returns its bindings.

    The public endpoint answers 429 while it is overloaded. core.fetch retries only 5xx and network errors, so the
    429 is waited out here (Retry-After if it is stated, else a minute) a few times before it is raised.
    """
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'format': 'json', 'query': sparql})}"
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            path = source.download(url, rel_path, headers={"Accept": "application/sparql-results+json"}, expect_binary=True)
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == RATE_LIMIT_RETRIES:
                raise
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            exc.close()
            wait = float(retry_after) if retry_after.isdigit() else RATE_LIMIT_WAIT_S
            print(f"      Wikidata answers 429 (overloaded); asking again in {wait:g}s")
            time.sleep(wait)
    return read_bindings(path)


def read_bindings(path) -> list[dict]:
    """The bindings of a saved answer."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["results"]["bindings"]


def river_lengths(bindings: list[dict]) -> dict[str, tuple[str, float]]:
    """{folded Serbian label: (Q-id, length in km)} from the bindings of RIVER_LENGTHS_SPARQL.

    A label borne by two rivers, or one river whose length is stated twice, gets the longest, so the result does not
    depend on the order the endpoint lists its rows in. The same river is often listed once per script.
    """
    lengths: dict[str, tuple[str, float]] = {}
    for b in bindings:
        key = fold_key(b["itemLabel"]["value"])
        qid, length = b["item"]["value"].rsplit("/", 1)[1], float(b["len"]["value"])
        known = lengths.get(key)
        if known is None or (length, qid) > (known[1], known[0]):
            lengths[key] = (qid, length)
    return lengths


def river_lengths_in_serbia(source) -> dict[str, tuple[str, float]]:
    """river_lengths() for RIVER_LENGTHS_SPARQL, asked once and then always read from the cache."""
    return river_lengths(query(source, RIVER_LENGTHS_SPARQL, RIVER_LENGTHS_FILE))
