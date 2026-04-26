"""Gap 分析器：EmployeeProfile + JobProfile → list[GapItem]。

三步融合：
1. 结构化差值：need_level - have_level（>0 才算 gap）
2. Embedding 辅助（本地可选，不阻塞）
3. LLM 优先级裁判（mock 模式也能跑）

最终每条 GapItem 带 priority(high/mid/low) + rationale。
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.llm.client import chat_json  # noqa: E402
from src.llm.prompts import RANK_GAP  # noqa: E402
from src.profile.ontology_loader import competency_name  # noqa: E402
from src.schemas import EmployeeProfile, GapItem, JobProfile  # noqa: E402


def _priority_from_score(gap: float, weight: float) -> str:
    """优先级启发式：以加权分 score=gap×weight 为主。

    设计原则：weight 反映该能力对岗位的重要性，绝对 gap 再大但 weight 很小
    也不应该是 high（否则"英语阅读差 2 级"会盖过"核心技术差 1 级"）。
    """
    if gap <= 0:
        return "low"
    score = gap * weight
    # 主判定：按加权分
    if score >= 0.40:
        return "high"   # 核心缺口（如 gap=2, weight=0.20 或 gap=1, weight=0.40）
    if score >= 0.15:
        return "mid"    # 中等缺口
    # 次判定：绝对 gap 很大但 weight 小，给 mid 不给 high
    if gap >= 2 and score >= 0.08:
        return "mid"
    return "low"


def analyze_gap(
    emp: EmployeeProfile,
    job: JobProfile,
    *,
    include_match: bool = True,
    use_llm_rank: bool = True,
) -> list[GapItem]:
    have_map: dict[str, float] = {t.competency_id: t.level for t in emp.competencies}
    items: list[GapItem] = []

    for cid, need_level, weight in job.required_competencies:
        have = float(have_map.get(cid, 1.0))  # 未掌握默认 level 1
        gap = max(0.0, need_level - have)
        if not include_match and gap <= 0:
            continue
        items.append(GapItem(
            competency_id=cid,
            name=competency_name(cid),
            have_level=round(have, 2),
            need_level=int(need_level),
            gap=round(gap, 2),
            priority=_priority_from_score(gap, weight),
            weight=round(weight, 3),
            rationale="",
        ))

    if not use_llm_rank or not items:
        return sorted(items, key=lambda x: (-x.gap * x.weight, -x.weight))

    # 只把真正有 gap (gap > 0) 的条目给 LLM 排序
    gap_items = [g for g in items if g.gap > 0]
    if not gap_items:
        return sorted(items, key=lambda x: (-x.gap * x.weight, -x.weight))

    # LLM 精调优先级 + 给 rationale
    gaps_text = "\n".join(
        f"- {g.competency_id}({g.name}): have={g.have_level:.1f}, need={g.need_level}, "
        f"gap={g.gap:.1f}, weight={g.weight:.2f}"
        for g in gap_items
    )
    prompt = RANK_GAP.format(gaps=gaps_text)
    try:
        out = chat_json([
            {"role": "system", "content": "你是能力评估专家。"},
            {"role": "user", "content": prompt},
        ])
        ranked = {r["competency_id"]: r for r in out.get("ranked", [])}
        for g in gap_items:  # 只更新有 gap 的条目，gap=0 的保持 low
            r = ranked.get(g.competency_id)
            if r:
                prio = r.get("priority", g.priority)
                if prio in ("high", "mid", "low"):
                    g.priority = prio
                g.rationale = r.get("rationale", "")
    except Exception as e:
        logger.warning(f"LLM rank gap failed: {e}")

    # 最终排序：priority + gap*weight
    prio_order = {"high": 0, "mid": 1, "low": 2}
    return sorted(items, key=lambda x: (prio_order[x.priority], -x.gap * x.weight))


def match_score(emp: EmployeeProfile, job: JobProfile) -> float:
    """员工-岗位匹配度（0-1），与触发引擎共享。

    match = Σ weight_i × min(have_i, need_i) / need_i / Σ weight_i
    """
    have_map = {t.competency_id: t.level for t in emp.competencies}
    num, den = 0.0, 0.0
    for cid, need_level, weight in job.required_competencies:
        den += weight * need_level
        have = have_map.get(cid, 0.0)
        num += weight * min(have, need_level)
    return round(num / den, 3) if den else 0.0
