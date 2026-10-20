"""Memory tools allowing the AI to store, recall, and forget user facts."""

from jarvis.brain.memory import delete_fact, search_facts, set_fact
from jarvis.tools.base import ToolResult, tool


@tool(
    name="remember",
    description="Stores a durable user fact or preference in long-term memory (e.g. 'favorite_music_app' = 'Spotify').",
    input_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Fact identifier or subject key."},
            "value": {"type": "string", "description": "The fact details or preference to remember."},
        },
        "required": ["key", "value"],
    },
    dangerous=False,
    category="memory",
)
def remember(key: str, value: str) -> ToolResult:
    """Saves a fact in persistent SQLite store."""
    ok, msg = set_fact(key, value)
    return ToolResult(ok=ok, output=msg)


@tool(
    name="recall",
    description="Searches long-term memory for previously stored facts matching a query substring.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search keyword or subject to recall."}
        },
        "required": ["query"],
    },
    dangerous=False,
    category="memory",
)
def recall(query: str) -> ToolResult:
    """Retrieves facts matching substring."""
    matches = search_facts(query)
    if not matches:
        return ToolResult(ok=True, output=f"No memories found matching '{query}'.")

    formatted = [f"- {k}: {v}" for k, v in matches]
    return ToolResult(ok=True, output=f"Found {len(matches)} facts:\n" + "\n".join(formatted))


@tool(
    name="forget",
    description="Removes a specific fact from long-term memory by key.",
    input_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Exact key to delete from memory."}
        },
        "required": ["key"],
    },
    dangerous=False,
    category="memory",
)
def forget(key: str) -> ToolResult:
    """Removes a key from persistent store."""
    deleted = delete_fact(key)
    if deleted:
        return ToolResult(ok=True, output=f"Forgot '{key}'.")
    return ToolResult(ok=False, output=f"No memory found with key '{key}'.")


@tool(
    name="clear_history",
    description="Clears past conversation turns and session exchanges from memory.",
    input_schema={
        "type": "object",
        "properties": {
            "clear_all": {"type": "boolean", "description": "If true, purges all historical session logs. If false, clears only active session context."}
        },
        "required": [],
    },
    dangerous=False,
    category="memory",
)
def clear_history(clear_all: bool = False) -> ToolResult:
    """Clears conversation context."""
    from jarvis.brain.context import context_manager
    context_manager.clear(clear_storage=clear_all)
    scope = "all past and active" if clear_all else "active"
    return ToolResult(ok=True, output=f"Cleared {scope} conversation history.")

