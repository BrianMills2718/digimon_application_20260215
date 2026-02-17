"""LLMClientAdapter — wraps llm_client.acall_llm behind the BaseLLM interface.

Operators call ctx.llm.aask() unchanged. This adapter routes calls through
llm_client which handles retry, fallback, cost tracking, and model routing.

Usage:
    from Core.Provider.LLMClientAdapter import LLMClientAdapter

    # Basic (same as before)
    adapter = LLMClientAdapter(model="anthropic/claude-sonnet-4-5-20250929")

    # With fallback chain and retry for graph building
    adapter = LLMClientAdapter(
        model="gemini/gemini-2.5-flash",
        fallback_models=["deepseek/deepseek-chat", "openai/gpt-4o-mini"],
        num_retries=3,
    )
    answer = await adapter.aask("What is the capital of France?")
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from Core.Common.Logger import logger
from Core.Provider.BaseLLM import BaseLLM
from Config.LLMConfig import LLMConfig, LLMType


class LLMClientAdapter(BaseLLM):
    """Adapter: makes llm_client look like BaseLLM for operator compatibility.

    BaseLLM.aask() builds messages then calls self.acompletion_text().
    We implement acompletion_text() via llm_client.acall_llm.
    """

    def __init__(
        self,
        model: str,
        *,
        fallback_models: List[str] | None = None,
        num_retries: int = 2,
        max_concurrency: int = 5,
        **llm_client_kwargs: Any,
    ):
        # Build a minimal LLMConfig so BaseLLM fields are satisfied
        self.config = LLMConfig(
            api_type=LLMType.LITELLM,
            model=model,
            api_key="managed-by-llm-client",
        )
        self.model = model
        self._fallback_models = fallback_models or []
        self._num_retries = num_retries
        self._kwargs = llm_client_kwargs
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.cost_manager = None  # llm_client tracks costs internally
        self.use_system_prompt = True
        self.system_prompt = "You are a helpful assistant."
        self.pricing_plan = model
        self.aclient = None

        self._task: str | None = None
        self._trace_id: str | None = None

        fb_info = f", fallbacks={self._fallback_models}" if self._fallback_models else ""
        logger.info(f"LLMClientAdapter initialized: {model}{fb_info}, retries={num_retries}")

    def set_task(self, task: str | None) -> None:
        """Set the task label for io_log tagging on subsequent LLM calls."""
        self._task = task

    def set_trace_id(self, trace_id: str | None) -> None:
        """Set the trace_id for correlating all LLM calls in a query."""
        self._trace_id = trace_id

    async def _achat_completion(
        self,
        messages: list[dict],
        timeout: int = 60,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Call llm_client.acall_llm and return OpenAI-compatible response dict."""
        from llm_client import acall_llm

        call_kwargs = {**self._kwargs}
        if self._fallback_models:
            call_kwargs["fallback_models"] = self._fallback_models
        call_kwargs["num_retries"] = self._num_retries

        result = await acall_llm(
            self.model,
            messages,
            timeout=timeout,
            task=self._task,
            trace_id=self._trace_id,
            **call_kwargs,
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

        call_kwargs = {**self._kwargs}
        if self._fallback_models:
            call_kwargs["fallback_models"] = self._fallback_models
        call_kwargs["num_retries"] = self._num_retries

        if format == "json":
            call_kwargs["response_format"] = {"type": "json_object"}

        result = await acall_llm(
            self.model,
            messages,
            timeout=timeout,
            task=self._task,
            trace_id=self._trace_id,
            **call_kwargs,
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
