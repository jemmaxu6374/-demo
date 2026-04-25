"""Patch employees.json: 根据 resume / projects / self_assessment 为每位员工
补充 structured base_competencies。用人工判断一次性写入，供 mock 模式零依赖跑通；
LLM 模式下仍会用 LLM 抽取，base 作为兜底合并。"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

P = ROOT / "data" / "samples" / "employees.json"
data = json.loads(P.read_text(encoding="utf-8"))

# 手工映射表：employee_id → list[(competency_id, level, confidence, evidence_short)]
BASE = {
    "emp_001": [  # 李明 / 后端 2y
        ("C.hard.prog.py", 4, 0.85, "2年 Python 后端开发"),
        ("C.hard.arch", 3, 0.8, "订单履约系统重构到微服务"),
        ("C.hard.distributed", 3, 0.75, "微服务拆分+Kafka 异步解耦"),
        ("C.hard.db.sql", 3, 0.8, "MySQL 分库分表实战"),
        ("C.hard.db.nosql", 3, 0.75, "Redis 缓存"),
        ("C.hard.ml.dl", 2, 0.7, "LangChain+bge-m3 做过内部知识库问答 Demo"),
        ("C.tool.prompt", 2, 0.7, "Demo 级 Prompt 调优"),
        ("C.domain.ai-app", 2, 0.65, "内部知识库 Bot 日活 30"),
        ("C.tool.git", 4, 0.9, "熟练"),
        ("C.soft.comm", 3, 0.7, "线上问题响应快"),
        ("C.soft.learn", 4, 0.85, "主动学习新技术"),
    ],
    "emp_002": [  # 张雨欣 / 前端 3y
        ("C.hard.prog.ts", 4, 0.9, "熟练 React+TS"),
        ("C.hard.ux", 3, 0.75, "对动效交互敏感"),
        ("C.tool.cicd", 3, 0.7, "monorepo+构建优化"),
        ("C.hard.arch", 3, 0.7, "商户后台重构"),
        ("C.hard.testing", 2, 0.6, "少量 E2E"),
        ("C.tool.git", 4, 0.9, ""),
        ("C.soft.collab", 3, 0.75, "前端负责人"),
        ("C.soft.comm", 3, 0.7, ""),
    ],
    "emp_003": [  # 王浩 / 算法 4y
        ("C.hard.ml.basic", 4, 0.9, "推荐系统 4 年"),
        ("C.hard.ml.dl", 4, 0.9, "DIN/Multi-interest 上线"),
        ("C.hard.prog.py", 4, 0.85, "TF/PyTorch"),
        ("C.hard.algo", 4, 0.8, ""),
        ("C.domain.social", 4, 0.85, "短视频推荐"),
        ("C.tool.prompt", 3, 0.7, "LLM 冷启动探索"),
        ("C.soft.problem", 4, 0.8, ""),
        ("C.soft.lead", 2, 0.6, "还没带过新人"),
    ],
    "emp_004": [  # 刘思远 / 数据 1.5y
        ("C.hard.db.sql", 4, 0.85, "SQL 扎实"),
        ("C.hard.data.eng", 3, 0.8, "Spark+Airflow 数仓"),
        ("C.hard.prog.py", 3, 0.75, "Python 脚本"),
        ("C.hard.ml.basic", 1, 0.6, "有兴趣但没实战"),
        ("C.soft.problem", 3, 0.7, "细致耐心"),
        ("C.hard.arch", 2, 0.6, "系统设计经验不足"),
    ],
    "emp_005": [  # 陈昕 / AI PM 3y
        ("C.hard.product.pm", 4, 0.9, "3 年产品"),
        ("C.domain.ai-app", 4, 0.85, "AI 写作助手 MAU 15w"),
        ("C.tool.prompt", 4, 0.9, "Prompt 写得好"),
        ("C.hard.data.analysis", 3, 0.75, "留存漏斗分析"),
        ("C.hard.db.sql", 3, 0.75, "SQL 能写"),
        ("C.hard.prog.py", 2, 0.6, "在学"),
        ("C.soft.comm", 4, 0.85, "沟通顺畅"),
        ("C.hard.ml.dl", 2, 0.6, "理解浅"),
    ],
    "emp_006": [  # 赵磊 / 资深后端 6y
        ("C.hard.prog.go", 4, 0.9, "Java/Go 双栈"),
        ("C.hard.prog.py", 3, 0.7, ""),
        ("C.hard.arch", 5, 0.95, "支付核心重构"),
        ("C.hard.distributed", 5, 0.95, "一致性/幂等/对账"),
        ("C.hard.db.sql", 4, 0.85, ""),
        ("C.domain.fintech", 5, 0.95, "支付领域专家"),
        ("C.soft.lead", 3, 0.75, "带 3 人小组"),
        ("C.hard.ml.dl", 2, 0.6, "在补"),
    ],
    "emp_007": [  # 孙佳 / 测试 2y
        ("C.hard.testing", 4, 0.9, "Pytest+Playwright"),
        ("C.hard.prog.py", 3, 0.8, "Python+Flask 自动化平台"),
        ("C.hard.security", 2, 0.65, "学过 OWASP Top 10"),
        ("C.tool.cicd", 3, 0.7, ""),
        ("C.hard.algo", 2, 0.6, "算法基础薄"),
        ("C.hard.arch", 2, 0.6, "后端业务理解浅"),
    ],
    "emp_008": [  # 周晨 / 前端 1y
        ("C.hard.prog.ts", 3, 0.8, "React+Vue"),
        ("C.hard.ux", 3, 0.7, "开源按钮组件库 500 star"),
        ("C.hard.testing", 2, 0.6, ""),
        ("C.soft.collab", 2, 0.6, "跨团队协作在学"),
        ("C.hard.arch", 1, 0.55, "缺大型系统经验"),
    ],
    "emp_009": [  # 林悦 / AI 应用 2y
        ("C.hard.prog.py", 4, 0.9, ""),
        ("C.hard.ml.dl", 3, 0.8, "LLM 应用 2 年"),
        ("C.tool.prompt", 4, 0.9, "深度 Prompt"),
        ("C.domain.ai-app", 4, 0.9, "Agent/RAG 上线"),
        ("C.hard.arch", 2, 0.6, "后端系统工程薄弱"),
        ("C.hard.distributed", 2, 0.6, ""),
        ("C.hard.db.nosql", 3, 0.7, ""),
        ("C.soft.problem", 3, 0.75, ""),
    ],
    "emp_010": [  # 郑宇 / SRE 4y
        ("C.tool.docker", 5, 0.95, "K8s 承接 200+ 微服务"),
        ("C.tool.cloud", 4, 0.9, ""),
        ("C.tool.observability", 5, 0.95, "Prom/Grafana/ELK"),
        ("C.tool.cicd", 4, 0.85, ""),
        ("C.hard.distributed", 3, 0.7, ""),
        ("C.hard.prog.py", 3, 0.7, "脚本"),
        ("C.soft.problem", 4, 0.85, "故障复盘"),
        ("C.soft.ownership", 4, 0.85, ""),
    ],
    "emp_011": [  # 吴雪 / UX 3y
        ("C.hard.ux", 4, 0.9, "设计系统 2.0"),
        ("C.hard.product.pm", 2, 0.6, "推动力不足"),
        ("C.hard.prog.ts", 2, 0.65, "能看懂 React"),
        ("C.soft.comm", 4, 0.85, ""),
        ("C.soft.collab", 3, 0.75, ""),
        ("C.hard.data.analysis", 2, 0.6, "待提升"),
    ],
    "emp_012": [  # 郭阳 / 大数据 3y
        ("C.hard.data.eng", 4, 0.9, "Flink+Iceberg"),
        ("C.hard.db.sql", 4, 0.85, ""),
        ("C.hard.prog.py", 3, 0.7, "Java+Scala 为主"),
        ("C.hard.arch", 3, 0.75, "实时指标平台"),
        ("C.tool.cloud", 3, 0.7, ""),
        ("C.hard.ml.dl", 1, 0.55, "AI 方向空白"),
        ("C.hard.product.pm", 1, 0.5, "产品思维较弱"),
    ],
    "emp_013": [  # 马辰 / 后端新人 0.5y
        ("C.hard.prog.py", 2, 0.6, "Java 背景"),
        ("C.hard.db.sql", 2, 0.65, ""),
        ("C.hard.arch", 1, 0.6, ""),
        ("C.hard.distributed", 1, 0.5, "理论认知但无实战"),
        ("C.tool.git", 2, 0.7, ""),
        ("C.soft.learn", 4, 0.85, "学习意愿强"),
    ],
    "emp_014": [  # 徐铭 / 高级 PM 5y
        ("C.hard.product.pm", 5, 0.95, "5 年支付产品"),
        ("C.domain.fintech", 5, 0.95, "聚合支付 10 亿+/月"),
        ("C.hard.security", 3, 0.75, "合规嗅觉"),
        ("C.soft.collab", 4, 0.85, ""),
        ("C.soft.lead", 3, 0.75, "带 2 人"),
        ("C.hard.data.analysis", 2, 0.6, "一般"),
        ("C.hard.ml.dl", 1, 0.5, "理解不足"),
    ],
    "emp_015": [  # 何思琪 / NLP 1.5y
        ("C.hard.ml.basic", 3, 0.8, ""),
        ("C.hard.ml.dl", 3, 0.8, "BERT+LoRA"),
        ("C.hard.prog.py", 3, 0.75, ""),
        ("C.tool.prompt", 2, 0.65, "还不系统"),
        ("C.hard.arch", 2, 0.6, "工程落地弱"),
        ("C.hard.data.eng", 2, 0.6, ""),
        ("C.soft.learn", 4, 0.85, "学术基础好"),
    ],
    "emp_016": [  # 韩子睿 / 全栈 3y
        ("C.hard.prog.ts", 4, 0.85, "Next.js"),
        ("C.hard.prog.py", 3, 0.75, ""),
        ("C.hard.db.sql", 3, 0.75, "PostgreSQL"),
        ("C.tool.aicopilot", 5, 0.95, "Cursor/CodeBuddy 深度用户"),
        ("C.tool.prompt", 3, 0.75, ""),
        ("C.hard.arch", 2, 0.65, "大型系统缺经验"),
        ("C.soft.ownership", 4, 0.85, "交付快"),
    ],
    "emp_017": [  # 黄雅 / 数据分析 2y
        ("C.hard.data.analysis", 4, 0.9, "漏斗诊断"),
        ("C.hard.db.sql", 4, 0.9, ""),
        ("C.hard.prog.py", 3, 0.75, "统计+可视化"),
        ("C.hard.product.pm", 3, 0.7, "业务理解"),
        ("C.soft.comm", 4, 0.85, ""),
        ("C.hard.ml.basic", 2, 0.6, "建模弱"),
        ("C.hard.data.eng", 1, 0.55, "大数据框架不熟"),
    ],
    "emp_018": [  # 冯楠 / 技术主管 7y
        ("C.soft.lead", 5, 0.95, "8 人团队"),
        ("C.hard.arch", 4, 0.85, "选型判断准"),
        ("C.domain.ai-app", 4, 0.85, "3 个 AI 产品"),
        ("C.hard.ml.dl", 3, 0.75, ""),
        ("C.soft.comm", 4, 0.85, ""),
        ("C.soft.collab", 4, 0.85, ""),
        ("C.soft.ownership", 5, 0.95, ""),
        ("C.hard.prog.py", 3, 0.7, "一线写代码减少"),
    ],
    "emp_019": [  # 唐小宇 / 安全 2y
        ("C.hard.security", 4, 0.9, "代码审计+渗透+应急"),
        ("C.hard.prog.py", 3, 0.75, "脚本"),
        ("C.hard.prog.go", 2, 0.65, ""),
        ("C.tool.cloud", 2, 0.65, "云安全有兴趣"),
        ("C.hard.data.analysis", 2, 0.6, ""),
        ("C.hard.ml.dl", 1, 0.5, "空白"),
    ],
    "emp_020": [  # 于萌 / iOS 3y
        ("C.hard.prog.ts", 2, 0.6, "前端接触少"),
        ("C.tool.observability", 3, 0.7, "性能调优"),
        ("C.hard.arch", 2, 0.65, "后端服务设计几乎为 0"),
        ("C.hard.ml.dl", 1, 0.5, "AI 空白"),
        ("C.hard.data.analysis", 1, 0.55, ""),
        ("C.soft.problem", 3, 0.75, "启动优化"),
    ],
}

updated = 0
for e in data:
    eid = e["employee_id"]
    if eid in BASE:
        e["base_competencies"] = [
            {"competency_id": cid, "level": lvl, "confidence": conf, "evidence": [ev] if ev else []}
            for cid, lvl, conf, ev in BASE[eid]
        ]
        updated += 1

P.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Patched employees.json: {updated}/{len(data)} updated")
