"""배치가 '언제, 어떻게' 돌았는지 기록한다.

GitHub 예약 실행은 정시를 보장하지 않으므로(수십 분~수 시간 지연, 가끔 누락),
실제 실행 시각과 예약 시각을 함께 남겨 리포트에 보여 준다.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_FILE = ROOT / "data" / "runs.csv"
KST = timezone(timedelta(hours=9))
FIELDS = ["run_at", "trigger", "scheduled_kst", "delay_min", "target_date", "collected"]


def now_kst() -> datetime:
    return datetime.now(KST)


def cron_to_kst(cron: str) -> str | None:
    """'40 7 * * 1-5'(UTC) → '16:40'. 분·시만 쓴다."""
    try:
        m, h = (int(x) for x in cron.split()[:2])
    except (ValueError, AttributeError):
        return None
    return f"{(h + 9) % 24:02d}:{m:02d}"


def trigger() -> tuple[str, str | None]:
    """(실행 방식, 예약 시각 KST). GitHub Actions 밖에서는 ('수동(로컬)', None)."""
    event = os.environ.get("RUN_EVENT", "")
    if event == "schedule":
        return "예약", cron_to_kst(os.environ.get("RUN_CRON", ""))
    if event == "workflow_dispatch":
        return "수동", None
    return "수동(로컬)", None


def delay_minutes(run_at: datetime, scheduled_kst: str | None) -> int | None:
    if not scheduled_kst:
        return None
    h, m = (int(x) for x in scheduled_kst.split(":"))
    planned = run_at.replace(hour=h, minute=m, second=0, microsecond=0)
    if planned > run_at:          # 예: 08:23 예약이 자정 넘겨 실행된 경우는 없지만, 날짜 경계 보호
        planned -= timedelta(days=1)
    return int((run_at - planned).total_seconds() // 60)


def record(target_date: str, collected: bool, path: Path = RUN_FILE) -> dict:
    run_at = now_kst()
    how, sched = trigger()
    row = {
        "run_at": run_at.strftime("%Y-%m-%d %H:%M"),
        "trigger": how,
        "scheduled_kst": sched or "",
        "delay_min": "" if delay_minutes(run_at, sched) is None else delay_minutes(run_at, sched),
        "target_date": target_date,
        "collected": "Y" if collected else "N",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def load(path: Path = RUN_FILE) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def describe(meta: dict | None) -> str:
    """리포트용 한 줄: '10/15 18:03 KST 수집 · 예약 실행(16:40 예약 → 83분 지연)'."""
    if not meta or not meta.get("collected_at"):
        return ""
    s = f"⏱ 데이터 수집 {meta['collected_at']} KST · {meta.get('trigger', '')} 실행"
    if meta.get("scheduled_kst"):
        d = meta.get("delay_min")
        s += f" ({meta['scheduled_kst']} 예약" + (f" → {d}분 지연)" if d not in (None, "") else ")")
    return s
