# Employee Empowerment Demo

面向知识工作者（研发 / 产品 / 数据 / 设计 / 技术运营）的**实时精准个性化赋能** AI 模型 Demo。

> 🌐 **在线体验**：本项目已适配 **Streamlit Community Cloud** 部署，3-5 分钟即可上线公网。
> 部署步骤见 [`docs/DEPLOY.md`](docs/DEPLOY.md)。本地运行见下方「快速开始」。

## 三阶段演进

- **Phase 1 静态基线（MVP）**：简历 + JD → 能力 Gap → 按 70-20-10 分组的**七路推荐** → 30/60/90 天成长路径
- **Phase 2 动态画像引擎**：六类行为事件流 → LLM 归因 → 贝叶斯 + 时间衰减 → 任务级画像 + 任务内嵌学习 + Expert Finder
- **Phase 3 双视图交互**：行为流时间线 ↔ 能力画像面板 + 时间轴滑块，回溯 6 个月成长轨迹

## 赋能形态：70-20-10 × 七小类

| 分组 | 占比 | 具体形态 |
| --- | --- | --- |
| 🎯 在实践中学 | 70% | 内部项目 / Hackathon、沙盒 Lab 环境 |
| 👥 向他人学 | 20% | 导师 1:1（静态池 + Expert Finder）、过往案例库、Tech Talk、学习社群 |
| 📚 系统学习 | 10% | 课程（含微课）、技术文档 / 书籍 |
| 🛠️ 工具直接用 | 正交 | AI Copilot / 工具、Prompt 模板库 / 工作流 SOP |

## v1.0 定位与边界

聚焦「知识工作者」个体成长赋能，**不覆盖**：销售 / HR / 客服 / 法务 / 后勤等行为流稀疏或非数字化岗位、团队 / 组织级赋能、软技能 / 心理维度。多岗位适配 / 组织级赋能 / 软技能归因列入 Phase 4 规划，详见 [`docs/scope_and_limitations.md`](docs/scope_and_limitations.md)。

## 快速开始

### 方式 A：本地运行（推荐开发用）

```bash
# 1. 安装部署版依赖（最少集，<30s）
pip install -r requirements.txt

# 2. 启动（首次启动自动生成数据，约 45s）
streamlit run app/streamlit_app.py
# → http://localhost:8501
```

如需真 LLM：`cp .env.example .env` 并填 API Key，将 `LLM_PROVIDER` 改为 `openai`。

### 方式 B：部署到 Streamlit Community Cloud

见 [`docs/DEPLOY.md`](docs/DEPLOY.md) 完整步骤。简要：

1. 把仓库推到 GitHub（Public）
2. 在 <https://share.streamlit.io> 绑定仓库
3. 入口脚本填 `app/streamlit_app.py`，Python 3.11
4. 点 Deploy，等 3-5 分钟即得公网 URL

### 方式 C：本地开发（含 Chroma / bge-m3 / 真 LLM 全套）

```bash
pip install -r requirements-dev.txt
python scripts/build_vector_index.py   # 建向量索引
streamlit run app/streamlit_app.py
```

## 目录结构

```
employee-empowerment-demo/
├── data/                  # 能力本体 / 样例数据 / 资源池 / 行为流 / 向量库
├── src/                   # 业务代码：profile/analysis/events/recommender/pathway/llm/...
├── scripts/               # 数据生成、向量索引、事件回放脚本
├── app/                   # Streamlit 前端
├── docs/                  # 设计与评估文档
└── tests/                 # 单元测试
```

详见 [`docs/architecture.md`](docs/architecture.md)。

## 文档索引

- [**部署到 Streamlit Cloud**](docs/DEPLOY.md) 🆕
- [架构说明](docs/architecture.md)
- [70-20-10 赋能形态分类法](docs/empowerment_forms_taxonomy.md)
- [v1.0 适用范围与扩展路线](docs/scope_and_limitations.md)
- [数据源方案对比](docs/data_source_comparison.md)
- [动态画像数学推导](docs/dynamic_profile_math.md)（P2）
- [行为事件分类法](docs/event_taxonomy.md)（P2）
- [评估方案](docs/evaluation.md)
