"""员工画像页：雷达图 + 标签云 + 证据溯源。"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from src.profile.employee_builder import build_profile, get_employee_raw  # noqa: E402
from src.profile.ontology_loader import category_name, get_competency  # noqa: E402


st.set_page_config(page_title="员工画像", page_icon="👤", layout="wide")
st.title("👤 员工画像")
st.caption("从简历 / 项目 / 自评抽取结构化能力标签，带熟练度评分与证据溯源。")


employee_id = st.session_state.get("employee_id")
if not employee_id:
    st.warning("请先从主页侧边栏选择员工。")
    st.stop()

raw = get_employee_raw(employee_id)
profile = build_profile(employee_id)

# ---- 基础信息 ----
c1, c2, c3 = st.columns([2, 2, 3])
with c1:
    st.metric("姓名", raw["name"])
    st.metric("部门", raw["department"])
with c2:
    st.metric("当前角色", raw["current_role"])
    st.metric("能力标签数", f"{len(profile.competencies)}")
with c3:
    st.markdown("**画像摘要**")
    st.info(profile.summary or "（LLM 未生成摘要）")

st.divider()

# ---- 雷达图（按四大类聚合，取每类平均 level） ----
cat_levels: dict[str, list[float]] = defaultdict(list)
for t in profile.competencies:
    c = get_competency(t.competency_id)
    if c:
        cat_levels[c.parent_id].append(t.level)

cat_names = ["CAT.hard", "CAT.soft", "CAT.domain", "CAT.tool"]
labels = [category_name(c) for c in cat_names]
values = [round(sum(cat_levels[c]) / len(cat_levels[c]), 2) if cat_levels[c] else 0 for c in cat_names]

col_l, col_r = st.columns([3, 4])
with col_l:
    st.markdown("#### 🎯 能力雷达（四大类均值）")
    fig = go.Figure(data=go.Scatterpolar(
        r=values + values[:1], theta=labels + labels[:1], fill="toself",
        fillcolor="rgba(30, 64, 175, 0.25)", line=dict(color="#1E40AF", width=2),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 5], tickvals=[1, 2, 3, 4, 5])),
        height=360, margin=dict(t=20, b=20, l=40, r=40), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.markdown("#### ☁️ 能力标签（按分类分组）")
    for cat_id in cat_names:
        items = [t for t in profile.competencies if (get_competency(t.competency_id) and get_competency(t.competency_id).parent_id == cat_id)]
        if not items:
            continue
        items.sort(key=lambda t: -t.level)
        st.markdown(f"**{category_name(cat_id)}**")
        html = ""
        for t in items:
            # 按 level 选配色
            if t.level >= 4:
                bg = "#1E40AF"; fg = "white"
            elif t.level >= 3:
                bg = "#0EA5E9"; fg = "white"
            elif t.level >= 2:
                bg = "#94A3B8"; fg = "white"
            else:
                bg = "#E2E8F0"; fg = "#475569"
            html += (f'<span style="background:{bg};color:{fg};padding:3px 10px;'
                     f'border-radius:999px;font-size:.8rem;margin:2px;display:inline-block;">'
                     f'{t.name} · L{t.level:.0f}</span>')
        st.markdown(html, unsafe_allow_html=True)

st.divider()

# ---- 证据溯源表 ----
st.markdown("#### 🔍 能力与证据溯源")
st.caption("每项能力对应的评分依据来自简历、项目经历与自评；LLM 模式下会叠加增量抽取结果。")

sorted_items = sorted(profile.competencies, key=lambda t: -t.level)
for t in sorted_items:
    prio = "🟢" if t.level >= 4 else "🟡" if t.level >= 3 else "🔵" if t.level >= 2 else "⚪"
    with st.expander(f"{prio} {t.name} · L{t.level:.0f}（置信 {t.confidence:.0%}）", expanded=False):
        st.caption(f"competency_id: `{t.competency_id}`")
        if t.evidence:
            for ev in t.evidence:
                st.markdown(f"- {ev}")
        else:
            st.markdown("_（暂无证据文本）_")

# ---- 原始资料 ----
with st.expander("📄 查看原始简历与项目经历", expanded=False):
    st.markdown("**简历**")
    st.write(raw["resume"])
    st.markdown("**项目经历**")
    for p in raw.get("projects", []):
        st.markdown(f"- **{p['name']}**（{p['role']}）：{p['description']}")
    st.markdown("**自评**")
    st.markdown(f"- 强项：{'；'.join(raw['self_assessment']['strengths'])}")
    st.markdown(f"- 待提升：{'；'.join(raw['self_assessment']['weaknesses'])}")
