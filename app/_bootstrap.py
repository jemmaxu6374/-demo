"""Cloud bootstrap：在 Streamlit Cloud 首次冷启动时自动准备数据。

Streamlit Cloud 的文件系统每次部署都是干净的。为了让访客看到 Phase 3 双视图页上
有完整的行为流和时间线，这里做一次性数据准备：

1. 检查 db/demo.sqlite 是否存在且有数据
2. 若无：生成行为流 jsonl → 加载入 DB → 回放事件 → 建快照
3. 用 Streamlit 的 @st.cache_resource 保证只跑一次

日志打到 stderr，Streamlit Cloud 的 "Manage app" 面板可以看到。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _need_bootstrap() -> tuple[bool, str]:
    """返回 (需要 bootstrap, 原因)。"""
    from config import settings

    db_path = settings.abs_path(settings.db_path)
    if not db_path.exists():
        return True, "db file missing"

    # 检查有没有 behavior_events 记录
    try:
        from src.storage.repository import count_events

        n = count_events()
        if n == 0:
            return True, "db empty"
        return False, f"db ready ({n} events)"
    except Exception as e:
        return True, f"db query failed: {e}"


def _run_bootstrap():
    logger.info("=== Cloud bootstrap: preparing demo data ===")

    # Step 1: 生成行为流 jsonl（若不存在）
    from config import settings

    bd = settings.abs_path(settings.behavior_dir)
    has_streams = bd.exists() and any(bd.iterdir())
    if not has_streams:
        logger.info("[1/4] Generating behavior streams...")
        from scripts.generate_behavior_streams import main as gen_main

        gen_main()
    else:
        logger.info("[1/4] Behavior streams already exist, skipped")

    # Step 2: 加载事件入 DB
    logger.info("[2/4] Loading events into DB...")
    from src.events.event_loader import load_into_db

    load_into_db(reset=True)

    # Step 3: 回放到 timeline
    logger.info("[3/4] Replaying events (this takes ~30-60s on Cloud)...")
    from scripts.replay_events import replay_for_employee, _reset_dynamic_tables

    _reset_dynamic_tables()
    ids = sorted(p.name for p in bd.iterdir() if p.is_dir())
    for eid in ids:
        replay_for_employee(eid)

    # Step 4: 建快照
    logger.info("[4/4] Building daily snapshots...")
    from scripts.build_timeline_snapshots import build_snapshots

    build_snapshots()

    logger.info("=== Bootstrap done ===")


def ensure_data_ready(silent: bool = False) -> str:
    """保证数据就绪；返回状态字符串供 UI 显示。"""
    need, reason = _need_bootstrap()
    if not need:
        return f"✅ {reason}"

    if not silent:
        import streamlit as st

        placeholder = st.empty()
        placeholder.info(
            f"🔧 首次启动需要准备数据（生成行为流 + 回放事件 + 建快照），预计 1-2 分钟..."
        )
    try:
        _run_bootstrap()
    except Exception as e:
        logger.exception(f"Bootstrap failed: {e}")
        return f"❌ bootstrap error: {e}"
    if not silent:
        placeholder.empty()
    return "✅ bootstrap done"


# Streamlit cache：进程生命期内只跑一次
try:
    import streamlit as st

    @st.cache_resource(show_spinner=False)
    def ensure_data_ready_cached():
        return ensure_data_ready(silent=False)
except Exception:
    # 非 Streamlit 环境下（比如 pytest / CLI）直接同步跑
    def ensure_data_ready_cached():
        return ensure_data_ready(silent=True)
