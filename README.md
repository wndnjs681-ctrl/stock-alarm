# MSCI 분기별 후보 대시보드

GitHub Actions에서 기존 KRX Secret을 사용해 9종목의 일별 종가를 조회하고, 대시보드는 키 없이 생성된 가격 자료를 읽습니다.

## 구성

- `docs/index.html`: 후보 선별, 관심 종목, 분기 복사, 종가 표시
- `docs/data/krx-quotes.json`: Actions에서 생성한 KRX 종가 스냅샷
- `scripts/update_krx.py`: 코스피·코스닥 종가 조회 및 날짜 검증
- `server.py`: KRX API 어댑터; 로컬 실행도 지원

등록한 Actions Secret을 워크플로의 `KRX_API_KEY` 환경변수에 연결해야 합니다. Secret 값은 코드나 출력에 넣지 않습니다. KRX의 유가증권·코스닥 일별매매정보 이용 승인이 필요합니다.

워크플로 실행 후 Actions의 대시보드 아티팩트를 내려받을 수 있습니다. GitHub Pages가 활성화되어 있다면 `main` 브랜치의 `/docs`를 게시 경로로 사용하세요. 웹 게시가 아직 활성화되지 않은 저장소에서는 주소가 자동으로 생기지 않습니다.

화면의 ‘GitHub KRX 종가 불러오기’는 마지막으로 생성된 스냅샷을 읽습니다. 클릭할 때마다 KRX API를 호출하는 기능이 아닙니다. 스냅샷의 실제 기준일과 갱신 시각을 표시하며, 연결 실패 시 기존 가격을 유지합니다.

기본 조회 후보: GS, 주성엔지니어링, 삼성E&A, LS, 이수페타시스, 삼성증권, 코웨이, LG유플러스, 유한양행. 후보 명단은 2026년 11월 리뷰 관찰 목록이며 자동으로 분기마다 재선정하지 않습니다.

테스트: `python -m unittest discover -s tests`. 승인된 키로 Actions가 성공하기 전에는 실제 KRX 연결 성공으로 표시하지 않습니다.
