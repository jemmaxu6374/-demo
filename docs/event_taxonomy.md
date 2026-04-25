# 行为事件分类法（六类 source）

> Phase 2 的六类行为事件流是整个动态画像的数据基础。本文档明确每类事件的 schema、归因策略与取证原则。

## 一、六类 source 总览

| source | 核心信号 | 产生频率（工作日） | 归因特点 |
| --- | --- | --- | --- |
| `task` | TAPD 任务流转、评审结果 | 高（每天 1-3 条） | 正向/负向均有，取决于评审结果 |
| `code` | Git commit / PR 合入 / 代码 review | 高（每天 1-3 条） | 主要正向，重构/性能优化证据强 |
| `doc` | 腾讯文档/Confluence 产出 | 中（每周 1-2 条） | 正向，说明有输出 |
| `learning` | 完课 / 搜索 / 提问 | 低（每周 0-3 条） | 弱正向，主要触发学习相关信号 |
| `meeting` | 评审会 / 站会 / 1:1 纪要 | 中（每天 0-2 条） | 中性偏正 |
| `feedback` | OKR / 360 / 绩效面谈 | 低（每月 1-2 条） | **权重最大**，上下两向均可 |

## 二、单条事件 schema

```python
class BehaviorEvent(BaseModel):
    event_id: str                # 全局唯一，含 employee_id + source + hash
    employee_id: str
    source: Literal["task","code","doc","learning","meeting","feedback"]
    ts: datetime
    title: str                   # 事件标题（评审结果、commit msg、文档标题）
    content: str                 # 摘要文本，给 LLM 归因用
    raw_ref: str                 # 原始链接/ID，"查看原始依据"入口
```

本 Demo 额外增加 `competency_hints` 字段（仅 jsonl 存储，不入 DB），用作归因的 ground truth 通道：

```python
competency_hints: list[{
    "competency_id": str,
    "delta_hint": float,         # -1 ~ 1
    "confidence_hint": float,    # 0 ~ 1
}]
```

## 三、归因策略（event_processor）

双轨：

1. **Hints 路径**（Demo 默认）：事件自带 `competency_hints` → 直接映射成 `CompetencyDelta`。用于模板生成流程。
2. **LLM 路径**：没有 hints 的事件走 `ATTRIBUTE_EVENT` Prompt；LLM 输出经 `resolve_competency` 归一化到本体内 competency_id，非法 id 一律丢弃。

两条路输出结构一致：`list[CompetencyDelta]`。

### 不同 source 的归因规则

| source | 典型正向事件 | 典型负向事件 | 单事件最大 \|delta\| |
| --- | --- | --- | --- |
| task | "完成 X 模块开发" | "评审被打回" | 0.5 |
| code | "feat: 核心流程实现" / "perf: 优化" | "hotfix 紧急回滚" | 0.5 |
| doc | "输出设计文档" / "踩坑总结" | — | 0.45 |
| learning | "完成课程 X" | — | 0.25（单次完课证据弱） |
| meeting | "主导技术评审" | "站会识别阻塞" | 0.3 |
| feedback | "OKR KR 达成 115%" / "360 反馈肯定" | "绩效面谈指出待提升" | 0.45（权重大，但 k 还在上限内） |

## 四、单事件可归因到多少能力？

建议 **1-3 项**。多了会让单次更新影响过大，违背"一次事件一个小证据"的直觉。

本 Demo 生成器：
- 主标签：1 项（基于员工 strength 加权采样）
- 次标签：25% 概率追加 1 项（delta 减半）

## 五、负向证据处理

负向 delta 在 Beta 更新中映射到 β（而非扣减 α）。物理意义：
- 不否定过去的成就（α 不减）
- 但增加反例证据（β 增加）→ 均值下降

**重要**：负向证据不会让一个 L5 员工直接降到 L2。它只会：
- 减缓该能力的进一步成长（降低下次正向证据的边际效用）
- 在持续出现负向证据时才真正拉低 level

## 六、生成器设计（generate_behavior_streams.py）

为 Demo 可演示，生成器做了以下约束：

1. **员工级种子**：`Random(f"{seed}-{eid}")` 保证每次生成结果一致
2. **工作日与周末区分**：工作日 2-5 条，周末 0-1 条
3. **能力采样偏好员工强项**：80% 从 base_competencies 里按 level × confidence 加权采样，20% 均匀采样（模拟"学新东西"）
4. **source 分布**：task/code 最多（30%+28%），feedback 最少（8%）
5. **时间点**：工作时间 9:00-20:00

## 七、隐私与合规（Phase 4 待处理）

生产化后，行为流采集必须：
- 员工明示同意（opt-in）
- 每个字段都声明用途（DPIA）
- 员工 always 可见自己的事件流
- 提供"删除某事件 / 重置画像"通道
- LLM 归因的原始文本默认脱敏（去 PII）

## 八、与 trigger_engine 的衔接

事件流不仅为画像更新服务，也直接给 trigger_engine 提供信号：

| trigger_type | 数据来源 |
| --- | --- |
| task_new | tasks.json 中 status=new |
| review_rejected | 事件文本中含"打回" / "待提升" / "需加强" |
| search | learning 类事件文本中含"搜索" |
| match_low | 从 timeline 算当前动态画像 vs JD 的 match_score |
| task_embedded_learning | task_profiler 识别任务能力 ∩ 当前画像 gap |
| expert_available | 近 30 天 delta 累积最多的员工作为隐形导师 |
