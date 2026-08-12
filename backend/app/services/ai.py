from __future__ import annotations

import logging

import httpx
import numpy as np
from numpy.linalg import norm

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fixed vector size stored in Qdrant. Real embedding models (e.g. Ollama's
# nomic-embed-text, 768-dim) and the offline hash fallback can produce
# vectors of different lengths, so every vector is padded/truncated to this
# size before being used for similarity search or written to Qdrant.
EMBEDDING_DIM = 768


def _to_fixed_dim(vec: np.ndarray, dim: int = EMBEDDING_DIM) -> np.ndarray:
    if vec.shape[0] == dim:
        return vec
    if vec.shape[0] > dim:
        return vec[:dim]
    padded = np.zeros(dim, dtype=np.float32)
    padded[: vec.shape[0]] = vec
    return padded


def _ollama_embed(text: str) -> list[float] | None:
    try:
        r = httpx.post(
            f"{settings.ollama_host}/api/embeddings",
            json={"model": settings.ollama_embed_model, "prompt": text},
            timeout=settings.ollama_timeout,
        )
        r.raise_for_status()
        return r.json().get("embedding")
    except Exception:
        return None


def _ollama_chat(messages: list[dict]) -> str | None:
    try:
        r = httpx.post(
            f"{settings.ollama_host}/api/chat",
            json={"model": settings.ollama_chat_model, "messages": messages, "stream": False},
            timeout=settings.ollama_timeout,
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content")
    except Exception:
        return None


def _groq_chat(messages: list[dict]) -> str | None:
    if not settings.groq_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={"model": settings.groq_chat_model, "messages": messages},
            timeout=settings.groq_timeout,
        )
        r.raise_for_status()
        choices = r.json().get("choices", [])
        return choices[0]["message"]["content"] if choices else None
    except Exception:
        logger.exception("Groq chat call failed, falling back to offline reply")
        return None


def _groq_chat_with_tools(messages: list[dict], tools: list[dict]) -> dict | None:
    if not settings.groq_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={"model": settings.groq_chat_model, "messages": messages, "tools": tools},
            timeout=settings.groq_timeout,
        )
        r.raise_for_status()
        choices = r.json().get("choices", [])
        if not choices:
            return None
        message = choices[0]["message"]
        return {"content": message.get("content"), "tool_calls": message.get("tool_calls")}
    except Exception:
        logger.exception("Groq structured tool-call chat failed, falling back to text parsing/offline reply")
        return None


def _jina_embed(text: str) -> list[float] | None:
    if not settings.jina_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.jina.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.jina_api_key}"},
            json={
                "model": settings.jina_embed_model,
                "task": "text-matching",
                "dimensions": EMBEDDING_DIM,
                "input": [text],
            },
            timeout=settings.jina_timeout,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        return data[0]["embedding"] if data else None
    except Exception:
        logger.exception("Jina embeddings call failed, falling back to offline hash embedding")
        return None


def chat_with_tools(messages: list[dict], tools: list[dict]) -> dict:
    """Structured function-calling when the active provider supports it.

    Ollama - the primary/local provider - is tried first as plain chat:
    small local models don't reliably honor a `tools=` parameter, so this
    deliberately doesn't ask Ollama for structured calls, it just returns
    its text reply for the caller to parse with the existing ReAct text
    format (Thought/Action/Observation). Only once Ollama is unreachable
    (Groq becomes the active provider, e.g. in production) does this
    attempt genuine JSON tool-calling via Groq's OpenAI-compatible `tools=`
    parameter, reading structured `tool_calls` instead of regex-parsing
    free text.

    Returns {"content": str | None, "tool_calls": list[dict] | None}.
    """
    text = _ollama_chat(messages)
    if text:
        return {"content": text, "tool_calls": None}
    structured = _groq_chat_with_tools(messages, tools)
    if structured:
        return structured
    return {"content": _offline_fallback(messages), "tool_calls": None}


def embed_text(text: str) -> np.ndarray:
    vec = _ollama_embed(text)
    if vec is not None:
        return _to_fixed_dim(np.array(vec, dtype=np.float32))
    vec = _jina_embed(text)
    if vec is not None:
        return _to_fixed_dim(np.array(vec, dtype=np.float32))
    return _to_fixed_dim(_hash_embed(text, dim=EMBEDDING_DIM))


def chat(messages: list[dict]) -> str:
    result = _ollama_chat(messages)
    if result:
        return result
    result = _groq_chat(messages)
    if result:
        return result
    return _offline_fallback(messages)


def _hash_embed(text: str, dim: int = 256) -> np.ndarray:
    import hashlib
    import re
    vec = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    if not tokens:
        return vec
    for t in tokens:
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign
    n = norm(vec)
    return vec / n if n > 0 else vec


def _offline_fallback(messages: list[dict]) -> str:
    last = messages[-1]["content"] if messages else ""
    return f"[Offline] Cannot answer without an LLM. Received question: {last[:200]}"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = norm(a) * norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0
