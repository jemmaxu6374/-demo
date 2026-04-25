"""Task Profiler：从任务描述抽取 required_competencies。

双轨：
- 关键词/别名匹配（兜底，mock 可用，无延迟）
- LLM 抽取（可选增量，mock 会返回空）

合并策略：先跑关键词匹配，再用 LLM 补充；权重归一化。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.llm.client import chat_json  # noqa: E402
from src.llm.prompts import EXTRACT_TASK  # noqa: E402
from src.profile.ontology_loader import (  # noqa: E402
    all_competencies,
    ontology_summary_text,
    resolve_competency,
)
from src.schemas import TaskProfile  # noqa: E402
from src.storage.repository import upsert_task_profile  # noqa: E402


def _load_tasks() -> list[dict]:
    return json.loads(settings.abs_path(settings.tasks_path).read_text(encoding="utf-8"))


def list_tasks() -> list[dict]:
    return _load_tasks()


def get_task_raw(task_id: str) -> dict | None:
    for t in _load_tasks():
        if t["task_id"] == task_id:
            return t
    return None


def _keyword_match(text: str) -> dict[str, float]:
    """基于能力名称 + 别名在文本中出现频率的关键词匹配，返回 cid → 原始分。"""
    scores: dict[str, float] = {}
    text_low = text.lower()
    for c in all_competencies():
        # 名字 + 别名 + id 末段
        needles = [c.name, *c.aliases, c.id.split(".")[-1]]
        s = 0.0
        for n in needles:
            n = n.strip().lower()
            if len(n) < 2:
                continue
            count = len(re.findall(re.escape(n), text_low))
            if count > 0:
                s += count * (1.0 if n == c.name.lower() else 0.5)
        if s > 0:
            scores[c.id] = s
    return scores


def _infer_need_level(comp_id: str, weight: float) -> int:
    """启发式 need_level：weight 越高需求越高（3-5）。"""
    if weight >= 0.2:
        return 4
    if weight >= 0.10:
        return 3
    return 3


def build_task_profile(task_id: str, *, use_llm: bool = True, persist: bool = True) -> TaskProfile:
    raw = get_task_raw(task_id)
    if raw is None:
        raise ValueError(f"task not found: {task_id}")

    text = f"{raw['title']}\n{raw['description']}"

    # Step 1: 关键词兜底
    scores = _keyword_match(text)

    # Step 2: LLM 增量
    if use_llm:
        prompt = EXTRACT_TASK.format(
            ontology=ontology_summary_text(max_len=1500),
            title=raw["title"],
            description=raw["description"],
        )
        try:
            out = chat_json([
                {"role": "system", "content": "你是任务能力分析师。"},
                {"role": "user", "content": prompt},
            ])
            for item in out.get("required_competencies", []):
                cid = resolve_competency(item.get("competency_id") or "")
                if not cid:
                    continue
                # LLM 分数加 1.0 权重
                scores[cid] = scores.get(cid, 0.0) + 1.0 * float(item.get("weight", 0.5))
        except Exception as e:
            logger.warning(f"LLM extract_task failed: {e}")

    if not scores:
        return TaskProfile(
            task_id=task_id,
            employee_id=raw.get("employee_id", ""),
            title=raw["title"],
            required_competencies=[],
            summary="[无法识别能力需求]",
        )

    total = sum(scores.values())
    required = sorted(
        [(cid, _infer_need_level(cid, s / total), round(s / total, 3)) for cid, s in scores.items()],
        key=lambda x: -x[2],
    )

    profile = TaskProfile(
        task_id=task_id,
        employee_id=raw.get("employee_id", ""),
        title=raw["title"],
        required_competencies=required,
        summary=f"{raw['title']}：识别 {len(required)} 项关键能力",
    )

    if persist:
        upsert_task_profile(
            task_id=task_id,
            employee_id=profile.employee_id,
            title=profile.title,
            summary=profile.summary,
            required=required,
        )

    return profile
