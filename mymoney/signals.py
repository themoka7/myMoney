"""🔎 해설 규칙의 자기검증.

리포트가 "급락 다음날 되돌림이 나오기 쉽다" 같은 말을 한다면, 그 말이 실제로 맞았는지 스스로 채점한다.
규칙은 유니버스 전체(거래대금 50억 이상)에 매일 적용하고, 결과는 저장된 다음 스냅샷들로 채운다.

data/signals.csv  — 규칙 발동 기록과 이후 결과 (매 빌드마다 스냅샷으로부터 재생성)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config

ROOT = Path(__file__).resolve().parent.parent
SIGNAL_FILE = ROOT / "data" / "signals.csv"

MIN_VALUE = 50e8      # 거래대금 50억 미만은 배수 지표가 의미 없이 튄다
MAX_TURNOVER = 1.0    # 회전율 100% 초과는 데이터 검증 대상 — 채점에서 뺀다
MIN_SAMPLE = 20

# rule_id -> (리포트 문구, '적중' 정의 설명)
RULES = {
    "EVENT_DROP":   ("급락 다음날 되돌림이 나오기 쉽다", "다음날 종가가 오름"),
    "EVENT_JUMP":   ("급등 다음날 되돌림이 나오기 쉽다", "다음날 종가가 내림"),
    "CAPITULATION": ("투매. 바닥 신호일 수도", "다음날 종가가 오름"),
    "CHASE_RISK":   ("따라 사면 고점에 물릴 위험", "다음날 종가가 내림"),
    "FOREIGN_LED":  ("외국인 주도", "5일 뒤 주가가 외국인 방향으로 감"),
}


def fired(ret, ret5, heat, fv) -> list[str]:
    """한 종목·하루에 발동한 규칙들. explain.py의 문장과 같은 기준."""
    out = []
    if ret is not None and abs(ret) >= 0.05 and ret5 is not None and (
            (ret * ret5 > 0 and abs(ret) >= 0.6 * abs(ret5)) or abs(ret) > abs(ret5)):
        out.append("EVENT_DROP" if ret < 0 else "EVENT_JUMP")
    if ret is not None and heat is not None and heat >= 3:
        if ret <= -0.05:
            out.append("CAPITULATION")
        elif ret >= 0.05:
            out.append("CHASE_RISK")
    if fv is not None and abs(fv) >= 0.2:
        out.append("FOREIGN_LED")
    return out


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


def build(dates: list[str], load) -> pd.DataFrame:
    """기록된 모든 날짜에 규칙을 적용하고, 이후 스냅샷으로 결과를 채운다."""
    ordered = [d for d in sorted(dates) if load(d) is not None]
    rows = []
    for i, d in enumerate(ordered):
        if i == 0:
            continue
        snap, prev = load(d), load(ordered[i - 1])
        past = [load(x)["trading_value"] for x in ordered[max(0, i - config.FLOW_BASELINE_DAYS):i]]
        base = pd.concat(past, axis=1).mean(axis=1).reindex(snap.index) if past else None
        last5 = [load(x)["trading_value"] for x in ordered[max(0, i - 4):i]]
        v5 = (pd.concat(last5, axis=1).sum(axis=1).reindex(snap.index).fillna(0) if last5 else 0) + snap["trading_value"]
        nxt = load(ordered[i + 1]) if i + 1 < len(ordered) else None
        n5 = load(ordered[i + 5]) if i + 5 < len(ordered) else None

        g = snap[(snap["trading_value"] >= MIN_VALUE) & (snap["market_cap"] > 0)]
        g = g[g["trading_value"] / g["market_cap"] <= MAX_TURNOVER]
        ret = g["close"] / prev["close"].reindex(g.index) - 1
        if "ret_5d" in g:
            ret5 = g["ret_5d"]
        elif i >= 5:
            ret5 = g["close"] / load(ordered[i - 5])["close"].reindex(g.index) - 1
        else:
            ret5 = pd.Series(float("nan"), index=g.index)
        for t in g.index:
            heat = _num(g.loc[t, "trading_value"] / base[t]) if base is not None and base.get(t) else None
            f5 = _num(g.loc[t, "foreign_net_5d"]) if "foreign_net_5d" in g else None
            fv = f5 / v5[t] if f5 is not None and v5[t] else None
            for rule in fired(_num(ret[t]), _num(ret5[t]), heat, fv):
                close = float(g.loc[t, "close"])
                no = _num(nxt.loc[t, "open"]) if nxt is not None and t in nxt.index else None
                nc = _num(nxt.loc[t, "close"]) if nxt is not None and t in nxt.index else None
                c5 = _num(n5.loc[t, "close"]) if n5 is not None and t in n5.index else None
                rows.append({
                    "date": d, "ticker": t, "name": g.loc[t, "name"], "rule_id": rule,
                    "ret": _num(ret[t]), "foreign_5d": f5, "close": close, "next_open": no, "next_close": nc,
                    "ret_gap": no / close - 1 if no and close else None,
                    "ret_intraday": nc / no - 1 if nc and no else None,
                    "ret_c2c": nc / close - 1 if nc and close else None,
                    "ret_5d": c5 / close - 1 if c5 and close else None,
                })
    cols = ["date", "ticker", "name", "rule_id", "ret", "foreign_5d", "close", "next_open", "next_close",
            "ret_gap", "ret_intraday", "ret_c2c", "ret_5d"]
    return pd.DataFrame(rows, columns=cols)


def _hit(rule: str, r: pd.Series) -> bool | None:
    if rule in ("EVENT_DROP", "CAPITULATION"):
        return None if pd.isna(r["ret_c2c"]) else r["ret_c2c"] > 0
    if rule in ("EVENT_JUMP", "CHASE_RISK"):
        return None if pd.isna(r["ret_c2c"]) else r["ret_c2c"] < 0
    if rule == "FOREIGN_LED":
        return None if pd.isna(r["ret_5d"]) or not r["foreign_5d"] else (r["ret_5d"] > 0) == (r["foreign_5d"] > 0)
    return None


def scorecard(sig: pd.DataFrame) -> dict[str, dict]:
    card = {}
    for rule in RULES:
        s = sig[sig["rule_id"] == rule]
        hits = [h for h in (_hit(rule, r) for _, r in s.iterrows()) if h is not None]
        n = len(hits)
        hit = sum(hits) / n if n else None
        gap = s["ret_gap"].mean() if s["ret_gap"].notna().any() else None
        intra = s["ret_intraday"].mean() if s["ret_intraday"].notna().any() else None
        card[rule] = {
            "fired": int(len(s)), "n": n, "hit": hit, "gap": gap, "intraday": intra,
            "c2c": s["ret_c2c"].mean() if s["ret_c2c"].notna().any() else None,
            "d5": s["ret_5d"].mean() if s["ret_5d"].notna().any() else None,
            "verdict": verdict(rule, n, hit, gap, intra),
        }
    return card


def verdict(rule: str, n: int, hit, gap, intra) -> str:
    if n < MIN_SAMPLE or hit is None:
        return "표본 부족"
    v = "맞는 편" if hit > 0.55 else ("근거 약함" if hit >= 0.45 else "반대로 나옴")
    # 되돌림을 노리는 규칙인데 갭에서만 반영되고 장중엔 못 먹는 경우
    rebound_up = rule in ("EVENT_DROP", "CAPITULATION")
    rebound_dn = rule in ("EVENT_JUMP", "CHASE_RISK")
    if gap is not None and intra is not None and (
            (rebound_up and gap > 0 and intra <= 0) or (rebound_dn and gap < 0 and intra >= 0)):
        v += " · 갭에서만 반영(보이지만 먹을 수 없는 신호)"
    return v


def save(sig: pd.DataFrame, path: Path = SIGNAL_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = sig.copy()
    out["date"] = out["date"].map(lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}")
    out.to_csv(path, index=False, float_format="%.6g", encoding="utf-8")


def as_of(sig: pd.DataFrame, date: str, dates: list[str]) -> pd.DataFrame:
    """date 시점에 이미 결과가 확정된 것만 남긴다 (미래 결과로 과거 리포트를 채점하지 않게)."""
    ordered = sorted(dates)
    pos = {d: i for i, d in enumerate(ordered)}
    if date not in pos or sig.empty:
        return sig.iloc[0:0]
    now = pos[date]
    s = sig[sig["date"].map(pos) < now].copy()
    late = s["date"].map(pos) + 5 > now
    s.loc[late, "ret_5d"] = float("nan")
    return s
