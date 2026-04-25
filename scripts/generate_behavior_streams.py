"""行为流生成器：为每位员工合成 6 个月的六类工作行为事件。

设计原则：
- 不依赖 LLM：用 **模板 + 能力标签加权采样** 确定性生成，便于验证
- 每条事件自带 `competency_hints`（供 event_processor 归因兜底）
- 覆盖 6 类 source：task / code / doc / learning / meeting / feedback
- 员工生成节奏：工作日 2-5 条事件，周末 0-1 条，持续 180 天

输出：data/behavior_streams/{emp_id}/{source}.jsonl，每行一个 BehaviorEvent JSON
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from loguru import logger  # noqa: E402


# ---------------------------------------------------------------- 模板

TASK_TEMPLATES = [
    ("{comp_name} 相关需求评审会", "评审了 {comp_name} 方向的新需求，输出 PRD/TD 初稿并识别风险 3 项", 0.3),
    ("完成 {comp_name} 模块开发", "完成 {comp_name} 模块的核心开发，提交联调环境", 0.5),
    ("{comp_name} 线上问题复盘", "定位并修复 {comp_name} 相关线上问题，输出复盘文档", 0.4),
    ("{comp_name} 方向的技术方案评审", "提交 {comp_name} 方向的架构方案，通过评审前修改 2 版", 0.4),
    ("评审被打回", "{comp_name} 的 PR/方案被 reviewer 打回，补充测试与文档后重提", -0.3),
]

CODE_TEMPLATES = [
    ("feat: {comp_name} 核心流程实现", "实现 {comp_name} 主流程，补 3 个单测", 0.4),
    ("fix: 修复 {comp_name} 边界问题", "修复 {comp_name} 边界条件 bug，回归通过", 0.2),
    ("refactor: {comp_name} 模块重构", "重构 {comp_name} 模块，代码量减少 30%", 0.3),
    ("perf: 优化 {comp_name} 性能", "{comp_name} 路径 P95 从 X ms 降到 Y ms", 0.4),
    ("test: {comp_name} 覆盖率提升", "{comp_name} 单测覆盖率从 60% 提升到 85%", 0.2),
]

DOC_TEMPLATES = [
    ("{comp_name} 设计文档 v1", "输出 {comp_name} 方向的 RFC/设计文档并挂内部 Wiki", 0.3),
    ("{comp_name} 踩坑总结", "整理 {comp_name} 项目中的 5 个坑点与解决方案", 0.35),
    ("{comp_name} 最佳实践分享", "输出 {comp_name} 方向的最佳实践 playbook", 0.45),
]

LEARNING_TEMPLATES = [
    ("完成 {comp_name} 课程", "完成 {comp_name} 相关课程，打分 {score} 分", 0.25),
    ("阅读 {comp_name} 相关文献", "精读 {comp_name} 方向论文/书籍一篇，做 5 页笔记", 0.2),
    ("搜索 {comp_name} 关键词", "频繁搜索 {comp_name} 相关资料，说明遇到学习触发点", 0.05),
]

MEETING_TEMPLATES = [
    ("{comp_name} 技术评审会", "主导 {comp_name} 方向的技术评审，同步跨组结论", 0.3),
    ("{comp_name} 项目站会", "同步 {comp_name} 项目进度，识别一项阻塞", 0.1),
    ("导师 1:1 | {comp_name}", "与导师讨论 {comp_name} 方向的成长路径", 0.2),
]

FEEDBACK_TEMPLATES = [
    ("季度 OKR 评估：{comp_name}", "{comp_name} 相关 KR 达成 {rate}%", 0.4),
    ("360 反馈：{comp_name}", "同事反馈 {comp_name} 方向值得肯定", 0.3),
    ("绩效面谈：{comp_name} 待提升", "上级指出 {comp_name} 方向需加强", -0.2),
]


TEMPLATE_MAP = {
    "task": TASK_TEMPLATES,
    "code": CODE_TEMPLATES,
    "doc": DOC_TEMPLATES,
    "learning": LEARNING_TEMPLATES,
    "meeting": MEETING_TEMPLATES,
    "feedback": FEEDBACK_TEMPLATES,
}


# ---------------------------------------------------------------- 核心生成

def _weighted_pick(rng: random.Random, competencies: list[dict]) -> dict:
    """按 level × confidence 加权挑选一个 competency，偏向员工的强项（模拟真实工作中的表现）。

    但会以 20% 概率从整体里均匀挑，模拟学习新事物。
    """
    if rng.random() < 0.2 or not competencies:
        return rng.choice(competencies) if competencies else {"competency_id": "C.soft.learn", "level": 3, "confidence": 0.7, "evidence": []}
    weights = [max(c.get("level", 3) * c.get("confidence", 0.7), 0.1) for c in competencies]
    total = sum(weights)
    r = rng.uniform(0, total)
    upto = 0.0
    for c, w in zip(competencies, weights):
        upto += w
        if r <= upto:
            return c
    return competencies[-1]


def _load_competency_name_index() -> dict[str, str]:
    """competency_id → name，用于模板文案替换。"""
    ont = json.loads((ROOT / "data/ontology/competency_ontology.json").read_text(encoding="utf-8"))
    return {c["id"]: c["name"] for c in ont["competencies"]}


def _business_day(d: datetime) -> bool:
    return d.weekday() < 5


def generate_for_employee(
    emp: dict,
    start: datetime,
    end: datetime,
    comp_name_idx: dict[str, str],
    rng: random.Random,
) -> dict[str, list[dict]]:
    """为单个员工生成各 source 事件列表。

    返回 {source: [event_dict, ...]}，事件按 ts 排序。
    """
    eid = emp["employee_id"]
    base = emp.get("base_competencies", [])
    if not base:
        return {s: [] for s in TEMPLATE_MAP}

    events: dict[str, list[dict]] = {s: [] for s in TEMPLATE_MAP}

    d = start
    seq = 0
    while d <= end:
        if _business_day(d):
            day_count = rng.randint(2, 5)
        else:
            day_count = 0 if rng.random() < 0.7 else 1

        for _ in range(day_count):
            source = rng.choices(
                list(TEMPLATE_MAP.keys()),
                weights=[0.30, 0.28, 0.12, 0.10, 0.12, 0.08],  # task/code 最多，feedback 最少
                k=1,
            )[0]
            templates = TEMPLATE_MAP[source]
            tpl_title, tpl_content, base_delta = rng.choice(templates)

            # 选一个 competency
            cm = _weighted_pick(rng, base)
            cid = cm["competency_id"]
            cname = comp_name_idx.get(cid, cid)

            title = tpl_title.format(comp_name=cname)
            content = tpl_content.format(
                comp_name=cname,
                score=rng.randint(70, 98),
                rate=rng.choice([70, 80, 90, 105, 115]),
            )

            # delta_hint: 叠加一个随机扰动 ±0.1
            delta_hint = round(base_delta + rng.uniform(-0.1, 0.1), 2)

            # 给事件加 1-2 个能力标签（主标签 + 可选关联）
            hints = [{
                "competency_id": cid,
                "delta_hint": delta_hint,
                "confidence_hint": round(0.6 + rng.random() * 0.3, 2),
            }]
            if rng.random() < 0.25 and len(base) > 1:
                secondary = rng.choice([c for c in base if c["competency_id"] != cid])
                hints.append({
                    "competency_id": secondary["competency_id"],
                    "delta_hint": round(delta_hint * 0.5, 2),
                    "confidence_hint": round(0.5 + rng.random() * 0.2, 2),
                })

            # 时间点落在工作时间内：9:00-20:00
            ts = d.replace(
                hour=rng.randint(9, 20),
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
                microsecond=0,
            )
            seq += 1
            eid_hash = hashlib.md5(f"{eid}-{seq}-{ts.isoformat()}".encode()).hexdigest()[:8]
            event = {
                "event_id": f"{eid}-{source}-{eid_hash}",
                "employee_id": eid,
                "source": source,
                "ts": ts.isoformat(),
                "title": title,
                "content": content,
                "raw_ref": f"mock://{source}/{eid_hash}",
                "competency_hints": hints,
            }
            events[source].append(event)

        d += timedelta(days=1)

    # 按 ts 排序
    for s in events:
        events[s].sort(key=lambda e: e["ts"])
    return events


# ---------------------------------------------------------------- 入口

def main(months: int = 6, seed: int = 42):
    comp_names = _load_competency_name_index()
    employees = json.loads((ROOT / "data/samples/employees.json").read_text(encoding="utf-8"))

    end = datetime(2026, 4, 25, 23, 0, 0)  # 以项目基准日对齐
    start = end - timedelta(days=30 * months)

    behavior_dir = settings.abs_path(settings.behavior_dir)
    behavior_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for emp in employees:
        eid = emp["employee_id"]
        rng = random.Random(f"{seed}-{eid}")  # 员工级独立种子，保证可复现
        out_dir = behavior_dir / eid
        out_dir.mkdir(parents=True, exist_ok=True)

        events_by_source = generate_for_employee(emp, start, end, comp_names, rng)
        n_emp = 0
        for source, events in events_by_source.items():
            fp = out_dir / f"{source}.jsonl"
            with fp.open("w", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            n_emp += len(events)
        total += n_emp
        logger.info(f"[{eid}] {emp['name']:<4s} | {n_emp:3d} events → {out_dir}")

    logger.info(f"\nTotal events generated: {total} across {len(employees)} employees, {months} months")
    return total


if __name__ == "__main__":
    main()
