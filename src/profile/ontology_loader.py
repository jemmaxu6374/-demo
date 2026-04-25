"""能力本体加载 + 查询工具。

职责：
- 单例加载本体 JSON → Pydantic
- 提供 name→id 的模糊匹配（alias 表）
- 分类聚合：按 decay_type / parent_category 取子集
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.schemas import Competency, CompetencyCategory, CompetencyOntology  # noqa: E402


@lru_cache(maxsize=1)
def load_ontology() -> CompetencyOntology:
    path = settings.abs_path(settings.ontology_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CompetencyOntology(**raw)


@lru_cache(maxsize=1)
def _competency_index() -> dict[str, Competency]:
    return {c.id: c for c in load_ontology().competencies}


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """alias(lower) / name(lower) → competency_id，供 LLM 输出兜底纠偏。"""
    idx: dict[str, str] = {}
    for c in load_ontology().competencies:
        idx[c.name.lower()] = c.id
        idx[c.id.lower()] = c.id
        for a in c.aliases:
            idx[a.lower()] = c.id
    return idx


def get_competency(cid: str) -> Competency | None:
    return _competency_index().get(cid)


def competency_name(cid: str) -> str:
    c = get_competency(cid)
    return c.name if c else cid


def resolve_competency(text: str) -> str | None:
    """将 LLM 输出的能力名称/别名/id 解析回标准 competency_id。

    不区分大小写；解析不到返回 None。
    """
    if not text:
        return None
    t = text.strip().lower()
    idx = _alias_index()
    if t in idx:
        return idx[t]
    # 尾部精确匹配（例如 "Python 编程" → "Python"）
    for k, v in idx.items():
        if k and (t.endswith(k) or k.endswith(t)) and min(len(k), len(t)) >= 3:
            return v
    return None


def all_competencies() -> list[Competency]:
    return list(load_ontology().competencies)


def categories() -> list[CompetencyCategory]:
    return list(load_ontology().categories)


def category_name(cat_id: str) -> str:
    for c in load_ontology().categories:
        if c.id == cat_id:
            return c.name
    return cat_id


def ontology_summary_text(max_len: int = 2000) -> str:
    """返回精简的能力清单文本，用于注入 Prompt。"""
    lines: list[str] = []
    for cat in load_ontology().categories:
        lines.append(f"# {cat.name}（{cat.id}）")
        for c in load_ontology().competencies:
            if c.parent_id == cat.id:
                aliases = f"（别名：{', '.join(c.aliases[:4])}）" if c.aliases else ""
                lines.append(f"- {c.id} | {c.name}{aliases}")
    s = "\n".join(lines)
    return s if len(s) <= max_len else s[:max_len] + "\n..."
