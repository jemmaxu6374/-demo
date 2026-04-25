# 评估方案

## 一、评估矩阵

| 维度 | 指标 | 目标 | 方法 |
| --- | --- | --- | --- |
| **画像准确率** | 人工标注 F1 | ≥ 0.75 | 抽 5 员工 × 8 能力人工打 level，与系统对比 |
| **推荐相关性** | Top-3 命中率 | ≥ 70% | 5 员工 × 3 高优 gap，人工判断 Top-3 有无可用 |
| **画像演化合理性**（P2） | 一致率 | ≥ 80% | 抽 20 组（事件, Δlevel），人工判断 delta 方向是否合理 |
| **触发时效**（P2） | task_new → 推送延迟 | < 30s（模拟时钟） | 模拟新任务事件注入，看触发器响应时间 |
| **个性化体感** | 推荐文案 Embedding 差异度 | ≥ 40% | 同 gap 对不同员工的推荐文本，两两余弦差 ≥ 0.4 |
| **响应延迟** | 静态 P95 | < 8s | Streamlit 4 页 + 全链路端到端 |
| | 事件批处理 50 条 | < 15s | replay 日志 |
| | 时间轴拖动 | < 300ms | snapshot 命中 |

## 二、当前实测（v1.0 Demo）

### 2.1 画像准确率

**方法**：用 `base_competencies` 作为 ground truth（来自人工对 20 位员工的打标）；`build_profile` 输出与 base 完全吻合（mock 模式走 base + LLM 合并路径，结果取 max）。

**数值**：mock 模式 F1=1.0（因为 base 直接注入）；LLM 模式待后续真 API 接入后单独评测。

### 2.2 推荐相关性

抽样 5 组冒烟结果：

| 员工 → JD | 高优 gap | Top-3 推荐（任意路） | 人工判断 |
| --- | --- | --- | --- |
| emp_001 → jd_002 | AI Copilot, ai-app | PROJ.002(AI 客服) / CASE.002(RAG) / COURSE.011(LangChain) | ✅ 3/3 强相关 |
| emp_013 → jd_001 | 分布式、架构、SQL | PROJ.001(压测演练) / CASE.001(订单拆分) / READ.001(DDIA) | ✅ 3/3 |
| emp_005 → jd_006 | 数据分析深化 | SOP.003(A/B SOP) / TOOL.021(Jupyter) / COURSE.021(分析师地图) | ✅ 3/3 |
| emp_018 → jd_010 | 已达标 | MENTOR.004(自己) / HACK.001 / CASE.010 | ⚠️ mentor 应排除自己 |
| emp_004 → jd_005 | Spark/Flink | COURSE.013(Flink) / CASE.008(NLP) / TOOL.009(Airflow) | ✅ 2/3（CASE.008 偏离） |

**Top-3 命中率**：~85%。mentor 不排除自己、部分案例跨度偏大是两个小问题，已记录。

### 2.3 画像演化合理性

**抽样**：emp_001 的 C.hard.prog.py 时间序列：
- 6 个月前：L3.07 → 当前 L4.25
- 76 个 timeline points
- 全程单调上升，无 >2 的 jump（贝叶斯上限起作用）

**emp_015 的 C.hard.ml.dl**：Expert Finder 识别累积 delta=4.17，证据数 20 条 —— 这是 NLP 方向持续产出的典型员工，数据正确。

### 2.4 响应延迟

| 操作 | 耗时 |
| --- | --- |
| Phase 1 单员工全链路（画像+Gap+七路推荐+路径） | ~50ms（mock） |
| replay 全员 9400 事件（hints 路径） | ~45s（一次性） |
| snapshot 构建 11788 → 9056 条 | ~1s |
| Streamlit 双视图页首次渲染 | ~2-3s（含 snapshot 查询） |
| 时间轴滑块拖动触发 rerun | ~500-800ms（Streamlit 原生限制） |

**与目标对比**：静态链路 << 8s ✅；事件批处理 45s / 9400 条 ≈ 250 条/s，远超 50/15s 目标 ✅；时间轴 ~600ms，略超 300ms 目标，Phase 3 可引入 session_state 缓存 snapshot 数据进一步压缩。

## 三、已知局限与改进项

| 问题 | 影响 | 改进 |
| --- | --- | --- |
| mentor_recommender 不排除自己 | 资深员工会推到自己 | 在 extra_score 里加 `-9999` 惩罚 |
| 软技能仅靠自评 | F1 低 | Phase 4 三角验证（自评+360+情境） |
| mock LLM 无真实语义 | 推荐解释文案弱 | 换真 API 时自动增强 |
| replay 按事件逐条更新 | 慢 | 同日多事件可批合并 |
| 时间轴 300ms 目标未达 | 交互略卡 | session_state 缓存 + 降级到每周 snapshot |

## 四、评估脚本位置（建议）

```
tests/
├── test_profile_builder.py   # base + LLM 合并正确性
├── test_gap_analyzer.py      # 权重、优先级、边界
├── test_recommender.py       # 七路召回/精排/learning_mode 一致性
├── test_case_recommender.py  # 案例匹配准确率
├── test_expert_finder.py     # 高产出识别逻辑
├── test_event_processor.py   # hints/LLM 归因 + 归一化
├── test_profile_updater.py   # 贝叶斯单调性、衰减下限
└── test_trigger_engine.py    # 六种触发规则命中率
```

当前 Demo 通过端到端冒烟（而非单测）来验收；生产化阶段应按上表补齐。
