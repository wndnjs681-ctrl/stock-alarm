import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update_krx import enrich_metrics


class MetricsTests(unittest.TestCase):
    def test_market_sessions_units_and_zero_turnover(self):
        days = []
        day = dt.date(2026, 10, 13)
        while len(days) < 21:
            if day.weekday() < 5:
                days.append(day)
            day -= dt.timedelta(days=1)

        class Client:
            def market(self, market, day):
                if market == 'KOSDAQ' or day not in days:
                    return []
                i = days.index(day)
                return [{'code': '078930', 'closePrice': 120 - i,
                         'tradingValueKRW': 0 if i == 0 else 100_000_000}]

        payload = {'asOf': '2026-10-13', 'quotes': [{'code': '078930', 'closePrice': 120,
                    'marketCapKRW': 10_000_000_000_000}]}
        result = enrich_metrics(payload, Client())['quotes'][0]
        self.assertEqual(result['cap'], 100000)
        self.assertEqual(result['adv'], .95)
        self.assertAlmostEqual(result['runup'], 20)

    def test_missing_sessions_are_not_replaced_with_zero(self):
        class Client:
            def market(self, *_args):
                return []

        payload = {'asOf': '2026-10-13', 'quotes': [{'code': '078930', 'closePrice': 120,
                    'marketCapKRW': 10_000_000_000_000}]}
        result = enrich_metrics(payload, Client())
        self.assertIsNone(result['quotes'][0]['adv'])
        self.assertIsNone(result['quotes'][0]['runup'])
        self.assertEqual(result['metricsMissingCodes'], ['078930'])


if __name__ == '__main__':
    unittest.main()
