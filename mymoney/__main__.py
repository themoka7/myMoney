"""사용법:
    python -m mymoney run [--date YYYYMMDD]   # 수집 → 점수 → 저장 → 대시보드 데이터 갱신
    python -m mymoney build                   # 저장된 데이터로 대시보드 데이터만 재생성
    python -m mymoney show [--date YYYYMMDD]  # 저장된 TOP N을 터미널에 출력
    python -m mymoney notes [--date YYYYMMDD] [--out FILE]  # Release 본문용 마크다운
"""
from __future__ import annotations

import argparse
import sys

from . import config, track


def cmd_run(args) -> int:
    from .collect import collect, latest_business_day, recent_closes
    from .score import score, top_n

    date = latest_business_day(args.date)
    if (track.TOP_DIR / f"{date}.json").exists() and not args.force:
        print(f"{date}: 이미 수집됨 (--force 로 덮어쓰기)")
    else:
        snap = collect(date)
        scores = score(snap)
        top = top_n(scores)
        tickers = sorted({it["ticker"] for items in top.values() for it in items})
        prices = recent_closes(date, tickers, cached=track.load_snapshot)
        track.save_day(date, snap, top, universe_size=len(scores), prices=prices)
        print(f"{date}: 전체 {len(snap)}종목, 유니버스 {len(scores)}종목 저장")
    track.build_site()
    _print_day(date)
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
    date = args.date or site["dates"][-1]
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
    sub.add_parser("build")
    s = sub.add_parser("show")
    s.add_argument("--date")
    n = sub.add_parser("notes")
    n.add_argument("--date")
    n.add_argument("--out")
    args = p.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "notes":
        return cmd_notes(args)
    _print_day(args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
