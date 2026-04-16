"""
Agent Memory — Simple key-value context store for agents.

Agents can persist short-term context between runs (e.g. "last processed ID",
"emails seen today") using this lightweight store backed by SQLite.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger("memory")


class AgentMemory:
    """
    SQLite-backed key-value store for agent run context.

    Usage:
        mem = AgentMemory("email_agent")
        await mem.set("last_processed_id", "msg_12345")
        val = await mem.get("last_processed_id")
    """

    def __init__(self, agent_name: str, db_path: str = "./autopilot.db"):
        self.agent_name = agent_name
        self.db_path = db_path
        self._cache: dict[str, Any] = {}

    def _namespaced(self, key: str) -> str:
        return f"{self.agent_name}:{key}"

    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from memory."""
        ns_key = self._namespaced(key)
        if ns_key in self._cache:
            return self._cache[ns_key]

        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_table(db)
                async with db.execute(
                    "SELECT value, expires_at FROM agent_memory WHERE key = ?", (ns_key,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        value_str, expires_at = row
                        if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
                            await self.delete(key)
                            return default
                        value = json.loads(value_str)
                        self._cache[ns_key] = value
                        return value
        except Exception as e:
            logger.warning("memory_get_failed", key=key, error=str(e))

        return default

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store a value in memory with optional TTL."""
        ns_key = self._namespaced(key)
        expires_at = None
        if ttl_seconds:
            expires_at = (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()

        self._cache[ns_key] = value

        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_table(db)
                await db.execute(
                    """INSERT OR REPLACE INTO agent_memory (key, value, updated_at, expires_at)
                       VALUES (?, ?, ?, ?)""",
                    (ns_key, json.dumps(value), datetime.utcnow().isoformat(), expires_at),
                )
                await db.commit()
        except Exception as e:
            logger.warning("memory_set_failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        """Delete a key from memory."""
        ns_key = self._namespaced(key)
        self._cache.pop(ns_key, None)

        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM agent_memory WHERE key = ?", (ns_key,))
                await db.commit()
        except Exception as e:
            logger.warning("memory_delete_failed", key=key, error=str(e))

    async def get_all(self) -> dict[str, Any]:
        """Get all keys for this agent."""
        prefix = f"{self.agent_name}:"
        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_table(db)
                async with db.execute(
                    "SELECT key, value FROM agent_memory WHERE key LIKE ?", (f"{prefix}%",)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {
                        row[0].removeprefix(prefix): json.loads(row[1])
                        for row in rows
                    }
        except Exception as e:
            logger.warning("memory_get_all_failed", error=str(e))
            return {}

    @staticmethod
    async def _ensure_table(db) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT
            )
        """)
        await db.commit()
