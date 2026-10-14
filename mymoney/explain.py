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


MIN_VALUE = 50e8          # 거래대금 50억 미만은 '평소 대비' 같은 배수가 의미 없이 튄다
SPOTLIGHT_MIN_VALUE = 300e8  # 전체 하이라이트는 거래대금 300억 이상만


def notes(r: dict, group: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    if (r.get("value") or 0) < MIN_VALUE:
        return out
    ret, ret5 = r.get("ret"), r.get("ret5")
    heat, turn = r.get("value_heat"), r.get("turnover")
    w, f5 = r.get("weight"), r.get("foreign_5d")
    fv, fc = r.get("foreign_vs_value"), r.get("foreign_vs_cap")

    # 1. 5일 움직임이 하루에 몰렸나
    kind = "급락" if (ret or 0) < 0 else "급등"
    if ret is not None and ret5 is not None and abs(ret) >= 0.05 and ret * ret5 > 0 and 0.6 * abs(ret5) <= abs(ret) <= abs(ret5):
        out.append((f"5일 {_p(ret5)} 중 대부분({_p(ret)})이 오늘 하루에 몰렸다. 서서히가 아니라 "
                    f"어떤 이벤트로 한 번에 재평가된 모양새 — 이런 {kind} 다음날은 되돌림이 나오기 쉽다.", abs(ret) * 10))
    elif ret is not None and ret5 is not None and abs(ret) >= 0.05 and abs(ret) > abs(ret5):
        out.append((f"오늘 하루 {_p(ret)}가 5일 누적({_p(ret5)})보다 크다 — 며칠간 반대로 움직이던 걸 하루에 뒤집은 "
                    f"이벤트성 {kind}. 이런 날 다음엔 되돌림이 나오기 쉽다.", abs(ret) * 10))
    elif ret is not None and abs(ret) >= 0.08:
        out.append((f"오늘 {_p(ret)}로 크게 움직였다.", abs(ret) * 5))

    # 2. 손바뀜
    if heat is not None and heat >= 3:
        s = f"거래대금이 평소(20일 평균)의 {heat:.1f}배"
        if turn is not None:
            s += f", 시가총액의 {turn:.1%}가 하루에 손바뀜"
        if ret is not None and ret <= -0.05:
            s += ". 팔고 싶은 물량이 쏟아졌고 누군가 받아갔다('투매'). 바닥 신호일 수도 있지만 이것만으로 단정할 수 없다."
        elif ret is not None and ret >= 0.05:
            s += ". 사려는 돈이 몰렸다. 뒤늦게 따라 사면 고점에 물릴 위험이 크다."
        else:
            s += ". 가격 변화에 비해 거래가 유난히 많다 — 손바뀜(매수·매도 주체 교체)이 일어나는 중."
        out.append((s, min(heat, 10)))
    elif turn is not None and turn >= 0.05:
        out.append((f"시가총액의 {turn:.1%}가 하루에 거래됐다 — 회전율이 매우 높다(단타 자금이 몰린 상태).", 3))

    # 3. 분야 안에서의 쏠림
    if w is not None and w >= 0.4:
        out.append((f"{group} 거래의 {w:.0%}가 이 종목 하나에서 나왔다 — 분야 전체 흐름이라기보다 "
                    f"이 종목 개별 이슈일 가능성이 크다.", w * 5))

    # 4. 외국인: 방향과 크기를 같이 본다
    if f5 is not None and fv is not None:
        if ret5 is not None and abs(ret5) >= 0.05 and f5 * ret5 < 0 and abs(fv) < 0.1:
            way = "순매수" if f5 > 0 else "순매도"
            s = f"주가가 5일 {_p(ret5)} 움직이는 동안 외국인은 반대로 {_won(f5)} {way}했지만, 같은 기간 거래대금의 {abs(fv):.0%}"
            if fc is not None:
                s += f"·시총의 {abs(fc):.2%}"
            s += " 수준 — 방향은 반대여도 흐름을 바꿀 힘은 아니었다. 순매수 숫자 하나로 외국인 의도를 읽기는 어렵다."
            out.append((s, 2))
        elif abs(fv) >= 0.2:
            way = "순매수" if f5 > 0 else "순매도"
            out.append((f"외국인이 5일 거래대금의 {abs(fv):.0%}에 해당하는 {_won(f5)}를 {way} — "
                        f"외국인이 주도한 흐름.", abs(fv) * 5))
    return out


def notable(rows: list[dict], group: str, limit: int = 3) -> list[tuple[dict, list[str]]]:  # noqa: E501
    """해석할 거리가 있는 종목을 중요도 순으로 limit개."""
    scored = []
    for r in rows:
        ns = notes(r, group)
        if ns:
            scored.append((sum(x for _, x in ns), r, [t for t, _ in ns]))
    scored.sort(key=lambda x: -x[0])
    return [(r, ts) for _, r, ts in scored[:limit]]


DISCLAIMER = "표가 말해주는 건 여기까지(사실). '그래서 싸다/더 빠진다'는 실적·뉴스 같은 다른 근거로 판단해야 한다."
