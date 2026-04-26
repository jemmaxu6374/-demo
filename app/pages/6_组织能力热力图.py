"""L&D 新页①：组织能力热力图。

- 完整员工×能力矩阵（20 × 36）
- 行列可按 level 排序，识别能力高峰/低谷
- 辅助图：按分类的能力覆盖度排行
- 仅 L&D 视角可见，员工视角下跳转提示
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


st.set_page_config(page_title="组织能力热力图", page_icon="🔥", layout="wide")
ensure_data_ready_cached()
inject_theme_css()

if not is_ld():
    st.info("🎯 此页仅在 **L&D 全局视角** 下可用。请在左侧侧边栏切换视角。")
    st.stop()

st.title("🔥 组织能力热力图")
st.caption("20 位员工 × 36 项能力的完整静态画像。颜色深 = level 高。")
render_view_banner()


# ---------------------------------------------------------------- 数据

from src.analysis.org_analyzer import build_competency_matrix  # noqa: E402
from src.profile.ontology_loader import category_name, get_competency  # noqa: E402

m = build_competency_matrix()


# ---------------------------------------------------------------- 控制栏

col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
with col_f1:
    category_filter = st.selectbox(
        "🗂️ 能力分类筛选",
        ["全部", "硬技能", "软技能", "领域知识", "工具熟练度"],
    )
with col_f2:
    min_show_level = st.slider("最低显示 level", 0.0, 5.0, 0.0, 0.5)
with col_f3:
    sort_mode = st.radio(
        "行排序",
        ["按员工 ID", "按平均 level（降）", "按平均 level（升）"],
        horizontal=True,
    )


# 过滤能力
cat_filter_id = {
    "硬技能": "CAT.hard", "软技能": "CAT.soft",
    "领域知识": "CAT.domain", "工具熟练度": "CAT.tool",
}.get(category_filter)

if cat_filter_id:
    keep_j = [j for j, cid in enumerate(m.competency_ids)
              if (c := get_competency(cid)) and c.parent_id == cat_filter_id]
else:
    keep_j = list(range(len(m.competency_ids)))

filtered_comp_ids = [m.competency_ids[j] for j in keep_j]
filtered_comp_names = [m.competency_names[j] for j in keep_j]

# 过滤 + 排序行
row_data = []
for i, eid in enumerate(m.employee_ids):
    row_vals = [m.matrix[i][j] if m.matrix[i][j] >= min_show_level else 0
                for j in keep_j]
    avg = sum(row_vals) / len(row_vals) if row_vals else 0
    row_data.append((i, eid, m.employee_names[i], row_vals, avg))

if sort_mode == "按平均 level（降）":
    row_data.sort(key=lambda r: -r[4])
elif sort_mode == "按平均 level（升）":
    row_data.sort(key=lambda r: r[4])

y_labels = [f"{nm} ({eid[-3:]})" for _, eid, nm, _, _ in row_data]
z_matrix = [r[3] for r in row_data]


# ---------------------------------------------------------------- 热力图

st.markdown("#### 📊 员工 × 能力 level 热力图")
fig = go.Figure(data=go.Heatmap(
    z=z_matrix,
    x=filtered_comp_names,
    y=y_labels,
    colorscale=[
        [0.0, "#F1F5F9"],    # 未掌握
        [0.2, "#DDD6FE"],
        [0.4, "#A78BFA"],
        [0.6, "#8B5CF6"],
        [0.8, "#6D28D9"],
        [1.0, "#4C1D95"],
    ],
    zmin=0, zmax=5,
    text=[[f"{v:.1f}" if v > 0 else "" for v in row] for row in z_matrix],
    texttemplate="%{text}",
    textfont={"size": 10, "color": "white"},
    colorbar=dict(title="level", ticks="outside"),
    hovertemplate="员工：%{y}<br>能力：%{x}<br>level：%{z:.2f}<extra></extra>",
))
fig.update_layout(
    height=max(500, 28 * len(row_data) + 150),
    margin=dict(t=20, b=140, l=120, r=20),
    xaxis=dict(tickangle=-50, side="bottom"),
    yaxis=dict(autorange="reversed"),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()


# ---------------------------------------------------------------- 辅助视图

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### 🏆 组织 Top-10 覆盖能力（L≥3 员工数）")
    ranked = sorted(m.coverage.items(), key=lambda x: -x[1])[:10]
    fig2 = go.Figure(data=go.Bar(
        x=[v for _, v in ranked],
        y=[next(cn for cid2, cn in zip(m.competency_ids, m.competency_names) if cid2 == cid)
           for cid, _ in ranked],
        orientation="h",
        text=[f"{v}/20 ({v/20:.0%})" for _, v in ranked],
        textposition="auto",
        marker=dict(color="#10B981"),
    ))
    fig2.update_layout(
        height=400, margin=dict(t=10, b=20, l=20, r=20),
        xaxis_title="员工数", yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig2, use_container_width=True)

with c2:
    st.markdown("#### 📉 组织 Bottom-10 薄弱能力（L≥3 员工数）")
    all_covered = {cid: m.coverage.get(cid, 0) for cid in m.competency_ids}
    bottom = sorted(all_covered.items(), key=lambda x: x[1])[:10]
    fig3 = go.Figure(data=go.Bar(
        x=[v for _, v in bottom],
        y=[next(cn for cid2, cn in zip(m.competency_ids, m.competency_names) if cid2 == cid)
           for cid, _ in bottom],
        orientation="h",
        text=[f"{v}/20 ({v/20:.0%})" for _, v in bottom],
        textposition="auto",
        marker=dict(color="#EF4444"),
    ))
    fig3.update_layout(
        height=400, margin=dict(t=10, b=20, l=20, r=20),
        xaxis_title="员工数", yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig3, use_container_width=True)
