"""LLM 客户端抽象层：支持 openai / anthropic / qwen / deepseek / mock。

mock provider 的价值：无需 API Key 即可跑通整条静态链路，便于 CI、离线演示、快速测试。
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import settings  # noqa: E402


@dataclass
class LLMResponse:
    content: str
    raw: Any = None
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------- 抽象接口

class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> LLMResponse:
        ...


# ---------------------------------------------------------------- Mock Provider

class MockProvider(LLMProvider):
    """离线可用的模拟 LLM。

    行为：
    - 对特定任务（画像抽取、Gap 排序、精排解释、归因、路径生成）返回结构正确的伪造 JSON
    - 通过消息内容做关键词匹配决定返回模板
    - 输出稳定可重复：hash(prompt) 作为随机种子
    """

    name = "mock"

    def chat(self, messages: list[dict], *, temperature=None, response_format=None, **kwargs) -> LLMResponse:
        t0 = time.time()
        prompt = "\n".join(m.get("content", "") for m in messages)
        seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        content = self._route(prompt, rng)
        latency = int((time.time() - t0) * 1000)
        return LLMResponse(content=content, latency_ms=latency)

    # -- 路由不同任务类型 --
    def _route(self, prompt: str, rng: random.Random) -> str:
        p = prompt.lower()
        if "employee_profile" in p or "员工画像" in p or "extract_employee" in p:
            return self._mock_extract_employee(prompt, rng)
        if "job_profile" in p or "岗位画像" in p or "extract_job" in p:
            return self._mock_extract_job(prompt, rng)
        if "gap_rank" in p or "gap 排序" in p or "rank_gap" in p:
            return self._mock_rank_gap(prompt, rng)
        if "rerank_resource" in p or "精排" in p:
            return self._mock_rerank(prompt, rng)
        if "generate_pathway" in p or "成长路径" in p:
            return self._mock_pathway(prompt, rng)
        if "attribute_event" in p or "事件归因" in p:
            return self._mock_attribute_event(prompt, rng)
        # 默认：回显+伪 JSON 结构
        return json.dumps({"mock": True, "hint": "generic mock response"}, ensure_ascii=False)

    # --- 下面的 mock 返回都是"结构合法的 JSON"，保证下游 Pydantic 校验通过 ---
    def _mock_extract_employee(self, prompt: str, rng: random.Random) -> str:
        # 尝试从 prompt 中抽取已出现的 competency id
        comp_ids = re.findall(r"C\.[a-z.]+\.[a-z0-9]+", prompt)
        comp_ids = list(dict.fromkeys(comp_ids))[:10] or ["C.hard.prog.py", "C.soft.comm"]
        comps = [
            {
                "competency_id": cid,
                "name": cid.split(".")[-1],
                "level": rng.choice([2, 3, 3, 4]),
                "confidence": round(rng.uniform(0.6, 0.9), 2),
                "evidence": ["mock-evidence-" + cid.split(".")[-1]],
            }
            for cid in comp_ids
        ]
        return json.dumps({"competencies": comps, "summary": "[mock] 员工画像合成摘要"}, ensure_ascii=False)

    def _mock_extract_job(self, prompt: str, rng: random.Random) -> str:
        # mock 只用于扩充 JD 中未显式列出的能力；本 Demo JD 已结构化，暂返回空扩展
        return json.dumps({"additional_competencies": [], "summary": "[mock] 岗位画像摘要"}, ensure_ascii=False)

    def _mock_rank_gap(self, prompt: str, rng: random.Random) -> str:
        # 给 prompt 中出现的 comp_id 打优先级
        comp_ids = re.findall(r"C\.[a-z.]+\.[a-z0-9]+", prompt)
        comp_ids = list(dict.fromkeys(comp_ids))[:10]
        items = [
            {
                "competency_id": cid,
                "priority": rng.choice(["high", "mid", "low"]),
                "rationale": f"[mock] {cid} 优先级分析（模拟）",
            }
            for cid in comp_ids
        ]
        return json.dumps({"ranked": items}, ensure_ascii=False)

    def _mock_rerank(self, prompt: str, rng: random.Random) -> str:
        ids = re.findall(r"[A-Z]+\.\d+", prompt)[:8] or ["COURSE.001"]
        scored = [
            {
                "resource_id": rid,
                "score": round(rng.uniform(0.5, 0.95), 3),
                "rationale": f"[mock] {rid} 与当前 gap 匹配度高",
            }
            for rid in ids
        ]
        return json.dumps({"reranked": scored}, ensure_ascii=False)

    def _mock_pathway(self, prompt: str, rng: random.Random) -> str:
        ids = re.findall(r"[A-Z]+\.\d+", prompt)[:9] or [f"COURSE.{i:03d}" for i in range(1, 10)]
        milestones = []
        for i, phase in enumerate(["30d", "60d", "90d"]):
            milestones.append({
                "phase": phase,
                "title": f"[mock] {phase} 里程碑",
                "description": f"{phase} 阶段核心任务（模拟文本）",
                "target_competencies": [],
                "resources": ids[i * 3 : (i + 1) * 3] or ids[:3],
            })
        return json.dumps({"milestones": milestones}, ensure_ascii=False)

    def _mock_attribute_event(self, prompt: str, rng: random.Random) -> str:
        comp_ids = re.findall(r"C\.[a-z.]+\.[a-z0-9]+", prompt)
        comp_ids = list(dict.fromkeys(comp_ids))[:3] or ["C.hard.prog.py"]
        deltas = [
            {
                "competency_id": cid,
                "delta_level": round(rng.uniform(-0.3, 0.5), 2),
                "confidence": round(rng.uniform(0.5, 0.9), 2),
                "rationale": f"[mock] 事件对 {cid} 的影响（模拟）",
            }
            for cid in comp_ids
        ]
        return json.dumps({"deltas": deltas}, ensure_ascii=False)


# ---------------------------------------------------------------- OpenAI / Anthropic 等

class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self):
        from openai import OpenAI
        kwargs = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self.client = OpenAI(**kwargs)
        self.model = settings.llm_model

    def chat(self, messages, *, temperature=None, response_format=None, **kwargs):
        t0 = time.time()
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
        }
        if response_format:
            params["response_format"] = response_format
        resp = self.client.chat.completions.create(**params)
        content = resp.choices[0].message.content or ""
        latency = int((time.time() - t0) * 1000)
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            content=content,
            raw=resp,
            latency_ms=latency,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.llm_api_key)
        self.model = settings.llm_model

    def chat(self, messages, *, temperature=None, response_format=None, **kwargs):
        t0 = time.time()
        # Anthropic API 需要 system / user 分离
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        resp = self.client.messages.create(
            model=self.model,
            system=system,
            messages=user_msgs,
            max_tokens=4096,
            temperature=temperature if temperature is not None else settings.llm_temperature,
        )
        content = resp.content[0].text if resp.content else ""
        latency = int((time.time() - t0) * 1000)
        return LLMResponse(content=content, raw=resp, latency_ms=latency)


# ---------------------------------------------------------------- 工厂 + 重试

_provider_cache: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache
    p = settings.llm_provider
    if p == "mock":
        _provider_cache = MockProvider()
    elif p == "openai" or p == "qwen" or p == "deepseek":
        # qwen / deepseek 都是 OpenAI 兼容协议，只是 base_url 不同
        _provider_cache = OpenAIProvider()
    elif p == "anthropic":
        _provider_cache = AnthropicProvider()
    else:
        logger.warning(f"Unknown provider {p}, falling back to mock")
        _provider_cache = MockProvider()
    logger.info(f"LLM provider initialized: {_provider_cache.name}")
    return _provider_cache


def chat(
    messages: list[dict],
    *,
    temperature: float | None = None,
    response_format: dict | None = None,
    retries: int | None = None,
) -> LLMResponse:
    """带重试的统一 chat 入口。"""
    provider = get_provider()
    max_retries = retries if retries is not None else settings.llm_max_retries
    last_err = None
    for attempt in range(max_retries):
        try:
            return provider.chat(messages, temperature=temperature, response_format=response_format)
        except Exception as e:
            last_err = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"LLM call exhausted retries: {last_err}")


def chat_json(messages: list[dict], **kwargs) -> dict:
    """让 LLM 返回 JSON 并解析。支持 mock / openai json_object 响应格式。"""
    resp = chat(
        messages,
        response_format={"type": "json_object"} if settings.llm_provider in ("openai", "qwen", "deepseek") else None,
        **kwargs,
    )
    content = resp.content.strip()
    # 剥去可能的 ```json ``` 代码块
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"JSON decode failed, raw content: {content[:200]}")
        # 再尝试提取第一个 JSON 对象
        m = re.search(r"\{.*\}", content, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise
