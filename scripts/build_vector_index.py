"""构建向量索引：本体 + 七类资源池 → Chroma。

执行：python scripts/build_vector_index.py

默认使用 settings.embedding_provider（bge-m3 本地 / openai / hash 降级）。
Mock/Hash 模式下可零依赖跑通。
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Iterable

from loguru import logger

# 允许从项目根执行
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from src.embedding.embedder import encode, get_embedder  # noqa: E402
from src.vector.chroma_store import get_store  # noqa: E402


# ---------------------------------------------------------------- 加载助手

def load_json(rel: str) -> list | dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def load_csv(rel: str) -> list[dict]:
    with open(ROOT / rel, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _split_list_field(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(";") if x.strip()]


# ---------------------------------------------------------------- 构建逻辑

def index_ontology(store):
    data = load_json(settings.ontology_path)
    items = []
    for c in data["competencies"]:
        doc = f"{c['name']}：{c['description']}"
        if c.get("aliases"):
            doc += f"（别名：{', '.join(c['aliases'])}）"
        items.append({
            "id": c["id"],
            "doc": doc,
            "meta": {
                "name": c["name"],
                "parent_id": c["parent_id"],
                "decay_type": c["decay_type"],
            },
        })
    _bulk_upsert(store, "competency_ontology", items)


def index_courses(store):
    rows = load_csv("data/resources/courses.csv")
    items = []
    for r in rows:
        doc = f"{r['title']}：{r['summary']}（时长 {r['duration_min']} 分钟，{'微课' if r['is_micro'].lower()=='true' else '课程'}）"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["title"],
                "source_type": "course",
                "learning_mode": r["learning_mode"],
                "provider": r["provider"],
                "url": r["url"],
                "duration_min": int(r["duration_min"]),
                "is_micro": r["is_micro"].lower() == "true",
                "level": r["level"],
                "related_competencies": ",".join(_split_list_field(r["related_competencies"])),
            },
        })
    _bulk_upsert(store, "res_course", items)


def index_readings(store):
    rows = load_csv("data/resources/readings.csv")
    items = []
    for r in rows:
        doc = f"{r['title']}（{r['author']}）：{r['summary']}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["title"],
                "source_type": "reading",
                "learning_mode": r["learning_mode"],
                "author": r["author"],
                "url": r["url"],
                "type": r["type"],
                "level": r["level"],
                "related_competencies": ",".join(_split_list_field(r["related_competencies"])),
            },
        })
    _bulk_upsert(store, "res_reading", items)


def index_tools(store):
    rows = load_csv("data/resources/tools.csv")
    items = []
    for r in rows:
        doc = f"{r['name']}（{r['vendor']}，{r['category']}）：{r['summary']}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["name"],
                "source_type": "tool",
                "learning_mode": r["learning_mode"],
                "vendor": r["vendor"],
                "category": r["category"],
                "url": r["url"],
                "related_competencies": ",".join(_split_list_field(r["related_competencies"])),
            },
        })
    _bulk_upsert(store, "res_tool", items)


def index_prompts(store):
    data = load_json("data/resources/prompt_library.json")
    items = []
    for r in data:
        doc = f"{r['title']}（{r['type']}）：{r['summary']}\n{r['content'][:200]}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["title"],
                "source_type": "prompt",
                "learning_mode": r["learning_mode"],
                "type": r["type"],
                "related_competencies": ",".join(r.get("related_competencies", [])),
            },
        })
    _bulk_upsert(store, "res_prompt", items)


def index_projects(store):
    data = load_json("data/resources/internal_projects.json")
    items = []
    for r in data:
        doc = f"[{r['type']}] {r['title']}（{r['owner_team']}，{r['duration_weeks']} 周）：{r['description']}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["title"],
                "source_type": "project",
                "learning_mode": r["learning_mode"],
                "type": r["type"],
                "owner_team": r["owner_team"],
                "duration_weeks": r["duration_weeks"],
                "commitment": r["commitment"],
                "related_competencies": ",".join(r.get("related_competencies", [])),
            },
        })
    _bulk_upsert(store, "res_project", items)


def index_labs(store):
    data = load_json("data/resources/labs.json")
    items = []
    for r in data:
        doc = f"[{r['type']}] {r['title']}：{r['description']}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["title"],
                "source_type": "lab",
                "learning_mode": r["learning_mode"],
                "url": r["url"],
                "related_competencies": ",".join(r.get("related_competencies", [])),
            },
        })
    _bulk_upsert(store, "res_lab", items)


def index_mentors(store):
    data = load_json("data/resources/mentors.json")
    items = []
    for r in data:
        doc = f"{r['name']}（{r['title']}）：{r['bio']}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["name"],
                "source_type": "mentor",
                "learning_mode": r["learning_mode"],
                "employee_id": r["employee_id"],
                "capacity_per_month": r["capacity_per_month"],
                "related_competencies": ",".join(r.get("expert_competencies", [])),
            },
        })
    _bulk_upsert(store, "res_mentor", items)


def index_cases(store):
    data = load_json("data/resources/case_studies.json")
    items = []
    for r in data:
        doc = (
            f"{r['title']}（{r['author']}，{r['date']}）\n"
            f"背景：{r['context']}\n"
            f"做法：{r['approach']}\n"
            f"踩坑：{r['pitfalls']}\n"
            f"结果：{r['outcome']}"
        )
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["title"],
                "source_type": "case",
                "learning_mode": r["learning_mode"],
                "author": r["author"],
                "date": r["date"],
                "related_competencies": ",".join(r.get("related_competencies", [])),
            },
        })
    _bulk_upsert(store, "res_case", items)


def index_talks(store):
    rows = load_csv("data/resources/tech_talks.csv")
    items = []
    for r in rows:
        doc = f"{r['title']}（{r['speaker']}，{r['source']}，{r['duration_min']} min）：{r['summary']}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["title"],
                "source_type": "talk",
                "learning_mode": r["learning_mode"],
                "speaker": r["speaker"],
                "source": r["source"],
                "url": r["url"],
                "duration_min": int(r["duration_min"]),
                "date": r["date"],
                "language": r["language"],
                "related_competencies": ",".join(_split_list_field(r["related_competencies"])),
            },
        })
    _bulk_upsert(store, "res_talk", items)


def index_communities(store):
    data = load_json("data/resources/communities.json")
    items = []
    for r in data:
        doc = f"{r['name']}（{r['type']}，{r['member_count']} 人）：{r['description']}"
        items.append({
            "id": r["resource_id"],
            "doc": doc,
            "meta": {
                "title": r["name"],
                "source_type": "community",
                "learning_mode": r["learning_mode"],
                "platform": r["platform"],
                "url": r["url"],
                "member_count": r["member_count"],
                "related_competencies": ",".join(r.get("related_competencies", [])),
            },
        })
    _bulk_upsert(store, "res_community", items)


def _bulk_upsert(store, collection: str, items: list[dict], batch_size: int = 64):
    if not items:
        logger.warning(f"[{collection}] no items to index")
        return
    t0 = time.time()
    for i in range(0, len(items), batch_size):
        chunk = items[i : i + batch_size]
        docs = [x["doc"] for x in chunk]
        ids = [x["id"] for x in chunk]
        metas = [x["meta"] for x in chunk]
        embs = encode(docs)
        store.upsert(collection, ids=ids, documents=docs, embeddings=embs, metadatas=metas)
    logger.info(f"[{collection}] indexed {len(items)} items in {time.time() - t0:.1f}s")


# ---------------------------------------------------------------- Main

def main():
    logger.info("Embedder warm-up")
    get_embedder()
    store = get_store()

    indexers = [
        index_ontology,
        index_courses,
        index_readings,
        index_tools,
        index_prompts,
        index_projects,
        index_labs,
        index_mentors,
        index_cases,
        index_talks,
        index_communities,
    ]
    for fn in indexers:
        try:
            fn(store)
        except Exception as e:
            logger.exception(f"Indexer {fn.__name__} failed: {e}")

    # 总结
    logger.info("--- Index summary ---")
    for col in [
        "competency_ontology",
        "res_course", "res_reading", "res_tool", "res_prompt",
        "res_project", "res_lab", "res_mentor", "res_case", "res_talk", "res_community",
    ]:
        logger.info(f"  {col:28s} {store.count(col)}")


if __name__ == "__main__":
    main()
