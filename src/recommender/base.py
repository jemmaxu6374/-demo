"""七路推荐器抽象基类 + 资源加载。

关键设计：
- 基类统一 retrieve → rerank → explain 三段式
- retrieve 用「related_competencies 重叠数 × competency 权重 × gap 严重度」打分
- rerank 可选：调用 LLM（mock 下返回伪分数）
- 所有 Recommendation 带 learning_mode 标签
- 资源池统一加载一次，放内存
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.llm.client import chat_json  # noqa: E402
from src.llm.prompts import LEARNING_MODE_CONSTRAINT, RERANK_RESOURCE  # noqa: E402
from src.schemas import EmployeeProfile, GapItem, LearningMode, Recommendation  # noqa: E402


RESOURCES_DIR = settings.abs_path(settings.resources_dir)


# ---------------------------------------------------------------- 资源加载

def _parse_comp_list(val) -> list[str]:
    if isinstance(val, list):
        return val
    if not val:
        return []
    return [x.strip() for x in str(val).split(";") if x.strip()]


@lru_cache(maxsize=None)
def load_courses() -> list[dict]:
    with open(RESOURCES_DIR / "courses.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append({
            "resource_id": r["resource_id"],
            "title": r["title"],
            "source_type": "course",
            "learning_mode": r["learning_mode"],
            "url": r["url"],
            "duration_min": int(r["duration_min"]),
            "is_micro": r["is_micro"].lower() == "true",
            "related_competencies": _parse_comp_list(r["related_competencies"]),
            "summary": r["summary"],
            "provider": r["provider"],
            "level": r["level"],
        })
    return out


@lru_cache(maxsize=None)
def load_readings() -> list[dict]:
    with open(RESOURCES_DIR / "readings.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append({
            "resource_id": r["resource_id"],
            "title": r["title"],
            "source_type": "reading",
            "learning_mode": r["learning_mode"],
            "url": r["url"],
            "type": r["type"],
            "level": r["level"],
            "related_competencies": _parse_comp_list(r["related_competencies"]),
            "summary": r["summary"],
            "author": r["author"],
        })
    return out


@lru_cache(maxsize=None)
def load_tools() -> list[dict]:
    with open(RESOURCES_DIR / "tools.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append({
            "resource_id": r["resource_id"],
            "title": r["name"],
            "source_type": "tool",
            "learning_mode": r["learning_mode"],
            "url": r["url"],
            "category": r["category"],
            "related_competencies": _parse_comp_list(r["related_competencies"]),
            "summary": r["summary"],
            "vendor": r["vendor"],
        })
    return out


@lru_cache(maxsize=None)
def load_prompts() -> list[dict]:
    data = json.loads((RESOURCES_DIR / "prompt_library.json").read_text(encoding="utf-8"))
    for r in data:
        r["source_type"] = "prompt"
        r["title"] = r["title"]
    return data


@lru_cache(maxsize=None)
def load_projects() -> list[dict]:
    data = json.loads((RESOURCES_DIR / "internal_projects.json").read_text(encoding="utf-8"))
    for r in data:
        r["source_type"] = "project"
    return data


@lru_cache(maxsize=None)
def load_labs() -> list[dict]:
    data = json.loads((RESOURCES_DIR / "labs.json").read_text(encoding="utf-8"))
    for r in data:
        r["source_type"] = "lab"
    return data


@lru_cache(maxsize=None)
def load_mentors() -> list[dict]:
    data = json.loads((RESOURCES_DIR / "mentors.json").read_text(encoding="utf-8"))
    for r in data:
        r["source_type"] = "mentor"
        r["title"] = r["name"]
        r["related_competencies"] = r.get("expert_competencies", [])
    return data


@lru_cache(maxsize=None)
def load_cases() -> list[dict]:
    data = json.loads((RESOURCES_DIR / "case_studies.json").read_text(encoding="utf-8"))
    for r in data:
        r["source_type"] = "case"
    return data


@lru_cache(maxsize=None)
def load_talks() -> list[dict]:
    with open(RESOURCES_DIR / "tech_talks.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append({
            "resource_id": r["resource_id"],
            "title": r["title"],
            "source_type": "talk",
            "learning_mode": r["learning_mode"],
            "url": r["url"],
            "duration_min": int(r["duration_min"]),
            "date": r["date"],
            "language": r["language"],
            "related_competencies": _parse_comp_list(r["related_competencies"]),
            "summary": r["summary"],
            "speaker": r["speaker"],
        })
    return out


@lru_cache(maxsize=None)
def load_communities() -> list[dict]:
    data = json.loads((RESOURCES_DIR / "communities.json").read_text(encoding="utf-8"))
    for r in data:
        r["source_type"] = "community"
        r["title"] = r["name"]
    return data


# ---------------------------------------------------------------- 基类

@dataclass
class RecommenderConfig:
    top_k_recall: int = 10
    top_k_rerank: int = 5
    use_llm_rerank: bool = True


class BaseRecommender:
    source_type: str = "base"
    learning_mode: LearningMode = "formal"
    resources_loader = staticmethod(lambda: [])

    def __init__(self, cfg: RecommenderConfig | None = None):
        self.cfg = cfg or RecommenderConfig(
            top_k_recall=settings.top_k_recall,
            top_k_rerank=settings.top_k_rerank,
        )

    # -- 子类可重写：对资源额外打分（如微课加分、新人友好加分） --
    def extra_score(self, resource: dict, gaps: list[GapItem], emp: EmployeeProfile) -> float:
        return 0.0

    # -- 召回：按 related_competencies 与 gap 匹配度打分 --
    def retrieve(self, emp: EmployeeProfile, gaps: list[GapItem]) -> list[tuple[dict, float, list[str]]]:
        gap_weight: dict[str, float] = {}
        for g in gaps:
            # 高=3 中=2 低=1
            prio_w = {"high": 3.0, "mid": 2.0, "low": 1.0}[g.priority]
            gap_weight[g.competency_id] = g.weight * prio_w * (1.0 + g.gap)

        if not gap_weight:
            return []

        scored: list[tuple[dict, float, list[str]]] = []
        for r in self.resources_loader():
            rel = r.get("related_competencies") or []
            hit = [c for c in rel if c in gap_weight]
            if not hit:
                continue
            score = sum(gap_weight[c] for c in hit)
            score += self.extra_score(r, gaps, emp)
            scored.append((r, round(score, 3), hit))

        scored.sort(key=lambda x: -x[1])
        return scored[: self.cfg.top_k_recall]

    # -- 精排：LLM 打分 + 解释（可选） --
    def rerank(
        self,
        emp: EmployeeProfile,
        gaps: list[GapItem],
        candidates: list[tuple[dict, float, list[str]]],
    ) -> list[Recommendation]:
        if not candidates:
            return []

        if not self.cfg.use_llm_rerank:
            return [self._to_recommendation(r, score=s, rationale="", hit=h) for r, s, h in candidates[: self.cfg.top_k_rerank]]

        cand_text = "\n".join(
            f"- {r['resource_id']} | {r.get('title', '')} | hit={','.join(h)} | score={s}"
            for r, s, h in candidates
        )
        gaps_text = "\n".join(
            f"- {g.competency_id}({g.name}): gap={g.gap:.1f}, priority={g.priority}" for g in gaps[:10]
        )
        prompt = RERANK_RESOURCE.format(
            top_k=self.cfg.top_k_rerank,
            learning_mode_label=self.learning_mode,
            learning_mode_constraint=LEARNING_MODE_CONSTRAINT.get(self.learning_mode, ""),
            employee_summary=f"{emp.name}（{emp.current_role}）：{emp.summary}",
            gaps=gaps_text,
            candidates=cand_text,
        )
        try:
            out = chat_json([
                {"role": "system", "content": "你是学习路径规划专家，严格输出 JSON。"},
                {"role": "user", "content": prompt},
            ])
            reranked = out.get("reranked", [])
        except Exception as e:
            logger.warning(f"[{self.source_type}] LLM rerank failed: {e}")
            reranked = []

        cand_map = {r["resource_id"]: (r, s, h) for r, s, h in candidates}
        rerank_map = {x["resource_id"]: x for x in reranked if "resource_id" in x}

        # 最终分数：召回分 × 0.4 + LLM 分 × 0.6
        final: list[Recommendation] = []
        seen: set[str] = set()
        # 先按 LLM 返回顺序
        for x in reranked:
            rid = x.get("resource_id")
            if rid in cand_map and rid not in seen:
                r, recall_s, hit = cand_map[rid]
                llm_s = float(x.get("score", 0.7))
                final_s = round(0.4 * (recall_s / (candidates[0][1] or 1.0)) + 0.6 * llm_s, 3)
                final.append(self._to_recommendation(r, score=final_s, rationale=x.get("rationale", ""), hit=hit))
                seen.add(rid)
            if len(final) >= self.cfg.top_k_rerank:
                break

        # 补齐不足的
        for r, s, hit in candidates:
            if len(final) >= self.cfg.top_k_rerank:
                break
            if r["resource_id"] in seen:
                continue
            final.append(self._to_recommendation(r, score=round(s / (candidates[0][1] or 1.0), 3), rationale="", hit=hit))
            seen.add(r["resource_id"])

        return final

    def _to_recommendation(self, r: dict, *, score: float, rationale: str, hit: list[str]) -> Recommendation:
        return Recommendation(
            resource_id=r["resource_id"],
            title=r.get("title") or r.get("name", ""),
            source_type=self.source_type,  # type: ignore[arg-type]
            learning_mode=self.learning_mode,
            target_competency_ids=hit,
            score=score,
            rationale=rationale,
            url=r.get("url", ""),
            extra={k: v for k, v in r.items() if k not in (
                "resource_id", "title", "name", "url", "summary", "related_competencies",
                "expert_competencies", "learning_mode", "source_type", "content",
            )},
        )

    # -- 串联入口 --
    def recommend(self, emp: EmployeeProfile, gaps: list[GapItem]) -> list[Recommendation]:
        cands = self.retrieve(emp, gaps)
        return self.rerank(emp, gaps, cands)


# ---------------------------------------------------------------- 七路具体实现

class CourseRecommender(BaseRecommender):
    source_type = "course"
    learning_mode: LearningMode = "formal"
    resources_loader = staticmethod(load_courses)

    def extra_score(self, resource, gaps, emp):
        # 新人（level 多 ≤ 2）偏向微课
        avg_have = sum(g.have_level for g in gaps) / max(len(gaps), 1)
        if avg_have <= 2 and resource.get("is_micro"):
            return 0.3
        return 0.0


class ReadingRecommender(BaseRecommender):
    source_type = "reading"
    learning_mode: LearningMode = "formal"
    resources_loader = staticmethod(load_readings)


class ToolRecommender(BaseRecommender):
    source_type = "tool"
    learning_mode: LearningMode = "tool"
    resources_loader = staticmethod(load_tools)


class PromptRecommender(BaseRecommender):
    source_type = "prompt"
    learning_mode: LearningMode = "tool"
    resources_loader = staticmethod(load_prompts)


class ProjectRecommender(BaseRecommender):
    """内部项目 + Hackathon + Lab 统一，learning_mode=experiential。

    注：此处只覆盖 internal_projects.json（含 hackathon）。Lab 单独一路。
    """
    source_type = "project"
    learning_mode: LearningMode = "experiential"
    resources_loader = staticmethod(load_projects)


class LabRecommender(BaseRecommender):
    source_type = "lab"
    learning_mode: LearningMode = "experiential"
    resources_loader = staticmethod(load_labs)


class MentorRecommender(BaseRecommender):
    source_type = "mentor"
    learning_mode: LearningMode = "social"
    resources_loader = staticmethod(load_mentors)

    def extra_score(self, resource, gaps, emp):
        # 同部门导师加分
        if resource.get("department") and resource["department"] == emp.department:
            return 0.5
        return 0.0


class CaseRecommender(BaseRecommender):
    source_type = "case"
    learning_mode: LearningMode = "social"
    resources_loader = staticmethod(load_cases)


def _load_talk_community():
    return load_talks() + load_communities()


class TalkCommunityRecommender(BaseRecommender):
    """Tech Talk + 社群合并为一路，learning_mode=social。"""
    source_type = "talk"
    learning_mode: LearningMode = "social"
    resources_loader = staticmethod(_load_talk_community)


# ---------------------------------------------------------------- Orchestrator

ALL_RECOMMENDERS = [
    ProjectRecommender,  # 实践 70%
    LabRecommender,
    MentorRecommender,   # 向他人学 20%
    CaseRecommender,
    TalkCommunityRecommender,
    CourseRecommender,   # 系统学 10%
    ReadingRecommender,
    ToolRecommender,     # 工具用（正交）
    PromptRecommender,
]


def recommend_all(
    emp: EmployeeProfile,
    gaps: list[GapItem],
    *,
    use_llm_rerank: bool = True,
    top_k_rerank: int | None = None,
) -> dict[str, list[Recommendation]]:
    """对所有 recommender 并行（当前顺序执行，后续可改 asyncio.gather）。

    返回 {source_type: [Recommendation...]}，调用方可按 learning_mode 再分组。
    """
    cfg = RecommenderConfig(
        top_k_recall=settings.top_k_recall,
        top_k_rerank=top_k_rerank or settings.top_k_rerank,
        use_llm_rerank=use_llm_rerank,
    )
    result: dict[str, list[Recommendation]] = {}
    for cls in ALL_RECOMMENDERS:
        rec = cls(cfg)
        try:
            result[cls.source_type] = rec.recommend(emp, gaps)
        except Exception as e:
            logger.exception(f"recommender {cls.__name__} failed: {e}")
            result[cls.source_type] = []
    return result


def group_by_learning_mode(
    recs: dict[str, list[Recommendation]],
) -> dict[LearningMode, list[Recommendation]]:
    """按 70-20-10 四组聚合，同 mode 按 score 排序。"""
    buckets: dict[str, list[Recommendation]] = {"experiential": [], "social": [], "formal": [], "tool": []}
    for items in recs.values():
        for r in items:
            buckets.setdefault(r.learning_mode, []).append(r)
    for k in buckets:
        buckets[k].sort(key=lambda x: -x.score)
    return buckets  # type: ignore[return-value]
