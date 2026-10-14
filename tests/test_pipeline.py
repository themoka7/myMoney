import numpy as np
import pandas as pd
import pytest

from mymoney import config, track
from mymoney.score import filter_universe, score, top_n


def make_snap(seed: int, n: int = 60, price_scale: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = [f"{i:06d}" for i in range(1, n + 1)]
    close = rng.integers(2_000, 300_000, n) * price_scale
    return pd.DataFrame({
        "name": [f"종목{i}" for i in range(1, n + 1)],
        "market": ["KOSPI"] * n,
        "open": close * 0.99,
        "close": close,
        "market_cap": rng.integers(100, 5_000, n) * 1e9,
        "trading_value": rng.integers(1, 100, n) * 1e9,
        "per": rng.normal(12, 8, n),
        "pbr": rng.uniform(0.2, 4, n),
        "div": rng.uniform(0, 7, n),
        "ret_1m": rng.normal(0, 10, n),
        "ret_3m": rng.normal(0, 20, n),
        "foreign_net_5d": rng.normal(0, 5e9, n),
    }, index=pd.Index(idx, name="ticker"))


def test_universe_excludes_small_and_preferred():
    s = make_snap(1)
    s.loc["000001", ["market_cap", "trading_value"]] = [1e12, 1e10]
    s.loc["000001", "name"] = "삼성전자우"
    s.loc["000002", "market_cap"] = 1e9
    u = filter_universe(s)
    assert "000001" not in u.index
    assert "000002" not in u.index
    assert (u["market_cap"] >= config.MIN_MARKET_CAP).all()


def test_value_excludes_loss_making_and_prefers_cheap():
    s = make_snap(2)
    s["market_cap"], s["trading_value"] = 1e12, 1e10
    s.loc["000003", ["per", "pbr"]] = [-5, 0.1]
    s.loc["000004", ["per", "pbr"]] = [0.5, 0.05]
    sc = score(s)
    assert np.isnan(sc.loc["000003", "value"])
    assert sc["value"].idxmax() == "000004"
    assert np.isnan(sc.loc["000003", "composite"])


def test_top_n_shape():
    s = make_snap(3, n=80)
    s["market_cap"], s["trading_value"] = 1e12, 1e10
    tops = top_n(score(s))
    assert set(tops) == set(config.CATEGORIES)
    for items in tops.values():
        assert len(items) == config.TOP_N
        scores = [x["score"] for x in items]
        assert scores == sorted(scores, reverse=True)
        assert [x["rank"] for x in items] == list(range(1, config.TOP_N + 1))


def _day(tickers):
    return {"universe_size": 100, "categories": {
        c: [{"rank": i + 1, "ticker": t, "name": t, "market": "KOSPI", "score": 90 - i, "close": 1}
            for i, t in enumerate(tickers)] for c in config.CATEGORIES}}


def test_annotate_changes_rank_streak_dropped():
    tops = {"20261012": _day(["A", "B", "C"]),
            "20261013": _day(["B", "A", "D"]),
            "20261014": _day(["B", "D", "E"])}
    days = track.annotate_changes(tops)
    d2 = {x["ticker"]: x for x in days["20261013"]["categories"]["value"]}
    assert d2["B"]["prev_rank"] == 2 and d2["B"]["streak"] == 2
    assert d2["D"]["prev_rank"] is None and d2["D"]["streak"] == 1
    assert [x["ticker"] for x in days["20261013"]["dropped"]["value"]] == ["C"]
    d3 = {x["ticker"]: x for x in days["20261014"]["categories"]["value"]}
    assert d3["B"]["streak"] == 3 and d3["D"]["streak"] == 2


def test_performance_decomposes_gap_and_intraday():
    s0 = pd.DataFrame({"name": ["a", "b"], "market": "KOSPI", "open": [100, 100], "close": [100, 200],
                       "market_cap": 1e12, "trading_value": 1e10},
                      index=pd.Index(["A", "B"], name="ticker"))
    s1 = s0.copy()
    s1["open"] = [110, 220]   # 갭 +10%
    s1["close"] = [121, 242]  # 장중 +10%, 종가대비 +21%
    snaps = {"d0": s0, "d1": s1}
    tops = {"d0": _day(["A", "B"]), "d1": _day(["A", "B"])}
    perf = track.performance(tops, load=snaps.get)
    p = perf["value"][0]
    assert p["date"] == "d1"
    assert p["gap"] == pytest.approx(0.10)
    assert p["intraday"] == pytest.approx(0.10)
    assert p["c2c"] == pytest.approx(0.21)
    assert p["turnover"] == 1.0
    assert p["c2c_net"] == pytest.approx(0.21 - config.ROUND_TRIP_COST)
    assert perf["universe"][0]["c2c"] == pytest.approx(0.21)


def test_save_and_build_roundtrip(tmp_path):
    snap_dir, top_dir, site = tmp_path / "s", tmp_path / "t", tmp_path / "site" / "h.json"
    for i, d in enumerate(["20261013", "20261014"]):
        s = make_snap(10 + i, n=80)
        s["market_cap"], s["trading_value"] = 1e12, 1e10
        sc = score(s)
        track.save_day(d, s, top_n(sc), len(sc), snap_dir=snap_dir, top_dir=top_dir)
    data = track.build_site(top_dir=top_dir, snap_dir=snap_dir, site_file=site)
    assert data["dates"] == ["20261013", "20261014"]
    assert site.exists()
    assert len(data["performance"]["composite"]) == 1
    assert data["performance"]["universe"][0]["date"] == "20261014"


def test_release_notes_contains_tables_and_performance(tmp_path):
    from mymoney.report import release_notes

    snap_dir, top_dir, site_file = tmp_path / "s", tmp_path / "t", tmp_path / "h.json"
    for i, d in enumerate(["20261012", "20261013", "20261014"]):
        s = make_snap(20 + i, n=80)
        s["market_cap"], s["trading_value"] = 1e12, 1e10
        sc = score(s)
        track.save_day(d, s, top_n(sc), len(sc), snap_dir=snap_dir, top_dir=top_dir)
    site = track.build_site(top_dir=top_dir, snap_dir=snap_dir, site_file=site_file)

    first = release_notes(site, "20261012")
    assert "첫 기록" in first and "2거래일 이상" in first

    md = release_notes(site, "20261014")
    assert "전일 비교 기준 2026-10-13" in md
    for label, _ in config.CATEGORIES.values():
        assert f"### {label}" in md
    assert "2일 누적" in md and "유니버스 평균" in md


def test_followup_tracks_price_after_selection():
    s = {d: pd.DataFrame({"close": [100.0, 50.0, 10.0]}, index=pd.Index(["A", "B", "C"], name="ticker"))
         for d in ["d1", "d2", "d3"]}
    s["d2"]["close"] = [110.0, 55.0, 11.0]
    s["d3"]["close"] = [121.0, 45.0, 12.0]
    tops = {"d1": _day(["A", "B"]), "d2": _day(["A", "C"]), "d3": _day(["A"])}
    for d, day in tops.items():
        for items in day["categories"].values():
            for it in items:
                it["close"] = float(s[d].loc[it["ticker"], "close"])
    f = {r["ticker"]: r for r in track.followup(tops, "d3", load=s.get)["value"]}
    assert f["A"]["first_date"] == "d1" and f["A"]["path"] == [["d2", 110.0], ["d3", 121.0]]
    assert f["A"]["ret"] == pytest.approx(0.21) and f["A"]["still_in"]
    assert f["B"]["ret"] == pytest.approx(-0.10) and not f["B"]["still_in"]
    assert f["C"]["first_date"] == "d2" and f["C"]["path"] == [["d3", 12.0]]


def test_release_notes_shows_recent_prices_and_followup(tmp_path):
    from mymoney.report import release_notes

    snap_dir, top_dir = tmp_path / "s", tmp_path / "t"
    for i, d in enumerate(["20261012", "20261013"]):
        s = make_snap(30 + i, n=80)
        s["market_cap"], s["trading_value"] = 1e12, 1e10
        sc = score(s)
        top = top_n(sc)
        prices = {it["ticker"]: [["20261008", 1000.0], ["20261009", 1100.0]]
                  for items in top.values() for it in items}
        track.save_day(d, s, top, len(sc), snap_dir=snap_dir, top_dir=top_dir, prices=prices)
    site = track.build_site(top_dir=top_dir, snap_dir=snap_dir, site_file=tmp_path / "h.json")
    load = lambda d: track.load_snapshot(d, snap_dir)
    md = release_notes(site, "20261013", track.followup(track.load_tops(top_dir), "20261013", load=load))
    assert "거래일 종가" in md and "| **10/13** |" in md
    # 10/12는 스냅샷에서, 10/8·10/9는 저장된 prices에서 온다
    assert "\n| 10/12 |" in md and "\n| 10/9 |" in md and "\n| 10/8 |" in md
    assert "선정 후 추적" in md and "20일 흐름" in md and "20일 등락" in md


def test_retrying_wrapper_retries_empty_then_succeeds(monkeypatch):
    from mymoney import collect

    monkeypatch.setattr(collect.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class Fake:
        def get(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("Expecting value")
            if calls["n"] == 2:
                return pd.DataFrame()
            return pd.DataFrame({"a": [1]})

    assert len(collect._Retrying(Fake()).get()) == 1 and calls["n"] == 3

    class Dead:
        def get(self):
            return []

    with pytest.raises(RuntimeError):
        collect._Retrying(Dead()).get()


def test_price_history_merges_snapshots_and_stored_prices():
    snaps = {d: pd.DataFrame({"close": [float(i)]}, index=pd.Index(["A"], name="ticker"))
             for i, d in enumerate(["d01", "d02", "d03", "d04"], start=1)}
    tops = {d: _day(["A"]) for d in snaps}
    tops["d04"]["prices"] = {"A": [["d00", 0.5], ["d01", 999.0]]}
    h = track.price_history(tops, "d04", load=snaps.get, days=3)
    assert h["A"] == [["d01", 1.0], ["d02", 2.0], ["d03", 3.0]]  # 스냅샷 우선, 최근 3일만


def test_flow_share_heat_and_weighted_return():
    from mymoney import flow

    def snap(close, value):
        return pd.DataFrame({"close": close, "trading_value": value, "market_cap": [100.0, 300.0, 600.0],
                             "foreign_net_5d": [1.0, 2.0, 3.0]}, index=pd.Index(["A", "B", "C"], name="ticker"))

    snaps = {"d1": snap([10.0, 10.0, 10.0], [10.0, 10.0, 80.0]),
             "d2": snap([11.0, 12.0, 10.0], [30.0, 30.0, 40.0])}
    res = flow.compute(["d1", "d2"], snaps.get, {"semi": ["A", "B"], "other": ["C"]})
    assert res["d1"]["semi"]["share"] == pytest.approx(0.2)
    assert res["d1"]["semi"]["ret"] is None and res["d1"]["semi"]["heat"] is None
    m = res["d2"]["semi"]
    assert m["share"] == pytest.approx(0.6)
    assert m["heat"] == pytest.approx(3.0)                    # 0.6 / 0.2
    assert m["ret"] == pytest.approx((0.1 * 100 + 0.2 * 300) / 400)  # 시총 가중
    assert m["foreign_5d"] == 3.0 and m["n"] == 2


def test_release_notes_flow_section(tmp_path):
    import json as _json
    from mymoney.report import release_notes

    snap_dir, top_dir, meta = tmp_path / "s", tmp_path / "t", tmp_path / "m"
    for i, d in enumerate(["20261012", "20261013"]):
        s = make_snap(40 + i, n=80)
        s["market_cap"], s["trading_value"] = 1e12, 1e10
        sc = score(s)
        track.save_day(d, s, top_n(sc), len(sc), snap_dir=snap_dir, top_dir=top_dir)
    meta.mkdir()
    pd.Series(["전기·전자"] * 40 + ["제약"] * 40, index=pd.Index(s.index, name="ticker"),
              name="sector").to_csv(meta / "sectors.csv")
    (meta / "themes.json").write_text(_json.dumps(
        {"반도체": {"etf": "091160", "etf_name": "KODEX 반도체", "tickers": list(s.index[:15])}}), encoding="utf-8")
    site = track.build_site(top_dir=top_dir, snap_dir=snap_dir, site_file=tmp_path / "h.json", meta_dir=meta)
    md = release_notes(site, "20261013")
    assert "돈의 흐름" in md and "KODEX 반도체" in md and "| 전기·전자 |" in md
    assert md.index("시장 전체") < md.index("돈의 흐름") < md.index("### 가치")
    assert "오늘의 숲" in md and "| KOSPI |" in md


def test_site_json_has_no_nan_even_with_missing_names(tmp_path):
    import json as _json

    snap_dir, top_dir, site = tmp_path / "s", tmp_path / "t", tmp_path / "h.json"
    for i, d in enumerate(["20261012", "20261013"]):
        s = make_snap(50 + i, n=80)
        s["market_cap"], s["trading_value"] = 1e12, 1e10
        s["name"] = s["name"].astype(object)
        s.iloc[:, s.columns.get_loc("name")] = np.nan  # 이름이 전부 없는 극단적 경우
        sc = score(s)
        track.save_day(d, s, top_n(sc), len(sc), snap_dir=snap_dir, top_dir=top_dir)
    track.build_site(top_dir=top_dir, snap_dir=snap_dir, site_file=site, meta_dir=tmp_path / "m")
    text = site.read_text(encoding="utf-8")
    assert "NaN" not in text
    data = _json.loads(text)
    first = data["days"]["20261013"]["categories"]["value"][0]
    assert first["name"] == first["ticker"]


def test_members_sorted_by_value_with_returns():
    from mymoney import flow

    def snap(close, value):
        return pd.DataFrame({"name": ["a", "b", "c"], "close": close, "trading_value": value,
                             "foreign_net_5d": [1.0, -2.0, 0.0]}, index=pd.Index(["A", "B", "C"], name="ticker"))

    prev, cur = snap([10.0, 10.0, 10.0], [1, 1, 1]), snap([11.0, 9.0, 10.0], [10.0, 30.0, 0.0])
    rows = flow.members(cur, prev, None, ["A", "B", "C", "Z"])
    assert [r["ticker"] for r in rows] == ["B", "A"]  # 거래 없는 C, 없는 Z 제외
    assert rows[0]["ret"] == pytest.approx(-0.1) and rows[0]["weight"] == pytest.approx(0.75)
    assert rows[0]["ret5"] is None


def test_release_notes_stays_under_github_limit(monkeypatch):
    from mymoney import report

    site = {"days": {"d": {"universe_size": 1, "categories": {}, "dropped": {}}}, "dates": ["d"],
            "performance": {}, "flows": {}}
    monkeypatch.setattr(report, "BODY_LIMIT", 500)
    assert len(report.release_notes(site, "d")) <= 500
