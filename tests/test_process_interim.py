"""Processing must retain the source vintage for downstream builders and provenance."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import __main__ as cli
from pipeline.core import store


class ProcessInterimTest(unittest.TestCase):
    def test_vintage_is_available_both_in_payload_and_source_data(self):
        source = mock.Mock()
        source.process.return_value = {"vintage": "Popis 2022", "units": {"1": {}}, "_files": ["a.xlsx"]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(store, "INTERIM", Path(tmp)), \
                mock.patch.object(cli, "BY_ID", {"census": source}):
            cli.cmd_process(["census"])
            payload = store.load_interim_payload("census")
        self.assertEqual(payload["vintage"], "Popis 2022")
        self.assertEqual(payload["data"]["vintage"], "Popis 2022")
        self.assertEqual(payload["files"], ["a.xlsx"])


if __name__ == "__main__":
    unittest.main()
