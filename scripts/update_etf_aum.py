"""Observe only the four published MSCI Korea-linked ETFs; never total global AUM."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import number

ETF_CODES = {'310970', '278540', '332940', '156080'}
SOURCE = 'https://openapi.krx.co.kr/'


def normalize_etfs(payload, asof):
    if not isinstance(payload, dict) or not isinstance(payload.get('OutBlock_1'), list):
        raise ValueError('KRX ETF 응답 형식 미확인')
    funds = []
    for row in payload['OutBlock_1']:
        if row.get('ISU_CD') not in ETF_CODES:
            continue
        if str(row.get('BAS_DD', '')).replace('-', '') != asof.replace('-', ''):
            raise ValueError('ETF 기준일 불일치')
        nav, shares = number(row.get('NAV')), number(row.get('LIST_SHRS'))
        if nav is None or shares is None:
            continue
        funds.append({'code': row['ISU_CD'], 'name': row.get('ISU_NM', ''),
                      'nav': nav, 'units': shares, 'aumKRW100m': nav * shares / 100_000_000})
    if not funds:
        raise ValueError('선택 ETF 자료 없음')
    return {'status': 'verified_etf_sample', 'provider': 'KRX Open API', 'asOf': asof,
            'aum': sum(f['aumKRW100m'] for f in funds), 'funds': funds,
            'source': SOURCE, 'formula': 'NAV × listed ETF units / 100,000,000 KRW',
            'scope': 'Observed published MSCI Korea ETF sample only; excludes EM/ACWI/capped funds',
            'missingETF': sorted(ETF_CODES - {f['code'] for f in funds})}


def main():
    target = ROOT / 'docs/data/etf-aum.json'
    asof = json.loads((ROOT / 'docs/data/krx-quotes.json').read_text())['asOf']
    key = os.environ.get('KRX_API_KEY', '')
    if not key:
        result = {'status': 'unavailable', 'message': 'KRX Secret 미설정', 'asOf': asof}
    else:
        request = urllib.request.Request(
            'https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd?' +
            urllib.parse.urlencode({'basDd': asof.replace('-', '')}),
            headers={'AUTH_KEY': key, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read(8_000_000).decode('utf-8-sig'))
            result = normalize_etfs(data, asof)
        except (urllib.error.URLError, OSError, ValueError):
            result = {'status': 'unavailable', 'asOf': asof,
                      'message': 'ETF API 승인·네트워크 또는 데이터 형식 미확인; 주식 조회는 유지'}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('ETF AUM lookup: ' + result['status'])


if __name__ == '__main__':
    main()
