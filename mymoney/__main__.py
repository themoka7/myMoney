"""사용법:
    python -m mymoney run [--date YYYYMMDD]   # 수집 → 점수 → 저장 → 대시보드 데이터 갱신
    python -m mymoney backfill --days 20      # 최근 20영업일 채우기 (있는 날은 건너뜀)
    python -m mymoney meta                    # 섹터 분류·테마 ETF 구성만 갱신
    python -m mymoney build                   # 저장된 데이터로 대시보드 데이터만 재생성
    python -m mymoney show [--date YYYYMMDD]  # 저장된 TOP N을 터미널에 출력
    python -m mymoney notes [--date YYYYMMDD] [--out FILE]  # Release 본문용 마크다운
"""
from __future__ import annotations

import argparse
import sys

from . import config, track


def _collect_day(date: str, force: bool) -> bool:
    """date 하루를 수집·저장한다. 새로 저장했으면 True."""
    from .collect import collect, recent_closes
    from .score import score, top_n

    if (track.TOP_DIR / f"{date}.json").exists() and not force:
        print(f"{date}: 이미 수집됨 (--force 로 덮어쓰기)")
        return False
    snap = collect(date, cached=track.load_snapshot)
    scores = score(snap)
    top = top_n(scores)
    tickers = sorted({it["ticker"] for items in top.values() for it in items})
    prices = recent_closes(date, tickers, cached=track.load_snapshot)
    track.save_day(date, snap, top, universe_size=len(scores), prices=prices)
    print(f"{date}: 전체 {len(snap)}종목, 유니버스 {len(scores)}종목 저장")
    return True


def _refresh_meta(date: str) -> None:
    """섹터 분류·테마 ETF 구성을 갱신한다. 실패해도 기존 파일로 계속 간다."""
    from . import flow
    from .collect import sector_map, theme_members

    try:
        flow.save_meta(sector_map(date), theme_members(date))
    except Exception as e:
        print(f"섹터/테마 구성 갱신 실패 (기존 파일 사용): {e}", file=sys.stderr)


def cmd_run(args) -> int:
    from .collect import latest_business_day

    from . import runlog

    date = latest_business_day(args.date)
    collected = _collect_day(date, args.force)
    runlog.record(date, collected)
    _refresh_meta(date)
    track.build_site()
    _print_day(date)
    return 0


def cmd_backfill(args) -> int:
    """최근 N영업일을 오래된 날부터 채운다. 이미 있는 날은 건너뛴다."""
    from .collect import business_days, latest_business_day

    end = latest_business_day(args.end)
    days = business_days(end, args.days)
    print(f"백필 {days[0]} ~ {days[-1]} ({len(days)}영업일)")
    from . import runlog

    failed = []
    for d in days:
        try:
            if _collect_day(d, args.force):
                runlog.record(d, True)
        except Exception as e:  # 하루 실패가 전체를 막지 않게
            failed.append(d)
            print(f"{d}: 실패 — {e}", file=sys.stderr)
    _refresh_meta(end)
    track.build_site()
    _print_day(end)
    if failed:
        print(f"\n실패 {len(failed)}일: {' '.join(failed)} — 다시 실행하면 빠진 날만 채운다", file=sys.stderr)
    return 0


def cmd_meta(args) -> int:
    from .collect import latest_business_day

    _refresh_meta(latest_business_day(args.date))
    track.build_site()
    return 0


def cmd_build(args) -> int:
    data = track.build_site()
    print(f"history.json 갱신: {len(data['dates'])}일치")
    return 0


def cmd_notes(args) -> int:
    from .report import release_notes

    site = track.build_site()
    if not site["dates"]:
        print("저장된 데이터가 없습니다.", file=sys.stderr)
        return 1
    # 휴장일을 넣으면 그 이전 마지막 기록일로
    date = max((d for d in site["dates"] if d <= (args.date or "99999999")), default=site["dates"][0])
    follow = track.followup(track.load_tops(), date)
    text = release_notes(site, date, follow)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(date)
    else:
        print(text)
    return 0


def _print_day(date: str | None) -> None:
    tops = track.load_tops()
    if not tops:
        print("저장된 데이터가 없습니다.")
        return
    date = date or max(tops)
    days = track.annotate_changes(tops)
    day = days.get(date)
    if day is None:
        print(f"{date}: 데이터 없음")
        return
    print(f"\n=== {date} (유니버스 {day['universe_size']}종목) ===")
    for cat, (label, _) in config.CATEGORIES.items():
        print(f"\n[{label}]")
        for it in day["categories"][cat]:
            pr = it["prev_rank"]
            move = "NEW" if pr is None else ("-" if pr == it["rank"] else f"{pr - it['rank']:+d}")
            print(f"{it['rank']:>3}. {it['name']:<14} {it['ticker']}  점수 {it['score']:6.2f}  "
                  f"{move:>4}  연속 {it['streak']}일")
        if day["dropped"][cat]:
            print("     이탈: " + ", ".join(f"{x['name']}({x['prev_rank']}위)" for x in day["dropped"][cat]))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mymoney")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--date")
    r.add_argument("--force", action="store_true")
    b = sub.add_parser("backfill")
    b.add_argument("--days", type=int, default=20)
    b.add_argument("--end")
    b.add_argument("--force", action="store_true")
    sub.add_parser("build")
    m = sub.add_parser("meta")
    m.add_argument("--date")
    s = sub.add_parser("show")
    s.add_argument("--date")
    n = sub.add_parser("notes")
    n.add_argument("--date")
    n.add_argument("--out")
    args = p.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "backfill":
        return cmd_backfill(args)
    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "meta":
        return cmd_meta(args)
    if args.cmd == "notes":
        return cmd_notes(args)
    _print_day(args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
