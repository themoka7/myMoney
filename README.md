# myMoney — 일별 TOP10 스크리너 & 추이 기록

## 👉 바로가기

| 보고 싶은 것 | 링크 |
|---|---|
| **오늘(가장 최근) 리포트** | [📊 최신 TOP10 리포트](https://github.com/themoka7/myMoney/releases/latest) |
| 날짜별 지난 리포트 전체 | [Releases 목록](https://github.com/themoka7/myMoney/releases) |
| 차트 대시보드 (순위 추이·누적 수익률 그래프) | [대시보드](https://themoka7.github.io/myMoney/) <sub>Settings → Pages 를 `main` / `/docs` 로 켜야 열림</sub> |
| 배치 실행 기록 / 수동 실행·백필 | [Actions → daily-top10](https://github.com/themoka7/myMoney/actions/workflows/daily.yml) |

리포트는 평일 16:40(KST)에 자동으로 새로 올라온다. "최신 리포트" 링크는 항상 가장 최근 날짜를 연다.

매 거래일 장 마감 후 KOSPI·KOSDAQ 전종목을 카테고리별로 점수화해 **TOP10**을 고르고,
그 결과를 날마다 쌓아서 **순위 변화**와 **"다음날 들고 있었다면?" 성과**를 비교하는 학습용 프로젝트.

> 감은 검증되지 않는다. 코드는 검증된다. — [`notes/01-소액투자-착각과-검증.md`](notes/01-소액투자-착각과-검증.md)

## 카테고리와 점수

모든 점수는 그날 **유니버스 안에서의 백분위(0~100)** 다. 절대 기준이 아니라 상대 순위.

| 카테고리 | 계산 | 제외 |
|---|---|---|
| 가치 | (PER 낮은 순 백분위 + PBR 낮은 순 백분위) / 2 | PER ≤ 0, PBR ≤ 0 (적자) |
| 배당 | 배당수익률 백분위 | 무배당, 적자 |
| 모멘텀 | (1개월 수익률 백분위 + 3개월 수익률 백분위) / 2 | |
| 외국인수급 | 최근 5거래일 외국인 순매수대금 ÷ 시가총액 백분위 | |
| 종합 | 가치 0.3 + 배당 0.2 + 모멘텀 0.3 + 외국인 0.2 | 4개 중 하나라도 없으면 제외 |

**유니버스**: 시가총액 3천억 원 이상 · 당일 거래대금 10억 원 이상 · 우선주 제외.
기준값은 전부 [`mymoney/config.py`](mymoney/config.py) 한 곳에서 바꾼다.

## 숲 → 돈의 흐름 → 나무

리포트는 **시장 전체(숲)** → **섹터·테마별 돈의 흐름** → **종목 TOP10(나무)** 순서로 읽는다.

- **시장 전체**: KOSPI·KOSDAQ 시총가중 등락, 오른/내린 종목 수, 거래대금(평소 대비), 외국인 5일 순매수
- **테마**: 반도체·2차전지·바이오 등 — 대표 ETF가 실제로 담은 종목 묶음으로 정의 (`config.THEME_ETFS`, 매일 구성 갱신)
- **섹터**: KRX 공식 업종 분류
- 지표: 시장 전체 거래대금 중 비중, 평소(20일 평균) 대비 배수(🔥/🧊), 시총가중 등락(오늘·5일·20일), 외국인 5일 순매수, 비중 추이
- 그룹 구성은 현재 기준을 과거 스냅샷에도 적용하므로, 테마는 오래된 날짜일수록 근사치
- 테마·섹터 줄을 누르면 구성 종목이 펼쳐진다: 종가·등락(오늘/5일)·거래대금·**평소 대비 거래 배수**·**회전율**(거래대금÷시총)·분야 내 비중·외국인 5일·**외국인/거래**(외국인 순매수÷5일 거래대금)
- **🔎 눈여겨볼 점**: 숫자로 확인되는 사실만 규칙 기반 문장으로 풀어 준다 (`mymoney/explain.py`) — 하루 몰림(이벤트성 재평가), 대량 손바뀜(투매/추격), 분야 내 쏠림(개별 이슈), 외국인 순매수의 실제 크기. "싸다/더 빠진다" 같은 결론은 내지 않는다

## 추이 비교 (대시보드)

`docs/index.html` — GitHub Pages로 띄우는 정적 페이지.

- **TOP10 표**: 전일 대비 순위 변동(▲▼ / NEW), 연속 진입 일수, TOP10 이탈 종목, 최근 5·20거래일 등락
- **최근 거래일 종가**: TOP10 종목의 전날·그 전날… 종가 (수집 시 KRX에서 직전 20거래일을 함께 받아 저장)
- **선정 후 추적**: 최근 60일 동안 TOP10에 들었던 종목을 처음 선정된 날부터 매일 종가로 계속 추적 (이탈해도 추적)
- **순위 추이**: 선택한 날의 TOP10이 최근 20일간 몇 위였는지
- **"다음날 보유했다면" 누적 수익률**: d일 TOP10을 동일가중으로 d+1일 보유했을 때
  - 종가→종가 (이론값, 교체율 × 0.3% 비용 차감)
  - 시가→종가 (결과를 보고 다음날 아침 사서 그날 판 경우, 매일 0.3% 비용 차감)
  - 평균 갭(종가→시가) vs 평균 장중(시가→종가)을 분리 표시 → *"보이지만 먹을 수 없는 정보"* 인지 확인
  - 유니버스 동일가중 평균을 기준선으로

## 구조

```
mymoney/
  config.py     기준값 (유니버스 필터, 가중치, 비용)
  collect.py    pykrx로 하루치 전종목 스냅샷 수집
  score.py      스냅샷 → 카테고리별 점수, TOP N
  track.py      저장, 순위 변화, 다음날 성과, 대시보드 데이터 생성
  report.py     Release 본문 마크다운 생성
  __main__.py   CLI
data/
  snapshots/YYYYMMDD.csv.gz   전종목 스냅샷 (성과 계산의 원천)
  top10/YYYYMMDD.json         그날의 카테고리별 TOP10
docs/
  index.html                  대시보드
  data/history.json           대시보드용 집계 (data/로부터 매번 재생성)
```

## 사용법

```bash
pip install -r requirements.txt

export KRX_ID=...   # KRX 정보데이터시스템(data.krx.co.kr) 계정
export KRX_PW=...   # pykrx 1.2.x부터 로그인 필요

python -m mymoney run                    # 최근 영업일 수집 → 저장 → 대시보드 데이터 갱신
python -m mymoney run --date 20261014    # 특정일
python -m mymoney backfill --days 20     # 최근 20영업일 채우기
python -m mymoney show                   # 저장된 최신 TOP10을 터미널로
python -m mymoney build                  # data/ 로부터 history.json만 재생성
python -m mymoney notes                  # Release 본문 마크다운 미리보기

python -m pytest -q                      # 합성 데이터로 점수·추이 로직 테스트
```

대시보드 로컬 확인: `cd docs && python -m http.server` → http://localhost:8000

## 자동화 (GitHub Actions)

`.github/workflows/daily.yml` 이 평일 16:40 KST에 실행되어 결과를 `main`에 커밋하고,
**GitHub Releases** 에 그날의 리포트(`daily-YYYYMMDD`)를 게시한다.
카테고리별 TOP10 표(전일대비 순위 변동·연속 진입일·이탈 종목)와 누적 성과 요약이 본문에 들어가고,
원본 JSON이 첨부된다. 저장소의 **Releases** 탭이 날짜별 기록 목록이 된다.

1. **Settings → Secrets and variables → Actions** 에 `KRX_ID`, `KRX_PW` 등록
2. (선택) **Settings → Pages** → Source: *Deploy from a branch*, Branch: `main` / `/docs` — 차트 대시보드
3. **Actions → daily-top10 → Run workflow** 로 첫 실행 (날짜를 넣어 과거 며칠을 백필하면 추이가 바로 보인다)

휴장일에는 가장 가까운 이전 영업일로 잡히고, 이미 수집된 날짜면 건너뛴다.
장중(16시 이전)에 날짜 없이 실행하면 아직 확정되지 않은 오늘 대신 전 영업일을 수집한다.

**과거 채우기(백필)**: Run workflow 에서 `backfill_days` 에 20을 넣으면 최근 20영업일을 오래된 날부터 채우고,
날짜별 Release도 모두 만들거나 갱신한다. 순위 변화·연속 진입·선정 후 추적이 바로 의미를 갖는다.

## 한계 (알고 쓰기)

- 성과는 **동일가중·슬리피지 무시·체결 가정**이다. 실전 수익이 아니다.
- 데이터는 장 마감 후 나오므로 **종가→종가는 실제로 먹을 수 없는 숫자**다. 시가→종가가 현실에 가깝다.
- 기간이 짧을 때의 승률·누적수익은 노이즈다. 최소 수개월, 상승·하락·횡보장을 모두 지나야 의미가 생긴다.
- 성장률(매출·EPS YoY) 기반 PEG는 OpenDART 연동이 필요해 아직 미포함.

*투자 권유가 아닌 개인 학습 기록입니다.*
