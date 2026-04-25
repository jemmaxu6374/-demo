"""Replay Events：把 behavior_events 全量归因 + 贝叶斯更新，写 competency_timeline。

执行：python scripts/replay_events.py [--employee EMP_ID]

会：
1. 清空 competency_deltas + competency_timeline + timeline_snapshots
2. 按时间升序重放所有事件
3. 每条事件 → attribute_event → update_from_deltas
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loguru import logger  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from src.events.event_loader import load_events_from_disk  # noqa: E402
from src.events.event_processor import attribute_event  # noqa: E402
from src.events.profile_updater import update_one  # noqa: E402
from src.storage.models import (  # noqa: E402
    CompetencyDeltaRow,
    CompetencyTimelineRow,
    TimelineSnapshotRow,
    get_session_factory,
    init_db,
)
from src.storage.repository import (  # noqa: E402
    bulk_insert_deltas,
)


def _reset_dynamic_tables():
    init_db()
    S = get_session_factory()
    with S() as s:
        s.execute(delete(CompetencyDeltaRow))
        s.execute(delete(CompetencyTimelineRow))
        s.execute(delete(TimelineSnapshotRow))
        s.commit()
    logger.info("Cleared deltas / timeline / snapshots")


def replay_for_employee(eid: str):
    # 从 jsonl 读（保留 competency_hints，作为归因的 ground truth）
    events = load_events_from_disk(eid)
    events.sort(key=lambda e: e["ts"])
    logger.info(f"[{eid}] replaying {len(events)} events (from jsonl, hints-driven)...")
    total_deltas = 0
    batch_deltas: list[dict] = []
    batch_size = 500
    for ev_dict in events:
        ts = ev_dict["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        deltas = attribute_event(ev_dict, prefer_hints=True)
        for d in deltas:
            update_one(
                employee_id=eid,
                competency_id=d.competency_id,
                delta_level=d.delta_level,
                confidence=d.confidence,
                event_ts=ts,
                event_id=d.event_id,
                persist=True,
            )
            batch_deltas.append({
                "event_id": d.event_id,
                "employee_id": eid,
                "competency_id": d.competency_id,
                "delta_level": d.delta_level,
                "confidence": d.confidence,
                "rationale": d.rationale,
                "ts": ts,
            })
            if len(batch_deltas) >= batch_size:
                bulk_insert_deltas(batch_deltas)
                total_deltas += len(batch_deltas)
                batch_deltas = []
    if batch_deltas:
        bulk_insert_deltas(batch_deltas)
        total_deltas += len(batch_deltas)
    logger.info(f"[{eid}] wrote {total_deltas} deltas")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--employee", help="single employee_id (for testing)")
    parser.add_argument("--keep", action="store_true", help="不重置 deltas/timeline 表")
    args = parser.parse_args()

    if not args.keep:
        _reset_dynamic_tables()

    if args.employee:
        replay_for_employee(args.employee)
    else:
        # 从 jsonl 目录扫描员工 ID
        from config import settings
        bd = settings.abs_path(settings.behavior_dir)
        ids = sorted(p.name for p in bd.iterdir() if p.is_dir())
        for eid in ids:
            replay_for_employee(eid)

    # 最终统计
    S = get_session_factory()
    with S() as s:
        n_d = s.query(CompetencyDeltaRow).count()
        n_t = s.query(CompetencyTimelineRow).count()
    logger.info(f"Replay done: deltas={n_d}, timeline points={n_t}")


if __name__ == "__main__":
    main()
