"""Event Loader：读取 data/behavior_streams/{emp}/{source}.jsonl 并入 SQLite。"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.storage.repository import bulk_insert_events, count_events  # noqa: E402


SOURCES = ["task", "code", "doc", "learning", "meeting", "feedback"]


def load_events_from_disk(employee_id: str | None = None) -> list[dict]:
    """读取 jsonl 返回事件列表，不入 DB。"""
    root = settings.abs_path(settings.behavior_dir)
    events: list[dict] = []
    employees = [employee_id] if employee_id else sorted(p.name for p in root.iterdir() if p.is_dir())
    for eid in employees:
        emp_dir = root / eid
        if not emp_dir.exists():
            continue
        for src in SOURCES:
            fp = emp_dir / f"{src}.jsonl"
            if not fp.exists():
                continue
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                events.append(json.loads(line))
    return events


def load_into_db(reset: bool = False) -> int:
    """把所有 jsonl 加载到 behavior_events 表。"""
    from src.storage.models import init_db, reset_db

    if reset:
        reset_db()
    else:
        init_db()

    events = load_events_from_disk()
    logger.info(f"Loaded {len(events)} events from disk, writing to DB...")
    n = bulk_insert_events(events)
    logger.info(f"Inserted {n} events; total in DB: {count_events()}")
    return n


if __name__ == "__main__":
    load_into_db(reset=True)
