"""Event Processor：把单条 BehaviorEvent → CompetencyDelta 列表。

双轨归因：
- 优先使用事件自带的 competency_hints（模板生成时预置，视作 ground truth）
- 当 hints 不存在时才走 LLM Function Calling（mock 也可）
- LLM 输出经过 resolve_competency 归一化，不在本体内的 id 一律丢弃
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.llm.client import chat_json  # noqa: E402
from src.llm.prompts import ATTRIBUTE_EVENT  # noqa: E402
from src.profile.ontology_loader import ontology_summary_text, resolve_competency  # noqa: E402
from src.schemas import BehaviorEvent, CompetencyDelta  # noqa: E402


def _from_hints(event: dict) -> list[CompetencyDelta]:
    """从事件自带的 hints 抽 delta（模板生成时预置的 ground truth 路径）。"""
    out: list[CompetencyDelta] = []
    for h in event.get("competency_hints", []) or []:
        cid = h.get("competency_id")
        if not cid:
            continue
        out.append(CompetencyDelta(
            event_id=event["event_id"],
            competency_id=cid,
            delta_level=float(h.get("delta_hint", 0.1)),
            confidence=float(h.get("confidence_hint", 0.7)),
            rationale=f"hint: {event.get('title', '')[:40]}",
        ))
    return out


def _from_llm(event: dict) -> list[CompetencyDelta]:
    """调用 LLM 归因（mock 模式返回伪造 delta）。"""
    prompt = ATTRIBUTE_EVENT.format(
        ontology=ontology_summary_text(max_len=1500),
        source=event["source"],
        title=event["title"],
        content=event["content"],
    )
    try:
        out = chat_json([
            {"role": "system", "content": "##TASK## attribute_event 归因助手。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        logger.warning(f"LLM attribute failed for {event['event_id']}: {e}")
        return []

    deltas: list[CompetencyDelta] = []
    for item in out.get("deltas", []):
        cid = resolve_competency(item.get("competency_id") or "")
        if not cid:
            continue
        deltas.append(CompetencyDelta(
            event_id=event["event_id"],
            competency_id=cid,
            delta_level=float(item.get("delta_level", 0.0)),
            confidence=float(item.get("confidence", 0.6)),
            rationale=item.get("rationale", ""),
        ))
    return deltas


def attribute_event(event: dict, *, prefer_hints: bool = True) -> list[CompetencyDelta]:
    """单事件归因，自动选择 hints 或 LLM 路径。"""
    if prefer_hints and event.get("competency_hints"):
        return _from_hints(event)
    return _from_llm(event)


def attribute_batch(events: Iterable[dict], *, prefer_hints: bool = True) -> dict[str, list[CompetencyDelta]]:
    """批量归因，返回 {event_id: [CompetencyDelta...]}。"""
    out: dict[str, list[CompetencyDelta]] = {}
    for ev in events:
        out[ev["event_id"]] = attribute_event(ev, prefer_hints=prefer_hints)
    return out


def attach_employee(deltas: Iterable[CompetencyDelta], employee_id: str) -> list[dict]:
    """把 employee_id 注入后返回 dict（方便直接送入 DB）。"""
    rows = []
    for d in deltas:
        r = d.model_dump()
        r["employee_id"] = employee_id
        rows.append(r)
    return rows
