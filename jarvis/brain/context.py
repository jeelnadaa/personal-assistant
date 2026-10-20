"""Short-term conversation buffer and session state tracking for Jarvis."""

from datetime import datetime, timezone
from typing import Any
from jarvis.brain.providers.base import Msg, ToolCall
from jarvis.config import config
from jarvis.tools.base import ToolResult


class ContextManager:
    """Manages short-term conversation context, token trimming, and session state."""

    def __init__(self) -> None:
        self.exchanges: list[dict[str, Any]] = []
        self.last_interaction_time: datetime | None = None
        self.session_state: dict[str, str] = {
            "last_app": "",
            "last_file": "",
            "last_url": "",
        }

    def _is_expired(self) -> bool:
        """Checks if the conversation buffer has expired due to inactivity."""
        if not self.last_interaction_time:
            return False
        ctx_cfg = config.get("context", {})
        expire_minutes = ctx_cfg.get("expire_minutes", 30)
        elapsed = (datetime.now(timezone.utc) - self.last_interaction_time).total_seconds() / 60.0
        return elapsed > expire_minutes

    def get_history_messages(self) -> list[Msg]:
        """Returns past exchanges formatted as neutral Msg objects for the LLM."""
        if self._is_expired():
            self.exchanges.clear()

        history_msgs: list[Msg] = []
        ctx_cfg = config.get("context", {})
        max_exchanges = ctx_cfg.get("recent_exchanges", 10)

        for exchange in self.exchanges[-max_exchanges:]:
            history_msgs.append(Msg(role="user", text=exchange["user_text"]))
            history_msgs.append(Msg(role="assistant", text=exchange["assistant_reply"]))

        return history_msgs

    def save_exchange(
        self,
        user_text: str,
        assistant_reply: str,
        actions_taken: list[str] | None = None,
    ) -> None:
        """Stores a completed turn in the history buffer."""
        self.last_interaction_time = datetime.now(timezone.utc)
        self.exchanges.append({
            "timestamp": self.last_interaction_time.isoformat(),
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "actions_taken": actions_taken or [],
        })

        # Cap exchanges by count
        ctx_cfg = config.get("context", {})
        max_exchanges = ctx_cfg.get("recent_exchanges", 10)
        if len(self.exchanges) > max_exchanges:
            self.exchanges = self.exchanges[-max_exchanges:]

    def update_session_state(self, tc: ToolCall, result: ToolResult) -> None:
        """Updates session state entities based on executed tool calls."""
        if tc.name == "open_app" and result.ok:
            self.session_state["last_app"] = tc.args.get("name", "")
        elif tc.name in ("open_file", "read_text_file", "write_text_file") and result.ok:
            self.session_state["last_file"] = tc.args.get("path", "")
        elif tc.name in ("open_url", "browser_open") and result.ok:
            self.session_state["last_url"] = tc.args.get("url", "")


# Global shared context manager
context_manager = ContextManager()
