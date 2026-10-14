"""KRX에서 하루치 전종목 스냅샷을 수집한다 (pykrx).

pykrx 1.2.x부터는 KRX 정보데이터시스템 로그인이 필요하다.
환경 변수 KRX_ID, KRX_PW 를 설정해야 한다 (GitHub Actions에서는 Secrets로 주입).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import config

MARKETS = ("KOSPI", "KOSDAQ")


RETRY_WAITS = (10, 30, 90)  # KRX가 연속 호출을 막으면(비JSON 응답·빈 결과) 쉬었다가 재시도
CALL_INTERVAL = 0.5


class _Retrying:
    """pykrx.stock 래퍼: 모든 호출에 간격·재시도를 건다. 빈 DataFrame/리스트도 실패로 본다."""

    def __init__(self, mod):
        self._mod = mod

    def __getattr__(self, name):
        fn = getattr(self._mod, name)

        def call(*args, **kwargs):
            last = None
            for wait in (0, *RETRY_WAITS):
                if wait:
                    print(f"  KRX 응답 이상 ({name}: {last}) → {wait}초 후 재시도", file=sys.stderr)
                time.sleep(wait or CALL_INTERVAL)
                try:
                    out = fn(*args, **kwargs)
                except Exception as e:  # pykrx는 내부 오류를 삼키고 빈 값을 주기도, 던지기도 한다
                    last = e
                    continue
                if (isinstance(out, pd.DataFrame) and out.empty) or (isinstance(out, list) and not out):
                    last = "빈 결과"
                    continue
                return out
            raise RuntimeError(f"{name} 실패: {last}")

        return call


_STOCK = None


def _stock():
    global _STOCK
    if _STOCK is None:
        from pykrx import stock  # 무거운 import는 수집 시점에만

        _STOCK = _Retrying(stock)
    return _STOCK


KST = timezone(timedelta(hours=9))
MARKET_FINAL_HOUR = 16  # 장 마감(15:30) 후 KRX 데이터가 확정되는 시각 근사치


def latest_business_day(date: str | None = None) -> str:
    """date(YYYYMMDD) 이하의 가장 가까운 영업일. date가 없으면 '데이터가 확정된' 가장 최근 영업일."""
    if date is None:
        now = datetime.now(KST)
        if now.hour < MARKET_FINAL_HOUR:  # 장중·장 시작 전이면 오늘은 아직 미확정
            now -= timedelta(days=1)
        date = now.strftime("%Y%m%d")
    return _stock().get_nearest_business_day_in_a_week(date, prev=True)


def business_days(end: str, count: int) -> list[str]:
    """end 이하 최근 count개 영업일 (오래된 순)."""
    days = _stock().get_previous_business_days(fromdate=_shift(end, count * 2 + 15), todate=end)
    return [pd.Timestamp(x).strftime("%Y%m%d") for x in days][-count:]


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
    # 종목명: 기간 등락률 표에는 최근 상장 종목이 빠질 수 있어 여러 출처를 겹쳐 쓴다
    df["name"] = short["종목명"].reindex(df.index).combine_first(long_["종목명"].reindex(df.index))
    df["name"] = df["name"].combine_first(foreign["종목명"].reindex(df.index))
    for t in df.index[df["name"].isna()]:
        try:
            df.loc[t, "name"] = stock.get_market_ticker_name(t)
        except Exception:
            df.loc[t, "name"] = t
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


def recent_closes(date: str, tickers: list[str], days: int = config.PRICE_HISTORY_DAYS,
                  cached=lambda d: None) -> dict[str, list[list]]:
    """tickers의 date 이전 days거래일 종가. {ticker: [[YYYYMMDD, close], ...]} (오래된 순, date 제외).

    cached(d)가 스냅샷 DataFrame을 돌려주면 KRX 호출 없이 그걸 쓴다.
    """
    stock = _stock()
    biz = [pd.Timestamp(x).strftime("%Y%m%d")
           for x in stock.get_previous_business_days(fromdate=_shift(date, days * 2 + 15), todate=date)]
    prev = [d for d in biz if d < date][-days:]
    out: dict[str, list[list]] = {t: [] for t in tickers}
    for d in prev:
        snap = cached(d)
        if snap is not None:
            close = snap["close"]
        else:
            df = stock.get_market_ohlcv(d, market="ALL")
            df.index = df.index.astype(str).str.zfill(6)
            close = df["종가"]
        for t in tickers:
            if t in close.index and pd.notna(close[t]):
                out[t].append([d, float(close[t])])
    return out


def sector_map(date: str) -> pd.Series:
    """종목코드 -> KRX 업종명."""
    stock = _stock()
    parts = []
    for m in MARKETS:
        df = stock.get_market_sector_classifications(date, m)
        df.index = df.index.astype(str).str.zfill(6)
        parts.append(df["업종명"])
    out = pd.concat(parts)
    out.index.name = "ticker"
    return out[~out.index.duplicated()]


def theme_members(date: str) -> dict[str, dict]:
    """테마명 -> {etf, etf_name, tickers}. 실패한 테마는 경고만 하고 뺀다."""
    stock = _stock()
    out = {}
    for theme, etf in config.THEME_ETFS.items():
        try:
            pdf = stock.get_etf_portfolio_deposit_file(etf, date)
            name = stock.get_etf_ticker_name(etf)
        except Exception as e:
            print(f"  테마 '{theme}'({etf}) 구성 조회 실패: {e}", file=sys.stderr)
            continue
        tickers = [t for t in pdf.index.astype(str) if t.isdigit() and len(t) == 6]
        out[theme] = {"etf": etf, "etf_name": str(name), "tickers": tickers}
        print(f"  테마 {theme}: {name} ({len(tickers)}종목)")
    return out
