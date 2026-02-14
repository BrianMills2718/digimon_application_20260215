"""LLMClientAdapter — wraps llm_client.acall_llm behind the BaseLLM interface.

Operators call ctx.llm.aask() unchanged. This adapter routes calls through
llm_client which handles retry, fallback, cost tracking, and model routing.

Usage:
    from Core.Provider.LLMClientAdapter import LLMClientAdapter
    adapter = LLMClientAdapter(model="anthropic/claude-sonnet-4-5-20250929")
    answer = await adapter.aask("What is the capital of France?")
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from Core.Common.Logger import logger
from Core.Provider.BaseLLM import BaseLLM
from Config.LLMConfig import LLMConfig, LLMType


class LLMClientAdapter(BaseLLM):
    """Adapter: makes llm_client look like BaseLLM for operator compatibility.

    BaseLLM.aask() builds messages then calls self.acompletion_text().
    We implement acompletion_text() via llm_client.acall_llm.
    """

    def __init__(self, model: str, **llm_client_kwargs: Any):
        # Build a minimal LLMConfig so BaseLLM fields are satisfied
        self.config = LLMConfig(
            api_type=LLMType.LITELLM,
            model=model,
            api_key="managed-by-llm-client",
        )
        self.model = model
        self._kwargs = llm_client_kwargs
        self.semaphore = asyncio.Semaphore(
            llm_client_kwargs.pop("max_concurrency", 5)
        )
        self.cost_manager = None  # llm_client tracks costs internally
        self.use_system_prompt = True
        self.system_prompt = "You are a helpful assistant."
        self.pricing_plan = model
        self.aclient = None

        logger.info(f"LLMClientAdapter initialized for model: {model}")

    async def _achat_completion(
        self,
        messages: list[dict],
        timeout: int = 60,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Call llm_client.acall_llm and return OpenAI-compatible response dict."""
        from llm_client import acall_llm

        result = await acall_llm(
            self.model,
            messages,
            timeout=timeout,
            **self._kwargs,
        )

        # Convert LLMCallResult to OpenAI-style response dict for get_choice_text()
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": result.content},
                    "finish_reason": result.finish_reason or "stop",
                }
            ],
            "usage": result.usage,
            "model": result.model,
        }

    async def acompletion_text(
        self,
        messages: list[dict],
        stream: bool = False,
        timeout: int = 60,
        max_tokens: Optional[int] = None,
        format: str = "text",
    ) -> str:
        """Return string response via llm_client. Called by BaseLLM.aask()."""
        if stream:
            raise NotImplementedError("Use non-streaming for operator calls")

        from llm_client import acall_llm

        result = await acall_llm(
            self.model,
            messages,
            timeout=timeout,
            **self._kwargs,
        )
        return result.content

    async def acompletion(
        self,
        messages: list[dict],
        timeout: int = 60,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Asynchronous completion returning OpenAI-compatible dict."""
        return await self._achat_completion(
            messages, timeout=timeout, max_tokens=max_tokens, **kwargs
        )

    async def _achat_completion_stream(
        self,
        messages: list[dict],
        timeout: int = 60,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        raise NotImplementedError("Use non-streaming for operator calls")
