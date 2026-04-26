"""岗位目标页。

- 员工视角：JD 详情 + 能力需求雷达 + 权重条
- L&D 视角：所有岗位的能力需求聚合（组织最需要哪些能力）
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app._view import inject_theme_css, is_ld, render_view_banner  # noqa: E402
from src.profile.job_builder import build_profile, get_jd_raw, list_jds  # noqa: E402
from src.profile.ontology_loader import category_name, competency_name, get_competency  # noqa: E402


st.set_page_config(page_title="岗位目标 / 岗位需求聚合", page_icon="🎯", layout="wide")
inject_theme_css()

# --------------------- L&D 视角分支 ---------------------
if is_ld():
    st.title("🎯 组织岗位能力需求聚合")
    st.caption("10 份 JD × 加权 need_level 聚合，回答：组织当前最重视哪些能力？")
    render_view_banner()

    jobs = [build_profile(j["jd_id"]) for j in list_jds()]

    # 聚合每个 competency 在多少个 JD 中出现 + 加权平均 need × weight
    comp_demand = defaultdict(lambda: {"count": 0, "score": 0.0})
    for job in jobs:
        for cid, need, w in job.required_competencies:
            comp_demand[cid]["count"] += 1
            comp_demand[cid]["score"] += need * w

    ranked = sorted(comp_demand.items(), key=lambda x: -x[1]["score"])[:18]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🔥 岗位最需要的能力（Top-18）")
        fig = go.Figure(data=go.Bar(
            x=[v["score"] for _, v in ranked],
            y=[competency_name(cid) for cid, _ in ranked],
            orientation="h",
            text=[f"{v['count']}/{len(jobs)} 个岗位" for _, v in ranked],
            textposition="auto",
            marker=dict(color="#6D28D9"),
        ))
        fig.update_layout(
            height=520, margin=dict(t=10, b=20, l=20, r=20),
            xaxis_title="聚合 need × weight",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("#### 📋 岗位清单")
        for j in list_jds():
            with st.expander(f"{j['title']}（{j.get('level', '')}） · {j['department']}"):
                st.caption(j["description"])
                st.markdown("**核心能力需求**")
                top = sorted(j["required_competencies"], key=lambda x: -x["weight"])[:5]
                for rc in top:
                    st.markdown(
                        f"- {competency_name(rc['competency_id'])} · need L{rc['need_level']} · w {rc['weight']:.1%}"
                    )

    st.stop()
# ------------------------------------------------------------

st.title("🎯 岗位目标")
st.caption("目标岗位的 JD 文本 + 结构化能力清单（need_level × weight）。")

jd_id = st.session_state.get("jd_id")
if not jd_id:
    st.warning("请先从主页侧边栏选择岗位。")
    st.stop()

raw = get_jd_raw(jd_id)
job = build_profile(jd_id)

# ---- 头部 ----
c1, c2, c3 = st.columns([3, 1, 1])
with c1:
    st.markdown(f"### {raw['title']}")
    st.caption(f"部门：{raw['department']} · 级别：{raw.get('level', '-')}")
with c2:
    st.metric("能力项", f"{len(job.required_competencies)}")
with c3:
    top_w = max((w for _, _, w in job.required_competencies), default=0)
    st.metric("最高权重", f"{top_w:.2%}")

with st.expander("📝 JD 原文", expanded=True):
    st.write(raw["description"])

st.divider()

# ---- 按分类聚合的雷达 ----
cat_need: dict[str, list[tuple[float, float]]] = defaultdict(list)  # (need_level, weight)
for cid, need, w in job.required_competencies:
    c = get_competency(cid)
    if c:
        cat_need[c.parent_id].append((float(need), float(w)))

cat_names = ["CAT.hard", "CAT.soft", "CAT.domain", "CAT.tool"]
labels = [category_name(c) for c in cat_names]
# 加权平均 need_level
values = []
for c in cat_names:
    items = cat_need[c]
    if items:
        total_w = sum(w for _, w in items)
        v = sum(n * w for n, w in items) / (total_w or 1)
        values.append(round(v, 2))
    else:
        values.append(0)

col_l, col_r = st.columns([3, 4])
with col_l:
    st.markdown("#### 🎯 能力需求雷达（四大类加权均值）")
    fig = go.Figure(data=go.Scatterpolar(
        r=values + values[:1], theta=labels + labels[:1], fill="toself",
        fillcolor="rgba(14, 165, 233, 0.25)", line=dict(color="#0EA5E9", width=2),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 5], tickvals=[1, 2, 3, 4, 5])),
        height=360, margin=dict(t=20, b=20, l=40, r=40), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.markdown("#### 📊 能力项权重分布（Top）")
    rows = sorted(job.required_competencies, key=lambda x: -x[2])
    fig2 = go.Figure(data=go.Bar(
        x=[w for _, _, w in rows],
        y=[competency_name(cid) for cid, _, _ in rows],
        orientation="h",
        text=[f"need {n}" for _, n, _ in rows],
        textposition="auto",
        marker=dict(color="#1E40AF"),
    ))
    fig2.update_layout(
        height=360, margin=dict(t=10, b=20, l=20, r=20),
        xaxis_title="权重",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

st.markdown("#### 📋 能力需求明细")
for cid, need, w in sorted(job.required_competencies, key=lambda x: -x[2]):
    c = get_competency(cid)
    cat = category_name(c.parent_id) if c else "-"
    st.markdown(
        f"<div class='metric-card'>"
        f"<b>{competency_name(cid)}</b> "
        f"<span style='color:#64748B;font-size:.8rem'>· {cat} · `{cid}`</span><br>"
        f"<span class='badge badge-mid'>need L{int(need)}</span>"
        f"<span class='badge badge-low'>weight {w:.2%}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
