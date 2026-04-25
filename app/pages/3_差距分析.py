"""差距分析页：双雷达叠加 + Gap 卡片列表 + 整体匹配度。"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.analysis.gap_analyzer import analyze_gap, match_score  # noqa: E402
from src.profile.employee_builder import build_profile as build_emp  # noqa: E402
from src.profile.job_builder import build_profile as build_job  # noqa: E402
from src.profile.ontology_loader import category_name, get_competency  # noqa: E402


st.set_page_config(page_title="差距分析", page_icon="📊", layout="wide")
st.title("📊 差距分析")
st.caption("员工 vs 岗位能力雷达叠加 + 关键 Gap 的优先级与理由。")

emp_id = st.session_state.get("employee_id")
jd_id = st.session_state.get("jd_id")
if not emp_id or not jd_id:
    st.warning("请先从主页侧边栏选择员工与岗位。")
    st.stop()

emp = build_emp(emp_id)
job = build_job(jd_id)
gaps = analyze_gap(emp, job)
ms = match_score(emp, job)

# ---- 匹配度 ----
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("整体匹配度", f"{ms:.0%}")
with c2:
    st.metric("高优 Gap", sum(1 for g in gaps if g.priority == "high" and g.gap > 0))
with c3:
    st.metric("中优 Gap", sum(1 for g in gaps if g.priority == "mid" and g.gap > 0))
with c4:
    st.metric("已达标能力", sum(1 for g in gaps if g.gap <= 0))

st.divider()

# ---- 双雷达 ----
cat_names = ["CAT.hard", "CAT.soft", "CAT.domain", "CAT.tool"]
labels = [category_name(c) for c in cat_names]

emp_levels = defaultdict(list)
for t in emp.competencies:
    c = get_competency(t.competency_id)
    if c:
        emp_levels[c.parent_id].append(t.level)

job_levels = defaultdict(list)
for cid, need, w in job.required_competencies:
    c = get_competency(cid)
    if c:
        job_levels[c.parent_id].append((float(need), float(w)))

emp_vals = [round(sum(emp_levels[c]) / len(emp_levels[c]), 2) if emp_levels[c] else 0 for c in cat_names]
job_vals = []
for c in cat_names:
    items = job_levels[c]
    if items:
        total_w = sum(w for _, w in items)
        job_vals.append(round(sum(n * w for n, w in items) / (total_w or 1), 2))
    else:
        job_vals.append(0)

col_l, col_r = st.columns([3, 5])
with col_l:
    st.markdown("#### 🧭 能力雷达对比")
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=emp_vals + emp_vals[:1], theta=labels + labels[:1],
        fill="toself", fillcolor="rgba(30, 64, 175, 0.25)",
        line=dict(color="#1E40AF", width=2), name=f"{emp.name}",
    ))
    fig.add_trace(go.Scatterpolar(
        r=job_vals + job_vals[:1], theta=labels + labels[:1],
        fill="toself", fillcolor="rgba(14, 165, 233, 0.15)",
        line=dict(color="#14B8A6", width=2, dash="dash"), name=f"岗位需求",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 5], tickvals=[1, 2, 3, 4, 5])),
        height=380, margin=dict(t=20, b=20, l=40, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=-0.1),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.markdown("#### 🔥 Gap 优先级（高 → 低）")
    prio_icon = {"high": "🔴", "mid": "🟡", "low": "🟢"}
    prio_class = {"high": "badge-high", "mid": "badge-mid", "low": "badge-low"}
    for g in gaps:
        if g.gap <= 0:
            continue
        pct = min(100, int((g.have_level / max(g.need_level, 1)) * 100))
        st.markdown(
            f"<div class='metric-card'>"
            f"<b>{prio_icon[g.priority]} {g.name}</b> "
            f"<span class='badge {prio_class[g.priority]}'>{g.priority.upper()}</span>"
            f"<span style='color:#64748B;font-size:.78rem'>gap {g.gap:.1f} · weight {g.weight:.1%}</span>"
            f"<div style='background:#E2E8F0;height:8px;border-radius:4px;margin-top:6px'>"
            f"<div style='background:linear-gradient(90deg,#14B8A6,#1E40AF);width:{pct}%;height:8px;border-radius:4px'></div>"
            f"</div>"
            f"<div style='font-size:.78rem;color:#64748B;margin-top:4px'>"
            f"当前 L{g.have_level:.1f} / 目标 L{g.need_level}"
            f"{(' · ' + g.rationale) if g.rationale else ''}"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

st.divider()

# ---- 已达标能力列表 ----
matched = [g for g in gaps if g.gap <= 0]
if matched:
    with st.expander(f"✅ 已达标能力（{len(matched)}）", expanded=False):
        for g in matched:
            st.markdown(f"- **{g.name}** · 当前 L{g.have_level:.1f} / 目标 L{g.need_level} · `{g.competency_id}`")
