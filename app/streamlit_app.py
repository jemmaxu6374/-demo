"""Streamlit 主入口。

侧边栏：
- Phase 选择（Phase 1 / Phase 3 预留）
- 员工选择 + JD 选择（全局 session_state，供四页共享）
- 匹配度显示（实时）

Phase 1 四页通过 `app/pages/` 多页路由自动加载（Streamlit 原生多页）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.profile.employee_builder import list_employees  # noqa: E402
from src.profile.job_builder import list_jds  # noqa: E402


st.set_page_config(
    page_title="员工实时精准个性化赋能 Demo",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------- 数据自举

from app._bootstrap import ensure_data_ready_cached  # noqa: E402

_boot_status = ensure_data_ready_cached()


# ---------------------------------------------------------------- 全局样式

st.markdown(
    """
<style>
  .main .block-container { padding-top: 1.5rem; }
  .demo-hero { padding: 1.5rem 2rem; border-radius: 16px;
               background: linear-gradient(135deg, #1E40AF 0%, #0EA5E9 60%, #14B8A6 100%);
               color: white; margin-bottom: 1rem; }
  .demo-hero h1 { color: white; margin: 0 0 .25rem 0; font-size: 1.8rem; }
  .demo-hero p { color: #E0F2FE; margin: 0; font-size: .95rem; }
  .metric-card { padding: 1rem 1.2rem; background: #F8FAFC; border-left: 4px solid #1E40AF;
                 border-radius: 8px; margin-bottom: .6rem; }
  .badge { display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px;
           font-weight: 600; margin-right: 6px; }
  .badge-high { background:#FEE2E2; color:#B91C1C; }
  .badge-mid  { background:#FEF3C7; color:#B45309; }
  .badge-low  { background:#D1FAE5; color:#047857; }
  .mode-experiential { background:#FEF3C7; color:#92400E; }
  .mode-social { background:#E0E7FF; color:#3730A3; }
  .mode-formal { background:#DBEAFE; color:#1E40AF; }
  .mode-tool { background:#D1FAE5; color:#065F46; }
  .rec-card { padding: .85rem 1rem; background:white; border:1px solid #E2E8F0;
              border-radius: 10px; margin-bottom: .55rem; }
  .rec-card:hover { border-color:#0EA5E9; box-shadow: 0 2px 6px rgba(14,165,233,0.08); }
  .rec-title { font-weight:600; color:#0F172A; font-size: .95rem; margin-bottom:3px; }
  .rec-meta { font-size: .78rem; color:#64748B; }
</style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- Sidebar

st.sidebar.markdown("### 🧭 员工赋能 Demo")
st.sidebar.caption("Phase 1：静态基线 MVP")

employees = list_employees()
jds = list_jds()

emp_options = {f"{e['name']} · {e['current_role']}": e["employee_id"] for e in employees}
jd_options = {f"{j['title']}（{j.get('level', '')}）": j["jd_id"] for j in jds}

emp_label = st.sidebar.selectbox("👤 当前员工", list(emp_options.keys()), key="emp_label")
jd_label = st.sidebar.selectbox("🎯 目标岗位", list(jd_options.keys()), key="jd_label")

st.session_state["employee_id"] = emp_options[emp_label]
st.session_state["jd_id"] = jd_options[jd_label]

st.sidebar.divider()
st.sidebar.markdown("#### 📖 使用指南")
st.sidebar.caption(
    "左侧选择「员工 + 岗位」→ 切换顶部页面：员工画像 / 岗位目标 / 差距分析 / 赋能推荐"
)
st.sidebar.divider()
st.sidebar.caption(
    "70-20-10 学习法则：70% 实践 · 20% 向他人学 · 10% 系统学习 · 工具正交使能"
)


# ---------------------------------------------------------------- 首页 Hero

st.markdown(
    """
<div class="demo-hero">
  <h1>员工实时精准个性化赋能 · 在线 Demo</h1>
  <p>"能力本体 + 三画像对齐" 的 Phase 1 静态基线 + 动态画像 Phase 2 + 双视图 Phase 3，按 <b>70-20-10 学习法则</b>
  为员工合成七类赋能路径。请从左侧选择员工与目标岗位，再切换顶部页面查看。</p>
  <p style="margin-top:.5rem;font-size:.8rem;opacity:.85">
    💡 本 Demo 使用 Mock LLM + 模拟行为流，零 API Key，访客无限制使用
  </p>
</div>
    """,
    unsafe_allow_html=True,
)

# 调试状态（仅 Dev 模式显示）
if st.query_params.get("debug") == "1":
    st.caption(f"🛠 bootstrap: `{_boot_status}`")


# ---------------------------------------------------------------- 快览卡

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("已加载员工", f"{len(employees)} 人")
with col2:
    st.metric("岗位样本", f"{len(jds)} 份")
with col3:
    st.metric("能力节点", "36")
with col4:
    st.metric("资源池", "155 条 / 10 类")

st.markdown(
    """
#### 👉 五页导览

| 页面 | Phase | 核心交互 |
| --- | --- | --- |
| **1️⃣ 员工画像** | P1 | 简历 + 项目 + 自评 → 雷达 + 标签云 + 证据溯源 |
| **2️⃣ 岗位目标** | P1 | JD 结构化能力清单 + 权重可视化 |
| **3️⃣ 差距分析** | P1 | 员工 vs 岗位双雷达 + Gap 优先级卡片 |
| **4️⃣ 赋能推荐** | P1 | **70-20-10 四组 Tab** + 30/60/90 天路径 |
| **5️⃣ 动态赋能双视图** | P2/P3 | 时间轴滑块 + 行为流 + 画像演化 + 推送卡片 ⭐ |

---

> 💡 **使用提示**：
> - 左侧先选「员工 + 目标岗位」，再从顶部切换页面
> - 推荐从 **1→2→3→4→5** 顺序浏览，体验完整"从静态到动态"的叙事
> - 第 5 页的时间轴可拖动，回溯 6 个月能力演化
    """,
    unsafe_allow_html=True,
)
