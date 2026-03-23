"""Tests for the execute_operator_chain PTC tool.

Verifies code execution, stdout capture, async operator calls, intermediate
variable isolation, error handling, and json availability.

All tests mock operator functions -- no running MCP server or real LLM calls needed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest


def _make_exec_fn(namespace_overrides: dict[str, Any] | None = None):
    """Build a standalone execute function that mimics execute_operator_chain.

    Uses the same exec-and-capture pattern as the real tool but with
    a controllable namespace. This avoids importing the full MCP server module
    (which requires DIGIMON config, graph context, etc.).

    Args:
        namespace_overrides: Extra names to inject into the exec namespace
            (e.g. mock operator functions).

    Returns:
        Async callable that takes code (str) and returns captured output (str).
    """
    import builtins
    import io
    import traceback

    async def execute(code: str) -> str:
        """Execute code and return captured stdout, same as the real tool."""
        namespace: dict[str, Any] = {"json": json, "__builtins__": {}}

        # Safe builtins
        safe_builtins = [
            "print", "len", "range", "enumerate", "zip", "map", "filter",
            "sorted", "reversed", "list", "dict", "set", "tuple", "str",
            "int", "float", "bool", "isinstance", "type", "hasattr", "getattr",
            "min", "max", "sum", "any", "all", "abs", "round",
            "ValueError", "TypeError", "KeyError", "IndexError", "Exception",
        ]
        for name in safe_builtins:
            obj = getattr(builtins, name, None)
            if obj is not None:
                namespace["__builtins__"][name] = obj  # type: ignore[index]

        if namespace_overrides:
            namespace.update(namespace_overrides)

        captured = io.StringIO()

        indented_code = "\n".join("    " + line for line in code.splitlines())
        wrapped = f"async def _ptc_main():\n{indented_code}\n"

        try:
            exec(compile(wrapped, "<test_execute>", "exec"), namespace)

            original_print = namespace["__builtins__"]["print"]

            def captured_print(*args: object, **kwargs: object) -> None:
                kwargs["file"] = captured  # type: ignore[assignment]
                original_print(*args, **kwargs)

            namespace["print"] = captured_print

            exec(compile(wrapped, "<test_execute>", "exec"), namespace)
            main_fn = namespace["_ptc_main"]
            await main_fn()
        except Exception:
            captured.write(traceback.format_exc())

        result = captured.getvalue()
        return result if result else "(no output -- did you forget to print()?)"

    return execute


# ---- Tests ----

class TestSimpleExecution:
    """Basic code execution and stdout capture."""

    @pytest.mark.asyncio
    async def test_simple_print(self) -> None:
        """Execute print('hello') and verify output."""
        execute = _make_exec_fn()
        result = await execute('print("hello")')
        assert result.strip() == "hello"

    @pytest.mark.asyncio
    async def test_multiline_code(self) -> None:
        """Execute multi-line code with variables."""
        execute = _make_exec_fn()
        code = 'x = 2 + 3\nprint(f"result={x}")'
        result = await execute(code)
        assert result.strip() == "result=5"

    @pytest.mark.asyncio
    async def test_no_output_message(self) -> None:
        """Code with no print() returns a helpful message."""
        execute = _make_exec_fn()
        result = await execute("x = 42")
        assert "no output" in result.lower()


class TestAwaitOperatorCall:
    """Verify async operator calls work via await."""

    @pytest.mark.asyncio
    async def test_await_tool_call(self) -> None:
        """Mock an operator, execute code that awaits it, verify result."""
        mock_search = AsyncMock(
            return_value=json.dumps({"similar_entities": [{"entity_name": "TestCo", "score": 0.95}]})
        )
        execute = _make_exec_fn({"entity_vdb_search": mock_search})

        code = (
            'result = await entity_vdb_search(query_text="TestCo")\n'
            "parsed = json.loads(result)\n"
            'print(parsed["similar_entities"][0]["entity_name"])'
        )
        result = await execute(code)
        assert result.strip() == "TestCo"
        mock_search.assert_awaited_once_with(query_text="TestCo")

    @pytest.mark.asyncio
    async def test_chained_await_calls(self) -> None:
        """Chain two mock operators, verify both are called and result is correct."""
        mock_search = AsyncMock(
            return_value=json.dumps({"similar_entities": [{"entity_name": "A"}, {"entity_name": "B"}]})
        )
        mock_rels = AsyncMock(
            return_value=json.dumps({"relationships": [{"src": "A", "tgt": "C", "type": "works_at"}]})
        )
        execute = _make_exec_fn({
            "entity_vdb_search": mock_search,
            "relationship_onehop": mock_rels,
        })

        code = (
            'entities = json.loads(await entity_vdb_search(query_text="test"))\n'
            'names = [e["entity_name"] for e in entities["similar_entities"]]\n'
            'rels = json.loads(await relationship_onehop(entity_ids=names, graph_reference_id=""))\n'
            'print(len(rels["relationships"]))'
        )
        result = await execute(code)
        assert result.strip() == "1"
        mock_search.assert_awaited_once()
        mock_rels.assert_awaited_once()


class TestIntermediatesNotInOutput:
    """Verify only print() output is returned, not intermediate values."""

    @pytest.mark.asyncio
    async def test_intermediates_not_in_output(self) -> None:
        """Execute chain with intermediates, verify only print output returned."""
        mock_search = AsyncMock(
            return_value=json.dumps({"similar_entities": [{"entity_name": "Secret", "score": 0.9}]})
        )
        execute = _make_exec_fn({"entity_vdb_search": mock_search})

        code = (
            'raw = await entity_vdb_search(query_text="secret")\n'
            'parsed = json.loads(raw)\n'
            'intermediate_list = parsed["similar_entities"]\n'
            'final = len(intermediate_list)\n'
            'print(f"count={final}")'
        )
        result = await execute(code)
        # Only the print output, not the raw JSON or intermediate data
        assert result.strip() == "count=1"
        # Make sure the raw entity data didn't leak into the output
        assert "Secret" not in result
        assert "similar_entities" not in result


class TestErrorHandling:
    """Verify error traceback is returned on failure."""

    @pytest.mark.asyncio
    async def test_error_returns_traceback(self) -> None:
        """Execute code that raises and verify traceback text is returned."""
        execute = _make_exec_fn()
        result = await execute('raise ValueError("deliberate test error")')
        assert "ValueError" in result
        assert "deliberate test error" in result

    @pytest.mark.asyncio
    async def test_syntax_error(self) -> None:
        """Malformed code returns error information."""
        execute = _make_exec_fn()
        result = await execute("def incomplete(")
        assert "SyntaxError" in result or "Error" in result

    @pytest.mark.asyncio
    async def test_operator_error_captured(self) -> None:
        """An operator that raises has its error captured in output."""
        mock_failing = AsyncMock(side_effect=RuntimeError("graph not loaded"))
        execute = _make_exec_fn({"entity_vdb_search": mock_failing})

        code = 'result = await entity_vdb_search(query_text="test")\nprint(result)'
        result = await execute(code)
        assert "RuntimeError" in result
        assert "graph not loaded" in result


class TestJsonAvailable:
    """Verify json module is available in the exec namespace."""

    @pytest.mark.asyncio
    async def test_json_loads(self) -> None:
        """json.loads works in exec context."""
        execute = _make_exec_fn()
        code = (
            'data = json.loads(\'{"key": "value"}\')\n'
            'print(data["key"])'
        )
        result = await execute(code)
        assert result.strip() == "value"

    @pytest.mark.asyncio
    async def test_json_dumps(self) -> None:
        """json.dumps works in exec context."""
        execute = _make_exec_fn()
        code = (
            'output = json.dumps({"a": 1, "b": 2})\n'
            "print(output)"
        )
        result = await execute(code)
        parsed = json.loads(result.strip())
        assert parsed == {"a": 1, "b": 2}
