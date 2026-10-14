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
    payload = KRXClient(key).quotes(day, CODES)
    if payload['missingCodes'] or payload['warnings']:
        raise DataError('일부 후보 또는 시장 자료가 없어 기존 전체 종가를 유지합니다.')
    write_snapshot(payload, ROOT / 'docs/data/krx-quotes.json')
    print('KRX 종가 갱신 완료: ' + payload['asOf'] + ', ' + str(len(payload['quotes'])) + '종목')


if __name__ == '__main__':
    try:
        main()
    except DataError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
