"""core.rzs and fetch.post: the client for the Statistical Office's dissemination database."""

import http.server
import json
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from pipeline.core import fetch, rzs


class PostTest(unittest.TestCase):
    def setUp(self):
        # _download_with prints its progress; keep the suite's output clean, as test_fetch.py does per call.
        quieter = mock.patch("builtins.print")
        quieter.start()
        self.addCleanup(quieter.stop)

    def test_post_caches_and_records_provenance(self):
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, self.rfile.read(int(self.headers["Content-Length"])).decode(), self.headers.get("User-Agent")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'[{"Vrednost": "1"}]')

            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/Home/DisplayResult"
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fetch, "RAW", Path(tmp)):
                p = fetch.post("rzs_db", url, {"a": "1"}, "t.json", timeout=5)
                self.assertEqual(json.loads(p.read_text()), [{"Vrednost": "1"}])
                self.assertEqual(seen[0][2], fetch.USER_AGENT)
                self.assertIn("a=1", seen[0][1])
                fetch.post("rzs_db", url, {"a": "1"}, "t.json", timeout=5)
                self.assertEqual(len(seen), 1)  # the second call read the cache
                self.assertEqual(fetch.read_manifest("rzs_db")["t.json"]["bytes"], p.stat().st_size)
                fetch.OFFLINE = True
                try:
                    with self.assertRaises(fetch.OfflineError):
                        fetch.post("rzs_db", url, {"a": "1"}, "missing.json", timeout=5)
                finally:
                    fetch.OFFLINE = False
        finally:
            srv.shutdown()
            srv.server_close()  # as test_fetch.py: shutdown() alone leaves the socket open (ResourceWarning)


PAGE = """<script>$('#agg-102').jstree({'core': {'data': [{"id": "RS", "text": "REPUBLIKA SRBIJA", "parent": "#"},
{"id": "RS11", "text": "Beogradski region", "parent": "RS"}, {"id": "RS110", "text": "Beogradska oblast", "parent": "RS11"},
{"id": "70114", "text": "Vračar", "parent": "RS110"}], 'check_callback': true}});
$('#agg-2').jstree({'core': {'data': [{"id": "202400", "text": "2024", "parent": "#"},
{"id": "202500", "text": "2025", "parent": "#"}], 'check_callback': true}});</script>
<label style="font-weight:bold" for="cbAggT-102"><input type="checkbox" id="cbAggT-102">Teritorija - NSTJ</label>"""


class ParseDatasetTest(unittest.TestCase):
    def test_trees_labels_and_lookups(self):
        ds = rzs.parse_dataset(PAGE, "18010602")
        self.assertEqual(ds.subarea, "18010602")
        self.assertEqual(ds.labels["agg-102"], "Teritorija - NSTJ")
        self.assertEqual([n.text for n in ds.dims["agg-102"]], ["REPUBLIKA SRBIJA", "Beogradski region", "Beogradska oblast", "Vračar"])
        self.assertEqual(rzs.query({"indicators": ["1IND01"], "agg-102": ["70114"], "agg-2": ["202400", "202500"], "agg-23": ["0"]}),
                         "indicators=1IND01&agg-102=70114&agg-2=202400,202500&agg-23=0")
        self.assertEqual(ds.find("agg-102", "vračar"), ["70114"])
        self.assertEqual(ds.find("agg-102", "oblast"), ["RS110"])
        with self.assertRaises(LookupError):
            ds.find("agg-102", "Nema me")

    def test_children_and_leaves(self):
        ds = rzs.parse_dataset(PAGE, "18010602")
        self.assertEqual(ds.children("agg-102", "RS110"), ["70114"])
        self.assertEqual(ds.leaves("agg-102"), ["70114"])
        self.assertEqual(ds.leaves("agg-2"), ["202400", "202500"])


class OfficeMarkupTest(unittest.TestCase):
    """What the office really serves: compact trees with a "data" key, boxes with an onclick, indicator checkboxes."""

    PAGE = """<label style="font-weight:bold" for="cbAggT-102"><input type="checkbox" id="cbAggT-102"
onclick="toggleAggregants(this.id, 'agg-102');" />Teritorija - NSTJ</label>
<label title="" for="18010602IND01"><input type="checkbox" id="18010602IND01"  /> Procene stanovništva, po starosti</label>
<label style="font-weight:bold" for="cbIndicators"><input type="checkbox" id="cbIndicators" /> Indikatori</label>
<label for="radio-title"><input type="radio" id="radio-title" /> Naziv</label>
<script>$('#agg-2').jstree({
            'core': {
                'data' : [{"id":"202500","text":"2025","parent":"#","data":null},{"id":"202400","text":"2024","parent":"#","data":null}],
                
                'check_callback': true
            },
            'plugins' : ['search', 'types']});</script>"""

    def test_indicators_and_labels(self):
        ds = rzs.parse_dataset(self.PAGE, "18010602")
        self.assertEqual(ds.indicators, ("18010602IND01",))
        self.assertEqual(ds.labels, {"agg-102": "Teritorija - NSTJ"})
        self.assertEqual([n.id for n in ds.dims["agg-2"]], ["202500", "202400"])
        self.assertEqual(rzs.parse_dataset(PAGE, "18010602").indicators, ())

    def test_parents_come_first_whatever_the_page_order(self):
        html = """$('#agg-5').jstree({'core': {'data': [{"id": "b", "text": "child", "parent": "a"},
{"id": "a", "text": "parent", "parent": "#"}, {"id": "c", "text": "grandchild", "parent": "b"}], 'check_callback': true}});"""
        ds = rzs.parse_dataset(html, "x")
        self.assertEqual([(n.id, n.parent) for n in ds.dims["agg-5"]], [("a", None), ("b", "a"), ("c", "b")])
        self.assertEqual(ds.children("agg-5", None), ["a"])
        self.assertEqual(ds.children("agg-5", "b"), ["c"])
        self.assertEqual(ds.leaves("agg-5"), ["c"])
        self.assertEqual(ds.find("agg-5", "GRAND"), ["c"])  # case-insensitive


class ValueTest(unittest.TestCase):
    def test_values_and_ids(self):
        self.assertEqual(rzs.value({"Vrednost": "109462"}), 109462.0)
        self.assertEqual(rzs.value({"Vrednost": "73.86"}), 73.86)
        self.assertEqual(rzs.value({"Vrednost": "1 234"}), 1234.0)
        for bad in ("…", "-", "", None):
            self.assertIsNone(rzs.value({"Vrednost": bad}))
        self.assertIsNone(rzs.value({}))
        self.assertEqual(rzs.unit_id({"IDTer": "RS11 "}), "RS11")


# --- a local server that answers like the office -----------------------------------------------------------------

class Office(http.server.BaseHTTPRequestHandler):
    """GET answers a result page, POST an export. The class attributes are what it serves and what it was asked."""

    page = PAGE
    export = '[{"Vrednost": "1"}, {"Vrednost": "…"}]'.encode("utf-8")
    cut = False  # promise more bytes than are sent, then hang up
    seen: list = []

    def _send(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        type(self).seen.append(("GET", self.path, None, dict(self.headers)))
        self._send(type(self).page.encode("utf-8"))

    def do_POST(self):
        form = self.rfile.read(int(self.headers["Content-Length"])).decode()
        type(self).seen.append(("POST", self.path, urllib.parse.parse_qs(form), dict(self.headers)))
        if type(self).cut:
            body = type(self).export
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body[:5])
            self.close_connection = True
            return
        self._send(type(self).export)

    def log_message(self, *a):
        pass


def setUpModule():
    Office.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Office)
    Office.base = f"http://127.0.0.1:{Office.server.server_address[1]}"
    threading.Thread(target=Office.server.serve_forever, daemon=True).start()


def tearDownModule():
    Office.server.shutdown()
    Office.server.server_close()


class OfficeCase:
    """An empty cache folder, the office's URLs pointed at the local server, and the pause watched instead of slept."""

    def setUp(self):
        Office.seen = []
        Office.export = '[{"Vrednost": "1"}, {"Vrednost": "…"}]'.encode("utf-8")
        Office.cut = False
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raw = Path(tmp.name)
        local_result_url = Office.base + "/Home/Result/{subarea}?languageCode=sr-Latn"
        self.pause = self.start_patch(mock.patch.object(rzs.time, "sleep"))
        self.start_patch(mock.patch("builtins.print"))
        self.start_patch(mock.patch.object(fetch, "RAW", self.raw))
        self.start_patch(mock.patch.object(fetch, "OFFLINE", False))
        self.start_patch(mock.patch.object(rzs, "RZS_EXPORT_URL", Office.base + "/Home/DisplayResult"))
        self.start_patch(mock.patch.object(rzs, "RZS_RESULT_URL", local_result_url))

    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result


class ExportTest(OfficeCase, unittest.TestCase):
    ds = rzs.parse_dataset(PAGE, "18010602")

    def test_posts_the_selection_as_a_form_and_caches_the_list(self):
        rows = rzs.export(self.ds, {"indicators": ["1IND01"], "agg-2": ["202400", "202500"]}, "t.json")
        self.assertEqual(rows, [{"Vrednost": "1"}, {"Vrednost": "…"}])
        method, path, form, headers = Office.seen[0]
        self.assertEqual((method, path), ("POST", "/Home/DisplayResult"))
        self.assertEqual(form, {"languageCode": ["sr-Latn"], "displayMode": ["exportJSON"], "subAreaId": ["18010602"],
                                "resultDisplayType": ["Title"], "uriQuery": ["indicators=1IND01&agg-2=202400,202500"]})
        self.assertEqual(headers["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(headers["Referer"], rzs.RZS_RESULT_URL.format(subarea="18010602"))
        self.assertEqual(headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(headers["User-Agent"], fetch.USER_AGENT)
        self.assertEqual((self.raw / "rzs_db" / "t.json").read_bytes(), Office.export)
        self.pause.assert_called_once_with(1.1)  # once, before the request that went out

    def test_a_cached_answer_costs_neither_a_request_nor_a_pause(self):
        selection = {"indicators": ["1IND01"]}
        rzs.export(self.ds, selection, "t.json")
        rzs.export(self.ds, selection, "t.json")
        self.assertEqual(len(Office.seen), 1)
        self.pause.assert_called_once_with(1.1)
        rzs.export(self.ds, selection, "t.json", force=True)
        self.assertEqual(len(Office.seen), 2)  # --force asks again, after another pause
        self.assertEqual(self.pause.call_count, 2)

    def test_a_body_that_is_not_a_json_list_is_rejected_and_forgotten(self):
        for bad in (b"<html>greska</html>", b'{"error": "syntax"}', b""):
            with self.subTest(body=bad):
                Office.export = bad
                with self.assertRaises(fetch.UnexpectedContentError):
                    rzs.export(self.ds, {"indicators": ["1IND01"]}, "bad.json")
                self.assertFalse((self.raw / "rzs_db" / "bad.json").exists())
                self.assertNotIn("bad.json", fetch.read_manifest("rzs_db"))

    def test_offline_never_asks(self):
        with mock.patch.object(fetch, "OFFLINE", True), self.assertRaises(fetch.OfflineError):
            rzs.export(self.ds, {"indicators": ["1IND01"]}, "missing.json")
        self.assertEqual(Office.seen, [])
        self.pause.assert_not_called()

    def test_a_cut_off_answer_is_retried_and_never_cached(self):
        Office.cut = True
        with mock.patch.object(fetch, "BACKOFF", 0.0), self.assertRaises(ConnectionError):
            rzs.export(self.ds, {"indicators": ["1IND01"]}, "cut.json")
        self.assertEqual(len(Office.seen), fetch.RETRIES)  # asked again, as a cut-off GET is
        self.assertEqual(sorted(p.name for p in (self.raw / "rzs_db").iterdir()), [])  # no file, no leftover, no manifest
        Office.cut = False
        self.assertEqual(rzs.export(self.ds, {"indicators": ["1IND01"]}, "cut.json"), [{"Vrednost": "1"}, {"Vrednost": "…"}])


class LoadDatasetTest(OfficeCase, unittest.TestCase):
    def test_loads_the_page_once_under_pages(self):
        ds = rzs.load_dataset("18010602")
        self.assertEqual(ds.subarea, "18010602")
        self.assertEqual(ds.find("agg-102", "vračar"), ["70114"])
        method, path, _, headers = Office.seen[0]
        self.assertEqual((method, path, headers["User-Agent"]), ("GET", "/Home/Result/18010602?languageCode=sr-Latn", fetch.USER_AGENT))
        self.assertEqual((self.raw / "rzs_db" / "pages" / "18010602.html").read_text(encoding="utf-8"), PAGE)
        self.assertEqual(fetch.read_manifest("rzs_db")["pages/18010602.html"]["url"], rzs.RZS_RESULT_URL.format(subarea="18010602"))
        self.pause.assert_called_once_with(1.1)
        rzs.load_dataset("18010602")
        self.assertEqual(len(Office.seen), 1)  # cached: no request, no pause
        self.assertEqual(self.pause.call_count, 1)
        rzs.load_dataset("18010602", force=True)
        self.assertEqual(len(Office.seen), 2)
        self.assertEqual(self.pause.call_count, 2)
