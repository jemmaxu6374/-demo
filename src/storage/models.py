"""SQLAlchemy 模型：三张时序表。

- behavior_events_row：所有原始事件（供查询 + 审计）
- competency_deltas_row：事件归因输出（可回放）
- competency_timeline_row：每次贝叶斯更新后的画像点
- timeline_snapshot_row：每日聚合快照（Phase 3 加速时间轴拖动）
- task_profile_row：任务画像

所有表走 SQLite 即可，Demo 级。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings  # noqa: E402


Base = declarative_base()


class BehaviorEventRow(Base):
    __tablename__ = "behavior_events"
    event_id = Column(String(64), primary_key=True)
    employee_id = Column(String(32), index=True, nullable=False)
    source = Column(String(16), index=True, nullable=False)
    ts = Column(DateTime, index=True, nullable=False)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    raw_ref = Column(String(256), default="")

    __table_args__ = (Index("ix_events_emp_ts", "employee_id", "ts"),)


class CompetencyDeltaRow(Base):
    __tablename__ = "competency_deltas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), index=True, nullable=False)
    employee_id = Column(String(32), index=True, nullable=False)
    competency_id = Column(String(64), index=True, nullable=False)
    delta_level = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    rationale = Column(Text, default="")
    ts = Column(DateTime, index=True, nullable=False)


class CompetencyTimelineRow(Base):
    __tablename__ = "competency_timeline"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(32), index=True, nullable=False)
    competency_id = Column(String(64), index=True, nullable=False)
    ts = Column(DateTime, index=True, nullable=False)
    level = Column(Float, nullable=False)       # 1-5 连续
    alpha = Column(Float, nullable=False)
    beta = Column(Float, nullable=False)
    source_event_id = Column(String(64), default="")  # 触发该点的事件（空表示衰减点）

    __table_args__ = (
        Index("ix_timeline_emp_comp_ts", "employee_id", "competency_id", "ts"),
    )


class TimelineSnapshotRow(Base):
    """每日快照（日终状态），加速时间轴查询。"""
    __tablename__ = "timeline_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(32), index=True, nullable=False)
    competency_id = Column(String(64), index=True, nullable=False)
    date = Column(DateTime, index=True, nullable=False)
    level = Column(Float, nullable=False)
    alpha = Column(Float, nullable=False)
    beta = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_snap_emp_date", "employee_id", "date"),
    )


class TaskProfileRow(Base):
    __tablename__ = "task_profiles"
    task_id = Column(String(64), primary_key=True)
    employee_id = Column(String(32), index=True, default="")
    title = Column(String(256), default="")
    summary = Column(Text, default="")
    required_json = Column(Text, nullable=False)  # JSON: [[cid, level, weight], ...]
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------- Engine

def _engine_url() -> str:
    db_path = settings.abs_path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


_engine = None
_Session = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_engine_url(), echo=False, future=True)
    return _engine


def get_session_factory():
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _Session


def init_db():
    """首次创建所有表。"""
    Base.metadata.create_all(get_engine())


def reset_db():
    """清空所有表（谨慎使用）。"""
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
