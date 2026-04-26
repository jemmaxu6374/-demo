"""Agent 向导 UI 模块。

管理一个 4 阶段的状态机：
  0. 选身份
  1. 选员工（仅员工路径）/ 选关注维度（仅管理员路径）
  2. 选目标岗位（仅员工路径）
  3. AI 执行（动画 + 结果）

状态存在 st.session_state.wizard_state。
每次渲染根据 state 决定显示哪个阶段的 UI。
"""
from __future__ import annotations

import time
from pathlib import Path

import streamlit as st


def _init_state():
    ss = st.session_state
    if "wizard_state" not in ss:
        ss.wizard_state = {
            "step": 0,              # 当前阶段 0-3
            "persona": None,        # "employee" / "admin"
            "employee_id": None,    # 员工路径
            "jd_id": None,          # 员工路径
            "focus_mode": None,     # 管理员路径的关注维度
            "plan_run_done": False, # AI 是否已跑完
        }


def reset_wizard():
    """重置向导到第 0 步。"""
    st.session_state.wizard_state = {
        "step": 0, "persona": None,
        "employee_id": None, "jd_id": None,
        "focus_mode": None, "plan_run_done": False,
    }


def _goto(step: int):
    st.session_state.wizard_state["step"] = step
    st.rerun()


# ---------------------------------------------------------------- Step 0: 选身份

def _render_step_persona():
    st.markdown(
        """
<div style="text-align:center;padding:2rem 1rem 1rem;">
  <h2 style="margin:0 0 .5rem;color:#0F172A;">欢迎来到 AI 个性化赋能模型 Demo</h2>
  <p style="color:#64748B;font-size:1rem;margin:0">
    先告诉我你的身份，我会为你定制一条完整的赋能故事线 🎯
  </p>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(
            """
<div style="border:1px solid #E2E8F0;border-radius:16px;padding:1.5rem;text-align:center;height:220px">
  <div style="font-size:3rem">👤</div>
  <h3 style="margin:.3rem 0">员工视角</h3>
  <p style="color:#64748B;font-size:.9rem">
    代入一位员工，看 AI 如何分析你的画像、识别 Gap、生成个性化成长路径
  </p>
</div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("以员工身份继续 →", key="btn_employee", use_container_width=True, type="primary"):
            st.session_state.wizard_state["persona"] = "employee"
            _goto(1)

    with c2:
        st.markdown(
            """
<div style="border:1px solid #E2E8F0;border-radius:16px;padding:1.5rem;text-align:center;height:220px">
  <div style="font-size:3rem">🎯</div>
  <h3 style="margin:.3rem 0">管理员 / L&D 视角</h3>
  <p style="color:#64748B;font-size:.9rem">
    看 AI 如何汇总组织能力分布、识别集体缺口与隐形专家、给出季度投入建议
  </p>
</div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("以管理员身份继续 →", key="btn_admin", use_container_width=True, type="primary"):
            st.session_state.wizard_state["persona"] = "admin"
            _goto(1)

    # 底部提示 + 跳过链接
    st.divider()
    c_l, c_r = st.columns([3, 1])
    with c_l:
        st.caption("💡 Demo 使用模拟数据（20 员工 × 6 个月行为流 × 9400 事件），"
                   "AI 会真实地跑画像抽取、Gap 分析、七路推荐、成长路径合成全链路。")
    with c_r:
        if st.button("直接进入仪表盘 →", key="btn_skip_wizard"):
            st.session_state["skip_wizard"] = True
            st.rerun()


# ---------------------------------------------------------------- Step 1: 选员工 / 选维度

EMPLOYEE_GROUPS = [
    ("🌱 新人（0-1 年）", ["emp_008", "emp_013"]),
    ("🛠️ 中坚（2-3 年）", ["emp_001", "emp_002", "emp_004", "emp_005", "emp_007", "emp_009", "emp_015", "emp_020"]),
    ("⚙️ 资深（3-5 年）", ["emp_003", "emp_010", "emp_011", "emp_012", "emp_014", "emp_016", "emp_017", "emp_019"]),
    ("🏆 Lead（5 年+）", ["emp_006", "emp_018"]),
]


def _render_step_employee_select():
    from src.profile.employee_builder import list_employees
    emps = {e["employee_id"]: e for e in list_employees()}

    st.markdown(
        """
<h2 style="margin:.5rem 0">Step 1 · 选一位员工代入体验</h2>
<p style="color:#64748B;font-size:.92rem;margin-bottom:1rem">
  这一步决定你在后续看到的所有数据都是基于哪位员工的画像。选完后 AI 会把你带入这位员工的视角。
</p>
        """,
        unsafe_allow_html=True,
    )

    # 分组渲染员工卡片
    for group_label, emp_ids in EMPLOYEE_GROUPS:
        st.markdown(f"#### {group_label}")
        cols = st.columns(4)
        for i, eid in enumerate(emp_ids):
            if eid not in emps:
                continue
            e = emps[eid]
            with cols[i % 4]:
                # 用 button 包成卡片（Streamlit button 不能自由 html，用 container 模拟）
                container = st.container(border=True)
                with container:
                    st.markdown(f"**{e['name']}**")
                    st.caption(f"{e['current_role']}")
                    st.caption(f"📍 {e['department']}")
                    if st.button(
                        "选 TA →", key=f"pick_{eid}", use_container_width=True,
                    ):
                        st.session_state.wizard_state["employee_id"] = eid
                        _goto(2)

    st.divider()
    if st.button("← 返回", key="btn_back_to_persona"):
        _goto(0)


# ---------------------------------------------------------------- Step 1 (admin): 选维度

def _render_step_admin_focus():
    from src.profile.job_builder import list_jds

    st.markdown(
        """
<h2 style="margin:.5rem 0">Step 1 · 选择你想关注的组织维度</h2>
<p style="color:#64748B;font-size:.92rem;margin-bottom:1rem">
  AI 会基于你选择的关注点，跑一轮组织能力体检并生成季度投入建议。
</p>
        """,
        unsafe_allow_html=True,
    )

    jds = list_jds()
    jd_opts = ["（不定向，看整体）"] + [f"{j['title']}（{j.get('level','')}）" for j in jds]
    jd_map = dict(zip(jd_opts[1:], [j["jd_id"] for j in jds]))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🎯 定向关注岗位（可选）")
        jd_label = st.selectbox(
            "AI 会聚合全员对此岗位的集体 Gap", jd_opts, key="admin_jd_select"
        )
        focus_jd = jd_map.get(jd_label)
    with c2:
        st.markdown("#### 🗂️ 能力分类侧重（可选）")
        cat = st.selectbox(
            "AI 会着重看这个分类下的强弱与专家分布",
            ["（不偏重）", "硬技能", "软技能", "领域知识", "工具熟练度"],
            key="admin_cat_select",
        )
    st.divider()
    col_l, col_r = st.columns([1, 3])
    with col_l:
        if st.button("← 返回", key="btn_back_admin"):
            _goto(0)
    with col_r:
        if st.button("开始 AI 组织体检 🚀", key="btn_start_admin",
                     type="primary", use_container_width=True):
            st.session_state.view_mode = "ld"
            st.session_state.wizard_state["jd_id"] = focus_jd
            st.session_state.wizard_state["focus_mode"] = (
                None if cat.startswith("（不") else cat
            )
            _goto(3)  # admin 跳过 step 2


# ---------------------------------------------------------------- Step 2: 选目标岗位（员工）

def _render_step_jd_select():
    from src.profile.employee_builder import get_employee_raw
    from src.profile.job_builder import list_jds

    ws = st.session_state.wizard_state
    emp = get_employee_raw(ws["employee_id"])

    st.markdown(
        f"""
<h2 style="margin:.5rem 0">Step 2 · 选一个目标岗位</h2>
<p style="color:#64748B;font-size:.92rem;margin-bottom:1rem">
  已选员工：<b>{emp['name']}</b>（{emp['current_role']}）· AI 接下来会对比这个员工与目标岗位的能力差距。
</p>
        """,
        unsafe_allow_html=True,
    )

    jds = list_jds()
    # 用卡片展示，3 列
    for i in range(0, len(jds), 3):
        cols = st.columns(3)
        for j, jd in enumerate(jds[i:i + 3]):
            with cols[j]:
                container = st.container(border=True)
                with container:
                    st.markdown(f"**{jd['title']}**")
                    st.caption(f"{jd.get('level', '')} · {jd.get('department', '')}")
                    desc = jd.get("description", "")[:60]
                    st.caption(desc + ("..." if len(jd.get("description", "")) > 60 else ""))
                    if st.button("选此岗位 →", key=f"pick_jd_{jd['jd_id']}",
                                 use_container_width=True):
                        st.session_state.wizard_state["jd_id"] = jd["jd_id"]
                        _goto(3)

    st.divider()
    if st.button("← 返回选择员工", key="btn_back_to_emp"):
        _goto(1)


# ---------------------------------------------------------------- Step 3: AI 执行

def _render_step_agent_run():
    from src.agent.agent_runner import AgentRunner, build_admin_plan, build_employee_plan

    ws = st.session_state.wizard_state

    # 1) 构建 Plan
    if ws["persona"] == "employee":
        from src.profile.employee_builder import get_employee_raw
        from src.profile.job_builder import get_jd_raw
        emp = get_employee_raw(ws["employee_id"])
        jd = get_jd_raw(ws["jd_id"])
        st.markdown(
            f"""
<h2 style="margin:.5rem 0">Step 3 · AI 正在为你分析</h2>
<p style="color:#64748B;font-size:.92rem;margin-bottom:1.5rem">
  员工：<b>{emp['name']}</b> · 目标岗位：<b>{jd['title']}</b>
</p>
            """,
            unsafe_allow_html=True,
        )
        plan = build_employee_plan(ws["employee_id"], ws["jd_id"])
    else:
        focus_txt = ws["focus_mode"] or "整体"
        jd_txt = ws.get("jd_id") or "（不定向）"
        st.markdown(
            f"""
<h2 style="margin:.5rem 0">Step 3 · AI 正在为你做组织体检</h2>
<p style="color:#64748B;font-size:.92rem;margin-bottom:1.5rem">
  定向岗位：<b>{jd_txt}</b> · 关注维度：<b>{focus_txt}</b>
</p>
            """,
            unsafe_allow_html=True,
        )
        plan = build_admin_plan(focus_jd_id=ws.get("jd_id"), focus_category=ws.get("focus_mode"))

    # 2) 如果已经跑过，直接渲染结果
    if ws.get("plan_run_done") and "cached_plan" in ws:
        _render_completed_plan(ws["cached_plan"])
        return

    # 3) 首次跑 Plan：用 st.status 展示分步动画
    runner = AgentRunner(plan, use_real_llm=st.session_state.get("use_real_llm", False))

    # 每个 step 对应一个 status 容器
    status_containers = {s.id: st.empty() for s in plan.steps}

    # 执行：每个 step 在 runner 里会 yield 两次（running → done）
    for step in runner.run():
        with status_containers[step.id].container():
            _render_step_card(step)
        # 给用户看动画的呼吸感
        if step.status == "running":
            time.sleep(0.15)
        else:
            time.sleep(0.25)

    # 执行完成
    ws["plan_run_done"] = True
    ws["cached_plan"] = plan
    st.rerun()


def _render_step_card(step):
    """单个 step 的卡片渲染。"""
    from src.agent.agent_runner import AgentStep

    status_emoji = {
        "pending": "⏳",
        "running": "⚙️",
        "done": "✅",
        "failed": "❌",
    }.get(step.status, "•")

    color = {
        "pending": "#94A3B8",
        "running": "#F59E0B",
        "done": "#10B981",
        "failed": "#EF4444",
    }.get(step.status, "#64748B")

    duration = f" · {step.duration_ms}ms" if step.status == "done" else ""

    with st.container():
        st.markdown(
            f"""
<div style="border-left:3px solid {color};padding:.6rem .9rem;margin:.3rem 0;
            background:linear-gradient(90deg,{color}12,transparent);border-radius:0 6px 6px 0">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <span style="font-weight:500;color:#0F172A">{status_emoji} {step.label}</span>
    <span style="font-size:.75rem;color:#64748B">{duration}</span>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
        if step.status == "done" and step.trace:
            with st.expander("🔎 查看 AI 的工作痕迹"):
                st.caption(step.description)
                st.json(step.trace, expanded=True)
        elif step.status == "failed":
            st.error(step.error)


def _render_completed_plan(plan):
    """所有 step 跑完后，展示最终结果 + 入口。"""
    # 上半部分：所有 step 卡片（折叠成小 summary）
    with st.expander("📋 AI 推理全过程（6 步）", expanded=False):
        for step in plan.steps:
            _render_step_card(step)

    st.divider()

    # 核心：AI 的自然语言总结
    narrative = plan.steps[-1].output or "（AI 未生成建议）"
    bg_color = "#EEF2FF" if plan.name == "admin_org_checkup" else "#FEF3C7"
    border_color = "#6366F1" if plan.name == "admin_org_checkup" else "#F59E0B"

    st.markdown(
        f"""
<div style="background:{bg_color};border-left:4px solid {border_color};
            padding:1.2rem 1.5rem;border-radius:0 12px 12px 0;margin:1rem 0">
  <h3 style="margin:0 0 .8rem;color:#0F172A">🤖 AI 的综合建议</h3>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(narrative)
    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # 跳转入口
    st.markdown("### 🔍 想看得更深？AI 已经为你准备好了详细分析")

    if plan.name == "employee_growth":
        cols = st.columns(5)
        deep_pages = [
            ("👤 员工画像", "1_员工画像"),
            ("🎯 岗位目标", "2_岗位目标"),
            ("📊 差距分析", "3_差距分析"),
            ("🚀 赋能推荐", "4_赋能推荐"),
            ("🕒 动态双视图", "5_动态赋能双视图"),
        ]
    else:
        cols = st.columns(4)
        deep_pages = [
            ("🔥 组织能力热力图", "6_组织能力热力图"),
            ("🌟 隐形专家图", "7_隐形专家图"),
            ("🎯 岗位匹配矩阵", "8_岗位匹配矩阵"),
            ("📊 赋能 ROI 仪表", "9_赋能ROI仪表"),
        ]

    # 为 admin 路径的跳转链接附上 view=ld query 参数
    link_view = "?view=ld" if plan.name == "admin_org_checkup" else ""

    for i, (label, page) in enumerate(deep_pages):
        with cols[i]:
            page_url = f"pages/{page}.py{link_view}"
            try:
                st.page_link(page_url, label=label, use_container_width=True)
            except Exception:
                if st.button(label, key=f"jump_{page}", use_container_width=True):
                    st.info(f"请从左侧菜单点击 **{label}** 进入")

    st.divider()
    col_l, col_r = st.columns([1, 1])
    with col_l:
        if st.button("🔄 重新开始（换身份或换员工）", use_container_width=True):
            reset_wizard()
            st.rerun()
    with col_r:
        if st.button("🚪 跳过向导，直接进仪表盘", use_container_width=True):
            st.session_state["skip_wizard"] = True
            st.rerun()


# ---------------------------------------------------------------- 主入口

def render_wizard():
    """向导总入口。根据 session_state.wizard_state.step 渲染不同阶段。"""
    _init_state()
    ws = st.session_state.wizard_state

    step = ws["step"]
    persona = ws.get("persona")

    if step == 0:
        _render_step_persona()
    elif step == 1 and persona == "employee":
        _render_step_employee_select()
    elif step == 1 and persona == "admin":
        _render_step_admin_focus()
    elif step == 2 and persona == "employee":
        _render_step_jd_select()
    elif step == 3:
        _render_step_agent_run()
    else:
        # 异常兜底
        reset_wizard()
        _render_step_persona()
