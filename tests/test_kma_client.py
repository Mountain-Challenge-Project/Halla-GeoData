"""Entire suite uses fake responses; no DNS, authentication or KMA requests."""
import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import kma_client as k

PAYLOAD = b'# SYNTHETIC TEST; NOT OBSERVATIONS\n3,2,=\n0,125,-30000,=\n-25000,600,250,=\n'


class FakeOpener:
    def __init__(self, *results):
        self.results = iter(results)
        self.requests = []
    def open(self, request, timeout):
        self.requests.append((request, timeout))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(result)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.config = k.Config('SYNTHETIC_FAKE_KEY/+=&?')
        self.params = k.parameters(self.config, '202001010000')

    def test_env_quotes_and_process_precedence(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            root = Path(td)
            (root/'.env').write_text('KMA_API_KEY="example#literal"\nKMA_POLL_SECONDS=600\n', encoding='utf-8')
            self.assertEqual(k.Config.load(root).key, 'example#literal')
            with patch.dict(os.environ, {'KMA_API_KEY': 'OVERRIDE'}):
                config = k.Config.load(root)
                self.assertEqual(config.key, 'OVERRIDE')
                self.assertNotIn('OVERRIDE', repr(config))
            (root/'.env').write_text('KMA_ACCUMULATION_MINUTES=30', encoding='utf-8')
            with self.assertRaises(k.ClientError):
                k.Config.load(root)

    def test_empty_key_never_opens_network(self):
        opener = FakeOpener()
        with self.assertRaises(k.ClientError):
            k.fetch_payload(k.Config(''), self.params, opener)
        self.assertEqual(opener.requests, [])

    def test_unit_and_url_encoding(self):
        opener = FakeOpener(PAYLOAD)
        self.assertEqual(k.fetch_payload(self.config, self.params, opener), PAYLOAD)
        params = parse_qs(urlsplit(opener.requests[0][0].full_url).query)
        self.assertEqual(params['authKey'], [self.config.key])
        self.assertEqual(params['unit'], ['MM'])
        self.assertEqual(params['cmp'], ['PCPH'])
        self.assertEqual(params['acc'], ['60'])

    def test_ascii_keeps_special_codes_and_rejects_partial_body(self):
        result = k.inspect_ascii(PAYLOAD)
        self.assertEqual(result['value_count'], 6)
        self.assertEqual(result['encoded_nonnegative_min'], 0)
        self.assertEqual(result['negative_code_counts'][-25000], 1)
        self.assertFalse(result['spatial_alignment_verified'])
        for payload in [b'<html>error</html>', b'{"resultCode":401}', b'3,2,=\n0,1,2,=\n',
                        b'3,1,=\n0,1,=\n2', b'2,1,=\n1,2,3,=', b'# no data']:
            with self.subTest(payload=payload), self.assertRaises(k.ClientError):
                k.inspect_ascii(payload)

    def test_retry_and_auth_failures_are_redacted(self):
        secret_url = k.ENDPOINT + '?authKey=' + self.config.key
        opener = FakeOpener(HTTPError(secret_url, 503, self.config.key, {}, None), PAYLOAD)
        sleeps = []
        k.fetch_payload(self.config, self.params, opener, sleeps.append)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleeps, [2])
        for code in [401, 403, 302]:
            opener = FakeOpener(HTTPError(secret_url, code, self.config.key, {}, None))
            with self.assertRaises(k.ClientError) as caught:
                k.fetch_payload(self.config, self.params, opener, lambda _: None)
            self.assertNotIn(self.config.key, str(caught.exception))
            self.assertEqual(caught.exception.http_status, code)
            self.assertEqual(len(opener.requests), 1)
        opener = FakeOpener(*[URLError(secret_url)] * 3)
        with self.assertRaises(k.ClientError) as caught:
            k.fetch_payload(self.config, self.params, opener, lambda _: None)
        self.assertNotIn(self.config.key, str(caught.exception))
        self.assertEqual(len(opener.requests), 3)

    def test_response_size_and_key_echo_are_rejected(self):
        with patch.object(k, 'MAX_BYTES', 4), self.assertRaises(k.ClientError):
            k.fetch_payload(self.config, self.params, FakeOpener(PAYLOAD))
        with self.assertRaises(k.ClientError):
            k.fetch_payload(self.config, self.params, FakeOpener(self.config.key.encode()))

    def test_kst_and_five_minute_floor(self):
        now = datetime(2026, 10, 14, 9, 23, tzinfo=k.KST)
        self.assertEqual(k.request_time(config=self.config, now=now), '202610140900')
        for value in ['bad', '202613010000', '202610140001', '209901010000']:
            with self.assertRaises(k.ClientError):
                k.request_time(value, now=now)

    def test_archive_is_private_and_failure_keeps_last_success(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            record = k.collect(self.config, '202001010000', root, FakeOpener(PAYLOAD))
            self.assertFalse(record['map_ready'])
            self.assertEqual(record['documented_unit'], 'mm')
            pointer = root/'runtime/kma/latest_raw.json'
            previous = pointer.read_bytes()
            with self.assertRaises(k.ClientError):
                k.collect(self.config, '202001010005', root, FakeOpener(b'<html>failed</html>'))
            self.assertEqual(pointer.read_bytes(), previous)
            self.assertFalse((root/'outputs').exists())
            for path in root.rglob('*'):
                if path.is_file():
                    self.assertNotIn(self.config.key.encode(), path.read_bytes())

    def test_check_and_setup_do_not_call_network_or_overwrite_key(self):
        with tempfile.TemporaryDirectory() as td, patch.object(k, 'ROOT', Path(td)), patch.object(k, 'build_opener') as opener, patch.dict(os.environ, {}, clear=True):
            root = Path(td)
            (root/'.env.example').write_text('KMA_API_KEY=\n', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(k.main(['setup']), 0)
                (root/'.env').write_text('KMA_API_KEY=USER_VALUE', encoding='utf-8')
                self.assertEqual(k.main(['setup']), 0)
                self.assertEqual(k.main(['check']), 0)
            self.assertEqual((root/'.env').read_text(), 'KMA_API_KEY=USER_VALUE')
            opener.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
