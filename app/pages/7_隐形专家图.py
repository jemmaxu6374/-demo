"""L&D 新页②：隐形专家图。

基于 competency_timeline 近 30 天累积正向 delta 识别每项能力的 Top-K 专家。
- 按分类浏览每项能力的 Top-K 专家
- 总榜：Top Contributors（贡献能力点数 × 平均 level）
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

from app._bootstrap import ensure_data_ready_cached  # noqa: E402
from app._view import inject_theme_css, is_ld, render_view_banner  # noqa: E402


st.set_page_config(page_title="隐形专家图", page_icon="🌟", layout="wide")
ensure_data_ready_cached()
inject_theme_css()

if not is_ld():
    st.info("🎯 此页仅在 **L&D 全局视角** 下可用。请在左侧侧边栏切换视角。")
    st.stop()

st.title("🌟 隐形专家图（Expert Finder）")
st.caption("基于近 30 天行为流自动识别：每项能力的 Top-K 高产出者，可替代静态 mentor 池做更精准匹配。")
render_view_banner()


# ---------------------------------------------------------------- 数据

from src.analysis.org_analyzer import build_expert_map  # noqa: E402
from src.profile.employee_builder import list_employees  # noqa: E402
from src.profile.ontology_loader import (  # noqa: E402
    all_competencies,
    category_name,
    competency_name,
    get_competency,
)


# 员工 id → name 映射
emp_map = {e["employee_id"]: e["name"] for e in list_employees()}

# 过滤器
col_a, col_b = st.columns([2, 1])
with col_a:
    cat_filter = st.selectbox(
        "🗂️ 能力分类", ["全部", "硬技能", "软技能", "领域知识", "工具熟练度"]
    )
with col_b:
    top_k = st.slider("每项 Top-K", 1, 5, 3)

cat_id = {
    "硬技能": "CAT.hard", "软技能": "CAT.soft",
    "领域知识": "CAT.domain", "工具熟练度": "CAT.tool",
}.get(cat_filter)

filter_cids = None
if cat_id:
    filter_cids = [c.id for c in all_competencies() if c.parent_id == cat_id]

as_of = datetime(2026, 4, 25, 23, 0, 0)
expert_map = build_expert_map(as_of=as_of, top_k=top_k, only_competencies=filter_cids)


st.metric("覆盖能力数（有可识别专家）", len(expert_map))
st.divider()


# ---------------------------------------------------------------- 主视图：每能力 Top-K

st.markdown("#### 👥 各能力的隐形专家（按综合分排序）")

# 两列布局
left_col, right_col = st.columns(2)
for idx, entry in enumerate(expert_map):
    col = left_col if idx % 2 == 0 else right_col
    with col:
        c = get_competency(entry.competency_id)
        cat_label = category_name(c.parent_id) if c else ""
        st.markdown(
            f"<div class='metric-card'>"
            f"<b>{entry.name}</b> "
            f"<span style='color:#64748B;font-size:.78rem'>· {cat_label} · "
            f"静态 L≥4 {entry.coverage_level_ge4} 人</span>",
            unsafe_allow_html=True,
        )
        for rank, exp in enumerate(entry.top_experts, 1):
            badge_color = "#FCD34D" if rank == 1 else ("#D1D5DB" if rank == 2 else "#F97316")
            nm = emp_map.get(exp.employee_id, exp.employee_id)
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;padding:4px 0'>"
                f"<span>"
                f"<span style='display:inline-block;width:22px;height:22px;border-radius:50%;"
                f"background:{badge_color};color:white;text-align:center;font-size:.75rem;"
                f"line-height:22px;margin-right:6px'>{rank}</span>"
                f"<b>{nm}</b> <span style='color:#64748B;font-size:.78rem'>{exp.employee_id}</span>"
                f"</span>"
                f"<span style='font-size:.82rem'>"
                f"L{exp.current_level:.1f} · "
                f"<span style='color:#10B981'>Δ{exp.recent_cumulative_delta:+.2f}</span> · "
                f"{exp.evidence_count} 证据"
                f"</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- 辅助：Top 贡献者总榜

st.divider()
st.markdown("#### 🏅 组织 Top-10 贡献者（被识别为多少项能力的专家）")

contribute = defaultdict(lambda: {"count": 0, "total_level": 0.0, "comps": []})
for entry in expert_map:
    for exp in entry.top_experts:
        contribute[exp.employee_id]["count"] += 1
        contribute[exp.employee_id]["total_level"] += exp.current_level
        contribute[exp.employee_id]["comps"].append(entry.name)

top_contrib = sorted(contribute.items(), key=lambda x: -x[1]["count"])[:10]

for rank, (eid, info) in enumerate(top_contrib, 1):
    nm = emp_map.get(eid, eid)
    top_comps = "、".join(info["comps"][:5])
    if len(info["comps"]) > 5:
        top_comps += f"...（+{len(info['comps'])-5}）"
    st.markdown(
        f"<div class='metric-card'>"
        f"<span style='display:inline-block;width:24px;height:24px;border-radius:50%;"
        f"background:#6D28D9;color:white;text-align:center;font-size:.8rem;"
        f"line-height:24px;margin-right:8px'>{rank}</span>"
        f"<b>{nm}</b> <span style='color:#64748B;font-size:.78rem'>{eid}</span>"
        f"<span class='badge badge-low'>{info['count']} 项专家</span>"
        f"<span class='badge badge-mid'>avg L{info['total_level']/info['count']:.1f}</span>"
        f"<div style='font-size:.78rem;color:#475569;margin-top:4px'>"
        f"覆盖：{top_comps}"
        f"</div></div>",
        unsafe_allow_html=True,
    )
