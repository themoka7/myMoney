"""하루치 결과를 GitHub Release 본문용 마크다운으로 만든다."""
from __future__ import annotations

from . import config, explain, flow

NAVER = "https://finance.naver.com/item/main.naver?code={}"
_REFS: set[str] = set()  # 본문에 쓴 종목코드 → 끝에 링크 정의를 한 번씩만 붙인다 (본문 길이 절약)


def _link(name: str, ticker: str) -> str:
    _REFS.add(ticker)
    return f"[{name}][{ticker}]"


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


SPARK = "▁▂▃▄▅▆▇█"


def _spark(vals: list[float]) -> str:
    if len(vals) < 2:
        return "–"
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return SPARK[3] * len(vals)
    return "".join(SPARK[round((v - lo) / (hi - lo) * (len(SPARK) - 1))] for v in vals)


def _md(d: str) -> str:
    return f"{int(d[4:6])}/{int(d[6:])}"


def _price_details(items: list[dict], prices: dict, date: str, days: int = 20) -> list[str]:
    hist = {it["ticker"]: dict((d, c) for d, c in prices.get(it["ticker"], [])) for it in items}
    rows = sorted({d for h in hist.values() for d in h}, reverse=True)[:days]
    if not rows:
        return []
    lines = [f"<details><summary>📅 최근 {len(rows)}거래일 종가 (전날·그 전날…)</summary>", "",
             "| 날짜 | " + " | ".join(it["name"] for it in items) + " |",
             "|---|" + "--:|" * len(items),
             f"| **{_md(date)}** | " + " | ".join(f"**{it['close']:,.0f}**" for it in items) + " |"]
    for d in rows:
        lines.append(f"| {_md(d)} | " + " | ".join(
            f"{hist[it['ticker']][d]:,.0f}" if d in hist[it["ticker"]] else "–" for it in items) + " |")
    return lines + ["", "</details>", ""]


FOLLOWUP_ROWS = 25
BODY_LIMIT = 124_000  # GitHub Release 본문 최대 125,000자


def _followup_details(rows: list[dict], max_rows: int = FOLLOWUP_ROWS, path_len: int = 8) -> list[str]:
    if not rows:
        return []
    lines = ["<details><summary>📌 선정 후 추적 — 최근 TOP10에 들었던 종목은 그 뒤로 어떻게 됐나</summary>", "",
             "처음 TOP10에 든 날의 종가에 샀다고 치고, 그 뒤 매일 종가를 따라간 기록.", "",
             "| 종목 | 최초 선정 | 선정일 종가 | 이후 종가 흐름 | 수익률 | 지금 |",
             "|---|---|--:|---|--:|:-:|"]
    shown = rows[:max_rows]
    for r in shown:
        flow = " → ".join(f"{c:,.0f}" for _, c in r["path"][-path_len:]) or "–"
        if len(r["path"]) > path_len:
            flow = "… → " + flow
        lines.append(
            f"| {_link(r['name'], r['ticker'])} | {_md(r['first_date'])} | {r['first_close']:,.0f} | "
            f"{flow} | {_pct(r['ret'])} | {'TOP10' if r['still_in'] else '이탈'} |"
        )
    if len(rows) > len(shown):
        lines.append(f"| _외 {len(rows) - len(shown)}개 (더 오래전 선정)_ | | | | | |")
    return lines + ["", "</details>", ""]


def _won(v: float | None, signed: bool = False) -> str:
    if v is None:
        return "–"
    sign = "+" if signed and v > 0 else ""
    if abs(v) >= 1e12:
        return f"{sign}{v / 1e12:,.1f}조"
    return f"{sign}{v / 1e8:,.0f}억"


def _heat(h: float | None) -> str:
    if h is None:
        return "–"
    mark = " 🔥" if h >= 1.5 else (" 🧊" if h <= 0.67 else "")
    return f"{h:.1f}배{mark}"


FLOW_INTRO = """> 💡 **쉽게 말하면** 오늘 시장에서 오간 돈(거래대금) 중 각 분야가 몇 %를 차지했는지. 비중이 크면 그쪽에 관심과 돈이 몰렸다는 뜻.
>
> **평소 대비**는 최근 20거래일 평균 비중과 비교한 배수다. 🔥 1.5배 이상 = 평소보다 확 몰림, 🧊 0.67배 이하 = 평소보다 썰렁.
> **외국인 5일**은 외국인이 최근 5거래일간 산 돈 − 판 돈. 괄호 안은 그 돈이 같은 기간 거래대금의 몇 %인지와 크기 등급(미미·약함·보통·강함) — **+라고 다 좋은 신호가 아니다. 크기부터 본다.** 등락률은 회사 크기(시가총액)로 가중한 평균이다.
>
> ⚠️ 거래대금은 '사고판 양'이지 '들어온 돈'이 아니다. 급락할 때도 거래대금은 터진다. 그래서 등락률과 같이 봐야 한다."""


def _x(v: float | None) -> str:
    return "–" if v is None else f"{v:.1f}배"


def _ratio(v: float | None, digits: int = 1) -> str:
    return "–" if v is None else f"{v * 100:+.{digits}f}%"


def _turn(v: float | None) -> str:
    return "–" if v is None else (f"{v:.1%}" if v >= 0.01 else f"{v:.2%}")


def _foreign_cell(f5: float | None, fv: float | None, ret5: float | None = None) -> str:
    """외국인 순매수 금액 + 크기 꼬리표. '샀다=좋다'로 오해하지 않도록 크기를 같이 보여 준다."""
    tag = explain.foreign_strength(fv, f5, ret5)
    return _won(f5, signed=True) + (f" <sub>{tag}</sub>" if tag else "")


def _member_table(rows: list[dict]) -> list[str]:
    lines = ["| 종목 | 종가 | 오늘 | 5일 | 거래대금 | 평소 대비 | 회전율 | 분야 내 비중 | 외국인 5일 (크기) |",
             "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in rows:
        lines.append(
            f"| {_link(r['name'], r['ticker'])} | {r['close']:,.0f} | {_pct(r['ret'])} | "
            f"{_pct(r['ret5'])} | {_won(r['value'])} | {_x(r.get('value_heat'))} | "
            f"{_turn(r.get('turnover'))} | "
            f"{_share(r['weight'])} | {_foreign_cell(r['foreign_5d'], r.get('foreign_vs_value'), r.get('ret5'))} |"
        )
    return lines


def _foreign_inline(m: dict, rets: list) -> str:
    tag = explain.foreign_strength(m.get("foreign_vs_value"), m.get("foreign_5d"), flow.compound(rets[-5:]))
    return _won(m.get("foreign_5d"), signed=True) + (f"({tag})" if tag else "")


def _flow_list(flows: dict, names: list[str], date: str, members: dict | None = None,
               sub=lambda n: "", member_note: str = "") -> list[str]:
    """분야마다 한 줄 요약을 펼치기 제목으로 쓰고, 누르면 바로 아래에 구성 종목이 열린다."""
    members = members or {}
    lines = ["<sub>각 줄: 시장 비중 · 평소 대비 · 오늘 · 5일 · 20일 등락 · 외국인 5일 · 비중 추이 — "
             "<b>줄을 누르면 종목이 펼쳐진다</b></sub>", ""]
    for n in names:
        m = flows[date][n]
        rets = flow.series(flows, n, "ret", date)
        shares = [x for x in flow.series(flows, n, "share", date)[-20:] if x is not None]
        summary = (
            f"<b>{n}</b> &nbsp; <b>{m['share'] * 100:.1f}%</b> · {_heat(m.get('heat'))} · "
            f"오늘 <b>{_pct(m['ret'])}</b> · 5일 {_pct(flow.compound(rets[-5:]))} · "
            f"20일 {_pct(flow.compound(rets[-20:]))} · 외국인 {_foreign_inline(m, rets)} · "
            f"<code>{_spark(shares)}</code>"
        )
        rows = members.get(n, [])
        head = " · ".join(x for x in [sub(n), f"거래대금 {_won(m['value'])}", f"{m['n']}종목 거래"] if x)
        lines += [f"<details><summary>{summary}</summary>", "", f"<sub>{head}{member_note if rows else ''}</sub>", ""]
        if rows:
            lines += _member_table(rows)
            picks = explain.notable(rows, n, limit=3)
            if picks:
                lines += ["", "🔎 **눈여겨볼 점**", ""]
                for r, ts in picks:
                    lines.append(f"- **{r['name']}** — " + " ".join(ts))
        else:
            lines.append("_종목 목록 없음 (리포트 길이 제한 또는 데이터 없음)_")
        lines += ["", "</details>", ""]
    return lines


def _forest_section(site: dict, date: str) -> list[str]:
    mk = site.get("flows", {}).get("market", {})
    if date not in mk or "전체" not in mk[date]:
        return []
    day = mk[date]
    allm = day["전체"]
    lines = ["## 🌳 시장 전체 — 숲부터 보자", "",
             "> 💡 개별 종목(나무)을 보기 전에 오늘 시장 전체(숲)가 어땠는지. 시장 전체가 빠지는 날엔 좋은 종목도 같이 빠진다.", "",
             "| 시장 | 등락 (시총가중) | 5일 | 20일 | 오른 종목 / 내린 종목 | 거래대금 | 평소 대비 | 외국인 5일 |",
             "|---|--:|--:|--:|:-:|--:|--:|--:|"]
    for n in ["전체", "KOSPI", "KOSDAQ"]:
        if n not in day:
            continue
        m = day[n]
        rets = flow.series(mk, n, "ret", date)
        vals = [x for x in flow.series(mk, n, "value", date)[:-1][-config.FLOW_BASELINE_DAYS:] if x]
        vheat = m["value"] / (sum(vals) / len(vals)) if vals else None
        lines.append(
            f"| {n} | {_pct(m['ret'])} | {_pct(flow.compound(rets[-5:]))} | {_pct(flow.compound(rets[-20:]))} | "
            f"🔺{m['up']} / 🔻{m['down']} | {_won(m['value'])} | {_heat(vheat)} | "
            f"{_foreign_cell(m['foreign_5d'], m.get('foreign_vs_value'), flow.compound(rets[-5:]))} |"
        )
    lines += ["", "<sub>평소 대비 = 최근 20거래일 평균 거래대금 대비. 오른/내린 종목 수는 전 기록일 종가 대비.</sub>", ""]
    return lines


def _headline(site: dict, date: str) -> list[str]:
    flows = site.get("flows", {})
    parts = []
    mk = flows.get("market", {}).get(date, {})
    if "KOSPI" in mk and mk["KOSPI"]["ret"] is not None:
        parts.append(f"KOSPI {_pct(mk['KOSPI']['ret'])}")
    if "KOSDAQ" in mk and mk["KOSDAQ"]["ret"] is not None:
        parts.append(f"KOSDAQ {_pct(mk['KOSDAQ']['ret'])}")
    if "전체" in mk and mk["전체"]["up"] + mk["전체"]["down"]:
        a = mk["전체"]
        parts.append(f"오른 종목 {a['up'] / (a['up'] + a['down']):.0%}")
    th = flows.get("theme", {}).get(date, {})
    if th:
        top = max(th, key=lambda n: th[n]["share"])
        parts.append(f"돈이 가장 몰린 테마 **{top}** (거래대금의 {th[top]['share']:.0%}, {_pct(th[top]['ret'])})")
    sec = flows.get("sector", {}).get(date, {})
    hot = [n for n in sec if sec[n].get("heat") and sec[n]["share"] >= 0.01]
    if hot:
        h = max(hot, key=lambda n: sec[n]["heat"])
        parts.append(f"평소보다 돈이 몰린 섹터 **{h}** ({sec[h]['heat']:.1f}배)")
    return [f"> 🌳 **오늘의 숲** · " + " · ".join(parts), ""] if parts else []


def _share(v: float | None) -> str:
    return "–" if v is None else f"{v:.0%}"


COLUMN_GUIDE = """<details><summary>📖 종목 표 칸 읽는 법</summary>

| 칸 | 뜻 | 이렇게 읽는다 |
|---|---|---|
| 오늘 / 5일 | 전 거래일 / 5거래일 전 종가 대비 | 5일 변동 대부분이 오늘이면 이벤트성 재평가 |
| 거래대금 | 오늘 사고판 금액 | 많을수록 관심·논란이 크다 |
| 평소 대비 | 오늘 거래대금 ÷ 최근 20일 평균 | 3배 이상이면 무슨 일이 있었다는 뜻 |
| 회전율 | 거래대금 ÷ 시가총액 | 회사 몸값 중 몇 %가 하루에 주인이 바뀌었나 |
| 분야 내 비중 | 테마·섹터 거래대금 중 이 종목 몫 | 40% 넘으면 분야 전체보다 이 종목 개별 이슈 |
| 외국인 5일 (크기) | 외국인 5일 순매수(산 돈 − 판 돈)와, 그게 5일 거래대금의 몇 %인지 | **+면 "좋다"로 읽기 쉽지만 크기를 먼저 본다.** 미미(<5%)·약함(<10%)이면 방향과 상관없이 주가를 움직일 힘이 아니다. 보통(<20%)·강함(≥20%)부터 외국인이 흐름을 만든 것. ⚠️주가와 반대 = 주가는 빠졌는데 외국인은 샀다(또는 그 반대) — 이때 특히 크기를 확인 |

</details>"""


def _spotlight(members: dict, limit: int = 5) -> list[str]:
    """테마 전체에서 해석할 거리가 가장 큰 종목들."""
    seen, pool = set(), []
    for group, rows in members.items():
        for r in rows:
            if r["ticker"] in seen or (r.get("value") or 0) < explain.SPOTLIGHT_MIN_VALUE:
                continue
            ns = explain.notes(r, group)
            if ns:
                seen.add(r["ticker"])
                pool.append((sum(x for _, x in ns), group, r, [t for t, _ in ns]))
    pool.sort(key=lambda x: -x[0])
    if not pool:
        return []
    out = ["### 🔎 오늘 눈에 띈 종목 — 숫자가 말해주는 것", ""]
    for _, group, r, ts in pool[:limit]:
        out.append(f"- **{_link(r['name'], r['ticker'])}** <sub>{group} · {_pct(r['ret'])} · "
                   f"거래 {_won(r['value'])}</sub><br>" + " ".join(ts))
    out += ["", f"> ⚠️ {explain.DISCLAIMER}", "", COLUMN_GUIDE, ""]
    return out


def _flow_section(site: dict, date: str, level: int = 0) -> list[str]:
    flows = site.get("flows", {})
    themes, sectors = flows.get("theme", {}), flows.get("sector", {})
    if date not in themes and date not in sectors:
        return []
    out = ["## 💰 돈의 흐름 — 오늘 돈이 어디로 갔나", "", FLOW_INTRO, ""]
    etfs = site.get("theme_etfs", {})
    if date in themes and themes[date]:
        names = sorted(themes[date], key=lambda n: -themes[date][n]["share"])
        mem = site.get("members", {}).get(date, {}).get("theme", {})
        out += ["### 테마", "<sub>테마 = 대표 ETF가 담고 있는 종목 묶음. 종목이 여러 테마에 겹칠 수 있다.</sub>", ""]
        out += _flow_list(themes, names, date, mem, sub=lambda n: etfs.get(n, ""))
        out += _spotlight(mem)
    if date in sectors and sectors[date]:
        day = sectors[date]
        top = sorted(day, key=lambda n: -day[n]["share"])[:10]
        hot = sorted((n for n in day if day[n].get("heat") and day[n]["share"] >= 0.01),
                     key=lambda n: -day[n]["heat"])[:5]
        smem = site.get("members", {}).get(date, {}).get("sector", {}) if level < 2 else {}
        note = " · 거래대금 상위 종목만"
        out += ["### 섹터 (KRX 업종) — 거래대금 비중 상위 10", ""] + _flow_list(sectors, top, date, smem, member_note=note)
        if hot:
            out += ["### 평소보다 돈이 몰린 섹터 TOP5", "<sub>시장 비중 1% 이상 중 '평소 대비' 배수가 큰 순</sub>", ""]
            out += _flow_list(sectors, hot, date, smem, member_note=note)
    return out


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
| 전일대비 | 🆕 어제는 없었는데 오늘 TOP10 진입(예전에 들었다가 다시 들어온 재진입 포함) · 🔺 어제보다 순위 상승 · 🔻 순위 하락 · – 그대로 |
| 20일 흐름 | 최근 20거래일(약 한 달) + 오늘 종가를 막대 높이로 그린 것 (▁ 낮음 → █ 높음). 표 아래 "최근 거래일 종가"를 펼치면 날짜별 실제 가격이 나온다 |
| 5일 / 20일 등락 | 5거래일(약 1주) / 20거래일(약 1달) 전 종가 대비 오늘 종가 변화율 |
| 연속 | 며칠째 연속으로 TOP10에 들어 있는지. 길수록 그 특성이 꾸준하다는 뜻 |
| 이탈 | 어제는 TOP10이었는데 오늘 빠진 종목 |
| 시장 | KOSPI(유가증권시장, 대형주 위주) / KOSDAQ(코스닥, 중소형·기술주 위주) |

**선정 후 추적**: 최근 60일 기록 중 TOP10에 한 번이라도 든 종목을, 처음 든 날 종가에 샀다고 치고 그 뒤 매일 종가를 이어 붙인 것.
"지금"이 이탈이어도 계속 따라간다. 뽑힌 뒤 실제로 올랐는지 확인하는 용도.

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


def release_notes(site: dict, date: str, follow: dict | None = None) -> str:
    """Release 본문. GitHub 한도를 넘으면 덜 중요한 펼치기부터 뺀다."""
    for level in range(5):
        text = _render(site, date, follow, level)
        if len(text) <= BODY_LIMIT:
            return text
    return text[:BODY_LIMIT - 200] + "\n\n_(본문이 길어 잘렸습니다. 전체는 첨부 JSON·대시보드 참고)_"


def _render(site: dict, date: str, follow: dict | None, level: int) -> str:
    _REFS.clear()
    body = _render_body(site, date, follow, level)
    refs = "\n".join(f"[{t}]: {NAVER.format(t)}" for t in sorted(_REFS))
    return body + "\n\n" + refs + "\n"


def _render_body(site: dict, date: str, follow: dict | None, level: int) -> str:
    """level 0: 전부 · 1: 과거 종가 표 10일, 선정 후 추적 15개로 · 2: +섹터 구성 종목 생략 · 3: +선정 후 추적 생략 · 4: +과거 종가 표 생략."""
    day = site["days"][date]
    prices = site.get("prices", {}).get(date, {})
    follow = follow or {}

    def series(it):
        return [c for _, c in prices.get(it["ticker"], [])] + [it["close"]]

    def _chg(it, n):
        s = series(it)
        if len(s) <= n or not s[-1 - n]:
            return "–"
        return _pct(s[-1] / s[-1 - n] - 1)

    dates = site["dates"]
    i = dates.index(date)
    prev = _fmt_date(dates[i - 1]) if i > 0 else None

    out = [
        f"유니버스 **{day['universe_size']}종목** · "
        + (f"전일 비교 기준 {prev}" if prev else "첫 기록 (전일 비교 없음)")
        + f" · 누적 기록 {i + 1}일",
        "",
    ]
    out = out[:1] + [""] + _headline(site, date) + out[2:]
    out += _forest_section(site, date) + _flow_section(site, date, level)
    out += ["## 🌱 종목 TOP10 — 이제 나무를 보자", "",
            "> 숲(시장)과 돈의 흐름을 본 뒤에, 기준별로 점수가 높은 종목. 시장이 빠지는 날엔 TOP10도 같이 빠지는 게 보통이다.", ""]
    for cat, (label, desc) in config.CATEGORIES.items():
        items = day["categories"].get(cat, [])
        easy, what, caution = config.CATEGORY_GUIDE[cat]
        out += [f"### {label}", f"> 💡 **쉽게 말하면** {easy}", ">",
                f"> {what}", ">", f"> ⚠️ {caution}", ""]
        if not items:
            out += ["_데이터 없음_", ""]
            continue
        out += ["| 순위 | 전일대비 | 종목 | 시장 | 점수 | 종가 | 20일 흐름 | 5일 등락 | 20일 등락 | 연속 |",
                "|--:|:-:|---|---|--:|--:|:-:|--:|--:|--:|"]
        for it in items:
            out.append(
                f"| {it['rank']} | {_move(it)} | {_link(it['name'], it['ticker'])} `{it['ticker']}` | "
                f"{it['market']} | {it['score']:.1f} | {it['close']:,.0f} | "
                f"{_spark(series(it))} | {_chg(it, 5)} | {_chg(it, 20)} | {it['streak']}일 |"
            )
        out += [""] + (_price_details(items, prices, date, days=20 if level < 1 else 10) if level < 4 else []) \
            + (_followup_details(follow.get(cat, []), *((FOLLOWUP_ROWS, 8) if level < 1 else (15, 5)))
               if level < 3 else [])
        dropped = day["dropped"].get(cat, [])
        if dropped:
            out += ["", "이탈: " + ", ".join(f"{x['name']}({x['prev_rank']}위)" for x in dropped)]
        out.append("")

    out += ["## 다음날 보유 성과 (누적)", ""] + _perf_table(site["performance"], date)
    out += ["", GLOSSARY, "", "---",
            "<sub>점수는 그날 유니버스 안에서의 백분위(0~100). 투자 권유가 아닌 개인 학습 기록입니다.</sub>"]
    return "\n".join(out)
