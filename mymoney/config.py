"""스크리너 설정값. 기준을 바꾸고 싶으면 이 파일만 수정한다."""

# 유니버스 필터: 유동성이 너무 낮은 종목은 점수 계산 대상에서 제외
MIN_MARKET_CAP = 300_000_000_000      # 시가총액 3천억 원 이상
MIN_TRADING_VALUE = 1_000_000_000     # 당일 거래대금 10억 원 이상
EXCLUDE_PREFERRED = True              # 우선주(이름이 '우', '우B' 등으로 끝남) 제외

TOP_N = 10

# 다음날 수익률 추적 시 리밸런싱 비용 (세금·수수료·스프레드 왕복 근사치)
ROUND_TRIP_COST = 0.003

# 카테고리 정의: key -> (표시 이름, 설명)
CATEGORIES = {
    "value":     ("가치",       "PER·PBR이 낮을수록 높은 점수 (적자 제외)"),
    "dividend":  ("배당",       "배당수익률이 높을수록 높은 점수 (적자 제외)"),
    "momentum":  ("모멘텀",     "최근 1개월·3개월 수익률이 높을수록 높은 점수"),
    "foreign":   ("외국인수급", "최근 5거래일 외국인 순매수대금 ÷ 시가총액"),
    "composite": ("종합",       "위 4개 점수의 가중 평균"),
}

COMPOSITE_WEIGHTS = {
    "value": 0.3,
    "dividend": 0.2,
    "momentum": 0.3,
    "foreign": 0.2,
}

# 모멘텀/수급 계산 기간 (달력 기준 일수, 영업일 수가 아님)
MOMENTUM_SHORT_DAYS = 30
MOMENTUM_LONG_DAYS = 90
FOREIGN_LOOKBACK_BUSINESS_DAYS = 5
