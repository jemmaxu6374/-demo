"""岗位画像构建器：JD JSON → JobProfile。

策略：
- JD 已结构化 required_competencies（由人工/招聘侧录入），直接读取
- LLM 负责扩充"应当具备但未显式列出"的能力（可选）
- 权重归一化到总和 1.0
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.llm.client import chat_json  # noqa: E402
from src.llm.prompts import EXTRACT_JOB  # noqa: E402
from src.profile.ontology_loader import ontology_summary_text, resolve_competency  # noqa: E402
from src.schemas import JobProfile  # noqa: E402


def _load_jds() -> list[dict]:
    return json.loads(settings.abs_path(settings.jds_path).read_text(encoding="utf-8"))


def list_jds() -> list[dict]:
    return _load_jds()


def get_jd_raw(jd_id: str) -> dict | None:
    for j in _load_jds():
        if j["jd_id"] == jd_id:
            return j
    return None


def build_profile(jd_id: str, llm_expand: bool = False) -> JobProfile:
    raw = get_jd_raw(jd_id)
    if raw is None:
        raise ValueError(f"JD not found: {jd_id}")

    # 基线：JD 内结构化字段
    base: dict[str, tuple[int, float]] = {}
    for rc in raw.get("required_competencies", []):
        cid = rc["competency_id"]
        base[cid] = (int(rc["need_level"]), float(rc["weight"]))

    # 可选：LLM 扩充
    if llm_expand:
        prompt = EXTRACT_JOB.format(
            ontology=ontology_summary_text(max_len=2500),
            title=raw["title"],
            description=raw["description"],
            existing_competencies=", ".join(base.keys()),
        )
        try:
            out = chat_json([
                {"role": "system", "content": "你是岗位能力分析师，输出严格 JSON。"},
                {"role": "user", "content": prompt},
            ])
            for item in out.get("additional_competencies", []):
                cid = resolve_competency(item.get("competency_id") or "")
                if not cid or cid in base:
                    continue
                base[cid] = (
                    int(item.get("need_level", 3)),
                    float(item.get("weight", 0.05)),
                )
        except Exception as e:
            logger.warning(f"LLM expand JD failed: {e}")

    # 归一化权重
    total_w = sum(w for _, w in base.values()) or 1.0
    required = [(cid, lvl, w / total_w) for cid, (lvl, w) in base.items()]

    return JobProfile(
        jd_id=jd_id,
        title=raw["title"],
        level=raw.get("level", ""),
        department=raw.get("department", ""),
        required_competencies=required,
        description=raw["description"],
    )
