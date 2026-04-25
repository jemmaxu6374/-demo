"""Embedding 抽象：优先 bge-m3 本地；无法加载时降级到确定性哈希向量。"""
from __future__ import annotations

import hashlib
import math
from typing import Sequence

from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import settings  # noqa: E402


class _Embedder:
    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbedder(_Embedder):
    """确定性哈希向量，仅保证单测与 mock 模式可跑。

    向量维度 = settings.embedding_dim；不承担语义相似度，只保证同文本向量一致。
    """

    name = "hash"

    def __init__(self, dim: int | None = None):
        self.dim = dim or settings.embedding_dim

    def encode(self, texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            # 把 sha256 32 字节扩展到 dim 维，再做 L2 归一化
            vec = [((h[i % len(h)] / 255) * 2 - 1) for i in range(self.dim)]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class BgeM3Embedder(_Embedder):
    name = "bge-m3"

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer  # lazy import
        self.model_name = model_name or settings.embedding_model
        logger.info(f"Loading sentence-transformers model: {self.model_name} (首次会较慢)")
        self.model = SentenceTransformer(self.model_name)

    def encode(self, texts):
        embs = self.model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return [e.tolist() for e in embs]


class OpenAIEmbedder(_Embedder):
    name = "openai"

    def __init__(self):
        from openai import OpenAI
        kwargs = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self.client = OpenAI(**kwargs)
        self.model = settings.openai_embedding_model

    def encode(self, texts):
        resp = self.client.embeddings.create(model=self.model, input=list(texts))
        return [d.embedding for d in resp.data]


_embedder: _Embedder | None = None


def get_embedder() -> _Embedder:
    global _embedder
    if _embedder is not None:
        return _embedder
    provider = settings.embedding_provider
    try:
        if provider == "bge-m3":
            _embedder = BgeM3Embedder()
        elif provider == "openai":
            _embedder = OpenAIEmbedder()
        else:
            logger.warning(f"Unknown embedding provider {provider}, fallback to hash")
            _embedder = HashEmbedder()
    except Exception as e:
        logger.warning(f"Embedder init failed ({e}), fallback to HashEmbedder")
        _embedder = HashEmbedder()
    logger.info(f"Embedder ready: {_embedder.name}")
    return _embedder


def encode(texts: Sequence[str]) -> list[list[float]]:
    return get_embedder().encode(texts)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return s / (na * nb)
