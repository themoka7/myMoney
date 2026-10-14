"""하루치 결과를 GitHub Release 본문용 마크다운으로 만든다."""
from __future__ import annotations

from . import config

NAVER = "https://finance.naver.com/item/main.naver?code={}"


def _fmt_date(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def _move(it: dict) -> str:
    pr = it["prev_rank"]
    if pr is None:
        return "🆕"
    if pr == it["rank"]:
        return "–"
    return f"🔺{pr - it['rank']}" if pr > it["rank"] else f"🔻{it['rank'] - pr}"


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:+.2f}%"


def _cum(series: list[dict], key: str) -> float | None:
    vals = [p[key] for p in series if p[key] is not None]
    if not vals:
        return None
    acc = 1.0
    for v in vals:
        acc *= 1 + v
    return acc - 1


def _avg(series: list[dict], key: str) -> float | None:
    vals = [p[key] for p in series if p[key] is not None]
    return sum(vals) / len(vals) if vals else None


def _perf_table(perf: dict, date: str) -> list[str]:
    upto = {k: [p for p in v if p["date"] <= date] for k, v in perf.items()}
    if not upto.get("universe"):
        return ["_성과 추적은 2거래일 이상 쌓이면 표시됩니다._"]
    days = len(upto["universe"])
    lines = [
        f"d일 TOP10을 동일가중으로 d+1일 보유했다고 가정 · {days}일 누적 · 비용 {config.ROUND_TRIP_COST:.1%} 반영",
        "",
        "| 카테고리 | 누적 종가→종가 (비용후) | 누적 시가→종가 (비용후) | 평균 갭 | 평균 장중 | 승률 | 평균 교체율 |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for cat, (label, _) in config.CATEGORIES.items():
        s = upto.get(cat, [])
        if not s:
            continue
        valid = [p for p in s if p["c2c_net"] is not None]
        win = sum(p["c2c_net"] > 0 for p in valid) / len(valid) if valid else 0
        lines.append(
            f"| {label} | {_pct(_cum(s, 'c2c_net'))} | {_pct(_cum(s, 'intraday_net'))} | "
            f"{_pct(_avg(s, 'gap'))} | {_pct(_avg(s, 'intraday'))} | {win:.0%} | {_avg(s, 'turnover'):.0%} |"
        )
    u = upto["universe"]
    lines.append(
        f"| _유니버스 평균 (기준선)_ | {_pct(_cum(u, 'c2c'))} | {_pct(_cum(u, 'intraday'))} | "
        f"{_pct(_avg(u, 'gap'))} | {_pct(_avg(u, 'intraday'))} | | |"
    )
    lines += ["", "> 종가→종가는 데이터가 장 마감 후 나오므로 실제로는 먹을 수 없는 이론값이다. "
                  "결과를 보고 다음날 아침 사서 그날 파는 현실적인 경우는 시가→종가 쪽이다."]
    return lines


GLOSSARY = """<details>
<summary><b>📖 표 읽는 법 · 용어 설명 (처음이면 펼쳐 보세요)</b></summary>

**TOP10 표**

| 칸 | 뜻 |
|---|---|
| 점수 | 0~100. 그날 비교 대상 종목들 사이에서의 **상대 등수**를 백분율로 바꾼 것. 90점 = 상위 10% 안. 절대 평가가 아니라서 시장 전체가 나빠도 누군가는 100점이다 |
| 전일대비 | 🆕 오늘 처음 TOP10 진입 · 🔺 어제보다 순위 상승 · 🔻 순위 하락 · – 그대로 |
| 연속 | 며칠째 연속으로 TOP10에 들어 있는지. 길수록 그 특성이 꾸준하다는 뜻 |
| 이탈 | 어제는 TOP10이었는데 오늘 빠진 종목 |
| 시장 | KOSPI(유가증권시장, 대형주 위주) / KOSDAQ(코스닥, 중소형·기술주 위주) |

**비교 대상(유니버스)**: 너무 작거나 거래가 적은 종목은 원하는 가격에 사고팔기 어려워서 뺐다.
시가총액(주가 × 주식 수 = 회사 몸값) 3천억 원 이상, 그날 거래대금 10억 원 이상, 우선주 제외.

**다음날 보유 성과 표**

"오늘 TOP10을 똑같은 금액씩 사서 하루 들고 있었다면?"을 매일 계산해 누적한 것.

| 칸 | 뜻 |
|---|---|
| 종가→종가 | 오늘 장 마감 가격에 사서 내일 장 마감 가격에 판 경우. 단, 이 리포트는 장 마감 **후**에 나오므로 실제로는 불가능한 **이론값** |
| 시가→종가 | 리포트를 보고 다음날 아침 장 시작 가격(시가)에 사서 그날 마감에 판 경우. **실제로 따라 할 수 있는 숫자** |
| 갭 | 어제 마감 → 오늘 시작 사이에 벌어진 가격 차이. 밤사이 뉴스·미국장이 여기에 반영된다 |
| 장중 | 오늘 시작 → 오늘 마감 사이 변동 |
| 비용후 | 세금·수수료·호가 차이를 매매 1회당 약 0.3%로 잡고 뺀 값 |
| 승률 | 하루 수익이 플러스였던 날의 비율 |
| 교체율 | 어제 TOP10 중 몇 %가 바뀌었는지. 높을수록 매일 갈아타야 해서 비용이 커진다 |
| 유니버스 평균 | 비교 대상 전체를 똑같이 샀을 때. **TOP10이 이것보다 못하면 고른 의미가 없다** |

**한 줄 요약**: TOP10은 "사라"는 목록이 아니라 "이런 기준으로 고르면 실제로 결과가 좋았나?"를 확인하는 실험 기록이다.

</details>"""


def release_notes(site: dict, date: str) -> str:
    """site: track.build_site() 반환값."""
    day = site["days"][date]
    dates = site["dates"]
    i = dates.index(date)
    prev = _fmt_date(dates[i - 1]) if i > 0 else None

    out = [
        f"유니버스 **{day['universe_size']}종목** · "
        + (f"전일 비교 기준 {prev}" if prev else "첫 기록 (전일 비교 없음)")
        + f" · 누적 기록 {i + 1}일",
        "",
    ]
    for cat, (label, desc) in config.CATEGORIES.items():
        items = day["categories"].get(cat, [])
        easy, what, caution = config.CATEGORY_GUIDE[cat]
        out += [f"## {label}", f"> 💡 **쉽게 말하면** {easy}", ">",
                f"> {what}", ">", f"> ⚠️ {caution}", ""]
        if not items:
            out += ["_데이터 없음_", ""]
            continue
        out += ["| 순위 | 전일대비 | 종목 | 시장 | 점수 | 종가 | 연속 |",
                "|--:|:-:|---|---|--:|--:|--:|"]
        for it in items:
            out.append(
                f"| {it['rank']} | {_move(it)} | [{it['name']}]({NAVER.format(it['ticker'])}) `{it['ticker']}` | "
                f"{it['market']} | {it['score']:.1f} | {it['close']:,.0f} | {it['streak']}일 |"
            )
        dropped = day["dropped"].get(cat, [])
        if dropped:
            out += ["", "이탈: " + ", ".join(f"{x['name']}({x['prev_rank']}위)" for x in dropped)]
        out.append("")

    out += ["## 다음날 보유 성과 (누적)", ""] + _perf_table(site["performance"], date)
    out += ["", GLOSSARY, "", "---",
            "<sub>점수는 그날 유니버스 안에서의 백분위(0~100). 투자 권유가 아닌 개인 학습 기록입니다.</sub>"]
    return "\n".join(out)
