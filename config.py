"""全局配置：集中管理模型、阈值、路径等参数。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 加载 .env
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


class Settings(BaseSettings):
    """运行时配置。优先级：环境变量 > .env > 默认值。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------- LLM ----------
    llm_provider: Literal["openai", "anthropic", "qwen", "deepseek", "mock"] = Field(
        default="mock", validation_alias="LLM_PROVIDER"
    )
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-4o-mini", validation_alias="LLM_MODEL")
    llm_temperature: float = 0.2
    llm_max_retries: int = 3
    llm_timeout_s: int = 60

    # ---------- Embedding ----------
    embedding_provider: Literal["bge-m3", "openai"] = Field(
        default="bge-m3", validation_alias="EMBEDDING_PROVIDER"
    )
    embedding_model: str = Field(default="BAAI/bge-m3", validation_alias="EMBEDDING_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", validation_alias="OPENAI_EMBEDDING_MODEL"
    )
    embedding_dim: int = 1024  # bge-m3 默认

    # ---------- Storage ----------
    db_path: str = Field(default="db/demo.sqlite", validation_alias="DB_PATH")
    vector_store_path: str = Field(
        default="data/vector_store", validation_alias="VECTOR_STORE_PATH"
    )

    # ---------- Data ----------
    ontology_path: str = "data/ontology/competency_ontology.json"
    employees_path: str = "data/samples/employees.json"
    jds_path: str = "data/samples/job_descriptions.json"
    tasks_path: str = "data/samples/tasks.json"
    resources_dir: str = "data/resources"
    behavior_dir: str = "data/behavior_streams"

    # ---------- Recommender ----------
    top_k_recall: int = 20            # 单路召回数量
    top_k_rerank: int = 5             # 精排保留
    recall_threshold: float = 0.55    # 相似度下限

    # ---------- Dynamic Profile（Phase 2） ----------
    bayes_alpha_init: float = 2.0
    bayes_beta_init: float = 2.0
    bayes_max_delta_per_event: float = 0.6  # 单次证据最大 Δα/Δβ，防极端翻转
    decay_lambda_hard: float = 1 / 365      # 硬技能：一年衰减到 37%
    decay_lambda_soft: float = 1 / 1095     # 软技能：三年
    decay_lambda_domain: float = 1 / 730    # 领域知识：两年
    decay_floor_ratio: float = 0.2          # 最低衰减到 peak × 0.2

    # ---------- Trigger Engine（Phase 2） ----------
    match_score_trigger: float = 0.6        # 低于此分触发 match_low
    gap_level_trigger: int = 2              # need - have ≥ 2 触发
    expert_recent_days: int = 30            # Expert Finder 观察窗口
    expert_min_delta: float = 1.0           # 30 天内累积 delta ≥ 此值判定为"高产出"

    # ---------- UI ----------
    timeline_snapshot_interval: Literal["day", "week"] = "day"
    radar_categories: list[str] = ["硬技能", "软技能", "领域知识", "工具熟练度"]

    # ---------- Runtime ----------
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    cache_ttl: int = Field(default=3600, validation_alias="CACHE_TTL")

    # ---------- Paths as Path objects ----------
    @property
    def root(self) -> Path:
        return ROOT

    def abs_path(self, rel: str) -> Path:
        """相对路径转绝对路径。"""
        p = Path(rel)
        return p if p.is_absolute() else ROOT / p


settings = Settings()


# 确保关键目录存在
for _d in [
    settings.abs_path(settings.vector_store_path),
    settings.abs_path("db"),
    settings.abs_path("logs"),
]:
    _d.mkdir(parents=True, exist_ok=True)
