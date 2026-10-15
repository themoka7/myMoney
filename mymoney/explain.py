"""종목 한 줄(숫자)을 '표가 말해주는 사실' 문장으로 풀어 준다.

원칙: 숫자로 확인되는 것만 말하고, '싸다/더 빠진다/사라' 같은 결론은 내지 않는다.
각 규칙은 (문장, 중요도)를 낸다. 중요도가 높은 종목부터 보여 준다.
"""
from __future__ import annotations


def _p(v: float) -> str:
    return f"{v * 100:+.1f}%"


def _won(v: float) -> str:
    sign = "+" if v > 0 else ""
    return f"{sign}{v / 1e12:,.1f}조" if abs(v) >= 1e12 else f"{sign}{v / 1e8:,.0f}억"


MIN_VALUE = 50e8             # 거래대금 50억 미만은 '평소 대비' 같은 배수가 의미 없이 튄다
SPOTLIGHT_MIN_VALUE = 300e8  # 전체 하이라이트는 거래대금 300억 이상만
MARKET_MOVER_SHARE = 0.05    # 시장 전체 외국인 순매수(같은 방향)의 5% 이상이면 '시장 수급 주도'
MAX_TURNOVER = 1.0           # 회전율 100% 초과는 '데이터 점검' 대상 — 해설하지 않는다

_CARD: dict = {}  # signals.scorecard() 결과. 문장 끝에 그 규칙의 과거 성적을 붙인다


def set_scorecard(card: dict) -> None:
    _CARD.clear()
    _CARD.update(card or {})


def evidence(rule: str) -> str:
    c = _CARD.get(rule)
    if not c:
        return ""
    if c["n"] < 20 or c["hit"] is None:
        return f" <sub>[{rule} 검증: 표본 {c['n']}개, 아직 부족]</sub>"
    return f" <sub>[{rule} 검증: 적중 {c['hit']:.0%}·표본 {c['n']} — {c['verdict']}]</sub>"


def claim(rule: str, default: str, contrary: str) -> str:
    """규칙 문구를 성적에 맞춰 바꾼다. 반대로 나오는 규칙을 그대로 말하지 않는다."""
    c = _CARD.get(rule)
    v = (c or {}).get("verdict", "")
    if v.startswith("반대로 나옴"):
        return f"{contrary} <sub>[{rule}: 통념과 반대 — 이 리포트 기록상 적중 {c['hit']:.0%}·표본 {c['n']}]</sub>"
    if v.startswith("근거 약함"):
        return f"{default} — 단, 이 리포트 기록상 근거 약함 <sub>[{rule}: 적중 {c['hit']:.0%}·표본 {c['n']}]</sub>"
    return default + evidence(rule)


_MARKET = {"foreign_5d": None}  # 그날 시장 전체 외국인 5일 순매수 (종목이 '시장을 움직였나' 판단용)


def set_market(foreign_5d_total: float | None) -> None:
    _MARKET["foreign_5d"] = foreign_5d_total


def market_share(f5: float | None) -> float | None:
    """이 종목 외국인 5일 순매수가 시장 전체 외국인 순매수(같은 방향)의 몇 %인지."""
    tot = _MARKET["foreign_5d"]
    if f5 is None or not tot or f5 * tot <= 0:
        return None
    return f5 / tot


def signal_score(r: dict) -> float:
    """해설 우선순위 = 오늘 등락 + 5일 등락 + 평소 대비 거래 + 외국인 비중 + 외국인 금액 규모 + 이벤트성.

    '오늘'만 보면 며칠에 걸쳐 고르게 빠진 대형주(예: 5일 -20%, 외국인 -6조)가 묻힌다.
    그래서 5일 등락과 금액 규모(log10 억 원)를 같이 넣는다.
    """
    import math

    ret, ret5, heat, fv, f5 = (r.get(k) for k in ("ret", "ret5", "value_heat", "foreign_vs_value", "foreign_5d"))
    event = ret is not None and ret5 is not None and abs(ret) >= 0.05 and (
        (ret * ret5 > 0 and abs(ret) >= 0.6 * abs(ret5)) or abs(ret) > abs(ret5))
    size = max(0.0, math.log10(abs(f5) / 1e8)) * 3 if f5 else 0.0   # 100억 → 3, 1조 → 6, 6조 → 11
    return (abs(ret or 0) * 100 * 1.0 + abs(ret5 or 0) * 100 * 0.5
            + max(0.0, (heat or 0) - 1) * 2.0 + abs(fv or 0) * 100 * 0.5
            + size + (5 if event else 0))


def notes(r: dict, group: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    if (r.get("value") or 0) < MIN_VALUE or (r.get("turnover") or 0) > MAX_TURNOVER:
        return out
    from .signals import fired
    ret, ret5 = r.get("ret"), r.get("ret5")
    heat, turn = r.get("value_heat"), r.get("turnover")
    w, f5, fv = r.get("weight"), r.get("foreign_5d"), r.get("foreign_vs_value")
    rules = fired(ret, ret5, heat, fv)
    kind = "급락" if (ret or 0) < 0 else "급등"

    # 1. 5일 움직임이 하루에 몰렸나 (EVENT_DROP / EVENT_JUMP)
    ev = "EVENT_DROP" if "EVENT_DROP" in rules else ("EVENT_JUMP" if "EVENT_JUMP" in rules else None)
    rebound = claim(ev, f"이런 {kind} 다음날은 되돌림이 나오기 쉽다",
                    f"흔히 다음날 되돌림을 기대하지만, 최근 기록에선 오히려 같은 방향으로 이어진 경우가 더 많았다") if ev else ""
    if ev and abs(ret) <= abs(ret5):
        out.append((f"5일 {_p(ret5)} 중 대부분({_p(ret)})이 오늘 하루에 몰렸다 — 서서히가 아니라 이벤트로 "
                    f"한 번에 재평가된 모양새. {rebound}.", 0))
    elif ev:
        out.append((f"오늘 하루 {_p(ret)}가 5일 누적({_p(ret5)})보다 크다 — 며칠간 반대로 가던 걸 하루에 뒤집은 "
                    f"이벤트성 {kind}. {rebound}.", 0))
    elif ret5 is not None and abs(ret5) >= 0.10:
        way = "빠졌다(추세적 매도)" if ret5 < 0 else "올랐다(추세적 매수)"
        today = f" 오늘은 {_p(ret)}." if ret is not None else ""
        out.append((f"5일 {_p(ret5)} — 하루가 아니라 며칠에 걸쳐 고르게 {way}.{today}", 0))
    elif ret is not None and abs(ret) >= 0.08:
        out.append((f"오늘 {_p(ret)}로 크게 움직였다.", 0))

    # 2. 손바뀜 (CAPITULATION / CHASE_RISK)
    if heat is not None and heat >= 3:
        s = f"거래대금이 평소(20일 평균)의 {heat:.1f}배" + (f", 시가총액의 {turn:.1%}가 하루에 손바뀜" if turn else "")
        if "CAPITULATION" in rules:
            s += ". 팔려는 물량을 누군가 받아갔다('투매') — " + claim(
                "CAPITULATION", "바닥 신호일 수도 있지만 이것만으로 단정할 수 없다",
                "흔히 바닥 신호로 읽지만, 최근 기록에선 다음날 더 빠진 경우가 많았다") + "."
        elif "CHASE_RISK" in rules:
            s += ". 사려는 돈이 몰렸다 — " + claim(
                "CHASE_RISK", "뒤늦게 따라 사면 고점에 물릴 위험이 크다",
                "흔히 추격 매수는 위험하다고 하지만, 최근 기록에선 다음날 더 오른 경우가 많았다") + "."
        else:
            s += ". 가격 변화에 비해 거래가 유난히 많다 — 손바뀜(주인 교체)이 일어나는 중."
        out.append((s, 0))
    elif turn is not None and turn >= 0.05:
        out.append((f"시가총액의 {turn:.1%}가 하루에 거래됐다 — 단타 자금이 몰린 상태.", 0))

    # 3. 분야 안에서의 쏠림
    # 원래 몸집(시가총액 비중)이 큰 대형주는 거래 비중도 큰 게 정상 → 몸집보다 1.5배 이상 쏠렸을 때만 '개별 이슈'
    cw = r.get("cap_weight")
    if w is not None and w >= 0.4 and (cw is None or w >= 1.5 * cw):
        out.append((f"{group} 거래의 {w:.0%}가 이 종목 하나에서 나왔다(시총 비중 {cw:.0%})" if cw is not None else
                    f"{group} 거래의 {w:.0%}가 이 종목 하나에서 나왔다", 0))
        out[-1] = (out[-1][0] + " — 분야 전체보다 이 종목 개별 이슈일 가능성이 크다.", 0)

    # 4-1. 시장 영향: 금액 기준. 시장 전체 외국인 순매수(같은 방향)의 5% 이상이면 비율과 무관하게 말한다
    ms = market_share(f5)
    if ms is not None and ms >= MARKET_MOVER_SHARE:
        way = "순매도" if f5 < 0 else "순매수"
        inner = f", 이 종목 5일 거래의 {abs(fv):.0%}" if fv is not None else ""
        out.append((f"외국인 5일 {_won(f5)} {way} — 시장 전체 외국인 {way}({_won(_MARKET['foreign_5d'])})의 "
                    f"**{ms:.0%}**{inner}. 비율이 아니라 금액으로 시장을 움직인 종목.", 0))
    # 4-2. 종목 안에서의 주도: 비율 기준. 10% 미만은 말하지 않는다(표의 꼬리표로 충분), 10~20%는 방향만, 20% 이상은 '주도'
    elif f5 is not None and fv is not None and abs(fv) >= 0.10:
        way = "순매수" if f5 > 0 else "순매도"
        if "FOREIGN_LED" in rules:
            out.append((f"외국인이 5일 거래의 {abs(fv):.0%}({_won(f5)})를 {way} — " + claim(
                "FOREIGN_LED", "외국인 주도", "외국인 주도처럼 보이지만, 최근 기록에선 주가가 외국인 반대로 간 경우가 많았다") + ".", 0))
        else:
            out.append((f"외국인 5일 {way}(거래의 {abs(fv):.0%}) — 방향만 참고.", 0))
    score = signal_score(r)
    return [(t, score) for t, _ in out]


def notable(rows: list[dict], group: str, limit: int = 2, seen: set | None = None) -> list[tuple[dict, list[str]]]:
    """해석할 거리가 있는 종목을 신호 강도 순으로 limit개. seen에 있는 종목은 '↑ 위 참고'로 줄인다."""
    scored = []
    for r in rows:
        ns = notes(r, group)
        if ns:
            scored.append((ns[0][1], r, [t for t, _ in ns]))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, r, ts in scored[:limit]:
        if seen is not None and r["ticker"] in seen:
            ts = ["↑ 위 해설 참고."]
        elif seen is not None:
            seen.add(r["ticker"])
        out.append((r, ts))
    return out


DISCLAIMER = "표가 말해주는 건 여기까지(사실). '그래서 싸다/더 빠진다'는 실적·뉴스 같은 다른 근거로 판단해야 한다."


# 외국인 순매수의 '크기'를 한눈에: 5일 거래대금 대비 비율로 등급을 매긴다
FOREIGN_LEVELS = ((0.05, "미미"), (0.10, "약함"), (0.20, "보통"), (float("inf"), "강함"))


def foreign_strength(fv: float | None, f5: float | None = None, ret5: float | None = None) -> str:
    """'거래의 4% · 미미 · ⚠️주가와 반대' 같은 짧은 꼬리표. 방향만 보고 오해하지 않게 한다."""
    if fv is None:
        return ""
    level = next(name for cut, name in FOREIGN_LEVELS if abs(fv) < cut)
    tag = f"거래 {abs(fv):.0%}·{level}"
    if f5 is not None and ret5 is not None and abs(ret5) >= 0.03 and f5 * ret5 < 0:
        tag += "·⚠️주가와 반대"
    return tag
