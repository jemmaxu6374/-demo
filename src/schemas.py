"""Pydantic 数据契约：静态 + 动态两阶段共用。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- 通用

LearningMode = Literal["experiential", "social", "formal", "tool"]
"""70-20-10 四大学习形态分组标签：
- experiential: 在实践中学（内部项目 / Hackathon / Lab）
- social:       向他人学（导师 / 案例 / Tech Talk / 社群）
- formal:       系统学习（课程 / 文档 / 书籍）
- tool:         工具直接用（AI 工具 / Prompt 模板 / SOP）
"""

DecayType = Literal["hard", "soft", "domain"]


# ---------------------------------------------------------------- 能力本体

class CompetencyCategory(BaseModel):
    id: str
    name: str
    description: str
    decay_type: DecayType


class Competency(BaseModel):
    id: str
    name: str
    parent_id: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    decay_type: DecayType


class CompetencyOntology(BaseModel):
    version: str
    description: str = ""
    categories: list[CompetencyCategory]
    competencies: list[Competency]


# ---------------------------------------------------------------- 静态画像

class CompetencyTag(BaseModel):
    """员工画像中对一项能力的评估结果。"""

    competency_id: str
    name: str                      # 冗余便于 UI 直显
    level: float                   # 1-5 连续值（静态画像用整数，动态画像会变连续）
    confidence: float = 0.7        # 0-1
    evidence: list[str] = Field(default_factory=list)


class EmployeeProfile(BaseModel):
    employee_id: str
    name: str
    current_role: str
    department: str
    competencies: list[CompetencyTag]
    summary: str = ""              # LLM 生成的一句话画像
    raw_resume: str = ""


class JobProfile(BaseModel):
    jd_id: str
    title: str
    level: str = ""
    department: str = ""
    required_competencies: list[tuple[str, int, float]]  # (comp_id, need_level, weight)
    description: str = ""


class GapItem(BaseModel):
    competency_id: str
    name: str
    have_level: float
    need_level: int
    gap: float                     # need - have，0 表示无 gap
    priority: Literal["high", "mid", "low"]
    weight: float                  # 来自 JD 的 weight
    rationale: str = ""            # LLM 给的分析理由


class Recommendation(BaseModel):
    resource_id: str
    title: str
    source_type: Literal[
        "course", "reading", "tool", "prompt", "project",
        "lab", "mentor", "case", "talk", "community",
    ]
    learning_mode: LearningMode
    target_competency_ids: list[str]
    score: float                   # 最终打分（召回分 * 权重 + LLM 精排分）
    rationale: str = ""            # 精排解释
    url: str = ""
    extra: dict = Field(default_factory=dict)


class PathwayMilestone(BaseModel):
    phase: Literal["30d", "60d", "90d"]
    title: str
    description: str
    target_competencies: list[str]
    resources: list[str]           # resource_id 列表


class Pathway(BaseModel):
    employee_id: str
    jd_id: str
    milestones: list[PathwayMilestone]


# ---------------------------------------------------------------- 动态行为流（Phase 2）

EventSource = Literal["task", "code", "doc", "learning", "meeting", "feedback"]


class BehaviorEvent(BaseModel):
    event_id: str
    employee_id: str
    source: EventSource
    ts: datetime
    title: str
    content: str                   # 摘要文本，供 LLM 归因
    raw_ref: str = ""              # 原始链接/ID


class CompetencyDelta(BaseModel):
    event_id: str
    competency_id: str
    delta_level: float             # -1 ~ +1
    confidence: float              # 0-1
    rationale: str


class TimelinePoint(BaseModel):
    employee_id: str
    competency_id: str
    ts: datetime
    level: float                   # 1-5 连续值
    alpha: float                   # Beta 分布参数
    beta: float


class TaskProfile(BaseModel):
    task_id: str
    employee_id: str = ""
    title: str = ""
    required_competencies: list[tuple[str, int, float]]  # (comp_id, need_level, weight)
    summary: str = ""


TriggerType = Literal[
    "task_new",
    "review_rejected",
    "search",
    "match_low",
    "task_embedded_learning",     # 任务 required 能力 ∩ 员工 gap
    "expert_available",           # 某能力上出现高产出同事
]


class TriggerSignal(BaseModel):
    employee_id: str
    trigger_type: TriggerType
    related_task_id: str | None = None
    target_gaps: list[str] = Field(default_factory=list)
    urgency: Literal["high", "mid", "low"] = "mid"
    suggested_action: str = ""
    learning_mode: LearningMode | None = None
    bundled_resources: list[str] = Field(default_factory=list)
    ts: datetime = Field(default_factory=datetime.utcnow)
