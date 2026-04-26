"""Agent 编排器：把 Demo 的业务函数串成"AI 教练"的推理链。

核心概念：
- AgentStep：一个推理步骤，有 label（给用户看的标题）、tool（调用的业务函数）、
  input（输入参数）、output（执行结果）、trace（给 UI 展示的"推理痕迹"）
- AgentPlan：一系列 step 的有序集合
- AgentRunner：执行 plan，每执行完一个 step 就 yield 一次，便于 UI 做分步动画

为什么要这样做：
- 现有 Demo 里 AI 的"工作"散落在 9 页各处。Agent 把它们串成一个叙事
- 每 step 的 trace 可以展开看"AI 干了什么"（Prompt / 工具调用 / 输出），这是"突出 AI"的关键
- 两条 Plan：EmployeePlan（员工路径）+ AdminPlan（管理员路径）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------- 数据结构

StepStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class AgentStep:
    """单个推理步骤。"""
    id: str
    label: str                      # 给用户看的一句话（"🔍 读取你的简历和项目经历"）
    tool_name: str                  # 调用的工具名（"build_employee_profile"）
    description: str = ""           # 展开时的说明文本
    input: dict = field(default_factory=dict)
    output: Any = None
    status: StepStatus = "pending"
    trace: dict = field(default_factory=dict)  # {"prompt": "...", "llm_output": "...", "tokens": 123}
    error: str = ""
    duration_ms: int = 0


@dataclass
class AgentPlan:
    """一条完整的 Agent 推理链。"""
    name: str
    persona: str                    # "员工 · 李明" / "L&D · 全局"
    context: dict                   # {"employee_id": "emp_001", "jd_id": "jd_002"} 等
    steps: list[AgentStep]
    final_narrative: str = ""       # AI 最终给用户的综合建议（最后一步的输出）


# ---------------------------------------------------------------- Plan 工厂

def build_employee_plan(employee_id: str, jd_id: str) -> AgentPlan:
    """员工路径的 plan：从画像到推荐到成长路径。"""
    return AgentPlan(
        name="employee_growth",
        persona=f"员工 · {employee_id}",
        context={"employee_id": employee_id, "jd_id": jd_id},
        steps=[
            AgentStep(
                id="profile",
                label="🔍 读取你的简历与项目经历，抽取能力标签",
                tool_name="build_employee_profile",
                description="基于 base_competencies 与 LLM 文本抽取，合成结构化能力画像",
                input={"employee_id": employee_id},
            ),
            AgentStep(
                id="job",
                label="🎯 对标目标岗位的能力要求",
                tool_name="build_job_profile",
                description="从 JD 结构化清单提取 required_competencies + 权重归一化",
                input={"jd_id": jd_id},
            ),
            AgentStep(
                id="gap",
                label="📊 识别你与目标岗位之间的关键能力 Gap",
                tool_name="analyze_gap",
                description="结构化差值 + 启发式优先级 + (可选) LLM rationale",
                input={"employee_id": employee_id, "jd_id": jd_id},
            ),
            AgentStep(
                id="recommend",
                label="🎁 为你挑选最匹配的七类赋能资源（70-20-10 分组）",
                tool_name="recommend_all",
                description="按 gap 召回 + LLM 精排 + learning_mode 约束",
                input={"employee_id": employee_id, "jd_id": jd_id},
            ),
            AgentStep(
                id="pathway",
                label="🗺️ 合成 30/60/90 天成长路径",
                tool_name="generate_pathway",
                description="基于 Gap + 推荐池，每阶段至少覆盖 experiential/social/formal 一种",
                input={"employee_id": employee_id, "jd_id": jd_id},
            ),
            AgentStep(
                id="narrative",
                label="📝 给你的个性化成长建议",
                tool_name="llm_summary",
                description="调用 LLM 综合前面所有结果，生成自然语言建议",
                input={"employee_id": employee_id, "jd_id": jd_id},
            ),
        ],
    )


def build_admin_plan(focus_jd_id: str | None = None, focus_category: str | None = None) -> AgentPlan:
    """管理员路径的 plan：从组织画像到缺口到专家到投资建议。"""
    ctx = {"focus_jd_id": focus_jd_id, "focus_category": focus_category}
    return AgentPlan(
        name="admin_org_checkup",
        persona="L&D · 全局",
        context=ctx,
        steps=[
            AgentStep(
                id="matrix",
                label="📊 汇总 20 位员工 × 36 项能力的组织画像",
                tool_name="build_competency_matrix",
                description="读取全员静态画像，聚合成 employee×competency 矩阵",
                input={},
            ),
            AgentStep(
                id="gap_agg",
                label=f"⚠️ 针对岗位聚合 Gap，找出组织集体缺口",
                tool_name="aggregate_gaps_for_job",
                description="为定向岗位计算所有员工的 Gap，输出 Top 薄弱能力",
                input={"jd_id": focus_jd_id or "jd_002"},
            ),
            AgentStep(
                id="expert",
                label="🌟 识别各能力维度的隐形专家",
                tool_name="build_expert_map",
                description="基于 competency_timeline 近 30 天累积 delta，找出 Top 贡献者",
                input={},
            ),
            AgentStep(
                id="match_matrix",
                label="🎯 计算组织的岗位匹配矩阵",
                tool_name="build_job_match_matrix",
                description="所有员工 × 所有 JD 的匹配度，识别人才与岗位的错配",
                input={},
            ),
            AgentStep(
                id="roi",
                label="📈 综合输出组织赋能 ROI 快照",
                tool_name="compute_org_roi",
                description="能力强弱分布 / 6 个月 level 涨幅 / 赋能推送潜力",
                input={},
            ),
            AgentStep(
                id="narrative",
                label="📝 你的组织能力体检报告",
                tool_name="llm_summary",
                description="调用 LLM 综合给出本季度投入建议",
                input={"focus_jd_id": focus_jd_id},
            ),
        ],
    )


# ---------------------------------------------------------------- 执行器

class AgentRunner:
    """执行 AgentPlan。每完成一步就 yield 一次。

    用法：
        plan = build_employee_plan("emp_001", "jd_002")
        runner = AgentRunner(plan)
        for step in runner.run():
            # UI 这里更新动画
            render_step(step)
    """

    def __init__(self, plan: AgentPlan, use_real_llm: bool = False):
        self.plan = plan
        self.use_real_llm = use_real_llm

    def run(self) -> Iterator[AgentStep]:
        for step in self.plan.steps:
            step.status = "running"
            yield step  # 让 UI 先显示"正在..."

            try:
                import time
                t0 = time.time()
                step.output = self._dispatch(step)
                step.duration_ms = int((time.time() - t0) * 1000)
                step.status = "done"
            except Exception as e:
                step.status = "failed"
                step.error = f"{type(e).__name__}: {e}"
            yield step  # 再 yield 一次，UI 显示结果

    def _dispatch(self, step: AgentStep) -> Any:
        """根据 step.tool_name 调用对应函数，并把 trace 写回 step.trace。"""
        tn = step.tool_name

        if tn == "build_employee_profile":
            from src.profile.employee_builder import build_profile
            prof = build_profile(step.input["employee_id"])
            step.trace = {
                "summary": f"识别 {len(prof.competencies)} 项能力标签",
                "top_competencies": [
                    f"{c.name} · L{c.level:.1f}" for c in sorted(prof.competencies, key=lambda x: -x.level)[:5]
                ],
            }
            return prof

        if tn == "build_job_profile":
            from src.profile.job_builder import build_profile
            job = build_profile(step.input["jd_id"])
            step.trace = {
                "summary": f"{job.title} 要求 {len(job.required_competencies)} 项能力",
                "top_weights": [
                    f"{cid.split('.')[-1]} · need L{nl} · w {w:.0%}"
                    for cid, nl, w in sorted(job.required_competencies, key=lambda x: -x[2])[:5]
                ],
            }
            return job

        if tn == "analyze_gap":
            from src.analysis.gap_analyzer import analyze_gap, match_score
            from src.profile.employee_builder import build_profile as build_emp
            from src.profile.job_builder import build_profile as build_job
            emp = build_emp(step.input["employee_id"])
            job = build_job(step.input["jd_id"])
            gaps = analyze_gap(emp, job)
            ms = match_score(emp, job)
            active = [g for g in gaps if g.gap > 0]
            step.trace = {
                "match_score": f"{ms:.0%}",
                "total_gaps": len(active),
                "high_priority_gaps": [
                    f"{g.name} · have L{g.have_level:.1f} / need L{g.need_level}"
                    for g in active if g.priority == "high"
                ][:5],
            }
            return {"gaps": gaps, "match_score": ms}

        if tn == "recommend_all":
            from src.analysis.gap_analyzer import analyze_gap
            from src.profile.employee_builder import build_profile as build_emp
            from src.profile.job_builder import build_profile as build_job
            from src.recommender.base import recommend_all, group_by_learning_mode
            emp = build_emp(step.input["employee_id"])
            job = build_job(step.input["jd_id"])
            gaps = analyze_gap(emp, job)
            recs = recommend_all(emp, gaps, top_k_rerank=3)
            grouped = group_by_learning_mode(recs)
            step.trace = {
                "total_recommendations": sum(len(v) for v in recs.values()),
                "by_mode": {
                    "experiential": len(grouped.get("experiential", [])),
                    "social": len(grouped.get("social", [])),
                    "formal": len(grouped.get("formal", [])),
                    "tool": len(grouped.get("tool", [])),
                },
                "top_picks": [
                    f"[{r.learning_mode}] {r.title}"
                    for items in recs.values() for r in items
                ][:6],
            }
            return {"recs": recs, "grouped": grouped}

        if tn == "generate_pathway":
            from src.analysis.gap_analyzer import analyze_gap
            from src.pathway.pathway_generator import generate
            from src.profile.employee_builder import build_profile as build_emp
            from src.profile.job_builder import build_profile as build_job
            from src.recommender.base import recommend_all
            emp = build_emp(step.input["employee_id"])
            job = build_job(step.input["jd_id"])
            gaps = analyze_gap(emp, job)
            recs = recommend_all(emp, gaps, top_k_rerank=3)
            path = generate(emp, job, gaps, recs)
            step.trace = {
                "milestones": [
                    f"{m.phase}: {m.title}（{len(m.resources)} 个资源）"
                    for m in path.milestones
                ],
            }
            return path

        if tn == "build_competency_matrix":
            from src.analysis.org_analyzer import build_competency_matrix
            m = build_competency_matrix()
            top = sorted(m.coverage.items(), key=lambda x: -x[1])[:3]
            step.trace = {
                "matrix_size": f"{len(m.employee_ids)} × {len(m.competency_ids)}",
                "top_covered": [
                    f"{next(cn for cid2, cn in zip(m.competency_ids, m.competency_names) if cid2 == cid)} · {v}/20"
                    for cid, v in top
                ],
            }
            return m

        if tn == "aggregate_gaps_for_job":
            from src.analysis.org_analyzer import aggregate_gaps_for_job
            jd_id = step.input.get("jd_id") or "jd_002"
            gaps = aggregate_gaps_for_job(jd_id)
            step.trace = {
                "jd_id": jd_id,
                "total_gap_competencies": len(gaps),
                "top_3": [
                    f"{g.name} · {g.high_priority_count} 人高优 · avg gap {g.avg_gap}"
                    for g in gaps[:3]
                ],
            }
            return gaps

        if tn == "build_expert_map":
            from src.analysis.org_analyzer import build_expert_map
            em = build_expert_map(top_k=2)
            from collections import Counter
            top_contributors = Counter()
            for e in em:
                for exp in e.top_experts:
                    top_contributors[exp.employee_id] += 1
            step.trace = {
                "competencies_with_experts": len(em),
                "top_contributors": [
                    f"{eid} · {n} 项" for eid, n in top_contributors.most_common(3)
                ],
            }
            return em

        if tn == "build_job_match_matrix":
            from src.analysis.org_analyzer import build_job_match_matrix
            jm = build_job_match_matrix()
            top_emp_per_jd = []
            for j in range(len(jm.jd_ids)):
                best_i = max(range(len(jm.employee_ids)), key=lambda i: jm.scores[i][j])
                top_emp_per_jd.append(f"{jm.jd_titles[j]}: {jm.employee_names[best_i]} ({jm.scores[best_i][j]:.0%})")
            step.trace = {
                "matrix_size": f"{len(jm.employee_ids)} × {len(jm.jd_ids)}",
                "best_matches": top_emp_per_jd[:3],
            }
            return jm

        if tn == "compute_org_roi":
            from src.analysis.org_analyzer import compute_org_roi
            r = compute_org_roi()
            step.trace = {
                "scale": f"{r.total_employees} 员工 · {r.total_events_6mo} 事件",
                "avg_gain_6mo": f"{r.avg_level_gain_6mo:+.2f} 级",
                "strong_vs_weak": f"💪 {r.strong_competencies} / ⚠️ {r.weak_competencies}",
                "expert_coverage": f"{r.expert_signals}/36 能力",
            }
            return r

        if tn == "llm_summary":
            # 综合前面所有步骤的结果，调 LLM 合成最终叙事
            return self._make_narrative()

        raise ValueError(f"Unknown tool: {tn}")

    def _make_narrative(self) -> str:
        """把前面 step 的结果拼成 prompt 交给 LLM，或走 mock 模板。"""
        outputs = {s.id: s.output for s in self.plan.steps if s.output is not None}

        if self.plan.name == "employee_growth":
            prompt = self._build_employee_narrative_prompt(outputs)
        else:
            prompt = self._build_admin_narrative_prompt(outputs)

        # 调 LLM（mock 或真）
        from src.llm.client import chat
        try:
            resp = chat([
                {"role": "system", "content": "你是一位专业的企业成长教练 / L&D 顾问，语言简洁有力。"},
                {"role": "user", "content": prompt},
            ])
            content = resp.content
            # 去掉 mock 的 JSON 壳（mock 返回的是 JSON，非结构化时返回 {"mock": true, ...}）
            if content.strip().startswith("{"):
                content = self._fallback_narrative(outputs)
            return content
        except Exception:
            return self._fallback_narrative(outputs)

    def _build_employee_narrative_prompt(self, outputs: dict) -> str:
        prof = outputs.get("profile")
        job = outputs.get("job")
        gap_info = outputs.get("gap", {})
        path = outputs.get("pathway")

        gaps = gap_info.get("gaps", []) if isinstance(gap_info, dict) else []
        ms = gap_info.get("match_score", 0) if isinstance(gap_info, dict) else 0

        top_gaps = [f"{g.name}(gap={g.gap})" for g in gaps if g.gap > 0 and g.priority == "high"][:3]
        milestones = [f"{m.phase}: {m.title}" for m in path.milestones] if path else []

        return f"""
基于以下分析为员工 {prof.name if prof else "?"}（当前角色 {prof.current_role if prof else "?"}）给出一段个性化成长建议。

目标岗位：{job.title if job else "?"}
当前匹配度：{ms:.0%}
Top 3 高优 gap：{', '.join(top_gaps) or '无明显 gap'}
30/60/90 路径：{' → '.join(milestones)}

要求：
1. 第一段用 2-3 句话直击他当前的优势 + 最大挑战
2. 第二段给 3 条具体的本月可执行建议（和他的 gap / 推荐资源强相关）
3. 第三段用 1-2 句话鼓励 + 强调 70-20-10 学习法则
不要超过 300 字，用"你"的口吻，不要用套话。
""".strip()

    def _build_admin_narrative_prompt(self, outputs: dict) -> str:
        roi = outputs.get("roi")
        gap_agg = outputs.get("gap_agg", [])
        em = outputs.get("expert", [])

        top_org_gaps = [
            f"{g.name}({g.high_priority_count}人高优)"
            for g in (gap_agg or [])[:3]
        ]

        return f"""
作为 L&D 顾问，基于以下组织体检结果给出一段季度投入建议。

组织规模：{roi.total_employees if roi else "?"} 员工 · {roi.total_events_6mo if roi else "?"} 事件（6 个月）
6 个月平均 level 涨幅：{roi.avg_level_gain_6mo if roi else "?":+.2f}
强能力数 / 弱能力数：{roi.strong_competencies if roi else "?"} / {roi.weak_competencies if roi else "?"}
可识别专家的能力数：{roi.expert_signals if roi else "?"}/36
组织 Top 3 集体缺口：{', '.join(top_org_gaps) or '无'}

要求：
1. 第一段点评整体健康度（2-3 句）
2. 第二段给 3 条具体行动建议（聚焦 Top 缺口 + 隐形专家利用）
3. 第三段给本季度重点投入方向（实践/社交/系统学习中哪类）
不要超过 350 字，给出具体动作，避免套话。
""".strip()

    def _fallback_narrative(self, outputs: dict) -> str:
        """mock / 失败时的兜底文案。确保 UI 永远有东西展示。"""
        if self.plan.name == "employee_growth":
            prof = outputs.get("profile")
            job = outputs.get("job")
            gap_info = outputs.get("gap", {})
            gaps = gap_info.get("gaps", []) if isinstance(gap_info, dict) else []
            ms = gap_info.get("match_score", 0) if isinstance(gap_info, dict) else 0

            top_gap_names = [g.name for g in gaps if g.gap > 0 and g.priority == "high"][:3]
            name = prof.name if prof else "同学"
            job_title = job.title if job else "目标岗位"

            return f"""
**{name}，这是我对你当前成长态势的判断：**

你当前的岗位匹配度是 **{ms:.0%}**。基于你 {len(prof.competencies) if prof else 0} 项已识别的能力，我发现你在一些维度已经达到 {job_title} 的要求，但仍有 {len(top_gap_names)} 项关键能力需要重点突破：{'、'.join(top_gap_names) or '（已较为均衡）'}。

**接下来 30 天，建议你做这 3 件事：**
- 🎯 **实践优先**：主动加入一个和上述 gap 能力相关的内部项目或 Hackathon（70-20-10 里的"70%"）
- 👥 **找对标者**：约一次与隐形专家的 1:1 对话，听他们怎么踩过同样的坑（"20%"）
- 📚 **精准学习**：挑一个 15 分钟微课 + 一条 Prompt 模板，立刻用到下周的任务中（"10%" + 工具）

**记住**：能力不是靠上课学出来的，是在真实任务里"用 + 反思 + 迭代"长出来的。祝你这季度有明显突破。
""".strip()
        else:
            roi = outputs.get("roi")
            gap_agg = outputs.get("gap_agg", [])
            top_gaps_text = "、".join(g.name for g in gap_agg[:3]) if gap_agg else "（无明显集体缺口）"

            return f"""
**组织能力体检报告**

当前组织规模 **{roi.total_employees if roi else "?"} 人**，过去 6 个月产生了 **{roi.total_events_6mo if roi else "?"}** 条行为流事件，平均 level 涨幅 **{roi.avg_level_gain_6mo if roi else 0:+.2f} 级**。整体处于 {"健康" if roi and roi.avg_level_gain_6mo >= 0.5 else "需关注"} 状态。

**本季度建议重点投入的方向：**
- ⚠️ **集体缺口治理**：Top 薄弱能力集中在 {top_gaps_text}，建议立项 3 场专项训练营（70% 实践 + 20% 专家共创）
- 🌟 **盘活隐形专家**：已识别可匹配专家的能力 {roi.expert_signals if roi else 0}/36 项，推动这些专家加入 Mentorship 计划，一对多辐射组织
- 📊 **建立基线**：把当前的 ROI 快照作为 Q2 起点，未来每季度复盘 level 涨幅 / 强弱能力比例的变化

**核心理念**：L&D 不是组织课程，而是**识别能力的内部流动 + 在任务中催化增长**。70-20-10 分布下，课程只占 10%，剩下 90% 都依赖实践和互相学习。
""".strip()
