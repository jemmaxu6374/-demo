"""Streamlit 主入口（Agent 向导版）。

- 默认：渲染向导（Agent 引导流程）
- 访客可"跳过向导"进入原仪表盘模式
- 侧边栏：LLM 模式切换（Mock / 真 LLM + Key 输入）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402


st.set_page_config(
    page_title="AI 个性化赋能模型 Demo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------- 数据自举

from app._bootstrap import ensure_data_ready_cached  # noqa: E402

_boot_status = ensure_data_ready_cached()


# ---------------------------------------------------------------- 样式（向导专用 + 复用原主题）

from app._view import (  # noqa: E402
    current_view,
    inject_theme_css,
    is_employee,
    is_ld,
    render_view_banner,
    render_view_switcher,
    view_meta,
)


# ---------------------------------------------------------------- 侧边栏

st.sidebar.markdown("### 🤖 AI 个性化赋能 Demo")
st.sidebar.caption("同一套数据 · 两种视角 · 完整 AI 流程")
st.sidebar.divider()

# LLM 模式开关
st.sidebar.markdown("#### 🧠 AI 模式")
llm_mode = st.sidebar.radio(
    "选择 LLM 模式",
    ["Mock（零成本，演示用）", "真 LLM（需要 API Key）"],
    index=0,
    label_visibility="collapsed",
    key="llm_mode_radio",
)

if llm_mode.startswith("真"):
    st.session_state["use_real_llm"] = True
    llm_provider = st.sidebar.selectbox(
        "Provider",
        ["openai", "anthropic", "deepseek", "qwen"],
        key="llm_provider_sel",
    )
    api_key = st.sidebar.text_input(
        "API Key",
        type="password",
        placeholder="sk-...",
        key="api_key_input",
        help="Key 只存在当前会话，不会上传或保存",
    )
    if api_key:
        # 动态覆盖配置
        import os
        os.environ["LLM_PROVIDER"] = llm_provider
        os.environ["LLM_API_KEY"] = api_key
        # 重置 llm client 缓存以便生效
        import src.llm.client as _lc
        _lc._provider_cache = None
        st.sidebar.success(f"✅ 已切换到 {llm_provider}")
    else:
        st.sidebar.caption("⚠️ 未填 Key，当前仍走 Mock")
        st.session_state["use_real_llm"] = False
else:
    st.session_state["use_real_llm"] = False

st.sidebar.divider()


# ---------------------------------------------------------------- 主体：向导 OR 仪表盘

# 主入口策略：
# - 默认跑向导（Agent 引导流程）
# - 用户点"跳过向导" → session_state.skip_wizard = True → 走原仪表盘
# - 向导完成后也可以进仪表盘

if not st.session_state.get("skip_wizard"):
    # 向导模式：侧边栏不显示 view_mode 切换（那是仪表盘才用的）
    st.sidebar.markdown("#### 📍 当前模式")
    st.sidebar.info("🎯 **Agent 引导流程**\n\n跟着 AI 的引导完成从身份识别到个性化建议的全过程。")

    # 底部给一个返回仪表盘的链接
    if st.sidebar.button("🔀 切换到仪表盘模式", use_container_width=True):
        st.session_state["skip_wizard"] = True
        st.rerun()

    # 渲染向导
    inject_theme_css()
    from app._wizard import render_wizard
    render_wizard()

else:
    # 仪表盘模式（原 UX）
    render_view_switcher()

    from src.profile.employee_builder import list_employees
    from src.profile.job_builder import list_jds

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
        st.sidebar.caption("L&D 视角默认看全员聚合。")
        jd_label = st.sidebar.selectbox(
            "🎯 定向岗位（可选）", ["（不选）"] + list(jd_options.keys()), key="jd_label"
        )
        st.session_state["jd_id"] = (jd_options[jd_label] if jd_label != "（不选）"
                                      else list(jd_options.values())[0])
        emp_label = st.sidebar.selectbox(
            "👤 代表员工", list(emp_options.keys()), key="emp_label",
        )
        st.session_state["employee_id"] = emp_options[emp_label]

    st.sidebar.divider()
    if st.sidebar.button("🤖 返回 AI 向导", use_container_width=True):
        st.session_state["skip_wizard"] = False
        from app._wizard import reset_wizard
        reset_wizard()
        st.rerun()

    inject_theme_css()
    m = view_meta()

    st.markdown(
        f"""
<div class="demo-hero">
  <h1>{m['label']} · 仪表盘模式</h1>
  <p>{m['caption']}</p>
</div>
        """,
        unsafe_allow_html=True,
    )
    render_view_banner()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("员工", f"{len(employees)} 人")
    with col2:
        st.metric("岗位", f"{len(jds)} 份")
    with col3:
        st.metric("能力节点", "36")
    with col4:
        st.metric("行为事件（6 个月）", "9,400")

    st.markdown(
        """
#### 👉 左侧切换视角查看对应的 5 / 4 页详细分析
        """ if is_employee() else """
#### 👉 左侧切换视角查看对应的 5 / 4 页详细分析
        """
    )
