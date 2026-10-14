"""KRX에서 하루치 전종목 스냅샷을 수집한다 (pykrx).

pykrx 1.2.x부터는 KRX 정보데이터시스템 로그인이 필요하다.
환경 변수 KRX_ID, KRX_PW 를 설정해야 한다 (GitHub Actions에서는 Secrets로 주입).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from . import config

MARKETS = ("KOSPI", "KOSDAQ")


def _stock():
    from pykrx import stock  # 무거운 import는 수집 시점에만

    return stock


def latest_business_day(date: str | None = None) -> str:
    """date(YYYYMMDD) 이하의 가장 가까운 영업일."""
    date = date or datetime.now().strftime("%Y%m%d")
    return _stock().get_nearest_business_day_in_a_week(date, prev=True)


def _shift(date: str, days: int) -> str:
    return (datetime.strptime(date, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")


def _market_snapshot(stock, date: str, market: str) -> pd.DataFrame:
    cap = stock.get_market_cap(date, market=market)[["종가", "시가총액", "거래대금"]]
    fund = stock.get_market_fundamental(date, market=market)[["PER", "PBR", "DIV"]]
    ohlcv = stock.get_market_ohlcv(date, market=market)[["시가"]]

    short = stock.get_market_price_change(_shift(date, config.MOMENTUM_SHORT_DAYS), date, market=market)
    long_ = stock.get_market_price_change(_shift(date, config.MOMENTUM_LONG_DAYS), date, market=market)

    days = stock.get_previous_business_days(
        fromdate=_shift(date, 20), todate=date
    )[-config.FOREIGN_LOOKBACK_BUSINESS_DAYS:]
    start = pd.Timestamp(days[0]).strftime("%Y%m%d")
    foreign = stock.get_market_net_purchases_of_equities(start, date, market, "외국인")

    df = pd.DataFrame(index=cap.index)
    df["name"] = short["종목명"]
    df["market"] = market
    df["open"] = ohlcv["시가"]
    df["close"] = cap["종가"]
    df["market_cap"] = cap["시가총액"]
    df["trading_value"] = cap["거래대금"]
    df["per"] = fund["PER"]
    df["pbr"] = fund["PBR"]
    df["div"] = fund["DIV"]
    df["ret_1m"] = short["등락률"]
    df["ret_3m"] = long_["등락률"]
    df["foreign_net_5d"] = foreign["순매수거래대금"].reindex(df.index).fillna(0)
    return df


def collect(date: str) -> pd.DataFrame:
    stock = _stock()
    frames = [_market_snapshot(stock, date, m) for m in MARKETS]
    df = pd.concat(frames)
    df.index = df.index.astype(str).str.zfill(6)
    df.index.name = "ticker"
    if df["close"].fillna(0).sum() == 0:
        raise RuntimeError(f"{date}: 시세 데이터가 비어 있습니다 (휴장일이거나 KRX 로그인 실패)")
    return df
