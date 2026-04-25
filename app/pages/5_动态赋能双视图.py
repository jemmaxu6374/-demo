"""动态赋能双视图页（Phase 3 核心）。

布局：
- 顶部：员工 + 时间轴滑块（0-180 天）+ 播放提示
- 左侧（40%）：垂直行为流时间线（按日期倒序，六类事件带图标）
- 右侧（60%）：四宫格
  - 左上：能力雷达（从 snapshot 查当时状态）
  - 右上：标签云 + 近 30 天变化
  - 左下：当前任务画像 + 匹配度
  - 右下：触发引擎推送卡片栈（按 70-20-10 色带）
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.analysis.gap_analyzer import match_score  # noqa: E402
from src.events.trigger_engine import run_all as run_triggers  # noqa: E402
from src.profile.employee_builder import build_profile as build_emp  # noqa: E402
from src.profile.job_builder import build_profile as build_job  # noqa: E402
from src.profile.ontology_loader import category_name, competency_name, get_competency  # noqa: E402
from src.profile.task_profiler import build_task_profile, list_tasks  # noqa: E402
from src.storage.repository import (  # noqa: E402
    list_events,
    query_profile_at,
    query_snapshot_at,
    query_timeline_series,
)


st.set_page_config(page_title="动态赋能双视图", page_icon="🕒", layout="wide")

# Cloud bootstrap（若访客直接打开此页）
from app._bootstrap import ensure_data_ready_cached  # noqa: E402

ensure_data_ready_cached()

st.title("🕒 动态赋能双视图（Phase 3）")
st.caption("左侧行为流 · 右侧能力画像 + 任务 + 推送卡片；顶部时间轴可回溯 6 个月。")


# ---------------------------------------------------------------- 顶部：时间轴

base_end = datetime(2026, 4, 25, 23, 0, 0)
base_start = base_end - timedelta(days=180)

emp_id = st.session_state.get("employee_id")
jd_id = st.session_state.get("jd_id")
if not emp_id:
    st.warning("请先从主页侧边栏选择员工。")
    st.stop()

st.markdown("#### ⏳ 时间轴")
col_slider, col_info = st.columns([6, 2])
with col_slider:
    day_offset = st.slider(
        "拖动回溯到 6 个月内任意时间点",
        min_value=0, max_value=180, value=180, step=1,
        label_visibility="collapsed",
    )
    as_of = base_start + timedelta(days=day_offset)
with col_info:
    st.metric("当前时间点", as_of.strftime("%Y-%m-%d"))

st.divider()


# ---------------------------------------------------------------- 左右分栏

left, right = st.columns([4, 6])


# ---------------------------------------------------------------- 左：行为流

SOURCE_ICONS = {
    "task": ("📋", "#1E40AF"), "code": ("🔀", "#10B981"),
    "doc": ("📝", "#0EA5E9"), "learning": ("📚", "#F59E0B"),
    "meeting": ("💬", "#8B5CF6"), "feedback": ("⭐", "#EF4444"),
}

with left:
    st.markdown("### 📜 行为流时间线")
    # 取 as_of 之前 30 天内的事件
    win_start = as_of - timedelta(days=30)
    events = list_events(emp_id, start=win_start, end=as_of, limit=60)
    events = sorted(events, key=lambda e: e.ts, reverse=True)

    st.caption(f"显示 {as_of.strftime('%Y-%m-%d')} 之前 30 天的 {len(events)} 条事件（倒序）")

    filter_sources = st.multiselect(
        "筛选来源",
        ["task", "code", "doc", "learning", "meeting", "feedback"],
        default=["task", "code", "doc", "learning", "meeting", "feedback"],
        label_visibility="collapsed",
    )

    for e in events:
        if e.source not in filter_sources:
            continue
        icon, color = SOURCE_ICONS.get(e.source, ("•", "#64748B"))
        st.markdown(
            f"<div style='border-left:3px solid {color};padding:.4rem .8rem;margin:.3rem 0;"
            f"background:#F8FAFC;border-radius:0 6px 6px 0'>"
            f"<div style='font-size:.78rem;color:#64748B'>"
            f"{e.ts.strftime('%m-%d %H:%M')} · {icon} {e.source}"
            f"</div>"
            f"<div style='font-size:.88rem;color:#0F172A;margin-top:2px'>{e.title}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------- 右：四宫格

with right:
    # --- 雷达图（查 snapshot） ---
    q1, q2 = st.columns(2)

    with q1:
        st.markdown("### 🎯 能力雷达")
        snap = query_snapshot_at(emp_id, as_of)
        cat_vals = defaultdict(list)
        for cid, row in snap.items():
            c = get_competency(cid)
            if c:
                cat_vals[c.parent_id].append(row.level)
        cat_names = ["CAT.hard", "CAT.soft", "CAT.domain", "CAT.tool"]
        labels = [category_name(c) for c in cat_names]
        values = [round(sum(cat_vals[c]) / len(cat_vals[c]), 2) if cat_vals[c] else 0 for c in cat_names]

        fig = go.Figure(data=go.Scatterpolar(
            r=values + values[:1], theta=labels + labels[:1], fill="toself",
            fillcolor="rgba(30, 64, 175, 0.25)", line=dict(color="#1E40AF", width=2),
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(range=[0, 5], tickvals=[1, 2, 3, 4, 5])),
            height=280, margin=dict(t=15, b=15, l=40, r=40), showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    with q2:
        st.markdown("### 📈 近 30 天变化")
        ago = as_of - timedelta(days=30)
        snap_ago = query_snapshot_at(emp_id, ago)
        # 每个能力 Δ = now - ago
        changes = []
        for cid, row_now in snap.items():
            prev = snap_ago.get(cid)
            prev_lvl = prev.level if prev else 0
            delta = row_now.level - prev_lvl
            changes.append((cid, row_now.level, delta))
        changes.sort(key=lambda x: -abs(x[2]))
        top_chg = changes[:8]

        if top_chg:
            for cid, lvl, delta in top_chg:
                arrow = "↑" if delta > 0.05 else "↓" if delta < -0.05 else "→"
                color = "#10B981" if delta > 0 else "#EF4444" if delta < 0 else "#64748B"
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;padding:3px 0'>"
                    f"<span style='font-size:.82rem'>{competency_name(cid)}</span>"
                    f"<span style='color:{color};font-weight:600;font-size:.82rem'>"
                    f"L{lvl:.1f} {arrow} {delta:+.2f}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("_暂无变化数据_")

    st.markdown("---")

    q3, q4 = st.columns(2)

    with q3:
        st.markdown("### 📋 当前任务画像")
        emp_tasks = [t for t in list_tasks() if t.get("employee_id") == emp_id]
        if emp_tasks:
            t = emp_tasks[0]
            tp = build_task_profile(t["task_id"], use_llm=False, persist=False)
            # 计算匹配度：用 snapshot 作为画像
            total_w = sum(w for _, _, w in tp.required_competencies) or 1.0
            num = 0.0
            den = 0.0
            for cid, need, w in tp.required_competencies:
                row = snap.get(cid)
                have = row.level if row else 0
                num += w * min(have, need)
                den += w * need
            ms_task = round(num / den, 3) if den else 0.0

            st.markdown(f"**📌 {t['title']}**")
            st.caption(t["description"][:100] + "...")
            st.progress(ms_task)
            st.caption(f"任务匹配度 {ms_task:.0%}")

            st.markdown("**关键能力**")
            for cid, need, w in tp.required_competencies[:4]:
                row = snap.get(cid)
                have = row.level if row else 0
                st.markdown(
                    f"- `{competency_name(cid)}` need L{need} / have L{have:.1f}"
                )
        else:
            st.info("该员工无进行中任务")

    with q4:
        st.markdown("### 🚨 赋能推送卡片栈")
        # 用 trigger_engine 输出
        jd_id_for_trigger = jd_id or "jd_002"
        signals = run_triggers(emp_id, jd_id=jd_id_for_trigger, as_of=as_of)

        if not signals:
            st.success("暂无触发信号")
        else:
            mode_color = {
                "experiential": "#F59E0B", "social": "#6366F1",
                "formal": "#1E40AF", "tool": "#10B981",
            }
            urgency_emoji = {"high": "🔴", "mid": "🟡", "low": "🟢"}
            for s in signals[:6]:
                color = mode_color.get(s.learning_mode, "#64748B") if s.learning_mode else "#64748B"
                embed = ""
                if s.trigger_type == "task_embedded_learning" and s.bundled_resources:
                    embed = (
                        "<div style='margin-top:6px;padding:6px;background:#F0F9FF;border-radius:4px;font-size:.75rem'>"
                        "📦 <b>三件套打包</b>："
                        + " · ".join(s.bundled_resources)
                        + "</div>"
                    )
                elif s.trigger_type == "expert_available" and s.bundled_resources:
                    embed = (
                        "<div style='margin-top:6px;padding:6px;background:#EEF2FF;border-radius:4px;font-size:.75rem'>"
                        "👤 <b>隐形导师</b>：" + ", ".join(s.bundled_resources)
                        + "</div>"
                    )

                st.markdown(
                    f"<div style='border-left:4px solid {color};padding:.5rem .7rem;margin:.3rem 0;"
                    f"background:white;border:1px solid #E2E8F0;border-radius:0 6px 6px 0'>"
                    f"<div style='font-size:.78rem;color:#64748B'>"
                    f"{urgency_emoji.get(s.urgency, '•')} {s.trigger_type}"
                    f"{' · ' + s.learning_mode if s.learning_mode else ''}"
                    f"</div>"
                    f"<div style='font-size:.85rem;color:#0F172A;margin-top:3px'>"
                    f"{s.suggested_action}</div>"
                    f"{embed}"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------- 底部：能力演化曲线

st.divider()
st.markdown("### 📊 单能力演化曲线（拖动时间轴看变化）")

all_comp_ids = sorted(set(snap.keys())) if snap else []
if all_comp_ids:
    selected_cid = st.selectbox(
        "选择要查看的能力",
        all_comp_ids,
        format_func=lambda c: f"{competency_name(c)}（{c}）",
    )
    series = query_timeline_series(emp_id, selected_cid, start=base_start, end=base_end)
    if series:
        xs = [p.ts for p in series]
        ys = [p.level for p in series]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers",
            line=dict(color="#1E40AF", width=2),
            marker=dict(size=4), name=competency_name(selected_cid),
        ))
        # 标红当前时间点
        fig.add_vline(x=as_of, line_width=2, line_dash="dash", line_color="#EF4444")
        fig.add_annotation(x=as_of, y=5, text="当前", showarrow=False, yshift=10, font=dict(color="#EF4444"))
        fig.update_layout(
            height=300, margin=dict(t=20, b=20, l=20, r=20),
            yaxis=dict(range=[1, 5], title="level"),
            xaxis_title="时间",
        )
        st.plotly_chart(fig, use_container_width=True)
