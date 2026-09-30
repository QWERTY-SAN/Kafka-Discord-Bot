from __future__ import annotations

import time
from collections import OrderedDict, deque
from collections.abc import Hashable
from typing import TypedDict


class Message(TypedDict):
    role: str
    content: str


class ConversationMemory:
    def __init__(
        self,
        max_history: int = 16,
        max_conversations: int = 500,
        ttl_seconds: float = 21600,
    ):
        self.max_history = max_history
        self.max_conversations = max_conversations
        self.ttl_seconds = ttl_seconds
        self._conversations: OrderedDict[
            Hashable, deque[Message]
        ] = OrderedDict()
        self._last_used: dict[Hashable, float] = {}

    def _is_expired(self, key: Hashable, now: float) -> bool:
        last_used = self._last_used.get(key)
        return last_used is not None and (now - last_used) >= self.ttl_seconds

    def _touch(self, key: Hashable, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._last_used[key] = now
        self._conversations.move_to_end(key)

    def _ensure(self, key: Hashable) -> deque[Message]:
        now = time.monotonic()

        if key in self._conversations and self._is_expired(key, now):
            self.reset(key)

        conversation = self._conversations.get(key)

        if conversation is None:
            while len(self._conversations) >= self.max_conversations:
                oldest_key, _ = self._conversations.popitem(last=False)
                self._last_used.pop(oldest_key, None)

            conversation = deque(maxlen=self.max_history)
            self._conversations[key] = conversation

        self._touch(key, now)
        return conversation

    def get(self, key: Hashable) -> list[Message]:
        conversation = self._ensure(key)
        return list(conversation)

    def add_turn(self, key: Hashable, user_content: str, assistant_content: str) -> None:
        conversation = self._ensure(key)
        conversation.append({"role": "user", "content": user_content})
        conversation.append({"role": "assistant", "content": assistant_content})
        self._touch(key)

    def reset(self, key: Hashable) -> None:
        self._conversations.pop(key, None)
        self._last_used.pop(key, None)

    def clear_all(self) -> None:
        self._conversations.clear()
        self._last_used.clear()

    def cleanup_expired(self) -> int:
        now = time.monotonic()
        expired = [
            key
            for key in self._conversations
            if self._is_expired(key, now)
        ]

        for key in expired:
            self.reset(key)

        return len(expired)

    def __len__(self) -> int:
        return len(self._conversations)
