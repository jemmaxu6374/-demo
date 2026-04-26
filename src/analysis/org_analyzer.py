"""组织级聚合分析器（L&D 视角核心）。

职责：
- 全员能力矩阵（competency × employee 的 level 热力数据）
- 全员 Gap 聚合（某能力在多少员工中存在 gap）
- 岗位匹配矩阵（所有员工 × 所有 JD 的 match_score）
- 隐形专家映射（每项能力的 Top-K 高产出员工）
- 赋能 ROI 代理指标（触发信号数、能力提升均值、推送响应率估算）

所有函数都是 **只读聚合**，不写任何数据。
用 @lru_cache 缓存结果，但因为员工/能力有限（20 × 36），也可直接计算。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analysis.gap_analyzer import analyze_gap, match_score  # noqa: E402
from src.profile.employee_builder import build_profile as build_emp, list_employees  # noqa: E402
from src.profile.job_builder import build_profile as build_job, list_jds  # noqa: E402
from src.profile.ontology_loader import (  # noqa: E402
    all_competencies,
    category_name,
    competency_name,
    get_competency,
)
from src.recommender.expert_finder import find_experts, ExpertCandidate  # noqa: E402
from src.storage.repository import (  # noqa: E402
    count_events,
    query_profile_at,
    query_snapshot_at,
)


# ---------------------------------------------------------------- 缓存辅助

@lru_cache(maxsize=1)
def _all_emp_profiles() -> list:
    return [build_emp(e["employee_id"]) for e in list_employees()]


@lru_cache(maxsize=1)
def _all_job_profiles() -> list:
    return [build_job(j["jd_id"]) for j in list_jds()]


# ---------------------------------------------------------------- 1) 能力热力矩阵

@dataclass
class CompetencyMatrix:
    employee_ids: list[str]
    employee_names: list[str]
    competency_ids: list[str]
    competency_names: list[str]
    matrix: list[list[float]]     # [emp_idx][comp_idx] = level（0 表示未掌握）
    coverage: dict[str, int]      # competency_id → 掌握 ≥ L3 的员工数


def build_competency_matrix(min_level: float = 0.0) -> CompetencyMatrix:
    """返回员工×能力的 level 热力矩阵（静态画像，Phase 1）。"""
    profiles = _all_emp_profiles()
    comps = all_competencies()

    emp_ids = [p.employee_id for p in profiles]
    emp_names = [p.name for p in profiles]
    comp_ids = [c.id for c in comps]
    comp_names = [c.name for c in comps]

    matrix: list[list[float]] = []
    coverage: dict[str, int] = defaultdict(int)
    for p in profiles:
        level_map = {t.competency_id: t.level for t in p.competencies}
        row = []
        for c in comps:
            lvl = float(level_map.get(c.id, 0.0))
            row.append(round(lvl, 2) if lvl >= min_level else 0.0)
            if lvl >= 3.0:
                coverage[c.id] += 1
        matrix.append(row)

    return CompetencyMatrix(
        employee_ids=emp_ids,
        employee_names=emp_names,
        competency_ids=comp_ids,
        competency_names=comp_names,
        matrix=matrix,
        coverage=dict(coverage),
    )


# ---------------------------------------------------------------- 2) 岗位匹配矩阵

@dataclass
class JobMatchMatrix:
    employee_ids: list[str]
    employee_names: list[str]
    jd_ids: list[str]
    jd_titles: list[str]
    scores: list[list[float]]     # [emp_idx][jd_idx] = match_score 0-1


def build_job_match_matrix() -> JobMatchMatrix:
    """全员×全 JD 的匹配度矩阵。"""
    emps = _all_emp_profiles()
    jobs = _all_job_profiles()

    scores: list[list[float]] = []
    for emp in emps:
        row = []
        for job in jobs:
            row.append(round(match_score(emp, job), 3))
        scores.append(row)

    return JobMatchMatrix(
        employee_ids=[e.employee_id for e in emps],
        employee_names=[e.name for e in emps],
        jd_ids=[j.jd_id for j in jobs],
        jd_titles=[j.title for j in jobs],
        scores=scores,
    )


# ---------------------------------------------------------------- 3) 全员 Gap 聚合

@dataclass
class GapAggregation:
    competency_id: str
    name: str
    category: str
    total_employees: int          # 该能力被多少员工 gap 到（针对推荐岗位）
    avg_gap: float                # 平均 gap 值
    avg_weight: float
    high_priority_count: int      # 被标为 high 的人数
    suggested_mode: str           # 建议主攻学习形态


def aggregate_gaps_for_job(jd_id: str) -> list[GapAggregation]:
    """针对某个 JD，聚合所有员工的 Gap。

    L&D 用这个来回答："如果我把所有员工推到这个目标岗位，最大集体缺口在哪？"
    """
    job = build_job(jd_id)
    profiles = _all_emp_profiles()

    bucket: dict[str, list] = defaultdict(list)  # comp_id → [GapItem]
    for p in profiles:
        gaps = analyze_gap(p, job, use_llm_rank=False)  # 聚合场景不用 LLM
        for g in gaps:
            if g.gap > 0:
                bucket[g.competency_id].append(g)

    out: list[GapAggregation] = []
    for cid, items in bucket.items():
        c = get_competency(cid)
        cat = category_name(c.parent_id) if c else "?"
        mode_map = {"hard": "formal", "soft": "experiential", "domain": "social"}
        out.append(GapAggregation(
            competency_id=cid,
            name=competency_name(cid),
            category=cat,
            total_employees=len(items),
            avg_gap=round(sum(g.gap for g in items) / len(items), 2),
            avg_weight=round(sum(g.weight for g in items) / len(items), 3),
            high_priority_count=sum(1 for g in items if g.priority == "high"),
            suggested_mode=mode_map.get(c.decay_type if c else "hard", "formal"),
        ))
    out.sort(key=lambda x: (-x.high_priority_count, -x.avg_gap * x.avg_weight))
    return out


# ---------------------------------------------------------------- 4) 全能力 Top 专家

@dataclass
class ExpertMapEntry:
    competency_id: str
    name: str
    top_experts: list[ExpertCandidate]
    coverage_level_ge4: int       # 静态画像中 ≥ L4 的员工数


def build_expert_map(
    as_of: datetime | None = None,
    top_k: int = 3,
    only_competencies: list[str] | None = None,
) -> list[ExpertMapEntry]:
    """为每个能力找出 Top-K 隐形专家（基于行为流近 30 天累积 delta）。

    若 DB 无 timeline（P2 未回放），仅回退到静态画像 L≥4 的员工作为专家候选。
    """
    as_of = as_of or datetime.utcnow()
    matrix = build_competency_matrix()

    # 静态覆盖：每个能力 ≥ L4 的员工
    static_map: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for i, eid in enumerate(matrix.employee_ids):
        for j, cid in enumerate(matrix.competency_ids):
            lvl = matrix.matrix[i][j]
            if lvl >= 4.0:
                static_map[cid].append((eid, lvl))

    has_timeline = count_events() > 0

    out: list[ExpertMapEntry] = []
    cids = only_competencies or matrix.competency_ids
    for cid in cids:
        if has_timeline:
            experts = find_experts(cid, as_of=as_of, top_k=top_k)
        else:
            experts = []

        # 若动态路径没结果，用静态候选补
        if not experts and static_map.get(cid):
            from src.recommender.expert_finder import ExpertCandidate as EC

            experts = [
                EC(
                    employee_id=eid,
                    competency_id=cid,
                    recent_cumulative_delta=0.0,
                    current_level=lvl,
                    score=lvl,
                    evidence_count=0,
                )
                for eid, lvl in sorted(static_map[cid], key=lambda x: -x[1])[:top_k]
            ]

        if not experts:
            continue

        out.append(ExpertMapEntry(
            competency_id=cid,
            name=competency_name(cid),
            top_experts=experts,
            coverage_level_ge4=len(static_map.get(cid, [])),
        ))
    return out


# ---------------------------------------------------------------- 5) 赋能 ROI 代理指标

@dataclass
class OrgROISnapshot:
    total_employees: int
    total_events_6mo: int
    avg_events_per_emp: float
    total_timeline_points: int
    avg_level_gain_6mo: float     # 近 6 个月每个员工平均 level 涨幅
    strong_competencies: int      # 覆盖 ≥ 60% 员工 @ L≥3 的能力数
    weak_competencies: int        # 覆盖 ≤ 20% 员工 @ L≥3 的能力数
    expert_signals: int           # 可识别隐形专家的能力数
    trigger_signals_est: int      # 预计可触发的赋能信号数（估算）


def compute_org_roi(as_of: datetime | None = None) -> OrgROISnapshot:
    """一次性计算组织级健康度指标，用于 ROI 仪表盘。"""
    as_of = as_of or datetime.utcnow()
    matrix = build_competency_matrix()

    total_emp = len(matrix.employee_ids)
    total_comp = len(matrix.competency_ids)

    strong = sum(1 for cid in matrix.competency_ids
                 if matrix.coverage.get(cid, 0) >= 0.6 * total_emp)
    weak = sum(1 for cid in matrix.competency_ids
               if matrix.coverage.get(cid, 0) <= 0.2 * total_emp)

    # 行为流规模
    total_events = count_events()
    avg_events = round(total_events / total_emp, 1) if total_emp else 0.0

    # 近 6 个月 level 涨幅（用每人每能力在 as_of vs 180 天前的 snapshot 差异）
    ago = as_of - timedelta(days=180)
    gains: list[float] = []
    expert_count = 0
    timeline_total = 0
    try:
        for eid in matrix.employee_ids:
            snap_now = query_snapshot_at(eid, as_of)
            snap_ago = query_snapshot_at(eid, ago)
            timeline_total += len(snap_now)
            for cid, row in snap_now.items():
                old = snap_ago.get(cid)
                if old:
                    gains.append(row.level - old.level)
    except Exception:
        pass

    avg_gain = round(sum(gains) / len(gains), 2) if gains else 0.0

    # Expert 信号：遍历所有能力看能否找到隐形专家
    try:
        expert_entries = build_expert_map(as_of=as_of, top_k=1)
        expert_count = sum(1 for e in expert_entries if e.top_experts)
    except Exception:
        pass

    # 触发信号估算：约等于 gap>0 的 (员工,能力) 对的数量（粗估）
    trigger_est = 0
    try:
        jobs = _all_job_profiles()[:3]  # 抽样 3 个 JD 估算
        for job in jobs:
            for p in _all_emp_profiles():
                gaps = analyze_gap(p, job, use_llm_rank=False)
                trigger_est += sum(1 for g in gaps if g.gap > 0 and g.priority != "low")
        trigger_est = int(trigger_est / 3)  # 平均到单 JD
    except Exception:
        pass

    return OrgROISnapshot(
        total_employees=total_emp,
        total_events_6mo=total_events,
        avg_events_per_emp=avg_events,
        total_timeline_points=timeline_total,
        avg_level_gain_6mo=avg_gain,
        strong_competencies=strong,
        weak_competencies=weak,
        expert_signals=expert_count,
        trigger_signals_est=trigger_est,
    )
