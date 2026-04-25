"""集中式 Prompt 模板。

设计原则：
1. Prompt 里总是声明 JSON 输出结构，并给出 few-shot 示例（必要时）
2. 所有 Prompt 都带 "##TASK##" 标签便于 mock 路由识别
3. 能力 ID 约束写在 Prompt 开头以抑制幻觉
4. 精排 Prompt 可接 learning_mode 参数对不同分组做差异化约束
"""
from __future__ import annotations

from textwrap import dedent

# ---------------------------------------------------------------- Phase 1

EXTRACT_EMPLOYEE = dedent("""\
    ##TASK## extract_employee_profile

    你是一个能力建模专家。基于给定员工的简历与项目经历，从下方【能力本体】中选择最匹配的能力打标（level 1-5），并给出证据。
    只允许输出本体内存在的 competency_id，严禁生造。

    【能力本体】
    {ontology}

    【员工信息】
    姓名: {name}
    当前角色: {current_role}
    简历与项目:
    {resume}
    自评:
    {self_assessment}

    【输出 JSON】
    {{
      "competencies": [
        {{"competency_id": "C.xxx", "name": "xxx", "level": 1-5, "confidence": 0-1, "evidence": ["..."]}}
      ],
      "summary": "一句话员工画像"
    }}
""").strip()

EXTRACT_JOB = dedent("""\
    ##TASK## extract_job_profile

    基于 JD 文本，结合已给出的 required_competencies 列表，从【能力本体】中补充其他应当具备但未显式列出的能力。
    只允许输出本体内存在的 competency_id。

    【能力本体】
    {ontology}

    【JD】
    标题: {title}
    描述: {description}
    已列出能力: {existing_competencies}

    【输出 JSON】
    {{
      "additional_competencies": [{{"competency_id": "C.xxx", "need_level": 1-5, "weight": 0-1}}],
      "summary": "一句话岗位摘要"
    }}
""").strip()

RANK_GAP = dedent("""\
    ##TASK## rank_gap

    给定员工 vs 岗位的能力差距列表，根据"对岗位胜任的影响 × gap 大小 × 学习难度"综合判断，
    为每项能力分配优先级 high/mid/low，并给出 30 字以内的理由。

    【Gap 列表】
    {gaps}

    【输出 JSON】
    {{
      "ranked": [
        {{"competency_id": "C.xxx", "priority": "high|mid|low", "rationale": "..."}}
      ]
    }}
""").strip()

# 七类复用同模板，learning_mode 约束注入到 constraint 段
RERANK_RESOURCE = dedent("""\
    ##TASK## rerank_resource

    你要从候选资源中为员工挑选最能弥补其能力 gap 的 Top-{top_k} 项。
    当前分组：{learning_mode_label}
    本组约束：{learning_mode_constraint}

    【员工摘要】
    {employee_summary}

    【Gap 列表（按优先级）】
    {gaps}

    【候选资源】
    {candidates}

    【输出 JSON】
    {{
      "reranked": [
        {{"resource_id": "XXX.001", "score": 0-1, "rationale": "..."}}
      ]
    }}
""").strip()

LEARNING_MODE_CONSTRAINT = {
    "experiential": "优先推荐可以动手产出可见成果、能在工作流中自然承接的实践机会；避免纯理论课程。",
    "social": "优先推荐与员工当前能力鸿沟差距适中（约 1-2 级）、能提供可复用模板或 1:1 指导的资源；案例库要挑与员工业务相近的。",
    "formal": "优先挑选路径清晰、可在 2-4 周完成的内容；偏好微课（<15min）+ 深度资料的组合。",
    "tool": "优先推荐可立即上手、ROI 高、不需要重度学习的工具或模板；给出一个 5 分钟的上手 tip。",
}

GENERATE_PATHWAY = dedent("""\
    ##TASK## generate_pathway

    你是成长路径规划师。基于员工 gap 与 Top-5 精排后的推荐资源池，为员工设计 30/60/90 天阶段性里程碑。
    每个阶段：1-2 个可验证的里程碑产出 + 3 个必选资源（含至少 1 个 experiential、1 个 social、1 个 formal）。

    【员工摘要】
    {employee_summary}
    【岗位目标】
    {job_summary}
    【Top Gap】
    {gaps}
    【候选资源（含 resource_id, title, learning_mode）】
    {resources}

    【输出 JSON】
    {{
      "milestones": [
        {{
          "phase": "30d|60d|90d",
          "title": "...",
          "description": "...",
          "target_competencies": ["C.xxx"],
          "resources": ["RES.001", "RES.002", "RES.003"]
        }}
      ]
    }}
""").strip()

# ---------------------------------------------------------------- Phase 2

EXTRACT_TASK = dedent("""\
    ##TASK## extract_task_profile

    从任务描述中抽取完成该任务所需的能力清单（competency_id），给出 need_level(1-5) 与 weight(0-1，和为 1)。

    【能力本体】
    {ontology}
    【任务】
    标题: {title}
    描述: {description}

    【输出 JSON】
    {{
      "required_competencies": [
        {{"competency_id": "C.xxx", "need_level": 3, "weight": 0.2}}
      ],
      "summary": "任务画像摘要"
    }}
""").strip()

ATTRIBUTE_EVENT = dedent("""\
    ##TASK## attribute_event

    把单条行为事件归因到至多 3 项能力的 delta（-1~+1，可为负），并给 confidence(0-1) 与 rationale。
    只允许输出本体内存在的 competency_id。

    【能力本体】
    {ontology}

    【事件】
    来源: {source}
    标题: {title}
    内容: {content}

    【输出 JSON】
    {{
      "deltas": [
        {{"competency_id": "C.xxx", "delta_level": 0.2, "confidence": 0.7, "rationale": "..."}}
      ]
    }}
""").strip()

GENERATE_TRIGGER_MSG = dedent("""\
    ##TASK## generate_trigger_msg

    基于触发类型和员工情况，生成一条推送卡片文案（30 字以内），语气友好、动作明确。

    触发类型: {trigger_type}
    员工: {employee_name}
    相关 gap: {target_gaps}
    推荐资源: {resources}

    【输出 JSON】
    {{"suggested_action": "..."}}
""").strip()

MATCH_CASE_STUDY = dedent("""\
    ##TASK## match_case_study

    为员工当前正在处理的任务，从案例库中选出最匹配的 Top-3 过往案例。
    匹配维度：能力相关性 + 业务领域接近度 + 难度匹配。

    【员工与任务】
    员工摘要: {employee_summary}
    任务: {task_title} - {task_description}
    任务关键能力: {task_competencies}

    【候选案例（含 CASE.id, title, related_competencies, context）】
    {candidates}

    【输出 JSON】
    {{
      "matches": [
        {{"case_id": "CASE.xxx", "score": 0-1, "reason": "..."}}
      ]
    }}
""").strip()
