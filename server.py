"""Local MSCI dashboard and authenticated KRX daily close bridge (Python 3.10+)."""
import argparse
import datetime as dt
import getpass
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KRX_BASE = 'https://data-dbg.krx.co.kr/svc/apis/sto/'
MARKETS = {'KOSPI': 'stk_bydd_trd', 'KOSDAQ': 'ksq_bydd_trd'}
SEOUL = dt.timezone(dt.timedelta(hours=9))


class DataError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def parse_day(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        day = dt.date.fromisoformat(value)
        if day < dt.date(2010, 1, 4) or day > dt.datetime.now(SEOUL).date():
            raise ValueError()
        return day
    except (ValueError, TypeError):
        raise DataError('조회일은 2010-01-04 이후의 오늘 또는 과거 날짜여야 합니다.', 400)


def number(value):
    try:
        result = float(str(value).replace(',', '').strip())
        return result if result > 0 and result < float('inf') else None
    except (TypeError, ValueError):
        return None


def normalize(payload, day, market):
    if not isinstance(payload, dict) or not isinstance(payload.get('OutBlock_1'), list):
        raise DataError('KRX 응답 형식이 예상과 다릅니다. 인증키·API 승인·명세를 확인하세요.')
    result = []
    for row in payload['OutBlock_1']:
        if not isinstance(row, dict):
            raise DataError('KRX 종목 데이터 형식이 올바르지 않습니다.')
        # KRX daily endpoints return the short stock code in ISU_CD; preserve zeros.
        code = str(row.get('ISU_CD', '')).strip()
        close = number(row.get('TDD_CLSPRC'))
        asof = str(row.get('BAS_DD', '')).replace('-', '')
        if asof != day.strftime('%Y%m%d'):
            raise DataError('KRX 응답 기준일이 조회일과 다릅니다. 기존 가격을 유지합니다.')
        if not re.fullmatch(r'[0-9A-Z]{6}', code) or close is None:
            continue
        result.append({'code': code, 'name': row.get('ISU_NM', ''),
                       'closePrice': close, 'closeDate': day.isoformat(),
                       'closeSource': 'https://openapi.krx.co.kr/',
                       'closeProvider': 'KRX Open API', 'market': market})
    return result


class KRXClient:
    def __init__(self, key='', opener=None):
        self.key = key
        self.opener = opener or urllib.request.urlopen
        self.cache = {}
        self.lock = threading.Lock()

    def market(self, market, day):
        cache_key = (market, day.isoformat())
        cached = self.cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
        url = KRX_BASE + MARKETS[market] + '?' + urllib.parse.urlencode({'basDd': day.strftime('%Y%m%d')})
        request = urllib.request.Request(url, headers={'AUTH_KEY': self.key, 'Accept': 'application/json'})
        try:
            with self.opener(request, timeout=15) as response:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise DataError('KRX 응답이 너무 큽니다.')
                payload = json.loads(raw.decode('utf-8-sig'))
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise DataError('KRX 인증 또는 API 이용 승인이 확인되지 않았습니다. 인증키와 두 API 승인을 확인하세요.', 502) from None
            if error.code == 429:
                raise DataError('KRX 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.', 429) from None
            raise DataError('KRX 요청에 실패했습니다. 잠시 후 다시 시도하세요.') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise DataError('KRX 서버에 연결하지 못했습니다. 네트워크를 확인하세요.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise DataError('KRX가 JSON 데이터를 반환하지 않았습니다. 인증과 이용 승인을 확인하세요.') from None
        rows = normalize(payload, day, market)
        self.cache[cache_key] = (time.monotonic(), rows)
        return rows

    def quotes(self, day, codes, fallback=True):
        if not self.key:
            raise DataError('KRX 인증키가 설정되지 않았습니다. 서버를 재실행해 인증키를 입력하세요.', 503)
        if not codes or len(codes) > 200 or any(not re.fullmatch(r'[0-9A-Z]{6}', c) for c in codes):
            raise DataError('후보 종목 코드 형식을 확인하세요. 최대 200종목입니다.', 400)
        with self.lock:
            for offset in range(8 if fallback else 1):
                candidate = day - dt.timedelta(days=offset)
                if candidate < dt.date(2010, 1, 4):
                    break
                if candidate.weekday() >= 5:
                    continue
                by_market = {market: self.market(market, candidate) for market in MARKETS}
                all_rows = [r for rows in by_market.values() for r in rows]
                if not all_rows:
                    continue
                wanted = set(codes)
                rows = [r for r in all_rows if r['code'] in wanted]
                missing = sorted(wanted - {r['code'] for r in rows})
                warnings = [market + ' 데이터 없음' for market, market_rows in by_market.items() if not market_rows]
                return {'provider': 'KRX Open API', 'requestedDate': day.isoformat(),
                        'asOf': candidate.isoformat(), 'quotes': rows, 'missingCodes': missing,
                        'warnings': warnings, 'fetchedAt': dt.datetime.now(SEOUL).isoformat()}
        raise DataError('조회 범위에 KRX 일별매매 데이터가 없습니다. 더 이전 날짜로 조회하세요.', 404)


def make_handler(client):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            # No headers, keys or provider response bodies in logs.
            pass

        def respond(self, status, payload, content_type='application/json; charset=utf-8'):
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            host = self.headers.get('Host', '')
            allowed_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if host not in allowed_hosts:
                self.respond(403, {'error': '로컬 대시보드에서만 사용할 수 있습니다.'})
                return
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://' + h for h in allowed_hosts}:
                self.respond(403, {'error': '허용되지 않은 요청입니다.'})
                return
            parsed = urllib.parse.urlsplit(self.path)
            try:
                if parsed.path in ('/', '/index.html'):
                    self.respond(200, (ROOT / 'dist/index.html').read_bytes(), 'text/html; charset=utf-8')
                elif parsed.path == '/api/krx/status':
                    self.respond(200, {'configured': bool(client.key), 'provider': 'KRX Open API',
                                       'approvalVerified': False})
                elif parsed.path == '/api/krx/quotes':
                    query = urllib.parse.parse_qs(parsed.query)
                    day = parse_day(query.get('date', [''])[0])
                    codes = list(dict.fromkeys(query.get('codes', [''])[0].split(',')))
                    self.respond(200, client.quotes(day, codes, query.get('fallback', ['1'])[0] != '0'))
                else:
                    self.respond(404, {'error': '찾을 수 없습니다.'})
            except DataError as error:
                self.respond(error.status, {'error': str(error)})
            except Exception:
                self.respond(500, {'error': '서버 처리 오류입니다. 기존 가격을 유지합니다.'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description='MSCI dashboard with KRX daily closes')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-prompt', action='store_true', help='Start without prompting when no key is configured')
    args = parser.parse_args()
    key = os.environ.get('KRX_API_KEY', '').strip()
    if not key and not args.no_prompt:
        key = getpass.getpass('KRX 인증키 (화면에 표시되지 않음): ').strip()
    if not key:
        print('인증키 미설정: 대시보드는 열리지만 KRX 갱신은 사용할 수 없습니다.')
    if '\r' in key or '\n' in key:
        raise SystemExit('인증키 형식이 올바르지 않습니다.')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(KRXClient(key)))
    print(f'대시보드: http://127.0.0.1:{server.server_port} (종료: Ctrl+C)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
