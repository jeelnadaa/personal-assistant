"""Audit logging for Jarvis tool execution and safety decisions.

Logs every tool call to logs/audit.jsonl with timestamps, arguments,
execution status, and confirmation outcomes.
"""

from pathlib import Path
import json
from datetime import datetime, timezone
from typing import Any

AUDIT_LOG_FILE = Path("logs/audit.jsonl")


def log_tool_execution(
    tool_name: str,
    args: dict[str, Any],
    ok: bool,
    output: str,
    confirmation_asked: bool = False,
    confirmation_decision: str | None = None,
) -> None:
    """Appends an entry to logs/audit.jsonl.

    Args:
        tool_name: The name of the tool called.
        args: Arguments passed to the tool.
        ok: Whether execution succeeded.
        output: Tool execution output.
        confirmation_asked: Whether user confirmation was requested.
        confirmation_decision: The confirmation outcome (e.g. 'allowed', 'denied', or None).
    """
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Redact long values in arguments to keep audit log readable
    safe_args: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 200:
            safe_args[k] = v[:197] + "..."
        else:
            safe_args[k] = v

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "args": safe_args,
        "ok": ok,
        "output_preview": output[:200] if output else "",
        "confirmation_asked": confirmation_asked,
        "confirmation_decision": confirmation_decision,
    }

    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Never fail a tool execution due to audit log write failure
        pass
