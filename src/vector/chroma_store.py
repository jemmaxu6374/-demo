"""ChromaDB 封装：多 collection 存储资源池与能力本体的向量。"""
from __future__ import annotations

from typing import Iterable, Sequence

from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import settings  # noqa: E402


class ChromaStore:
    """薄封装：upsert + query，支持 metadata 过滤。

    每种资源使用独立 collection，方便按 learning_mode 筛选。
    collection 列表：
      - competency_ontology
      - res_course / res_reading / res_tool / res_prompt
      - res_project / res_lab / res_mentor / res_case / res_talk / res_community
    """

    def __init__(self, path: str | None = None):
        import chromadb
        path = path or str(settings.abs_path(settings.vector_store_path))
        Path(path).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=path)
        logger.info(f"Chroma persistent client @ {path}")

    def get_or_create(self, name: str):
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        collection: str,
        ids: Sequence[str],
        documents: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict] | None = None,
    ):
        col = self.get_or_create(collection)
        col.upsert(
            ids=list(ids),
            documents=list(documents),
            embeddings=[list(e) for e in embeddings],
            metadatas=list(metadatas) if metadatas else None,
        )

    def query(
        self,
        collection: str,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[list[dict]]:
        """返回 [ [ {id, document, metadata, distance}, ... ] ]。外层按查询数，内层按召回数。"""
        col = self.get_or_create(collection)
        res = col.query(
            query_embeddings=[list(e) for e in query_embeddings],
            n_results=n_results,
            where=where,
        )
        out = []
        for i in range(len(res["ids"])):
            out.append([
                {
                    "id": res["ids"][i][j],
                    "document": res["documents"][i][j] if res.get("documents") else None,
                    "metadata": res["metadatas"][i][j] if res.get("metadatas") else {},
                    "distance": res["distances"][i][j] if res.get("distances") else None,
                }
                for j in range(len(res["ids"][i]))
            ])
        return out

    def count(self, collection: str) -> int:
        return self.get_or_create(collection).count()


_store: ChromaStore | None = None


def get_store() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store
