"""赋能触发引擎：六种规则 + ML 阈值双通道。

触发类型：
1. task_new                —— 任务新建
2. review_rejected         —— 评审打回（feedback/task 类事件中带"打回"）
3. search                  —— 学习搜索关键词（learning 类事件 "搜索"）
4. match_low               —— 员工在岗画像与岗位匹配度低于阈值
5. task_embedded_learning  —— 任务 required 能力 ∩ 员工 gap（含 bundle 资源）
6. expert_available        —— 某能力上近 30 天出现高产出者（为其他同事推送）

输出：list[TriggerSignal]
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402
from src.analysis.gap_analyzer import analyze_gap, match_score  # noqa: E402
from src.profile.employee_builder import build_profile as build_emp  # noqa: E402
from src.profile.job_builder import build_profile as build_job  # noqa: E402
from src.profile.ontology_loader import competency_name  # noqa: E402
from src.profile.task_profiler import build_task_profile, list_tasks  # noqa: E402
from src.recommender.expert_finder import find_experts  # noqa: E402
from src.schemas import EmployeeProfile, TaskProfile, TriggerSignal  # noqa: E402
from src.storage.repository import list_events  # noqa: E402


# ---------------------------------------------------------------- helper

def _employee_level_map(emp: EmployeeProfile) -> dict[str, float]:
    return {t.competency_id: t.level for t in emp.competencies}


def _bundle_resources_for(gap_competency_ids: list[str]) -> list[str]:
    """任务内嵌学习场景：为 gap 能力打包「案例+Prompt+微课」三件套 ID。

    简化实现：读资源池，挑命中概率最高的 3 个。
    """
    from src.recommender.base import load_cases, load_prompts, load_courses

    case_match = next((c["resource_id"] for c in load_cases()
                       if set(c.get("related_competencies", [])) & set(gap_competency_ids)), None)
    prompt_match = next((p["resource_id"] for p in load_prompts()
                         if set(p.get("related_competencies", [])) & set(gap_competency_ids)), None)
    micro_match = next((c["resource_id"] for c in load_courses()
                        if c.get("is_micro") and set(c.get("related_competencies", [])) & set(gap_competency_ids)), None)
    return [x for x in [case_match, prompt_match, micro_match] if x]


# ---------------------------------------------------------------- rules

def rule_task_new(employee_id: str, as_of: datetime) -> list[TriggerSignal]:
    """每个 status=new 的任务触发一条 task_new 信号。"""
    signals = []
    for t in list_tasks():
        if t.get("employee_id") != employee_id:
            continue
        if t.get("status") != "new":
            continue
        signals.append(TriggerSignal(
            employee_id=employee_id,
            trigger_type="task_new",
            related_task_id=t["task_id"],
            urgency="mid",
            suggested_action=f"新任务「{t['title']}」已分配，点击查看推荐资源",
            ts=as_of,
        ))
    return signals


def rule_review_rejected(employee_id: str, as_of: datetime, window_days: int = 14) -> list[TriggerSignal]:
    """近 N 天内遇到评审打回事件 → review_rejected。"""
    start = as_of - timedelta(days=window_days)
    rows = list_events(employee_id, start=start, end=as_of, sources=["task", "feedback"])
    out = []
    for r in rows:
        if "打回" in r.title or "待提升" in r.title or "打回" in r.content or "需加强" in r.content:
            out.append(TriggerSignal(
                employee_id=employee_id,
                trigger_type="review_rejected",
                related_task_id=None,
                urgency="high",
                suggested_action=f"最近有一次「{r.title[:20]}」的打回/反馈，建议花 30 分钟复盘",
                ts=as_of,
            ))
            break  # 同员工只触发一次
    return out


def rule_search(employee_id: str, as_of: datetime, window_days: int = 7) -> list[TriggerSignal]:
    """近 N 天有 learning/搜索事件 → search。"""
    start = as_of - timedelta(days=window_days)
    rows = list_events(employee_id, start=start, end=as_of, sources=["learning"])
    for r in rows:
        if "搜索" in r.title:
            return [TriggerSignal(
                employee_id=employee_id,
                trigger_type="search",
                related_task_id=None,
                urgency="low",
                suggested_action=f"检测到学习搜索行为，系统为你整理了相关推荐",
                learning_mode="formal",
                ts=as_of,
            )]
    return []


def rule_match_low(
    employee_id: str,
    jd_id: str,
    as_of: datetime,
) -> list[TriggerSignal]:
    """员工画像 vs 岗位匹配度低于阈值 → match_low。"""
    emp = build_emp(employee_id)
    job = build_job(jd_id)
    ms = match_score(emp, job)
    if ms >= settings.match_score_trigger:
        return []
    gaps = analyze_gap(emp, job)
    target_gaps = [g.competency_id for g in gaps if g.priority == "high" and g.gap > 0][:3]
    if not target_gaps:
        return []
    return [TriggerSignal(
        employee_id=employee_id,
        trigger_type="match_low",
        target_gaps=target_gaps,
        urgency="high",
        suggested_action=f"当前岗位匹配度 {ms:.0%}，系统识别 {len(target_gaps)} 项高优缺口",
        ts=as_of,
    )]


def rule_task_embedded_learning(
    employee_id: str,
    as_of: datetime,
) -> list[TriggerSignal]:
    """任务 required 能力 ∩ 员工 gap → task_embedded_learning。

    对所有 in_progress/new 的任务扫描；bundle "案例+Prompt+微课"三件套。
    """
    emp = build_emp(employee_id)
    level_map = _employee_level_map(emp)
    out = []
    for t in list_tasks():
        if t.get("employee_id") != employee_id:
            continue
        if t.get("status") not in ("new", "in_progress"):
            continue
        task_profile = build_task_profile(t["task_id"], use_llm=False, persist=False)
        # 找 gap：任务 need_level - 员工 have_level ≥ gap_level_trigger
        gaps: list[str] = []
        for cid, need, w in task_profile.required_competencies:
            have = level_map.get(cid, 1.0)
            if (need - have) >= settings.gap_level_trigger or (need - have) >= 2:
                gaps.append(cid)
        gaps = gaps[:3]
        if not gaps:
            continue
        bundle = _bundle_resources_for(gaps)
        out.append(TriggerSignal(
            employee_id=employee_id,
            trigger_type="task_embedded_learning",
            related_task_id=t["task_id"],
            target_gaps=gaps,
            urgency="high",
            learning_mode="experiential",
            bundled_resources=bundle,
            suggested_action=(
                f"任务「{t['title']}」涉及你的 {len(gaps)} 项能力 gap，"
                f"已打包 {len(bundle)} 份参考资源"
            ),
            ts=as_of,
        ))
    return out


def rule_expert_available(
    employee_id: str,
    as_of: datetime,
    top_gap_competencies: list[str] | None = None,
) -> list[TriggerSignal]:
    """某能力上出现高产出者 → 为当前员工推 expert_available。

    只对员工 gap 较大的能力维度做 Expert Finder。
    """
    if not top_gap_competencies:
        return []
    out = []
    for cid in top_gap_competencies[:3]:
        experts = find_experts(cid, as_of=as_of, exclude={employee_id}, top_k=1)
        if not experts:
            continue
        exp = experts[0]
        out.append(TriggerSignal(
            employee_id=employee_id,
            trigger_type="expert_available",
            target_gaps=[cid],
            urgency="mid",
            learning_mode="social",
            bundled_resources=[f"EXPERT:{exp.employee_id}"],
            suggested_action=(
                f"同事 {exp.employee_id} 近 30 天在「{competency_name(cid)}」上产出强（L{exp.current_level}），"
                f"可约 1:1"
            ),
            ts=as_of,
        ))
    return out


# ---------------------------------------------------------------- Orchestrator

def run_all(
    employee_id: str,
    jd_id: str | None = None,
    as_of: datetime | None = None,
) -> list[TriggerSignal]:
    """运行全部六种规则。"""
    as_of = as_of or datetime.utcnow()
    signals: list[TriggerSignal] = []

    signals.extend(rule_task_new(employee_id, as_of))
    signals.extend(rule_review_rejected(employee_id, as_of))
    signals.extend(rule_search(employee_id, as_of))

    top_gap_cids: list[str] = []
    if jd_id:
        ml_signals = rule_match_low(employee_id, jd_id, as_of)
        signals.extend(ml_signals)
        if ml_signals:
            top_gap_cids = ml_signals[0].target_gaps

    signals.extend(rule_task_embedded_learning(employee_id, as_of))
    signals.extend(rule_expert_available(employee_id, as_of, top_gap_cids))

    # 按 urgency 排序：high → mid → low
    order = {"high": 0, "mid": 1, "low": 2}
    signals.sort(key=lambda s: order.get(s.urgency, 3))
    return signals
