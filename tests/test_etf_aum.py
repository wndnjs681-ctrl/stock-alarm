import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update_etf_aum import normalize_etfs


class AUMTests(unittest.TestCase):
    def test_nav_units_and_exclude_other_indexes(self):
        payload = {'OutBlock_1': [
            {'ISU_CD': '310970', 'BAS_DD': '20261013', 'NAV': '50,000', 'LIST_SHRS': '10,000,000'},
            {'ISU_CD': '999999', 'BAS_DD': '20261013', 'NAV': '50000', 'LIST_SHRS': '10000000'}]}
        result = normalize_etfs(payload, '2026-10-13')
        self.assertEqual(result['aum'], 5000)
        self.assertEqual(len(result['funds']), 1)
        self.assertIn('278540', result['missingETF'])

    def test_wrong_date_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_etfs({'OutBlock_1': [{'ISU_CD': '310970', 'BAS_DD': '20261012'}]}, '2026-10-13')
