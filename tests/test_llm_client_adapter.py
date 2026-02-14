"""Tests for LLMClientAdapter.

mock-ok: acall_llm makes real API calls — must mock for unit tests.
"""

import os
import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Setup path once at module level
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from Core.Provider.LLMClientAdapter import LLMClientAdapter


@dataclass
class FakeLLMCallResult:
    content: str
    usage: dict
    cost: float
    model: str
    tool_calls: list = None
    finish_reason: str = "stop"
    raw_response: Any = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


FAKE_RESULT = FakeLLMCallResult(
    content="Paris is the capital of France.",
    usage={"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
    cost=0.001,
    model="anthropic/claude-sonnet-4-5-20250929",
)


@pytest.fixture
def adapter():
    """Create LLMClientAdapter without hitting real APIs."""
    return LLMClientAdapter(model="anthropic/claude-sonnet-4-5-20250929")


class TestLLMClientAdapter:

    @pytest.mark.asyncio
    async def test_acompletion_text_returns_string(self, adapter):
        with patch("llm_client.acall_llm", new_callable=AsyncMock, return_value=FAKE_RESULT):
            result = await adapter.acompletion_text(
                [{"role": "user", "content": "What is the capital of France?"}]
            )
            assert isinstance(result, str)
            assert "Paris" in result

    @pytest.mark.asyncio
    async def test_aask_routes_through_acall_llm(self, adapter):
        with patch("llm_client.acall_llm", new_callable=AsyncMock, return_value=FAKE_RESULT) as mock_call:
            result = await adapter.aask("What is the capital of France?")
            assert isinstance(result, str)
            assert "Paris" in result
            mock_call.assert_called()
            call_args = mock_call.call_args
            assert call_args[0][0] == "anthropic/claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    async def test_achat_completion_returns_openai_format(self, adapter):
        with patch("llm_client.acall_llm", new_callable=AsyncMock, return_value=FAKE_RESULT):
            result = await adapter._achat_completion(
                [{"role": "user", "content": "test"}]
            )
            assert "choices" in result
            assert result["choices"][0]["message"]["content"] == FAKE_RESULT.content
            assert result["usage"] == FAKE_RESULT.usage

    @pytest.mark.asyncio
    async def test_acompletion_returns_openai_format(self, adapter):
        with patch("llm_client.acall_llm", new_callable=AsyncMock, return_value=FAKE_RESULT):
            result = await adapter.acompletion(
                [{"role": "user", "content": "test"}]
            )
            text = adapter.get_choice_text(result)
            assert text == FAKE_RESULT.content

    @pytest.mark.asyncio
    async def test_stream_raises_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError, match="non-streaming"):
            await adapter.acompletion_text(
                [{"role": "user", "content": "test"}], stream=True
            )

    @pytest.mark.asyncio
    async def test_stream_completion_raises_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError, match="non-streaming"):
            await adapter._achat_completion_stream(
                [{"role": "user", "content": "test"}]
            )

    def test_model_stored(self, adapter):
        assert adapter.model == "anthropic/claude-sonnet-4-5-20250929"
        assert adapter.config.model == "anthropic/claude-sonnet-4-5-20250929"

    def test_semaphore_default(self, adapter):
        assert adapter.semaphore._value == 5

    def test_custom_concurrency(self):
        a = LLMClientAdapter(model="gpt-4o", max_concurrency=10)
        assert a.semaphore._value == 10
