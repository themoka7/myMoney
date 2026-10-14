"""일별 결과 저장과 추이 계산.

data/snapshots/YYYYMMDD.csv.gz  전종목 스냅샷 (다음날 수익률 계산의 원천)
data/top10/YYYYMMDD.json        그날의 카테고리별 TOP N
docs/data/history.json          대시보드용 집계 (매번 위 파일들로부터 재생성)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config
from .score import filter_universe

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "snapshots"
TOP_DIR = ROOT / "data" / "top10"
SITE_FILE = ROOT / "docs" / "data" / "history.json"


# ---------- 저장 ----------

def save_day(date: str, snap: pd.DataFrame, top: dict, universe_size: int,
             snap_dir: Path = SNAP_DIR, top_dir: Path = TOP_DIR) -> None:
    snap_dir.mkdir(parents=True, exist_ok=True)
    top_dir.mkdir(parents=True, exist_ok=True)
    snap.to_csv(snap_dir / f"{date}.csv.gz", encoding="utf-8")
    payload = {"date": date, "universe_size": universe_size, "categories": top}
    (top_dir / f"{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def load_tops(top_dir: Path = TOP_DIR) -> dict[str, dict]:
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(top_dir.glob("*.json"))
    }


def load_snapshot(date: str, snap_dir: Path = SNAP_DIR) -> pd.DataFrame | None:
    p = snap_dir / f"{date}.csv.gz"
    if not p.exists():
        return None
    return pd.read_csv(p, dtype={"ticker": str}, index_col="ticker")


# ---------- 순위 변화 ----------

def annotate_changes(tops: dict[str, dict]) -> dict[str, dict]:
    """각 종목에 전일 순위(prev_rank), 연속 진입일(streak)을, 각 날짜에 이탈 종목(dropped)을 붙인다."""
    dates = sorted(tops)
    out: dict[str, dict] = {}
    prev: dict[str, dict[str, dict]] = {}  # cat -> ticker -> annotated item
    for d in dates:
        day = {"date": d, "universe_size": tops[d].get("universe_size"), "categories": {}, "dropped": {}}
        for cat in config.CATEGORIES:
            items = tops[d]["categories"].get(cat, [])
            before = prev.get(cat, {})
            annotated = []
            for it in items:
                p = before.get(it["ticker"])
                annotated.append({
                    **it,
                    "prev_rank": p["rank"] if p else None,
                    "streak": (p["streak"] + 1) if p else 1,
                })
            today = {it["ticker"] for it in items}
            day["dropped"][cat] = [
                {"ticker": t, "name": v["name"], "prev_rank": v["rank"]}
                for t, v in before.items() if t not in today
            ]
            day["categories"][cat] = annotated
            prev[cat] = {it["ticker"]: it for it in annotated}
        out[d] = day
    return out


# ---------- 성과 추적 ----------

def _mean_ret(num: pd.Series, den: pd.Series) -> float | None:
    r = (num / den - 1).replace([float("inf"), float("-inf")], pd.NA).dropna()
    return float(r.mean()) if len(r) else None


def performance(tops: dict[str, dict], load=load_snapshot) -> dict[str, list[dict]]:
    """d일 TOP N을 d+1일에 보유했다면? 을 카테고리별로 계산한다.

    - c2c     : d 종가 → d+1 종가 (이론값. 데이터가 장 마감 후 나오므로 실제로는 d 종가 매수 불가)
    - gap     : d 종가 → d+1 시가 (밤사이 반영분. 미리 사두지 않으면 못 먹는 구간)
    - intraday: d+1 시가 → d+1 종가 (장 마감 후 결과를 보고 다음날 아침 사는 경우 실제 먹을 수 있는 구간)
    - c2c_net : c2c - 교체비율 × 왕복비용
    - intraday_net: intraday - 왕복비용 (매일 사고 팖)
    'universe'는 같은 날 유니버스 전체 동일가중 평균 (비교 기준선).
    """
    dates = sorted(tops)
    result: dict[str, list[dict]] = {cat: [] for cat in config.CATEGORIES}
    result["universe"] = []
    prev_members: dict[str, set] = {}

    for d0, d1 in zip(dates, dates[1:]):
        s0, s1 = load(d0), load(d1)
        if s0 is None or s1 is None:
            prev_members = {}
            continue
        groups = {cat: [it["ticker"] for it in tops[d0]["categories"].get(cat, [])]
                  for cat in config.CATEGORIES}
        groups["universe"] = list(filter_universe(s0).index)

        for cat, tickers in groups.items():
            t = [x for x in tickers if x in s0.index and x in s1.index]
            if not t:
                continue
            c0, o1, c1 = s0.loc[t, "close"], s1.loc[t, "open"], s1.loc[t, "close"]
            c2c, gap, intra = _mean_ret(c1, c0), _mean_ret(o1, c0), _mean_ret(c1, o1)
            if cat == "universe":
                turnover = 0.0
            else:
                before = prev_members.get(cat)
                turnover = 1.0 if before is None else len(set(tickers) - before) / max(len(tickers), 1)
                prev_members[cat] = set(tickers)
            result[cat].append({
                "date": d1,
                "c2c": c2c,
                "gap": gap,
                "intraday": intra,
                "turnover": round(turnover, 3),
                "c2c_net": None if c2c is None else c2c - turnover * config.ROUND_TRIP_COST,
                "intraday_net": None if intra is None else intra - config.ROUND_TRIP_COST,
            })
    return result


# ---------- 대시보드 데이터 ----------

def build_site(top_dir: Path = TOP_DIR, snap_dir: Path = SNAP_DIR,
               site_file: Path = SITE_FILE) -> dict:
    tops = load_tops(top_dir)
    data = {
        "categories": {
            k: {"label": v[0], "desc": v[1], "easy": config.CATEGORY_GUIDE[k][0],
                "caution": config.CATEGORY_GUIDE[k][2]}
            for k, v in config.CATEGORIES.items()
        },
        "top_n": config.TOP_N,
        "round_trip_cost": config.ROUND_TRIP_COST,
        "dates": sorted(tops),
        "days": annotate_changes(tops),
        "performance": performance(tops, load=lambda d: load_snapshot(d, snap_dir)),
    }
    site_file.parent.mkdir(parents=True, exist_ok=True)
    site_file.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return data
