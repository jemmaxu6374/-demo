"""Build Timeline Snapshots：把 competency_timeline 聚合为每日快照。

执行：python scripts/build_timeline_snapshots.py

策略：
- 对每位员工 × 每个已出现的 competency，取"日末"状态（当日有多条则最后一条）
- 若某天该能力无新事件，保留前一天快照（不重复写，查询时向前回溯即可）
- 只生成"有任何 timeline 数据"的日期
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loguru import logger  # noqa: E402
from sqlalchemy import delete, func  # noqa: E402

from src.storage.models import (  # noqa: E402
    CompetencyTimelineRow,
    TimelineSnapshotRow,
    get_session_factory,
)


def _date_only(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)


def build_snapshots(chunk_size: int = 2000) -> int:
    S = get_session_factory()
    with S() as s:
        s.execute(delete(TimelineSnapshotRow))
        s.commit()

    with S() as s:
        # 一次性读全量 timeline（对 9k events × ~1.5 delta 量级是可接受的）
        rows = s.query(CompetencyTimelineRow).order_by(
            CompetencyTimelineRow.employee_id,
            CompetencyTimelineRow.competency_id,
            CompetencyTimelineRow.ts.asc(),
        ).all()

    # (emp, comp, date) → last point
    per_day: dict[tuple[str, str, datetime], CompetencyTimelineRow] = {}
    for r in rows:
        key = (r.employee_id, r.competency_id, _date_only(r.ts))
        per_day[key] = r  # 后插的覆盖，即日末

    logger.info(f"Timeline rows: {len(rows)}; distinct (emp,comp,day): {len(per_day)}")

    # 写入
    batch = []
    count = 0
    with S() as s:
        for (eid, cid, day), r in per_day.items():
            batch.append(TimelineSnapshotRow(
                employee_id=eid,
                competency_id=cid,
                date=day,
                level=r.level,
                alpha=r.alpha,
                beta=r.beta,
            ))
            if len(batch) >= chunk_size:
                s.add_all(batch)
                s.commit()
                count += len(batch)
                batch = []
        if batch:
            s.add_all(batch)
            s.commit()
            count += len(batch)

    logger.info(f"Inserted {count} daily snapshots")
    return count


if __name__ == "__main__":
    build_snapshots()
