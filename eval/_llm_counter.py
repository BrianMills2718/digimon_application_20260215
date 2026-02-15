"""LLM call counter wrapper for benchmarking.

Wraps a BaseLLM instance to count calls and track token usage.
Thread-safe for async usage.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMStats:
    """Accumulated LLM usage stats."""
    n_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, input_tokens: int = 0, output_tokens: int = 0):
        with self._lock:
            self.n_calls += 1
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens

    def reset(self):
        with self._lock:
            self.n_calls = 0
            self.total_input_tokens = 0
            self.total_output_tokens = 0

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "n_llm_calls": self.n_calls,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": self.total_input_tokens + self.total_output_tokens,
            }


class CountingLLMWrapper:
    """Wraps a BaseLLM to count calls and tokens.

    Proxies all attributes to the wrapped LLM. Intercepts aask() to count.
    """

    def __init__(self, wrapped_llm: Any):
        self._wrapped = wrapped_llm
        self.stats = LLMStats()

    async def aask(self, *args, **kwargs):
        result = await self._wrapped.aask(*args, **kwargs)

        # Estimate tokens from input/output
        # Most LLM providers return usage in the response metadata
        # For litellm: check if there's a _last_response with usage
        input_tokens = 0
        output_tokens = 0

        # Try to get actual token counts from litellm's response tracking
        if hasattr(self._wrapped, '_last_usage'):
            usage = self._wrapped._last_usage
            input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
            output_tokens = getattr(usage, 'completion_tokens', 0) or 0

        # Fallback: estimate from string lengths (~4 chars per token)
        if input_tokens == 0:
            msg = args[0] if args else kwargs.get('msg', '')
            if isinstance(msg, str):
                input_tokens = len(msg) // 4
            elif isinstance(msg, list):
                input_tokens = sum(len(str(m.get('content', ''))) for m in msg) // 4

        if output_tokens == 0 and isinstance(result, str):
            output_tokens = len(result) // 4

        self.stats.record(input_tokens, output_tokens)
        return result

    def __getattr__(self, name):
        """Proxy all other attributes to the wrapped LLM."""
        return getattr(self._wrapped, name)
