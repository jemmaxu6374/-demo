"""赋能推荐页（核心）：

- Gap 下拉筛选
- 按 70-20-10 四组 Tab 展示：🎯 在实践中学 / 👥 向他人学 / 📚 系统学习 / 🛠️ 工具直接用
- 每张卡带 learning_mode 色带、来源类型、score、命中的 competency
- 底部 30/60/90 天成长路径
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.analysis.gap_analyzer import analyze_gap  # noqa: E402
from src.pathway.pathway_generator import generate as gen_pathway  # noqa: E402
from src.profile.employee_builder import build_profile as build_emp  # noqa: E402
from src.profile.job_builder import build_profile as build_job  # noqa: E402
from src.profile.ontology_loader import competency_name  # noqa: E402
from src.recommender.base import group_by_learning_mode, recommend_all  # noqa: E402


st.set_page_config(page_title="赋能推荐", page_icon="🚀", layout="wide")
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
