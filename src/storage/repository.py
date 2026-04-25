"""Storage Repository：封装所有 DB 查询。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.schemas import BehaviorEvent, CompetencyDelta, TimelinePoint  # noqa: E402
from src.storage.models import (  # noqa: E402
    BehaviorEventRow,
    CompetencyDeltaRow,
    CompetencyTimelineRow,
    TaskProfileRow,
    TimelineSnapshotRow,
    get_session_factory,
)


def _session() -> Session:
    return get_session_factory()()


# ---------------------------------------------------------------- Events

def bulk_insert_events(events: Iterable[dict | BehaviorEvent]) -> int:
    rows = []
    for e in events:
        if isinstance(e, BehaviorEvent):
            d = e.model_dump()
        else:
            d = e
        ts = d["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        rows.append(BehaviorEventRow(
            event_id=d["event_id"],
            employee_id=d["employee_id"],
            source=d["source"],
            ts=ts,
            title=d["title"],
            content=d["content"],
            raw_ref=d.get("raw_ref", ""),
        ))
    with _session() as s:
        # SQLite 没有 UPSERT，先删旧的再插
        ids = [r.event_id for r in rows]
        s.query(BehaviorEventRow).filter(BehaviorEventRow.event_id.in_(ids)).delete(synchronize_session=False)
        s.add_all(rows)
        s.commit()
    return len(rows)


def list_events(
    employee_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    sources: list[str] | None = None,
    limit: int | None = None,
) -> list[BehaviorEventRow]:
    with _session() as s:
        q = s.query(BehaviorEventRow).filter(BehaviorEventRow.employee_id == employee_id)
        if start:
            q = q.filter(BehaviorEventRow.ts >= start)
        if end:
            q = q.filter(BehaviorEventRow.ts <= end)
        if sources:
            q = q.filter(BehaviorEventRow.source.in_(sources))
        q = q.order_by(BehaviorEventRow.ts.asc())
        if limit:
            q = q.limit(limit)
        return list(q)


def count_events(employee_id: str | None = None) -> int:
    with _session() as s:
        q = s.query(BehaviorEventRow)
        if employee_id:
            q = q.filter(BehaviorEventRow.employee_id == employee_id)
        return q.count()


# ---------------------------------------------------------------- Deltas

def bulk_insert_deltas(deltas: Iterable[dict | CompetencyDelta], ts_map: dict[str, datetime] | None = None) -> int:
    """ts_map: event_id → ts（若 delta 本身没携带 ts）。"""
    rows = []
    for d in deltas:
        if isinstance(d, CompetencyDelta):
            d = d.model_dump()
        ts = d.get("ts") or (ts_map.get(d["event_id"]) if ts_map else None)
        if not ts:
            continue
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        rows.append(CompetencyDeltaRow(
            event_id=d["event_id"],
            employee_id=d["employee_id"],
            competency_id=d["competency_id"],
            delta_level=float(d["delta_level"]),
            confidence=float(d["confidence"]),
            rationale=d.get("rationale", ""),
            ts=ts,
        ))
    with _session() as s:
        s.add_all(rows)
        s.commit()
    return len(rows)


# ---------------------------------------------------------------- Timeline

def insert_timeline_points(points: Iterable[dict | TimelinePoint], source_event_id: str = "") -> int:
    rows = []
    for p in points:
        if isinstance(p, TimelinePoint):
            p = p.model_dump()
        ts = p["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        rows.append(CompetencyTimelineRow(
            employee_id=p["employee_id"],
            competency_id=p["competency_id"],
            ts=ts,
            level=float(p["level"]),
            alpha=float(p["alpha"]),
            beta=float(p["beta"]),
            source_event_id=p.get("source_event_id", source_event_id),
        ))
    with _session() as s:
        s.add_all(rows)
        s.commit()
    return len(rows)


def query_latest_before(employee_id: str, competency_id: str, ts: datetime) -> CompetencyTimelineRow | None:
    """取指定员工+能力在 ts 时间点之前的最新画像点。"""
    with _session() as s:
        row = (
            s.query(CompetencyTimelineRow)
            .filter(
                CompetencyTimelineRow.employee_id == employee_id,
                CompetencyTimelineRow.competency_id == competency_id,
                CompetencyTimelineRow.ts <= ts,
            )
            .order_by(CompetencyTimelineRow.ts.desc())
            .first()
        )
        return row


def query_profile_at(employee_id: str, ts: datetime) -> dict[str, CompetencyTimelineRow]:
    """取员工在 ts 时间点的完整画像（每个能力取 ts 之前最新一点）。"""
    with _session() as s:
        # 先找每个 competency 对应的 max(ts ≤ ts)
        sub = (
            s.query(
                CompetencyTimelineRow.competency_id,
                func.max(CompetencyTimelineRow.ts).label("mx"),
            )
            .filter(
                CompetencyTimelineRow.employee_id == employee_id,
                CompetencyTimelineRow.ts <= ts,
            )
            .group_by(CompetencyTimelineRow.competency_id)
            .subquery()
        )
        rows = (
            s.query(CompetencyTimelineRow)
            .join(
                sub,
                and_(
                    CompetencyTimelineRow.competency_id == sub.c.competency_id,
                    CompetencyTimelineRow.ts == sub.c.mx,
                ),
            )
            .filter(CompetencyTimelineRow.employee_id == employee_id)
            .all()
        )
        return {r.competency_id: r for r in rows}


def query_timeline_series(
    employee_id: str,
    competency_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[CompetencyTimelineRow]:
    with _session() as s:
        q = s.query(CompetencyTimelineRow).filter(
            CompetencyTimelineRow.employee_id == employee_id,
            CompetencyTimelineRow.competency_id == competency_id,
        )
        if start:
            q = q.filter(CompetencyTimelineRow.ts >= start)
        if end:
            q = q.filter(CompetencyTimelineRow.ts <= end)
        return list(q.order_by(CompetencyTimelineRow.ts.asc()))


# ---------------------------------------------------------------- Snapshot

def bulk_insert_snapshots(rows: Iterable[dict]) -> int:
    payload = [TimelineSnapshotRow(**r) for r in rows]
    with _session() as s:
        s.add_all(payload)
        s.commit()
    return len(payload)


def query_snapshot_at(employee_id: str, date: datetime) -> dict[str, TimelineSnapshotRow]:
    """精确到日的快照；若当日无快照，取之前最近的一天。"""
    with _session() as s:
        # 先找 max(date ≤ date)
        sub = (
            s.query(
                TimelineSnapshotRow.competency_id,
                func.max(TimelineSnapshotRow.date).label("mx"),
            )
            .filter(
                TimelineSnapshotRow.employee_id == employee_id,
                TimelineSnapshotRow.date <= date,
            )
            .group_by(TimelineSnapshotRow.competency_id)
            .subquery()
        )
        rows = (
            s.query(TimelineSnapshotRow)
            .join(
                sub,
                and_(
                    TimelineSnapshotRow.competency_id == sub.c.competency_id,
                    TimelineSnapshotRow.date == sub.c.mx,
                ),
            )
            .filter(TimelineSnapshotRow.employee_id == employee_id)
            .all()
        )
        return {r.competency_id: r for r in rows}


# ---------------------------------------------------------------- Task profile

def upsert_task_profile(task_id: str, employee_id: str, title: str, summary: str, required: list[tuple[str, int, float]]) -> None:
    with _session() as s:
        s.query(TaskProfileRow).filter(TaskProfileRow.task_id == task_id).delete()
        s.add(TaskProfileRow(
            task_id=task_id,
            employee_id=employee_id,
            title=title,
            summary=summary,
            required_json=json.dumps(required, ensure_ascii=False),
        ))
        s.commit()


def get_task_profile(task_id: str) -> TaskProfileRow | None:
    with _session() as s:
        return s.query(TaskProfileRow).filter(TaskProfileRow.task_id == task_id).first()
