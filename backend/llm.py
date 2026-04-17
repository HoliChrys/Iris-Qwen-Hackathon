"""
LLM service for IRIS reporting — Alibaba Cloud DashScope (qwen3.6-plus).

OpenAI-compatible API — uses AsyncOpenAI directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Alibaba Cloud DashScope
API_KEY = os.environ["DASHSCOPE_API_KEY"]
BASE_URL = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
MODEL = os.environ.get("DASHSCOPE_MODEL", "qwen3.6-plus")

MAX_CONCURRENT = 5
MAX_RETRIES = 3
RETRY_BACKOFF = 2

_client = None
_semaphore: asyncio.Semaphore | None = None


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


async def chat_completion(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    model: str = MODEL,
    temperature: float = 0.7,
) -> dict:
    """Chat completion via Alibaba Cloud DashScope (OpenAI-compatible)."""
    client = _get_client()
    sem = _get_semaphore()

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        # Force tool invocation — skill prompts are instructive but qwen3.6-plus
        # may otherwise emit conversational text. "required" + enable_thinking=False
        # is the only combo that reliably triggers tool_calls with this model.
        kwargs["tool_choice"] = "required"
        kwargs["extra_body"] = {"enable_thinking": False}

    async with sem:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.chat.completions.create(**kwargs)
                choice = response.choices[0]

                result: dict = {
                    "content": choice.message.content or "",
                    "role": "assistant",
                }

                if choice.message.tool_calls:
                    result["tool_calls"] = [
                        {
                            "id": tc.id,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in choice.message.tool_calls
                    ]

                return result

            except Exception as e:
                if "429" in str(e) and attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (attempt + 1)
                    logger.warning("LLM 429, retry %d/%d in %ds", attempt + 1, MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                    continue
                raise

    return {"content": "", "role": "assistant"}
