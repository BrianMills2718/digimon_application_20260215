"""
Integration test fixtures requiring heavy Core imports.

These imports pull in LiteLLM, tiktoken, NetworkX, etc. — kept out of
the root conftest so unit tests can collect without those dependencies.
"""

from unittest.mock import Mock, AsyncMock

import pytest

from Config.LLMConfig import LLMConfig
from Core.Provider.LiteLLMProvider import LiteLLMProvider
from Core.AgentSchema.context import GraphRAGContext
from Core.AgentOrchestrator.orchestrator import AgentOrchestrator


@pytest.fixture
def mock_llm_config():
    """Mock LLM configuration for testing."""
    return LLMConfig(
        api_type="litellm",
        model="openai/gpt-3.5-turbo",
        api_key="test-key",
        base_url="http://localhost:11434",
        temperature=0.0,
        max_token=1000,
        calc_usage=False
    )


@pytest.fixture
def mock_llm_provider(mock_llm_config):
    """Mock LLM provider that doesn't make real API calls."""
    provider = LiteLLMProvider(mock_llm_config)

    provider.acompletion = AsyncMock(return_value=Mock(
        choices=[Mock(message=Mock(content="Test response"))]
    ))
    provider.async_instructor_completion = AsyncMock()
    provider._achat_completion = AsyncMock(return_value=Mock(
        choices=[Mock(message=Mock(content="Test response"))]
    ))

    return provider


@pytest.fixture
def mock_context():
    """Mock GraphRAG context for testing."""
    return GraphRAGContext(
        corpus_name="test_corpus",
        dataset_name="test_dataset",
        graph_id="test_graph",
        vdb_collection_name="test_vdb"
    )


@pytest.fixture
def mock_orchestrator(mock_context):
    """Mock agent orchestrator for testing."""
    orchestrator = Mock(spec=AgentOrchestrator)
    orchestrator.context = mock_context
    orchestrator.execute_plan = AsyncMock(return_value={"status": "success"})
    orchestrator.execute_tool = AsyncMock(return_value={"result": "test"})
    return orchestrator
