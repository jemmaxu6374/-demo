"""贝叶斯 Beta 后验 + 指数时间衰减的画像更新器。

### 数学模型（严格对齐 plan）

1. **Beta 后验**：每个 competency 维护 Beta(α, β)，level ≈ 5 × α/(α+β)
   - 新事件贡献 Δα/Δβ：
     - delta > 0（正向证据）：Δα = |delta| × confidence × k，Δβ = 0
     - delta < 0（反例）：Δα = 0，Δβ = |delta| × confidence × k
   - k = settings.bayes_max_delta_per_event 控制单事件最大影响（防极端翻转）

2. **指数时间衰减**：
   - level(t) = level_peak × exp(-λ × Δt_days)
   - λ 按 decay_type 区分（hard/soft/domain）
   - 最低衰减到 level_peak × decay_floor_ratio（保留"曾经达到"记忆）
   - α/β 按同比缩放

3. **合理性检查**：单次更新 |Δlevel| > 2 时打 WARN，但不阻塞（仅记录）
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.profile.ontology_loader import get_competency  # noqa: E402
from src.schemas import CompetencyDelta, TimelinePoint  # noqa: E402
from src.storage.repository import (  # noqa: E402
    insert_timeline_points,
    query_latest_before,
)


def _decay_lambda(competency_id: str) -> float:
    """按 decay_type 取 λ。"""
    c = get_competency(competency_id)
    if not c:
        return settings.decay_lambda_hard
    return {
        "hard": settings.decay_lambda_hard,
        "soft": settings.decay_lambda_soft,
        "domain": settings.decay_lambda_domain,
    }.get(c.decay_type, settings.decay_lambda_hard)


def _level_from_beta(alpha: float, beta: float) -> float:
    """Beta(α, β) → level 1-5 连续值。α+β=0 防御。"""
    total = max(alpha + beta, 1e-6)
    raw = alpha / total  # 0-1
    return round(1.0 + raw * 4.0, 3)


def apply_decay(
    prev_alpha: float,
    prev_beta: float,
    delta_days: float,
    lam: float,
) -> tuple[float, float, float]:
    """时间衰减：Beta 参数按指数缩放，但保留最低值。

    返回 (alpha_decayed, beta_decayed, decay_factor)
    """
    factor = math.exp(-lam * max(delta_days, 0))
    # 最低保留 decay_floor_ratio
    factor = max(factor, settings.decay_floor_ratio)
    # α、β 等比缩放，保留 shape
    return prev_alpha * factor, prev_beta * factor, factor


def update_one(
    *,
    employee_id: str,
    competency_id: str,
    delta_level: float,
    confidence: float,
    event_ts: datetime,
    event_id: str = "",
    persist: bool = True,
) -> TimelinePoint:
    """单点更新：读最新状态 → 衰减到 event_ts → 吸收新证据 → 写回 timeline。"""
    prev = query_latest_before(employee_id, competency_id, event_ts)

    if prev is None:
        # 冷启动：默认先验
        alpha = settings.bayes_alpha_init
        beta = settings.bayes_beta_init
        prev_ts = event_ts  # 无需衰减
    else:
        delta_days = (event_ts - prev.ts).total_seconds() / 86400
        alpha, beta, _ = apply_decay(prev.alpha, prev.beta, delta_days, _decay_lambda(competency_id))
        prev_ts = prev.ts

    # 吸收证据
    k = settings.bayes_max_delta_per_event
    magnitude = min(abs(delta_level), 1.0) * confidence * k
    if delta_level >= 0:
        alpha += magnitude
    else:
        beta += magnitude

    # 软下限防止退化
    alpha = max(alpha, 0.5)
    beta = max(beta, 0.5)

    new_level = _level_from_beta(alpha, beta)

    # 合理性检查
    if prev is not None and abs(new_level - prev.level) > 2.0:
        logger.warning(
            f"Level jump >2 detected: {employee_id}/{competency_id} "
            f"{prev.level:.2f} → {new_level:.2f} (Δlevel={delta_level:+.2f}, conf={confidence})"
        )

    point = TimelinePoint(
        employee_id=employee_id,
        competency_id=competency_id,
        ts=event_ts,
        level=new_level,
        alpha=round(alpha, 4),
        beta=round(beta, 4),
    )
    if persist:
        insert_timeline_points([point.model_dump() | {"source_event_id": event_id}])
    return point


def update_from_deltas(
    deltas: list[CompetencyDelta],
    employee_id: str,
    event_ts_map: dict[str, datetime],
) -> list[TimelinePoint]:
    """批量更新（按 ts 升序吸收）。

    event_ts_map: event_id → ts（因 delta 里没带 ts）。
    """
    # 先把 deltas 按 ts 排序
    triples = []
    for d in deltas:
        ts = event_ts_map.get(d.event_id)
        if ts is None:
            continue
        triples.append((ts, d))
    triples.sort(key=lambda x: x[0])

    points: list[TimelinePoint] = []
    for ts, d in triples:
        p = update_one(
            employee_id=employee_id,
            competency_id=d.competency_id,
            delta_level=d.delta_level,
            confidence=d.confidence,
            event_ts=ts,
            event_id=d.event_id,
            persist=True,
        )
        points.append(p)
    return points
