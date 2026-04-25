"""Expert Finder：基于 competency_timeline 实时识别"近 N 天在某能力上高产出"的员工。

定义"高产出"：
- 在时间窗口内，该员工在该能力上的累积 delta_level（加权 confidence）≥ 阈值
- 或当前 level ≥ 4

输出作为"隐形导师"候选，与静态 mentor 池叠加。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.storage.models import CompetencyDeltaRow, CompetencyTimelineRow, get_session_factory  # noqa: E402


@dataclass
class ExpertCandidate:
    employee_id: str
    competency_id: str
    recent_cumulative_delta: float
    current_level: float
    score: float                # 综合分
    evidence_count: int


def find_experts(
    competency_id: str,
    *,
    as_of: datetime | None = None,
    window_days: int | None = None,
    exclude: set[str] | None = None,
    min_delta: float | None = None,
    top_k: int = 5,
) -> list[ExpertCandidate]:
    """查询某能力维度上近期高产出的员工。"""
    as_of = as_of or datetime.utcnow()
    window_days = window_days or settings.expert_recent_days
    min_delta = min_delta if min_delta is not None else settings.expert_min_delta
    start = as_of - timedelta(days=window_days)
    exclude = exclude or set()

    s = get_session_factory()()
    try:
        # 近 N 天该能力累积正向 delta（加权 conf）
        delta_rows = (
            s.query(
                CompetencyDeltaRow.employee_id,
                func.sum(CompetencyDeltaRow.delta_level * CompetencyDeltaRow.confidence).label("sum_d"),
                func.count(CompetencyDeltaRow.id).label("cnt"),
            )
            .filter(
                CompetencyDeltaRow.competency_id == competency_id,
                CompetencyDeltaRow.ts >= start,
                CompetencyDeltaRow.ts <= as_of,
                CompetencyDeltaRow.delta_level > 0,
            )
            .group_by(CompetencyDeltaRow.employee_id)
            .all()
        )

        if not delta_rows:
            return []

        # 取每个候选的当前 level（as_of 之前的最新）
        candidates: list[ExpertCandidate] = []
        for row in delta_rows:
            if row.employee_id in exclude or float(row.sum_d) < min_delta:
                continue
            latest = (
                s.query(CompetencyTimelineRow)
                .filter(
                    CompetencyTimelineRow.employee_id == row.employee_id,
                    CompetencyTimelineRow.competency_id == competency_id,
                    CompetencyTimelineRow.ts <= as_of,
                )
                .order_by(CompetencyTimelineRow.ts.desc())
                .first()
            )
            lvl = latest.level if latest else 1.0
            if lvl < 2.5 and float(row.sum_d) < min_delta * 1.5:
                continue
            # 综合分：level × 0.6 + 累积 delta × 0.4
            score = round(lvl * 0.6 + float(row.sum_d) * 0.4, 3)
            candidates.append(ExpertCandidate(
                employee_id=row.employee_id,
                competency_id=competency_id,
                recent_cumulative_delta=round(float(row.sum_d), 3),
                current_level=round(lvl, 2),
                score=score,
                evidence_count=int(row.cnt),
            ))
        candidates.sort(key=lambda x: -x.score)
        return candidates[:top_k]
    finally:
        s.close()
