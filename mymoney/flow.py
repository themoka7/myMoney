"""섹터·테마별 '돈의 흐름'.

그룹(섹터 또는 테마)마다, 날짜별로:
    value      거래대금 합 (원)
    share      시장 전체 거래대금 중 비중 — 돈이 어디에 몰렸나
    heat       share ÷ 직전 FLOW_BASELINE_DAYS 기록일 평균 share — 평소보다 몇 배 몰렸나
    ret        시가총액 가중 당일 등락률 (전 기록일 종가 대비)
    foreign_5d 외국인 최근 5거래일 순매수대금 합 (원)
    n          그날 거래된 종목 수

그룹 구성은 '현재' 기준(업종 분류, ETF 구성)을 과거 스냅샷에도 그대로 적용한다.
업종은 거의 안 바뀌지만, 테마 ETF 구성은 리밸런싱으로 바뀌므로 오래된 날짜일수록 근사치다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config

ROOT = Path(__file__).resolve().parent.parent
META_DIR = ROOT / "data" / "meta"
SECTOR_FILE = META_DIR / "sectors.csv"
THEME_FILE = META_DIR / "themes.json"


# ---------- 그룹 정의 저장/로드 ----------

def save_meta(sectors: pd.Series, themes: dict, meta_dir: Path = META_DIR) -> None:
    meta_dir.mkdir(parents=True, exist_ok=True)
    sectors.rename("sector").to_csv(meta_dir / SECTOR_FILE.name, encoding="utf-8")
    (meta_dir / THEME_FILE.name).write_text(json.dumps(themes, ensure_ascii=False, indent=1), encoding="utf-8")


def load_groups(meta_dir: Path = META_DIR) -> dict[str, dict[str, list[str]]]:
    """{"sector": {업종명: [tickers]}, "theme": {테마명: [tickers]}}. 파일이 없으면 빈 dict."""
    groups: dict[str, dict[str, list[str]]] = {"sector": {}, "theme": {}}
    sf, tf = meta_dir / SECTOR_FILE.name, meta_dir / THEME_FILE.name
    if sf.exists():
        s = pd.read_csv(sf, dtype={"ticker": str}).dropna()
        groups["sector"] = {k: list(v) for k, v in s.groupby("sector")["ticker"]}
    if tf.exists():
        groups["theme"] = {k: v["tickers"] for k, v in json.loads(tf.read_text(encoding="utf-8")).items()}
    return groups


def theme_labels(meta_dir: Path = META_DIR) -> dict[str, str]:
    tf = meta_dir / THEME_FILE.name
    if not tf.exists():
        return {}
    return {k: v["etf_name"] for k, v in json.loads(tf.read_text(encoding="utf-8")).items()}


def market_groups(snap: pd.DataFrame | None) -> dict[str, list[str]]:
    """시장 전체(숲): 전체 / KOSPI / KOSDAQ."""
    if snap is None:
        return {}
    groups = {"전체": list(snap.index)}
    for m, idx in snap.groupby("market").groups.items():
        groups[str(m)] = list(idx)
    return groups


# ---------- 계산 ----------

def _day_metrics(snap: pd.DataFrame, prev: pd.DataFrame | None, members: dict[str, list[str]]) -> dict:
    total = snap["trading_value"].sum()
    if prev is not None:
        ret = (snap["close"] / prev["close"].reindex(snap.index) - 1).replace([float("inf"), float("-inf")], pd.NA)
    else:
        ret = pd.Series(pd.NA, index=snap.index, dtype="Float64")
    out = {}
    for name, tickers in members.items():
        idx = snap.index.intersection(tickers)
        g = snap.loc[idx]
        g = g[g["trading_value"] > 0]
        if g.empty:
            continue
        r = pd.to_numeric(ret.reindex(g.index), errors="coerce")
        w = g["market_cap"].where(r.notna())
        out[name] = {
            "up": int((r > 0).sum()), "down": int((r < 0).sum()),
            "value": float(g["trading_value"].sum()),
            "share": float(g["trading_value"].sum() / total) if total else None,
            "ret": float((r * w).sum() / w.sum()) if w.sum() else None,
            "foreign_5d": float(g["foreign_net_5d"].sum()) if "foreign_net_5d" in g else None,
            "n": int(len(g)),
        }
    return out


def compute(dates: list[str], load, groups: dict[str, list[str]]) -> dict[str, dict[str, dict]]:
    """{date: {group: metrics}}. heat는 직전 기록일들의 평균 share 대비 배수."""
    out: dict[str, dict[str, dict]] = {}
    prev = None
    for d in sorted(dates):
        snap = load(d)
        if snap is None:
            prev = None
            continue
        out[d] = _day_metrics(snap, prev, groups)
        prev = snap
    ordered = sorted(out)
    for i, d in enumerate(ordered):
        base = ordered[max(0, i - config.FLOW_BASELINE_DAYS):i]
        for name, m in out[d].items():
            past = [out[b][name]["share"] for b in base if name in out[b] and out[b][name]["share"]]
            m["heat"] = (m["share"] / (sum(past) / len(past))) if past and m["share"] else None
    return out


def series(flows: dict[str, dict[str, dict]], name: str, key: str, until: str) -> list[float | None]:
    return [flows[d].get(name, {}).get(key) for d in sorted(flows) if d <= until]


def compound(vals: list[float | None]) -> float | None:
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    acc = 1.0
    for v in vals:
        acc *= 1 + v
    return acc - 1


def members(snap: pd.DataFrame, prev: pd.DataFrame | None, prev5: pd.DataFrame | None,
            tickers: list[str], limit: int | None = None) -> list[dict]:
    """그룹 구성 종목별 오늘 모습. 거래대금 큰 순."""
    idx = snap.index.intersection(tickers)
    g = snap.loc[idx]
    g = g[g["trading_value"] > 0].sort_values("trading_value", ascending=False)
    total = g["trading_value"].sum()
    if limit:
        g = g.head(limit)

    def chg(base):
        if base is None:
            return {}
        r = g["close"] / base["close"].reindex(g.index) - 1
        return {t: float(v) for t, v in r.items() if pd.notna(v) and abs(v) != float("inf")}

    r1, r5 = chg(prev), chg(prev5)
    return [{
        "ticker": t,
        "name": row["name"] if isinstance(row["name"], str) else t,
        "close": float(row["close"]),
        "ret": r1.get(t),
        "ret5": r5.get(t),
        "value": float(row["trading_value"]),
        "weight": float(row["trading_value"] / total) if total else None,
        "foreign_5d": float(row["foreign_net_5d"]) if "foreign_net_5d" in row and pd.notna(row["foreign_net_5d"]) else None,
    } for t, row in g.iterrows()]


def members_by_date(dates: list[str], load, groups: dict[str, dict[str, list[str]]],
                    flows: dict[str, dict], keep_days: int = 60, sector_top: int = 10,
                    sector_limit: int = 15) -> dict[str, dict]:
    """{date: {"theme": {이름: [종목...]}, "sector": {...}}}. 섹터는 비중 상위 sector_top개만, 종목은 sector_limit개까지."""
    ordered = [d for d in sorted(dates) if load(d) is not None]
    out = {}
    for i, d in enumerate(ordered):
        if i < len(ordered) - keep_days:
            continue
        snap = load(d)
        prev = load(ordered[i - 1]) if i >= 1 else None
        prev5 = load(ordered[i - 5]) if i >= 5 else None
        day = {"theme": {n: members(snap, prev, prev5, t) for n, t in groups.get("theme", {}).items()}}
        sec_day = flows.get("sector", {}).get(d, {})
        top = sorted(sec_day, key=lambda n: -sec_day[n]["share"])[:sector_top]
        hot = sorted((n for n in sec_day if sec_day[n].get("heat") and sec_day[n]["share"] >= 0.01),
                     key=lambda n: -sec_day[n]["heat"])[:5]
        day["sector"] = {n: members(snap, prev, prev5, groups["sector"][n], limit=sector_limit)
                         for n in dict.fromkeys(top + hot) if n in groups.get("sector", {})}
        out[d] = day
    return out
