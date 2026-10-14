"""Generate the GitHub-hosted dashboard's KRX close snapshot using Actions secrets."""
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import DataError, KRXClient, SEOUL

CODES = ['078930', '036930', '028050', '006260', '007660', '016360', '021240', '032640', '000100']


def enrich_metrics(payload, client):
    """Use 21 market sessions for close[t]/close[t-20] and 20 daily turnovers."""
    asof = dt.date.fromisoformat(payload['asOf'])
    sessions = []
    for offset in range(75):
        day = asof - dt.timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        all_rows = client.market('KOSPI', day) + client.market('KOSDAQ', day)
        if not all_rows:
            continue
        sessions.append({r['code']: r for r in all_rows})
        if len(sessions) == 21:
            break
    for quote in payload['quotes']:
        code = quote['code']
        history = [session.get(code) for session in sessions]
        cap = quote.get('marketCapKRW')
        quote['cap'] = cap / 100_000_000 if cap is not None else None
        turnover = [r.get('tradingValueKRW') if r else None for r in history[:20]]
        quote['adv'] = (sum(turnover) / 20 / 100_000_000
                        if len(turnover) == 20 and all(v is not None for v in turnover) else None)
        base = history[20]['closePrice'] if len(history) == 21 and history[20] else None
        quote['runup'] = (quote['closePrice'] / base - 1) * 100 if base else None
        quote['metricsDate'] = payload['asOf']
        quote['historySessions'] = len(sessions)
        quote['returnBasis'] = '20 trading sessions; unadjusted KRX closes'
    payload['metricsDefinition'] = {
        'cap': 'KRX market capitalization / 100,000,000 KRW',
        'adv': 'Mean of most recent 20 market sessions trading value / 100,000,000 KRW',
        'runup': '(Unadjusted close[t] / close[t-20] - 1) * 100; corporate actions may affect return',
        'floatPct': 'Not provided; MSCI FIF requires a separate source',
        'newWeight': 'Not provided; future index weight is a scenario assumption',
    }
    payload['metricsMissingCodes'] = [q['code'] for q in payload['quotes']
                                      if any(q.get(k) is None for k in ('cap', 'adv', 'runup'))]
    return payload


def write_snapshot(payload, path):
    if payload.get('provider') != 'KRX Open API' or not payload.get('quotes'):
        raise DataError('유효한 KRX 종가가 없어 기존 파일을 유지합니다.')
    if path.exists():
        prior = json.loads(path.read_text(encoding='utf-8'))
        if prior.get('provider') == 'KRX Open API' and prior.get('asOf', '') > payload['asOf']:
            raise DataError('기존 데이터보다 오래된 응답입니다. 기존 파일을 유지합니다.')
    # Only normalized closes enter GitHub; neither keys nor raw provider bodies are stored.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    key = os.environ.get('KRX_API_KEY', '').strip()
    if not key:
        raise DataError('Actions에 연결된 KRX 인증키가 없습니다. 워크플로의 Secret 이름을 확인하세요.', 503)
    now = dt.datetime.now(SEOUL)
    day = now.date() if now.hour >= 16 else now.date() - dt.timedelta(days=1)
    client = KRXClient(key)
    payload = client.quotes(day, CODES)
    if payload['missingCodes'] or payload['warnings']:
        raise DataError('일부 후보 또는 시장 자료가 없어 기존 전체 종가를 유지합니다.')
    enrich_metrics(payload, client)
    write_snapshot(payload, ROOT / 'docs/data/krx-quotes.json')
    print('KRX 종가 갱신 완료: ' + payload['asOf'] + ', ' + str(len(payload['quotes'])) + '종목')


if __name__ == '__main__':
    try:
        main()
    except DataError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
