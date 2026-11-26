import gzip
import tempfile
import unittest
from pathlib import Path

from scripts.report_data_size import report


class DataSizeReportTests(unittest.TestCase):
    def test_counts_actual_cache_and_independent_gzip_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'raw' / 'dem').mkdir(parents=True)
            (base / 'raw' / 'dem' / 'tile').write_bytes(b'abc')
            (base / 'interim').mkdir()
            (base / 'interim' / 'world.json').write_bytes(b'12345')
            (base / 'web').mkdir()
            payload = b'{"values": [1, 2, 3]}'
            (base / 'web' / 'world.json').write_bytes(payload)
            result = report(base / 'raw', base / 'interim', base / 'web')
            self.assertEqual(result['raw_cache']['dem'], {'files': 1, 'bytes': 3})
            self.assertEqual(result['interim'], {'files': 1, 'bytes': 5})
            self.assertEqual(result['published_data']['world.json'], {
                'bytes': len(payload), 'gzip_bytes': len(gzip.compress(payload, mtime=0))})
            self.assertEqual(result['published_totals'], result['published_data']['world.json'])

    def test_missing_directories_are_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'absent'
            self.assertEqual(report(missing, missing, missing)['published_totals'], {'bytes': 0, 'gzip_bytes': 0})


if __name__ == '__main__':
    unittest.main()
