"""core.wikidata: running one SPARQL query and reading river lengths out of its response."""

import contextlib
import io
import json
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest import mock

from pipeline.core import wikidata

RESPONSE = Path(__file__).parent / "fixtures" / "wikidata_river_lengths.json"  # recorded from the endpoint
BINDINGS = json.loads(RESPONSE.read_text(encoding="utf-8"))["results"]["bindings"]
ONE_QUERY = "SELECT ?a WHERE {}"


def binding(qid: str, label: str, length: str) -> dict:
    return {"item": {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"},
            "itemLabel": {"xml:lang": "sr", "type": "literal", "value": label},
            "len": {"datatype": "http://www.w3.org/2001/XMLSchema#decimal", "type": "literal", "value": length}}


class FakeSource:
    """Stands in for a Source: its download() only records what it is asked for and hands over a saved file."""

    id = "water"

    def __init__(self, path: Path):
        self.path, self.calls = path, []

    def download(self, url, rel_path, **kwargs):
        self.calls.append((url, rel_path, kwargs))
        return self.path


class RateLimited:
    """Stands in for a Source whose endpoint answers 429 `times` times before letting the request through."""

    def __init__(self, path: Path, times: int, retry_after: str | None = None):
        self.path, self.left, self.calls = path, times, []
        self.headers = Message()
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after

    def download(self, url, rel_path, **kwargs):
        self.calls.append(url)
        if self.left:
            self.left -= 1
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", self.headers, None)
        return self.path


def answered(source) -> list:
    """query() the source with the waiting (and the line printed about it) recorded instead of done."""
    with contextlib.redirect_stdout(io.StringIO()) as out, mock.patch.object(wikidata.time, "sleep") as sleep:
        bindings = wikidata.query(source, ONE_QUERY, "q.json")
    return bindings, [call.args[0] for call in sleep.call_args_list], out.getvalue()


class Query(unittest.TestCase):
    def test_asks_the_endpoint_for_the_query_and_returns_the_bindings(self):
        source = FakeSource(RESPONSE)
        sparql = 'SELECT ?a WHERE { ?a wdt:P17 wd:Q403 . FILTER(LANG(?a) IN ("sr")) }'
        self.assertEqual(wikidata.query(source, sparql, "q.json"), BINDINGS)
        ((url, rel_path, kwargs),) = source.calls
        self.assertEqual((rel_path, kwargs["expect_binary"]), ("q.json", True))
        self.assertEqual(kwargs["headers"], {"Accept": "application/sparql-results+json"})
        parts = urlsplit(url)
        self.assertEqual((parts.scheme, parts.netloc, parts.path), ("https", "query.wikidata.org", "/sparql"))
        self.assertEqual(parse_qs(parts.query), {"format": ["json"], "query": [sparql]})  # safely encoded
        self.assertNotIn(" ", url)


class RateLimit(unittest.TestCase):
    """The public endpoint answers 429, allowing one request a minute, while it is overloaded."""

    def test_waits_a_minute_and_asks_again(self):
        bindings, waits, out = answered(RateLimited(RESPONSE, times=2))
        self.assertEqual(bindings, BINDINGS)
        self.assertEqual(waits, [60.0, 60.0])
        self.assertIn("429", out)

    def test_honours_retry_after(self):
        _, waits, _ = answered(RateLimited(RESPONSE, times=1, retry_after="7"))
        self.assertEqual(waits, [7.0])

    def test_gives_up_after_a_few_waits(self):
        source = RateLimited(RESPONSE, times=99)
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(wikidata.time, "sleep"), \
                self.assertRaises(urllib.error.HTTPError) as raised:
            wikidata.query(source, ONE_QUERY, "q.json")
        self.assertEqual(raised.exception.code, 429)
        self.assertEqual(len(source.calls), wikidata.RATE_LIMIT_RETRIES + 1)

    def test_other_errors_are_left_to_core_fetch(self):
        unavailable = urllib.error.HTTPError("https://query.wikidata.org/sparql", 503, "Service Unavailable", None, None)
        source = FakeSource(RESPONSE)
        with mock.patch.object(source, "download", side_effect=unavailable) as download, \
                self.assertRaises(urllib.error.HTTPError):
            wikidata.query(source, ONE_QUERY, "q.json")
        self.assertEqual(download.call_count, 1)  # 5xx are retried by core.fetch: not a second time here


class ReadBindings(unittest.TestCase):
    def test_a_saved_response_gives_the_same_bindings_as_the_endpoint(self):
        self.assertEqual(wikidata.read_bindings(RESPONSE), BINDINGS)


class RiverLengths(unittest.TestCase):
    def test_the_recorded_response(self):
        source = FakeSource(RESPONSE)
        lengths = wikidata.river_lengths_in_serbia(source)
        ((url, rel_path, _),) = source.calls
        self.assertEqual(parse_qs(urlsplit(url).query)["query"], [wikidata.RIVER_LENGTHS_SPARQL])
        self.assertEqual(rel_path, "river_lengths.json")
        self.assertEqual(lengths["dunav"], ("Q1653", 2850.0))  # the interim's example
        self.assertEqual(lengths["sava"], ("Q14383", 945.0))
        self.assertEqual(lengths["velika morava"], ("Q211328", 185.0))
        self.assertEqual(lengths["tisa"], ("Q134350", 966.0))  # listed in sr and in sr-ec: one entry
        self.assertEqual(len(lengths), 108)  # 157 bindings, 111 rivers, three names borne by two rivers each
        self.assertEqual(wikidata.river_lengths(wikidata.read_bindings(RESPONSE)), lengths)

    def test_the_query_is_the_one_agreed(self):
        self.assertEqual(
            " ".join(wikidata.RIVER_LENGTHS_SPARQL.split()),
            'SELECT ?item ?itemLabel ?len WHERE { ?item wdt:P31/wdt:P279* wd:Q4022 ; wdt:P2043 ?len ; wdt:P17 wd:Q403 . '
            '?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) IN ("sr", "sr-latn", "sr-ec")) }',
        )

    def test_a_name_borne_by_two_rivers_takes_the_longer_one(self):
        lengths = wikidata.river_lengths_in_serbia(FakeSource(RESPONSE))
        self.assertEqual(lengths["jablanica"], ("Q1288026", 85.0))  # the other Jablanica (Q1632229) is 24 km
        self.assertEqual(lengths["rzav"], ("Q2060975", 72.0))
        self.assertEqual(lengths["pusta reka"], ("Q2563343", 71.0))

    def test_a_river_with_several_lengths_stated_takes_the_longest(self):
        lengths = wikidata.river_lengths_in_serbia(FakeSource(RESPONSE))
        self.assertEqual(lengths["gaberska reka"], ("Q12275890", 36.0))  # Wikidata states 36, 5.3 and 30.7

    def test_both_scripts_fold_to_one_key(self):
        lengths = wikidata.river_lengths([binding("Q1653", "Dunav", "2850"), binding("Q1653", "Дунав", "2850"),
                                          binding("Q37740", "Morava", "293"), binding("Q37740", "Морава", "293")])
        self.assertEqual(lengths, {"dunav": ("Q1653", 2850.0), "morava": ("Q37740", 293.0)})

    def test_the_order_of_the_response_does_not_matter(self):
        rows = [binding("Q1", "Reka", "10"), binding("Q2", "Река", "10"), binding("Q3", "Река", "90.5")]
        self.assertEqual(wikidata.river_lengths(rows), wikidata.river_lengths(rows[::-1]))
        self.assertEqual(wikidata.river_lengths(rows), {"reka": ("Q3", 90.5)})


if __name__ == "__main__":
    unittest.main()
