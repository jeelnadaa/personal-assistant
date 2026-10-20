"""Persistent long-term SQLite memory store for user facts and past sessions."""

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any

from jarvis.logger import logger

DB_PATH = Path("data/memory.db")

# Patterns indicating potential secrets or sensitive tokens
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"gsk_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9+/]{40,}[=]{0,2}\b"),  # base64 secret tokens
]


def _init_db() -> sqlite3.Connection:
    """Ensures database directory and schema exist and returns a connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                user_text TEXT,
                final_reply TEXT
            )
        """)
    return conn


SENSITIVE_KEY_WORDS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
}


def is_potentially_sensitive(text: str) -> bool:
    """Detects whether text might contain an API key, token, or password."""
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def set_fact(key: str, value: str) -> tuple[bool, str]:
    """Stores or updates a long-term user fact, rejecting sensitive tokens."""
    clean_k = key.strip().lower()
    clean_v = value.strip()

    # Reject if key or value indicates credentials, secrets, or passwords
    if any(w in clean_k for w in SENSITIVE_KEY_WORDS):
        return False, "Refused to store: key indicates sensitive credentials or passwords."

    if is_potentially_sensitive(clean_v) or is_potentially_sensitive(clean_k):
        return False, "Refused to store: value appears to contain a password or secret key."

    now_ts = datetime.now(timezone.utc).isoformat()
    try:
        conn = _init_db()
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO facts (key, value, updated_at) VALUES (?, ?, ?)",
                (clean_k, clean_v, now_ts),
            )
        conn.close()
        return True, f"Remembered '{clean_k}' = '{clean_v}'."
    except Exception as e:
        logger.error("Failed to store fact (%s): %s", key, e)
        return False, f"Failed to store fact: {str(e)}"


def get_fact(key: str) -> str | None:
    """Retrieves an exact fact by key."""
    conn = _init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM facts WHERE key = ?", (key.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def search_facts(query: str) -> list[tuple[str, str]]:
    """Searches stored facts where key or value contains query substring."""
    conn = _init_db()
    cursor = conn.cursor()
    pattern = f"%{query.strip().lower()}%"
    cursor.execute(
        "SELECT key, value FROM facts WHERE key LIKE ? OR value LIKE ? ORDER BY updated_at DESC",
        (pattern, pattern),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_fact(key: str) -> bool:
    """Removes a fact by key."""
    conn = _init_db()
    with conn:
        cursor = conn.execute("DELETE FROM facts WHERE key = ?", (key.strip().lower(),))
        deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def add_history(user_text: str, final_reply: str) -> None:
    """Logs conversation exchange to persistent history table."""
    now_ts = datetime.now(timezone.utc).isoformat()
    try:
        conn = _init_db()
        with conn:
            conn.execute(
                "INSERT INTO history (ts, user_text, final_reply) VALUES (?, ?, ?)",
                (now_ts, user_text, final_reply),
            )
        conn.close()
    except Exception as e:
        logger.error("Failed to add history: %s", e)


def get_memory_context() -> str:
    """Formats all stored facts plus the last 5 history items into a string capped at 1500 chars."""
    try:
        conn = _init_db()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM facts ORDER BY key ASC")
        facts = cursor.fetchall()

        cursor.execute("SELECT user_text, final_reply FROM history ORDER BY id DESC LIMIT 5")
        history = list(reversed(cursor.fetchall()))
        conn.close()

        lines: list[str] = []
        if facts:
            lines.append("Stored Facts:")
            for k, v in facts:
                lines.append(f"- {k}: {v}")

        if history:
            lines.append("\nRecent Exchanges:")
            for u, r in history:
                lines.append(f"User: {u}\nJarvis: {r}")

        combined = "\n".join(lines).strip()
        if len(combined) > 1500:
            combined = combined[:1497] + "..."
        return combined if combined else "No long-term preferences stored yet."
    except Exception as e:
        logger.error("Failed to read memory context: %s", e)
        return "No long-term preferences stored yet."
