import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from weather_collect import write_csv, save_json
from work.package_weather import contained, verify


class SnapshotTests(unittest.TestCase):
    def fixture(self, root, reported_rows=1):
        data = root / 'latest' / 'example.csv'
        write_csv(data, [{'station_id': '184', 'temperature_c': '-1'}])
        write_csv(root / 'file_inventory.csv', [dict(
            file='latest/example.csv', rows=reported_rows,
            sha256=hashlib.sha256(data.read_bytes()).hexdigest())])
        save_json(root / 'latest' / 'latest.json', {'sources': {'example': {'csv': 'latest/example.csv'}}})
        entries = [dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size,
                        sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                   for p in sorted(root.rglob('*')) if p.is_file()]
        save_json(root / 'MANIFEST.json', {'files': entries})
        return data

    def test_verify_is_offline_and_detects_modified_csv(self):
        with tempfile.TemporaryDirectory() as temp, patch('work.package_weather.Config.load', side_effect=AssertionError('must not read credentials')):
            root = Path(temp)
            data = self.fixture(root)
            self.assertEqual(verify(root)['checksums'], 'passed')
            data.write_bytes(data.read_bytes() + b'corruption')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                verify(root)

    def test_inventory_row_count_must_match_even_with_valid_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, reported_rows=2)
            with self.assertRaisesRegex(ValueError, 'row count mismatch'):
                verify(root)

    def test_snapshot_paths_support_windows_separators_and_reject_escape(self):
        root = Path.cwd()
        self.assertEqual(contained(root, 'latest\\example.csv'), root / 'latest' / 'example.csv')
        with self.assertRaises(ValueError):
            contained(root, '../outside.csv')


if __name__ == '__main__':
    unittest.main()
