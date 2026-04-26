"""赋能推荐页（核心）。

- 员工视角：70-20-10 四组 Tab 推荐卡 + 30/60/90 天路径
- L&D 视角：资源池规模分布 + 每类资源命中率（覆盖多少员工 Gap）
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app._view import inject_theme_css, is_ld, render_view_banner  # noqa: E402
from src.analysis.gap_analyzer import analyze_gap  # noqa: E402
from src.pathway.pathway_generator import generate as gen_pathway  # noqa: E402
from src.profile.employee_builder import build_profile as build_emp  # noqa: E402
from src.profile.job_builder import build_profile as build_job  # noqa: E402
from src.profile.ontology_loader import competency_name  # noqa: E402
from src.recommender.base import group_by_learning_mode, recommend_all  # noqa: E402


st.set_page_config(page_title="赋能推荐 / 资源池分析", page_icon="🚀", layout="wide")
inject_theme_css()

# --------------------- L&D 视角分支 ---------------------
if is_ld():
    from src.recommender.base import (
        load_cases, load_communities, load_courses, load_labs,
        load_mentors, load_projects, load_prompts, load_readings,
        load_talks, load_tools,
    )

    st.title("📚 学习资源池分析")
    st.caption("按 70-20-10 分类统计资源池规模、覆盖能力、使用潜力。")
    render_view_banner()

    # 资源池规模统计
    pools = {
        "🎯 内部项目 + Hackathon": ("experiential", load_projects()),
        "🎯 Lab 沙盒": ("experiential", load_labs()),
        "👥 导师": ("social", load_mentors()),
        "👥 案例库": ("social", load_cases()),
        "👥 Tech Talk": ("social", load_talks()),
        "👥 社群": ("social", load_communities()),
        "📚 课程（含微课）": ("formal", load_courses()),
        "📚 文档 / 书籍": ("formal", load_readings()),
        "🛠️ AI 工具": ("tool", load_tools()),
        "🛠️ Prompt / SOP": ("tool", load_prompts()),
    }

    # 按 mode 聚合总量
    mode_totals = defaultdict(int)
    for label, (mode, items) in pools.items():
        mode_totals[mode] += len(items)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🎯 实践（70%）", f"{mode_totals['experiential']} 条",
                  help="内部项目 + Hackathon + Lab")
    with c2:
        st.metric("👥 社交（20%）", f"{mode_totals['social']} 条",
                  help="导师 + 案例 + Tech Talk + 社群")
    with c3:
        st.metric("📚 系统学习（10%）", f"{mode_totals['formal']} 条",
                  help="课程 + 文档 / 书籍")
    with c4:
        st.metric("🛠️ 工具（正交）", f"{mode_totals['tool']} 条",
                  help="AI 工具 + Prompt / SOP")

    st.divider()

    c1, c2 = st.columns([3, 2])
    with c1:
        import plotly.graph_objects as go
        st.markdown("#### 📊 各类资源池规模")
        labels = list(pools.keys())
        sizes = [len(pools[l][1]) for l in labels]
        mode_color = {"experiential": "#F59E0B", "social": "#6366F1", "formal": "#1E40AF", "tool": "#10B981"}
        colors = [mode_color[pools[l][0]] for l in labels]
        fig = go.Figure(data=go.Bar(
            x=sizes, y=labels, orientation="h",
            text=[f"{s} 条" for s in sizes],
            textposition="auto", marker=dict(color=colors),
        ))
        fig.update_layout(
            height=440, margin=dict(t=10, b=20, l=20, r=20),
            xaxis_title="条目数", yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("#### 📐 70-20-10 实际分布 vs 目标")
        total = sum(mode_totals.values())
        actual = {
            "experiential": mode_totals["experiential"] / total,
            "social": mode_totals["social"] / total,
            "formal": mode_totals["formal"] / total,
            "tool": mode_totals["tool"] / total,
        }
        target = {"experiential": 0.70, "social": 0.20, "formal": 0.10, "tool": 0.0}

        for mode in ["experiential", "social", "formal", "tool"]:
            emoji = {"experiential": "🎯", "social": "👥", "formal": "📚", "tool": "🛠️"}[mode]
            t = target[mode]
            a = actual[mode]
            delta = a - t
            delta_color = "#10B981" if abs(delta) < 0.05 else "#F59E0B"
            st.markdown(
                f"<div style='margin-bottom:.7rem'>"
                f"<div style='font-size:.85rem'>{emoji} <b>{mode}</b> "
                f"<span style='color:#64748B'>目标 {t:.0%} · 实际 {a:.0%}</span>"
                f"</div>"
                f"<div style='background:#E2E8F0;height:10px;border-radius:5px;overflow:hidden'>"
                f"<div style='background:{mode_color[mode]};width:{a*100:.0f}%;height:10px'></div>"
                f"</div>"
                f"<div style='font-size:.72rem;color:{delta_color};margin-top:2px'>"
                f"差异：{delta:+.0%}"
                f"</div></div>",
                unsafe_allow_html=True,
            )
        st.caption(
            "💡 实际是资源**数量**分布（当前过度偏向 formal），不是推荐时"
            "**推送**分布（推送会主动按 70-20-10 分组展示）。"
        )

    st.stop()
# ------------------------------------------------------------

st.title("🚀 赋能推荐")
st.caption("基于 70-20-10 学习法则的七类赋能形态 + 30/60/90 天成长路径。")

emp_id = st.session_state.get("employee_id")
jd_id = st.session_state.get("jd_id")
if not emp_id or not jd_id:
    st.warning("请先从主页侧边栏选择员工与岗位。")
    st.stop()


# ---------------------------------------------------------------- 业务加载（缓存）

@st.cache_data(show_spinner=False)
def _prepare(emp_id: str, jd_id: str):
    emp = build_emp(emp_id)
    job = build_job(jd_id)
    gaps = analyze_gap(emp, job)
    recs = recommend_all(emp, gaps)
    return emp, job, gaps, recs


with st.spinner("正在合成推荐..."):
    emp, job, gaps, recs = _prepare(emp_id, jd_id)


# ---------------------------------------------------------------- 顶部筛选

gap_options = ["全部"] + [f"{g.name} ({g.priority})" for g in gaps if g.gap > 0]
selected = st.selectbox("🔎 按 Gap 筛选", gap_options, index=0)

selected_comp_id: str | None = None
if selected != "全部":
    idx = gap_options.index(selected) - 1
    real_gaps = [g for g in gaps if g.gap > 0]
    if 0 <= idx < len(real_gaps):
        selected_comp_id = real_gaps[idx].competency_id


# ---------------------------------------------------------------- 分组 + 筛选

grouped = group_by_learning_mode(recs)

def _filter(items):
    if not selected_comp_id:
        return items
    return [r for r in items if selected_comp_id in r.target_competency_ids]


# ---------------------------------------------------------------- 卡片渲染

MODE_META = {
    "experiential": {"label": "🎯 在实践中学", "ratio": "70%", "color": "#F59E0B",
                      "tag_class": "mode-experiential",
                      "subtitle": "内部项目 · Hackathon · Lab 沙盒"},
    "social":       {"label": "👥 向他人学", "ratio": "20%", "color": "#6366F1",
                      "tag_class": "mode-social",
                      "subtitle": "导师 1:1 · 过往案例 · Tech Talk · 社群"},
    "formal":       {"label": "📚 系统学习", "ratio": "10%", "color": "#1E40AF",
                      "tag_class": "mode-formal",
                      "subtitle": "课程（含微课）· 文档 / 书籍 / 论文"},
    "tool":         {"label": "🛠️ 工具直接用", "ratio": "正交", "color": "#10B981",
                      "tag_class": "mode-tool",
                      "subtitle": "AI 工具 · Prompt 模板 · 工作流 SOP"},
}

SOURCE_BADGES = {
    "project": "📂 项目",
    "lab": "🧪 Lab",
    "mentor": "🧑‍🏫 导师",
    "case": "📘 案例",
    "talk": "🎙️ 社群/分享",
    "course": "🎓 课程",
    "reading": "📖 文档",
    "tool": "🔧 工具",
    "prompt": "💬 Prompt",
}


def _card(r, mode_class: str):
    comps = "、".join(competency_name(c) for c in r.target_competency_ids[:4])
    extra_bits = []
    if r.extra.get("duration_min"):
        is_micro = r.extra.get("is_micro")
        extra_bits.append(("🎯 微课" if is_micro else "") or f"⏱ {r.extra['duration_min']}min")
    if r.extra.get("type"):
        extra_bits.append(str(r.extra["type"]))
    if r.extra.get("date"):
        extra_bits.append(str(r.extra["date"]))
    extra_text = " · ".join(b for b in extra_bits if b)

    url_link = f"<a href='{r.url}' target='_blank' style='color:#0EA5E9;text-decoration:none'>↗ 打开</a>" if r.url else ""
    rationale = f"<div style='font-size:.78rem;color:#475569;margin-top:4px'>💡 {r.rationale}</div>" if r.rationale else ""

    st.markdown(
        f"<div class='rec-card'>"
        f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
        f"<div class='rec-title'>"
        f"<span class='badge {mode_class}'>{SOURCE_BADGES.get(r.source_type, r.source_type)}</span> "
        f"{r.title}</div>"
        f"<div style='font-size:.78rem;color:#64748B'>score {r.score:.2f} {url_link}</div>"
        f"</div>"
        f"<div class='rec-meta'>🎯 覆盖能力：{comps}{' · ' + extra_text if extra_text else ''}</div>"
        f"{rationale}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- Tabs

mode_order = ["experiential", "social", "formal", "tool"]
tab_labels = [f"{MODE_META[m]['label']} ({MODE_META[m]['ratio']})" for m in mode_order]
tabs = st.tabs(tab_labels)

for tab, mode in zip(tabs, mode_order):
    meta = MODE_META[mode]
    items = _filter(grouped.get(mode, []))
    with tab:
        st.markdown(
            f"<div style='margin-bottom:.5rem;color:#64748B;font-size:.85rem'>"
            f"{meta['subtitle']} · 共 <b>{len(items)}</b> 条"
            f"</div>",
            unsafe_allow_html=True,
        )
        if not items:
            st.info("该分组暂无匹配推荐。可切换筛选或尝试其他员工/岗位组合。")
            continue
        # 按来源再分子组
        by_source: dict[str, list] = defaultdict(list)
        for r in items:
            by_source[r.source_type].append(r)
        for src, rs in by_source.items():
            st.markdown(f"**{SOURCE_BADGES.get(src, src)}**")
            for r in rs:
                _card(r, meta["tag_class"])

st.divider()

# ---------------------------------------------------------------- 成长路径

st.markdown("### 🗺️ 30 / 60 / 90 天成长路径")
st.caption("基于 Gap 与推荐池合成阶段性里程碑；每阶段至少覆盖「实践」「向他人学」「系统学习」三个学习维度之一。")

pathway = gen_pathway(emp, job, gaps, recs)

# resource_id → Recommendation 索引
rec_idx = {}
for items in recs.values():
    for r in items:
        rec_idx[r.resource_id] = r

cols = st.columns(3)
for col, m in zip(cols, pathway.milestones):
    with col:
        st.markdown(f"#### 📅 {m.phase} · {m.title}")
        st.caption(m.description)
        if m.target_competencies:
            st.markdown("**目标能力**")
            st.markdown(" ".join(f"`{competency_name(c)}`" for c in m.target_competencies))
        st.markdown("**推荐资源**")
        for rid in m.resources:
            r = rec_idx.get(rid)
            if not r:
                st.markdown(f"- `{rid}`（未在精排池中，建议重新生成）")
                continue
            url_link = f" [↗]({r.url})" if r.url else ""
            st.markdown(
                f"- <span class='badge {MODE_META[r.learning_mode]['tag_class']}'>"
                f"{SOURCE_BADGES.get(r.source_type, r.source_type)}</span> "
                f"**{r.title}**{url_link}  \n"
                f"  <span style='color:#64748B;font-size:.78rem'>score {r.score:.2f}</span>",
                unsafe_allow_html=True,
            )
