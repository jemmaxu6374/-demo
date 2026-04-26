"""Streamlit 主入口。

侧边栏：
- 视角切换（👤 员工 / 🎯 L&D）
- 员工选择 + JD 选择（员工视角必填；L&D 视角可选，用于 Gap 聚合定向）
- 数据自举状态

顶部内容随视角切换：
- 员工视角：导航指引到 Phase 1-3 的五页
- L&D 视角：导航指引到四页 L&D 分析面板
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402


st.set_page_config(
    page_title="员工赋能 Demo · 双视角版",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------- 数据自举

from app._bootstrap import ensure_data_ready_cached  # noqa: E402

_boot_status = ensure_data_ready_cached()


# ---------------------------------------------------------------- 视角与样式

from app._view import (  # noqa: E402
    current_view,
    inject_theme_css,
    is_employee,
    is_ld,
    render_view_banner,
    render_view_switcher,
    view_meta,
)

from src.profile.employee_builder import list_employees  # noqa: E402
from src.profile.job_builder import list_jds  # noqa: E402

# Sidebar: 视角切换
render_view_switcher()

# Sidebar: 员工 / JD 选择（两视角都要，但 L&D 用于聚焦某 JD 的 gap 聚合）
st.sidebar.markdown("### 🎯 聚焦目标")

employees = list_employees()
jds = list_jds()

emp_options = {f"{e['name']} · {e['current_role']}": e["employee_id"] for e in employees}
jd_options = {f"{j['title']}（{j.get('level', '')}）": j["jd_id"] for j in jds}

if is_employee():
    emp_label = st.sidebar.selectbox("👤 当前员工", list(emp_options.keys()), key="emp_label")
    jd_label = st.sidebar.selectbox("🎯 目标岗位", list(jd_options.keys()), key="jd_label")
    st.session_state["employee_id"] = emp_options[emp_label]
    st.session_state["jd_id"] = jd_options[jd_label]
else:
    st.sidebar.caption("L&D 视角默认看全员聚合。下方可选一个岗位，用于 Gap 聚合定向分析。")
    jd_label = st.sidebar.selectbox(
        "🎯 定向岗位（可选）", ["（不选）"] + list(jd_options.keys()), key="jd_label"
    )
    if jd_label != "（不选）":
        st.session_state["jd_id"] = jd_options[jd_label]
    else:
        st.session_state["jd_id"] = list(jd_options.values())[0]  # 默认第一个，避免页面空

    # 员工选择在 L&D 视角下变成 "代表性员工"，用于现有 5 页展示
    emp_label = st.sidebar.selectbox(
        "👤 代表员工（用于员工视角的 5 页展示）",
        list(emp_options.keys()),
        key="emp_label",
    )
    st.session_state["employee_id"] = emp_options[emp_label]

st.sidebar.divider()

# Sidebar: 使用指南（随视角变化）
if is_employee():
    st.sidebar.markdown("#### 📖 员工视角路径")
    st.sidebar.caption("1️⃣ 员工画像 → 2️⃣ 岗位目标 → 3️⃣ 差距分析 → 4️⃣ 赋能推荐 → 5️⃣ 动态双视图")
else:
    st.sidebar.markdown("#### 📖 L&D 视角路径")
    st.sidebar.caption("🔥 组织能力热力图 · 🌟 隐形专家 · 🎯 岗位匹配矩阵 · 📊 赋能 ROI")

st.sidebar.divider()
st.sidebar.caption("70-20-10 学习法则：70% 实践 · 20% 向他人学 · 10% 系统学习 · 工具正交使能")


# ---------------------------------------------------------------- 主体

inject_theme_css()

m = view_meta()

# Hero
st.markdown(
    f"""
<div class="demo-hero">
  <h1>{m['label']} · 实时精准个性化赋能 Demo</h1>
  <p>{m['caption']}</p>
  <p style="margin-top:.4rem;font-size:.8rem;opacity:.85">
    💡 同一套数据，两种视角：**员工** 看自己成长路径，**L&D** 看组织能力分布
  </p>
</div>
    """,
    unsafe_allow_html=True,
)

render_view_banner()

# 快览卡（两视角共享）
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("员工", f"{len(employees)} 人")
with col2:
    st.metric("岗位", f"{len(jds)} 份")
with col3:
    st.metric("能力节点", "36")
with col4:
    st.metric("行为事件（6 个月）", "9,400")


# 导航指引（随视角变化）
if is_employee():
    st.markdown(
        """
#### 👉 员工视角 · 五页路径

| 页面 | 核心问题 | 核心交互 |
| --- | --- | --- |
| **1️⃣ 员工画像** | 我有什么？ | 雷达 + 标签云 + 证据溯源 |
| **2️⃣ 岗位目标** | 岗位要什么？ | JD 结构化能力清单 + 权重 |
| **3️⃣ 差距分析** | 我差什么？ | 双雷达对比 + Gap 优先级 |
| **4️⃣ 赋能推荐** | 我该学什么？ | 70-20-10 四组 Tab + 七类资源 |
| **5️⃣ 动态双视图** | 我怎么变的？ | 时间轴回溯 + 画像演化 + 推送卡 |
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
#### 👉 L&D 视角 · 四页路径

| 页面 | 核心问题 | 核心交互 |
| --- | --- | --- |
| **🔥 组织能力热力图** | 组织强在哪？弱在哪？ | 20×36 热力图 + 覆盖度排行 |
| **🌟 隐形专家图** | 每项能力谁最强？ | 基于时间线的 Top-K 高产出识别 |
| **🎯 岗位匹配矩阵** | 谁最适合哪个岗位？ | 20×10 匹配度热力 + 岗位人才池 |
| **📊 赋能 ROI 仪表** | 系统运转得怎样？ | 事件数、Level 涨幅、触发信号估算 |

> 💡 原员工视角的 5 页仍可访问（作为"抽一个员工代表看"的子视图）。L&D 进入每页会看到**聚合**而非**单员工**数据。
        """,
        unsafe_allow_html=True,
    )
