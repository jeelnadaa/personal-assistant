"""Base tool definitions, registry, decorator, and execution framework for Jarvis.

All tools define schemas, execution functions, safety levels, and register
themselves in the global tool registry.
"""

from dataclasses import dataclass
from typing import Any, Callable
import inspect

from jarvis.logger import logger
from jarvis.safety.audit import log_tool_execution


@dataclass
class ToolResult:
    """Represents the execution outcome of a tool."""

    ok: bool
    output: str
    image_path: str | None = None


@dataclass
class Tool:
    """Metadata and execution callable for an AI-invokable tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    func: Callable[..., ToolResult]
    dangerous: bool = False
    category: str = "general"


# Global registry of all registered tools
_TOOL_REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    dangerous: bool = False,
    category: str = "general",
) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
    """Decorator to register a function as a Jarvis tool.

    Args:
        name: Unique snake_case name of the tool.
        description: Description explaining to the LLM what the tool does and when to use it.
        input_schema: JSON Schema describing the input parameters.
        dangerous: Whether this tool requires user confirmation before execution.
        category: Logical grouping category.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        t = Tool(
            name=name,
            description=description.strip(),
            input_schema=input_schema,
            func=func,
            dangerous=dangerous,
            category=category,
        )
        _TOOL_REGISTRY[name] = t
        return func

    return decorator


def get_tool(name: str) -> Tool | None:
    """Retrieves a registered tool by name."""
    return _TOOL_REGISTRY.get(name)


def get_all_tools() -> dict[str, Tool]:
    """Returns a copy of all registered tools."""
    return dict(_TOOL_REGISTRY)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Returns tool schemas in Anthropic's tool format (name, description, input_schema)."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in _TOOL_REGISTRY.values()
    ]


def run_tool(name: str, args: dict[str, Any] | None = None) -> ToolResult:
    """Executes a registered tool by name with provided arguments safely.

    Validates schema requirements, wraps execution in try/except,
    truncates output to 2000 characters, and logs to the audit log.

    Args:
        name: Tool name to execute.
        args: Dictionary of arguments.

    Returns:
        ToolResult with execution status and output message.
    """
    if args is None:
        args = {}

    tool_obj = _TOOL_REGISTRY.get(name)
    if not tool_obj:
        msg = f"Unknown tool: '{name}'"
        log_tool_execution(tool_name=name, args=args, ok=False, output=msg)
        return ToolResult(ok=False, output=msg)

    # Validate required parameters from schema
    required_params = tool_obj.input_schema.get("required", [])
    missing = [param for param in required_params if param not in args]
    if missing:
        msg = f"Missing required parameter(s) for '{name}': {', '.join(missing)}"
        log_tool_execution(tool_name=name, args=args, ok=False, output=msg)
        return ToolResult(ok=False, output=msg)

    try:
        # Check callable parameters
        sig = inspect.signature(tool_obj.func)
        bound_args = sig.bind_partial(**args)
        bound_args.apply_defaults()

        result = tool_obj.func(**bound_args.arguments)
        if not isinstance(result, ToolResult):
            result = ToolResult(ok=True, output=str(result))

    except Exception as exc:
        logger.exception("Error executing tool '%s' with args %s", name, args)
        result = ToolResult(ok=False, output=f"Error executing {name}: {str(exc)}")

    # Truncate output to 2000 characters to keep LLM context clean
    if len(result.output) > 2000:
        result.output = result.output[:1997] + "..."

    log_tool_execution(
        tool_name=name,
        args=args,
        ok=result.ok,
        output=result.output,
    )
    return result
