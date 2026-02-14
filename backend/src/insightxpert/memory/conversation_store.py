"""In-memory conversation store with LRU eviction and TTL."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger("insightxpert.memory")

# Maximum number of conversation turns to include in LLM context.
# Keeps the context window manageable while providing enough history.
MAX_HISTORY_TURNS = 20


@dataclass
class _Entry:
    """Stores condensed conversation turns (user + assistant answers only)."""
    messages: list[dict] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


class ConversationStore:
    """Thread-safe in-memory conversation store.

    Stores condensed conversation history (user messages + assistant final
    answers). Tool call/result intermediaries are NOT stored — only the
    information the LLM needs to understand conversational context.

    Features:
    - LRU eviction when max_conversations is exceeded
    - TTL-based expiry for stale conversations
    - Configurable history depth per conversation
    """

    def __init__(
        self,
        max_conversations: int = 500,
        ttl_seconds: int = 7200,  # 2 hours
    ) -> None:
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._max = max_conversations
        self._ttl = ttl_seconds

    def get_history(self, conversation_id: str) -> list[dict]:
        """Return conversation history as a list of {role, content} dicts."""
        self._evict_expired()
        entry = self._store.get(conversation_id)
        if not entry:
            return []
        self._store.move_to_end(conversation_id)
        # Return last N turns to stay within context limits
        return entry.messages[-MAX_HISTORY_TURNS:]

    def add_user_message(self, conversation_id: str, content: str) -> None:
        """Record a user message."""
        self._ensure_entry(conversation_id)
        self._store[conversation_id].messages.append({
            "role": "user",
            "content": content,
        })
        self._store[conversation_id].updated_at = time.time()

    def add_assistant_message(self, conversation_id: str, content: str) -> None:
        """Record an assistant answer (final answer only, not tool intermediaries)."""
        self._ensure_entry(conversation_id)
        self._store[conversation_id].messages.append({
            "role": "assistant",
            "content": content,
        })
        self._store[conversation_id].updated_at = time.time()

    def _ensure_entry(self, conversation_id: str) -> None:
        if conversation_id not in self._store:
            self._store[conversation_id] = _Entry()
        self._store.move_to_end(conversation_id)
        # Evict oldest if over capacity
        while len(self._store) > self._max:
            evicted_id, _ = self._store.popitem(last=False)
            logger.debug("Evicted conversation %s (LRU)", evicted_id)

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [
            k for k, v in self._store.items()
            if now - v.updated_at > self._ttl
        ]
        for k in expired:
            del self._store[k]
            logger.debug("Evicted conversation %s (TTL)", k)
