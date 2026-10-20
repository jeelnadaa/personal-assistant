"""Unit tests for Jarvis tools system and Phase 1 tools."""

from unittest.mock import patch
import pytest

from jarvis.tools import get_tool, get_tool_schemas, run_tool
from jarvis.tools.base import ToolResult, tool
from jarvis.tools.system import get_system_info
from jarvis.tools.web import open_url


def test_tool_registry_and_schema():
    """Verifies that tools are registered and schemas match Anthropic format."""
    schemas = get_tool_schemas()
    names = [s["name"] for s in schemas]

    assert "open_app" in names
    assert "get_system_info" in names
    assert "open_url" in names

    sys_tool = get_tool("get_system_info")
    assert sys_tool is not None
    assert sys_tool.name == "get_system_info"
    assert "CPU" in sys_tool.description


def test_get_system_info_real_execution():
    """Verifies get_system_info executes and returns system metrics."""
    result = get_system_info()
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert "Date:" in result.output
    assert "Time:" in result.output
    assert "CPU Usage:" in result.output
    assert "RAM Usage:" in result.output


def test_open_url_execution():
    """Verifies open_url formats URLs and calls webbrowser.open."""
    with patch("webbrowser.open", return_value=True) as mock_open:
        res = open_url(url="google.com")
        assert res.ok is True
        assert "https://google.com" in res.output
        mock_open.assert_called_once_with("https://google.com")


def test_run_tool_unknown_name():
    """Verifies run_tool gracefully handles unknown tool names."""
    res = run_tool("nonexistent_tool_xyz", {})
    assert res.ok is False
    assert "Unknown tool" in res.output


def test_run_tool_missing_required_args():
    """Verifies run_tool rejects calls missing required parameters."""
    res = run_tool("open_app", {})
    assert res.ok is False
    assert "Missing required parameter" in res.output


def test_run_tool_output_truncation():
    """Verifies run_tool truncates outputs longer than 2000 characters."""

    @tool(
        name="test_long_output_tool",
        description="Generates very long text",
        input_schema={"type": "object", "properties": {}},
    )
    def dummy_long() -> ToolResult:
        return ToolResult(ok=True, output="X" * 3000)

    res = run_tool("test_long_output_tool", {})
    assert res.ok is True
    assert len(res.output) <= 2000
    assert res.output.endswith("...")
