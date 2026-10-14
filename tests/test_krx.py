import datetime as dt
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import DataError, KRXClient, normalize, parse_day


class KRXTests(unittest.TestCase):
    def row(self, code='078930', price='99,500', date='20261013'):
        return {'BAS_DD': date, 'ISU_CD': code, 'ISU_NM': 'GS', 'TDD_CLSPRC': price}

    def test_normalization_preserves_zero_and_date(self):
        rows = normalize({'OutBlock_1': [self.row()]}, dt.date(2026, 10, 13), 'KOSPI')
        self.assertEqual(rows[0]['code'], '078930')
        self.assertEqual(rows[0]['closePrice'], 99500)
        self.assertEqual(rows[0]['closeDate'], '2026-10-13')

    def test_wrong_date_is_not_applied(self):
        with self.assertRaises(DataError):
            normalize({'OutBlock_1': [self.row(date='20261012')]}, dt.date(2026, 10, 13), 'KOSPI')

    def test_error_object_is_not_an_empty_trading_day(self):
        with self.assertRaises(DataError):
            normalize({'error': 'invalid auth'}, dt.date(2026, 10, 13), 'KOSPI')

    def test_no_key_prevents_network_request(self):
        with self.assertRaises(DataError) as error:
            KRXClient().quotes(dt.date(2026, 10, 13), ['078930'])
        self.assertEqual(error.exception.status, 503)

    def test_request_header_and_date_and_cache(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            self.assertEqual(timeout, 15)
            return io.BytesIO(json.dumps({'OutBlock_1': [self.row()]}).encode())

        client = KRXClient('test-key-not-a-real-credential', opener)
        client.market('KOSPI', dt.date(2026, 10, 13))
        client.market('KOSPI', dt.date(2026, 10, 13))
        self.assertEqual(len(requests), 1)
        self.assertIn('/sto/stk_bydd_trd?basDd=20261013', requests[0].full_url)
        self.assertEqual(requests[0].get_header('Auth_key'), 'test-key-not-a-real-credential')

    def test_unpublished_date_falls_back_and_missing_codes_reported(self):
        client = KRXClient('test-key')

        def market(name, date):
            if date == dt.date(2026, 10, 14):
                return []
            return normalize({'OutBlock_1': [self.row()]}, date, name) if name == 'KOSPI' else []

        client.market = market
        data = client.quotes(dt.date(2026, 10, 14), ['078930', '036930'])
        self.assertEqual(data['asOf'], '2026-10-13')
        self.assertEqual(data['missingCodes'], ['036930'])
        self.assertEqual(data['warnings'], ['KOSDAQ 데이터 없음'])

    def test_exact_date_does_not_fall_back(self):
        client = KRXClient('test-key')
        client.market = lambda *_args: []
        with self.assertRaises(DataError) as error:
            client.quotes(dt.date(2026, 10, 14), ['078930'], False)
        self.assertEqual(error.exception.status, 404)

    def test_auth_failure_does_not_expose_key_or_provider_response(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, 'test-key', {}, None)

        with self.assertRaises(DataError) as error:
            KRXClient('test-key', opener).market('KOSPI', dt.date(2026, 10, 13))
        self.assertNotIn('test-key', str(error.exception))

    def test_invalid_date(self):
        with self.assertRaises(DataError):
            parse_day('2026-02-30')


if __name__ == '__main__':
    unittest.main()
