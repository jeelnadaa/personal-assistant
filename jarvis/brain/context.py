"""Multi-turn and cross-session conversation context manager for Jarvis."""

from datetime import datetime, timezone
from typing import Any
from jarvis.brain.providers.base import Msg, ToolCall
from jarvis.config import config
from jarvis.logger import logger
from jarvis.tools.base import ToolResult


class ContextManager:
    """Manages conversational context across turns and sessions with persistent SQLite backup."""

    def __init__(self) -> None:
        self.exchanges: list[dict[str, Any]] = []
        self.last_interaction_time: datetime | None = None
        self.session_state: dict[str, str] = {
            "last_app": "",
            "last_file": "",
            "last_url": "",
        }
        self.load_from_storage()

    def load_from_storage(self, limit: int | None = None) -> None:
        """Loads recent conversation history from persistent SQLite storage."""
        if limit is None:
            ctx_cfg = config.get("context", {})
            limit = ctx_cfg.get("recent_exchanges", 10)

        try:
            from jarvis.brain.memory import get_recent_history
            recent = get_recent_history(limit=limit)
            if recent:
                self.exchanges = recent
                self.last_interaction_time = datetime.now(timezone.utc)
                logger.info("Loaded %d conversation turns from persistent storage.", len(recent))
        except Exception as exc:
            logger.debug("Could not load history from storage: %s", exc)

    def _is_expired(self) -> bool:
        """Checks if the ephemeral active session state (last opened app/file) has expired."""
        if not self.last_interaction_time:
            return False
        ctx_cfg = config.get("context", {})
        expire_minutes = ctx_cfg.get("expire_minutes", 60)
        elapsed = (datetime.now(timezone.utc) - self.last_interaction_time).total_seconds() / 60.0
        return elapsed > expire_minutes

    def get_history_messages(self) -> list[Msg]:
        """Returns past exchanges formatted as neutral Msg objects for the LLM."""
        if not self.exchanges:
            self.load_from_storage()

        if self._is_expired():
            # Reset temporary app/file session entities after idle timeout, but retain conversation context
            self.session_state = {"last_app": "", "last_file": "", "last_url": ""}

        history_msgs: list[Msg] = []
        ctx_cfg = config.get("context", {})
        max_exchanges = ctx_cfg.get("recent_exchanges", 10)

        for exchange in self.exchanges[-max_exchanges:]:
            user_text = exchange.get("user_text", "").strip()
            assistant_reply = exchange.get("assistant_reply", "").strip()
            if user_text and assistant_reply:
                history_msgs.append(Msg(role="user", text=user_text))
                history_msgs.append(Msg(role="assistant", text=assistant_reply))

        return history_msgs

    def save_exchange(
        self,
        user_text: str,
        assistant_reply: str,
        actions_taken: list[str] | None = None,
    ) -> None:
        """Stores a completed turn in the history buffer and persists to disk."""
        self.last_interaction_time = datetime.now(timezone.utc)
        self.exchanges.append({
            "timestamp": self.last_interaction_time.isoformat(),
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "actions_taken": actions_taken or [],
        })

        # Cap in-memory buffer
        ctx_cfg = config.get("context", {})
        max_exchanges = ctx_cfg.get("recent_exchanges", 15)
        if len(self.exchanges) > max_exchanges:
            self.exchanges = self.exchanges[-max_exchanges:]

        # Persist to long-term SQLite history table
        try:
            from jarvis.brain.memory import add_history
            add_history(user_text, assistant_reply)
        except Exception as e:
            logger.warning("Could not persist turn to history: %s", e)

    def clear(self, clear_storage: bool = False) -> None:
        """Clears the in-memory conversation buffer and optionally persistent storage."""
        self.exchanges.clear()
        self.last_interaction_time = None
        self.session_state = {"last_app": "", "last_file": "", "last_url": ""}
        if clear_storage:
            try:
                from jarvis.brain.memory import clear_all_history
                clear_all_history()
            except Exception as exc:
                logger.warning("Failed clearing persistent history: %s", exc)

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
