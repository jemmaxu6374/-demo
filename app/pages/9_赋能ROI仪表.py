"""L&D 新页④：赋能 ROI 仪表。

展示组织级健康度指标：
- 规模：员工 / 事件 / timeline
- 学习效果：6 个月平均 level 涨幅
- 能力分布：强 / 弱 能力数
- 赋能推送：可识别 expert 数、估算触发信号数
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app._bootstrap import ensure_data_ready_cached  # noqa: E402
from app._view import inject_theme_css, is_ld, render_view_banner  # noqa: E402


st.set_page_config(page_title="赋能 ROI 仪表", page_icon="📊", layout="wide")
ensure_data_ready_cached()
inject_theme_css()

if not is_ld():
    st.info("🎯 此页仅在 **L&D 全局视角** 下可用。请在左侧侧边栏切换视角。")
    st.stop()

st.title("📊 赋能 ROI 仪表盘")
st.caption("组织级健康度指标：规模、学习效果、能力分布、赋能推送覆盖。")
render_view_banner()


# ---------------------------------------------------------------- 计算

from src.analysis.org_analyzer import compute_org_roi  # noqa: E402

with st.spinner("正在计算组织级指标..."):
    r = compute_org_roi(as_of=datetime(2026, 4, 25, 23, 0, 0))


# ---------------------------------------------------------------- Section 1: 规模

st.markdown("### 📏 组织规模与数据体量")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("员工数", f"{r.total_employees}")
with c2:
    st.metric("行为事件（6 个月）", f"{r.total_events_6mo:,}")
with c3:
    st.metric("人均事件数", f"{r.avg_events_per_emp:.0f}")
with c4:
    st.metric("当前画像点", f"{r.total_timeline_points:,}")

st.divider()


# ---------------------------------------------------------------- Section 2: 学习效果

st.markdown("### 📈 学习效果")

c1, c2 = st.columns([1, 2])
with c1:
    # 6 个月平均 level 涨幅（用 Gauge 显示）
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=r.avg_level_gain_6mo,
        number={"suffix": " 级", "valueformat": ".2f"},
        delta={"reference": 0.5, "increasing": {"color": "#10B981"}},
        gauge={
            "axis": {"range": [0, 2.0]},
            "bar": {"color": "#6D28D9"},
            "steps": [
                {"range": [0, 0.3], "color": "#FEE2E2"},
                {"range": [0.3, 0.7], "color": "#FEF3C7"},
                {"range": [0.7, 2.0], "color": "#D1FAE5"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 3},
                "thickness": 0.75,
                "value": 0.5,  # 目标线：半年涨 0.5 级
            },
        },
        title={"text": "6 个月平均 Level 涨幅"},
    ))
    fig_gauge.update_layout(height=280, margin=dict(t=40, b=10, l=10, r=10))
    st.plotly_chart(fig_gauge, use_container_width=True)

with c2:
    st.markdown("#### 📌 解读")
    if r.avg_level_gain_6mo >= 0.7:
        verdict = "🟢 **优秀** —— 组织整体能力增长显著，超出目标。"
    elif r.avg_level_gain_6mo >= 0.3:
        verdict = "🟡 **良好** —— 能力稳步提升，但仍有空间。"
    else:
        verdict = "🔴 **偏低** —— 整体学习效果不够，需加大赋能投入。"
    st.info(verdict)

    st.markdown(
        "**计算方式**：取所有（员工 × 能力）对的当前 level 与 6 个月前 level 之差，再求平均。\n\n"
        "此指标反映行为流驱动的贝叶斯画像更新的「累积效应」。静态画像不会变化，"
        "只有在事件持续积累后，level 才能从 3 慢慢涨到 4。"
    )

st.divider()


# ---------------------------------------------------------------- Section 3: 能力分布

st.markdown("### 🏋️ 组织能力分布")

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("💪 强能力", f"{r.strong_competencies}",
              help="覆盖 ≥ 60% 员工 @ L≥3 的能力数")
with c2:
    st.metric("⚠️ 弱能力", f"{r.weak_competencies}",
              help="覆盖 ≤ 20% 员工 @ L≥3 的能力数")
with c3:
    balanced = 36 - r.strong_competencies - r.weak_competencies
    st.metric("🟰 中等能力", f"{balanced}")

# 饼图显示分布
fig_pie = go.Figure(data=go.Pie(
    labels=["💪 强能力", "🟰 中等", "⚠️ 弱能力"],
    values=[r.strong_competencies, balanced, r.weak_competencies],
    marker=dict(colors=["#10B981", "#F59E0B", "#EF4444"]),
    hole=0.4,
))
fig_pie.update_layout(
    height=320, margin=dict(t=10, b=10, l=10, r=10),
    annotations=[dict(text=f"36 项<br>能力", x=0.5, y=0.5, font_size=14, showarrow=False)],
)
st.plotly_chart(fig_pie, use_container_width=True)

st.divider()


# ---------------------------------------------------------------- Section 4: 赋能推送覆盖

st.markdown("### 🚨 赋能推送潜力")

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### 🌟 可识别隐形专家的能力数")
    ratio = r.expert_signals / 36
    fig_bar = go.Figure(go.Indicator(
        mode="number+gauge+delta",
        value=r.expert_signals,
        delta={"reference": 20, "increasing": {"color": "#10B981"}},
        gauge={
            "shape": "bullet",
            "axis": {"range": [0, 36]},
            "bar": {"color": "#6D28D9"},
            "threshold": {
                "line": {"color": "red", "width": 2},
                "thickness": 0.75,
                "value": 30,
            },
        },
        title={"text": f"{r.expert_signals}/36 能力可匹配专家"},
    ))
    fig_bar.update_layout(height=150, margin=dict(t=20, b=10, l=10, r=10))
    st.plotly_chart(fig_bar, use_container_width=True)
    st.caption(f"覆盖率：**{ratio:.0%}**。说明行为流能稳定捕捉 {r.expert_signals} 项能力的高产出者。")

with c2:
    st.markdown("#### 🎯 估算每 JD 可触发的赋能信号数")
    st.metric("平均每 JD 触发信号", r.trigger_signals_est)
    st.caption(
        "计算方式：抽样 3 个 JD，对每个 JD 统计"
        "所有员工 gap > 0 且 priority ≠ low 的 (员工, 能力) 对，取平均。"
    )

st.divider()


# ---------------------------------------------------------------- 导出建议

st.markdown("### 💡 基于当前数据的 L&D 行动建议")

action_items = []
if r.weak_competencies >= 20:
    action_items.append(
        f"⚠️ **{r.weak_competencies} 项能力整体薄弱**（覆盖<20%），建议本季度至少"
        "立项 3 项能力专项训练营。"
    )
if r.avg_level_gain_6mo < 0.5:
    action_items.append(
        "📉 **整体能力增长偏慢**（<0.5 级/半年），考虑加强"
        "实践性赋能（内部项目、Hackathon）的比例。"
    )
if r.expert_signals >= 25:
    action_items.append(
        f"🌟 **{r.expert_signals} 项能力已识别隐形专家**，"
        "建议在「隐形专家图」页挑选 Top 贡献者参与组织 Mentorship 计划。"
    )
if r.trigger_signals_est >= 100:
    action_items.append(
        f"🚨 **估算每 JD 可触发 {r.trigger_signals_est} 次赋能推送**，"
        "需配合推送频控策略，避免员工疲劳。"
    )
if not action_items:
    action_items.append("✅ 各项指标在健康区间，建议维持现有赋能节奏。")

for ai in action_items:
    st.markdown(f"- {ai}")
