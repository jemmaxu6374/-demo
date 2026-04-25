"""30/60/90 天成长路径生成器。

策略：
- LLM 基于 Gap + 精排推荐池合成里程碑
- mock 模式下 LLM 返回伪结构，兜底规则保证路径可用：每阶段按 gap 优先级挑 3 个资源，覆盖至少 1 个 experiential + 1 个 social + 1 个 formal
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.llm.client import chat_json  # noqa: E402
from src.llm.prompts import GENERATE_PATHWAY  # noqa: E402
from src.schemas import (  # noqa: E402
    EmployeeProfile,
    GapItem,
    JobProfile,
    Pathway,
    PathwayMilestone,
    Recommendation,
)


def _fallback_pathway(
    emp: EmployeeProfile,
    job: JobProfile,
    gaps: list[GapItem],
    pool: list[Recommendation],
) -> list[PathwayMilestone]:
    """规则兜底路径。

    每阶段挑 3 个资源，覆盖 experiential+social+formal 三种 mode（若有）。
    """
    by_mode: dict[str, list[Recommendation]] = {"experiential": [], "social": [], "formal": [], "tool": []}
    for r in pool:
        by_mode.setdefault(r.learning_mode, []).append(r)
    for k in by_mode:
        by_mode[k].sort(key=lambda x: -x.score)

    # 高优 gap 前三
    top_gaps = [g for g in gaps if g.priority == "high"][:3] or gaps[:3]
    used: set[str] = set()

    def pick(modes: list[str]) -> list[str]:
        out = []
        for m in modes:
            for r in by_mode.get(m, []):
                if r.resource_id in used:
                    continue
                out.append(r.resource_id)
                used.add(r.resource_id)
                break
        return out

    milestones: list[PathwayMilestone] = []
    phases = [
        ("30d", "打基础", "补齐最紧迫的 1 项高优能力 gap，上手关键工具与 Prompt 套路", ["formal", "tool", "social"]),
        ("60d", "在实践中学", "加入一个内部项目或 Lab，把学到的方法论落到产出上", ["experiential", "social", "formal"]),
        ("90d", "独当一面", "复盘前两阶段，挑战一个有风险的小项目或 Hackathon 形成产出", ["experiential", "social", "tool"]),
    ]
    for i, (phase, title, desc, modes) in enumerate(phases):
        picked = pick(modes)
        target_comp = [g.competency_id for g in top_gaps[i : i + 2]] or [g.competency_id for g in top_gaps[:1]]
        milestones.append(PathwayMilestone(
            phase=phase,  # type: ignore[arg-type]
            title=title,
            description=desc,
            target_competencies=target_comp,
            resources=picked or [r.resource_id for r in pool[:3]],
        ))
    return milestones


def generate(
    emp: EmployeeProfile,
    job: JobProfile,
    gaps: list[GapItem],
    recs_by_source: dict[str, list[Recommendation]] | None = None,
    *,
    use_llm: bool = True,
) -> Pathway:
    # 汇总资源池（从七路推荐）
    pool: list[Recommendation] = []
    if recs_by_source:
        for items in recs_by_source.values():
            pool.extend(items)
    pool.sort(key=lambda x: -x.score)

    milestones: list[PathwayMilestone] | None = None
    if use_llm and pool:
        gaps_text = "\n".join(
            f"- {g.competency_id}({g.name}): gap={g.gap}, priority={g.priority}" for g in gaps[:8]
        )
        pool_text = "\n".join(
            f"- {r.resource_id} | {r.title} | mode={r.learning_mode} | score={r.score}"
            for r in pool[:25]
        )
        prompt = GENERATE_PATHWAY.format(
            employee_summary=f"{emp.name}（{emp.current_role}）",
            job_summary=f"{job.title}（{job.level}）",
            gaps=gaps_text,
            resources=pool_text,
        )
        try:
            out = chat_json([
                {"role": "system", "content": "你是成长路径规划师。"},
                {"role": "user", "content": prompt},
            ])
            ms = []
            valid_ids = {r.resource_id for r in pool}
            for item in out.get("milestones", []):
                phase = item.get("phase")
                if phase not in ("30d", "60d", "90d"):
                    continue
                resources = [r for r in item.get("resources", []) if r in valid_ids][:4]
                if not resources:
                    continue
                ms.append(PathwayMilestone(
                    phase=phase,
                    title=item.get("title", f"{phase} 里程碑"),
                    description=item.get("description", ""),
                    target_competencies=item.get("target_competencies", []),
                    resources=resources,
                ))
            if len(ms) == 3:
                milestones = ms
        except Exception as e:
            logger.warning(f"LLM pathway failed, fallback: {e}")

    if milestones is None:
        milestones = _fallback_pathway(emp, job, gaps, pool)

    return Pathway(employee_id=emp.employee_id, jd_id=job.jd_id, milestones=milestones)
