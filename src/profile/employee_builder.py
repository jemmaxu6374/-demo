"""员工画像构建器：简历/项目/自评 → EmployeeProfile。

策略：
- LLM 抽取（Mock 模式也能跑）
- 结果通过 resolve_competency 归一化到本体
- 去重合并：同一 competency 取 max level
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.llm.client import chat_json  # noqa: E402
from src.llm.prompts import EXTRACT_EMPLOYEE  # noqa: E402
from src.profile.ontology_loader import (  # noqa: E402
    competency_name,
    ontology_summary_text,
    resolve_competency,
)
from src.schemas import CompetencyTag, EmployeeProfile  # noqa: E402


def _load_employees() -> list[dict]:
    return json.loads(settings.abs_path(settings.employees_path).read_text(encoding="utf-8"))


def list_employees() -> list[dict]:
    return _load_employees()


def get_employee_raw(employee_id: str) -> dict | None:
    for e in _load_employees():
        if e["employee_id"] == employee_id:
            return e
    return None


def build_profile(employee_id: str) -> EmployeeProfile:
    raw = get_employee_raw(employee_id)
    if raw is None:
        raise ValueError(f"employee not found: {employee_id}")

    resume_text = raw["resume"]
    projects_text = "\n".join(
        f"- {p['name']}（{p['role']}）：{p['description']}" for p in raw.get("projects", [])
    )
    self_text = (
        f"强项：{', '.join(raw['self_assessment']['strengths'])}\n"
        f"待提升：{', '.join(raw['self_assessment']['weaknesses'])}"
    )

    prompt = EXTRACT_EMPLOYEE.format(
        ontology=ontology_summary_text(max_len=2500),
        name=raw["name"],
        current_role=raw["current_role"],
        resume=f"{resume_text}\n\n项目经历：\n{projects_text}",
        self_assessment=self_text,
    )

    try:
        out = chat_json([
            {"role": "system", "content": "你是能力建模专家，严格输出 JSON。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        logger.warning(f"LLM extract failed, fallback to empty profile: {e}")
        out = {"competencies": [], "summary": ""}

    tags: dict[str, CompetencyTag] = {}

    # 1) 先写入 base_competencies（人工预置基线，mock 模式唯一数据来源）
    for item in raw.get("base_competencies", []):
        cid = item["competency_id"]
        tags[cid] = CompetencyTag(
            competency_id=cid,
            name=competency_name(cid),
            level=float(item["level"]),
            confidence=float(item.get("confidence", 0.8)),
            evidence=item.get("evidence") or [],
        )

    # 2) LLM 输出合并：同 competency 取较高 level & 较高 confidence
    for item in out.get("competencies", []):
        cid = resolve_competency(item.get("competency_id") or item.get("name") or "")
        if not cid:
            continue
        level = float(item.get("level", 3))
        level = max(1.0, min(5.0, level))
        conf = float(item.get("confidence", 0.7))
        evidence = item.get("evidence") or []
        if cid in tags:
            # 合并：取较高 level
            prev = tags[cid]
            if level > prev.level:
                tags[cid] = CompetencyTag(
                    competency_id=cid,
                    name=competency_name(cid),
                    level=level,
                    confidence=max(prev.confidence, conf),
                    evidence=list({*prev.evidence, *evidence}),
                )
        else:
            tags[cid] = CompetencyTag(
                competency_id=cid,
                name=competency_name(cid),
                level=level,
                confidence=conf,
                evidence=evidence,
            )

    summary = out.get("summary") or f"{raw['name']}，{raw['current_role']}"
    return EmployeeProfile(
        employee_id=employee_id,
        name=raw["name"],
        current_role=raw["current_role"],
        department=raw["department"],
        competencies=list(tags.values()),
        summary=summary,
        raw_resume=resume_text,
    )
