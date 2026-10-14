"""스냅샷 DataFrame -> 카테고리별 점수와 TOP N.

입력 스냅샷 컬럼 (index = 종목코드 6자리):
    name, market, close, market_cap, trading_value,
    per, pbr, div, ret_1m, ret_3m, foreign_net_5d

모든 점수는 유니버스 내 백분위(0~100). 절대값이 아니라 '오늘 시장 안에서의 상대 순위'다.
"""
from __future__ import annotations

import re

import pandas as pd

from . import config

_PREFERRED = re.compile(r"\d*우[A-C]?$|우\(전환\)$")


def filter_universe(snap: pd.DataFrame) -> pd.DataFrame:
    df = snap[
        (snap["market_cap"] >= config.MIN_MARKET_CAP)
        & (snap["trading_value"] >= config.MIN_TRADING_VALUE)
        & (snap["close"] > 0)
    ]
    if config.EXCLUDE_PREFERRED:
        df = df[~df["name"].astype(str).str.contains(_PREFERRED)]
    return df


def _pct(s: pd.Series, ascending: bool = True) -> pd.Series:
    """백분위 점수(0~100). ascending=False면 값이 작을수록 높은 점수."""
    r = s.rank(pct=True, ascending=ascending, method="average")
    return (r * 100).round(2)


def score(snap: pd.DataFrame) -> pd.DataFrame:
    """유니버스 종목별 카테고리 점수를 계산한다. 계산 불가 항목은 NaN."""
    u = filter_universe(snap).copy()
    out = pd.DataFrame(index=u.index)

    profitable = u[(u["per"] > 0) & (u["pbr"] > 0)]
    out["value"] = (
        (_pct(profitable["per"], ascending=False) + _pct(profitable["pbr"], ascending=False)) / 2
    )

    payers = u[(u["div"] > 0) & (u["per"] > 0)]
    out["dividend"] = _pct(payers["div"])

    mom = u.dropna(subset=["ret_1m", "ret_3m"])
    out["momentum"] = (_pct(mom["ret_1m"]) + _pct(mom["ret_3m"])) / 2

    flow = u.dropna(subset=["foreign_net_5d"])
    out["foreign"] = _pct(flow["foreign_net_5d"] / flow["market_cap"])

    w = pd.Series(config.COMPOSITE_WEIGHTS)
    parts = out[w.index]
    # 4개 중 하나라도 없으면(적자, 무배당 등) 종합 점수는 계산하지 않는다
    out["composite"] = (parts * w).sum(axis=1, min_count=len(w)).where(parts.notna().all(axis=1))

    return out.round(2).join(u[["name", "market", "close"]])


def top_n(scores: pd.DataFrame, n: int = config.TOP_N) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for cat in config.CATEGORIES:
        ranked = scores.dropna(subset=[cat]).sort_values(
            [cat, "close"], ascending=[False, False]
        ).head(n)
        result[cat] = [
            {
                "rank": i + 1,
                "ticker": str(t),
                "name": row["name"],
                "market": row["market"],
                "score": float(row[cat]),
                "close": float(row["close"]),
            }
            for i, (t, row) in enumerate(ranked.iterrows())
        ]
    return result
