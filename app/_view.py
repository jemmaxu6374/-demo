"""视角管理器：员工视角 / L&D 全局视角切换。

- 侧边栏 radio 控件
- session_state 持久化
- 双主题 CSS（员工=蓝，L&D=紫）
- 提供 current_view() / is_ld() / is_employee() 等便捷函数
"""
from __future__ import annotations

from typing import Literal

import streamlit as st


ViewMode = Literal["employee", "ld"]

VIEW_META = {
    "employee": {
        "label": "👤 员工视角",
        "caption": "我看自己的成长：画像 → Gap → 推荐 → 路径",
        "primary": "#1E40AF",
        "secondary": "#0EA5E9",
        "accent": "#14B8A6",
    },
    "ld": {
        "label": "🎯 L&D 全局视角",
        "caption": "我看组织的能力：热力图 → 缺口 → 专家 → ROI",
        "primary": "#6D28D9",
        "secondary": "#A855F7",
        "accent": "#EC4899",
    },
}


def current_view() -> ViewMode:
    return st.session_state.get("view_mode", "employee")


def is_ld() -> bool:
    return current_view() == "ld"


def is_employee() -> bool:
    return current_view() == "employee"


def view_meta(mode: ViewMode | None = None) -> dict:
    return VIEW_META[mode or current_view()]


def render_view_switcher(in_sidebar: bool = True):
    """在侧边栏渲染视角切换 radio。调用后会写入 session_state。"""
    container = st.sidebar if in_sidebar else st
    container.markdown("### 🔀 视角切换")
    choice = container.radio(
        "选择视角",
        options=["employee", "ld"],
        format_func=lambda v: VIEW_META[v]["label"],
        index=0 if current_view() == "employee" else 1,
        key="_view_switcher",
        label_visibility="collapsed",
    )
    st.session_state["view_mode"] = choice
    container.caption(VIEW_META[choice]["caption"])
    container.divider()


def inject_theme_css():
    """根据当前视角注入主题色变量 + 通用组件样式。

    放在每页顶部（set_page_config 之后）调用。
    """
    m = view_meta()
    st.markdown(
        f"""
<style>
  :root {{
    --brand-primary: {m['primary']};
    --brand-secondary: {m['secondary']};
    --brand-accent: {m['accent']};
  }}
  .main .block-container {{ padding-top: 1.5rem; }}

  /* Hero 自适应主题色 */
  .demo-hero {{
    padding: 1.5rem 2rem; border-radius: 16px;
    background: linear-gradient(135deg,
                  {m['primary']} 0%,
                  {m['secondary']} 60%,
                  {m['accent']} 100%);
    color: white; margin-bottom: 1rem;
  }}
  .demo-hero h1 {{ color: white; margin: 0 0 .25rem 0; font-size: 1.7rem; }}
  .demo-hero p {{ color: #F8FAFC; margin: 0; font-size: .95rem; opacity: .95; }}

  /* 通用 metric-card */
  .metric-card {{
    padding: 1rem 1.2rem; background: #F8FAFC;
    border-left: 4px solid {m['primary']}; border-radius: 8px;
    margin-bottom: .6rem;
  }}

  /* 通用 badges（两种视角共享） */
  .badge {{
    display:inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 600; margin-right: 6px;
  }}
  .badge-high {{ background:#FEE2E2; color:#B91C1C; }}
  .badge-mid  {{ background:#FEF3C7; color:#B45309; }}
  .badge-low  {{ background:#D1FAE5; color:#047857; }}

  .mode-experiential {{ background:#FEF3C7; color:#92400E; }}
  .mode-social       {{ background:#E0E7FF; color:#3730A3; }}
  .mode-formal       {{ background:#DBEAFE; color:#1E40AF; }}
  .mode-tool         {{ background:#D1FAE5; color:#065F46; }}

  .rec-card {{
    padding: .85rem 1rem; background:white; border:1px solid #E2E8F0;
    border-radius: 10px; margin-bottom: .55rem; transition: all .15s;
  }}
  .rec-card:hover {{
    border-color: {m['secondary']};
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
  }}
  .rec-title {{ font-weight:600; color:#0F172A; font-size: .95rem; margin-bottom:3px; }}
  .rec-meta  {{ font-size: .78rem; color:#64748B; }}

  /* L&D 视角专属提示条 */
  .ld-context-bar {{
    background: linear-gradient(90deg, {m['primary']}15, {m['secondary']}15);
    border-left: 3px solid {m['primary']};
    padding: .5rem .8rem; border-radius: 0 6px 6px 0;
    font-size: .85rem; color: #374151; margin-bottom: 1rem;
  }}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_view_banner():
    """在每页顶部根据 view_mode 显示 banner。

    员工视角：不显示（避免信息噪音）
    L&D 视角：显示聚合范围提示
    """
    if is_ld():
        st.markdown(
            "<div class='ld-context-bar'>"
            "🎯 <b>L&D 全局视角</b> · 当前数据来自 20 位员工 × 6 个月行为流的聚合分析，"
            "默认只读模式（L&D 看组织，不修改员工画像）"
            "</div>",
            unsafe_allow_html=True,
        )
