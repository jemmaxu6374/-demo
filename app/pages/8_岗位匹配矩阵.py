"""L&D 新页③：岗位匹配矩阵。

- 20 员工 × 10 JD 的匹配度热力图
- 每个 JD 的 Top-3 候选人
- 每个员工的 Top-3 匹配岗位
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app._bootstrap import ensure_data_ready_cached  # noqa: E402
from app._view import inject_theme_css, is_ld, render_view_banner  # noqa: E402


st.set_page_config(page_title="岗位匹配矩阵", page_icon="🎯", layout="wide")
ensure_data_ready_cached()
inject_theme_css()

if not is_ld():
    st.info("🎯 此页仅在 **L&D 全局视角** 下可用。请在左侧侧边栏切换视角。")
    st.stop()

st.title("🎯 岗位匹配矩阵")
st.caption("20 位员工 × 10 个目标岗位的匹配度（基于能力画像 vs JD 加权对齐）。")
render_view_banner()


# ---------------------------------------------------------------- 数据

from src.analysis.org_analyzer import build_job_match_matrix  # noqa: E402

jm = build_job_match_matrix()


# ---------------------------------------------------------------- 热力图

st.markdown("#### 🔥 匹配度热力图（0-1，色越深越匹配）")

fig = go.Figure(data=go.Heatmap(
    z=jm.scores,
    x=jm.jd_titles,
    y=[f"{nm} ({eid[-3:]})" for eid, nm in zip(jm.employee_ids, jm.employee_names)],
    colorscale=[
        [0.0, "#FEE2E2"],
        [0.3, "#FECACA"],
        [0.5, "#FDE68A"],
        [0.7, "#BBF7D0"],
        [0.85, "#6EE7B7"],
        [1.0, "#10B981"],
    ],
    zmin=0, zmax=1,
    text=[[f"{v:.0%}" for v in row] for row in jm.scores],
    texttemplate="%{text}",
    textfont={"size": 10, "color": "#1F2937"},
    hovertemplate="员工：%{y}<br>岗位：%{x}<br>匹配度：%{z:.1%}<extra></extra>",
    colorbar=dict(title="match", tickformat=".0%"),
))
fig.update_layout(
    height=max(500, 28 * len(jm.employee_ids) + 150),
    margin=dict(t=20, b=160, l=140, r=20),
    xaxis=dict(tickangle=-30, side="bottom"),
    yaxis=dict(autorange="reversed"),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()


# ---------------------------------------------------------------- 每 JD Top-3

c_jd, c_emp = st.columns(2)

with c_jd:
    st.markdown("#### 👥 每个岗位的 Top-3 候选人")
    for j, jd_title in enumerate(jm.jd_titles):
        pairs = [(jm.scores[i][j], jm.employee_ids[i], jm.employee_names[i])
                 for i in range(len(jm.employee_ids))]
        pairs.sort(key=lambda x: -x[0])
        top3 = pairs[:3]
        st.markdown(
            f"<div class='metric-card'>"
            f"<b>{jd_title}</b> "
            f"<span style='color:#64748B;font-size:.78rem'>· `{jm.jd_ids[j]}`</span>",
            unsafe_allow_html=True,
        )
        for rank, (score, eid, nm) in enumerate(top3, 1):
            medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else "🥉")
            color = "#10B981" if score >= 0.8 else ("#F59E0B" if score >= 0.6 else "#EF4444")
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;padding:4px 0'>"
                f"<span>{medal} <b>{nm}</b> <span style='color:#64748B;font-size:.78rem'>{eid}</span></span>"
                f"<span style='color:{color};font-weight:600'>{score:.0%}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

with c_emp:
    st.markdown("#### 🎯 每个员工的 Top-3 适配岗位")
    for i, (eid, nm) in enumerate(zip(jm.employee_ids, jm.employee_names)):
        pairs = [(jm.scores[i][j], jm.jd_ids[j], jm.jd_titles[j])
                 for j in range(len(jm.jd_ids))]
        pairs.sort(key=lambda x: -x[0])
        top3 = pairs[:3]
        st.markdown(
            f"<div class='metric-card'>"
            f"<b>{nm}</b> "
            f"<span style='color:#64748B;font-size:.78rem'>· {eid}</span>",
            unsafe_allow_html=True,
        )
        for rank, (score, jid, title) in enumerate(top3, 1):
            medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else "🥉")
            color = "#10B981" if score >= 0.8 else ("#F59E0B" if score >= 0.6 else "#EF4444")
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;padding:4px 0'>"
                f"<span>{medal} {title} <span style='color:#64748B;font-size:.78rem'>{jid}</span></span>"
                f"<span style='color:{color};font-weight:600'>{score:.0%}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
