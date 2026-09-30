import asyncio
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class Conversation:
    messages: deque[dict[str, str]]
    last_access: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConversationMemory:
    def __init__(self, max_history: int = 16, ttl_seconds: int = 21600, max_conversations: int = 500):
        self.max_history = max_history
        self.ttl_seconds = ttl_seconds
        self.max_conversations = max_conversations
        self._conversations: OrderedDict[Any, Conversation] = OrderedDict()
        self._index_lock = asyncio.Lock()

    def _expired(self, conversation: Conversation, now: float) -> bool:
        return now - conversation.last_access >= self.ttl_seconds

    async def _get_or_create(self, key: Any) -> Conversation:
        async with self._index_lock:
            now = time.monotonic()
            self._prune_locked(now)
            conversation = self._conversations.get(key)
            if conversation is None:
                conversation = Conversation(deque(maxlen=self.max_history))
                self._conversations[key] = conversation
            else:
                conversation.last_access = now
                self._conversations.move_to_end(key)
            self._enforce_limit_locked()
            return conversation

    def _prune_locked(self, now: float) -> None:
        expired = [
            key
            for key, conversation in self._conversations.items()
            if self._expired(conversation, now)
        ]
        for key in expired:
            self._conversations.pop(key, None)

    def _enforce_limit_locked(self) -> None:
        while len(self._conversations) > self.max_conversations:
            removable_key = next(
                (key for key, conversation in self._conversations.items() if not conversation.lock.locked()),
                None,
            )
            if removable_key is None:
                break
            self._conversations.pop(removable_key, None)

    @asynccontextmanager
    async def session(self, key: Any) -> AsyncIterator["ConversationSession"]:
        conversation = await self._get_or_create(key)
        async with conversation.lock:
            conversation.last_access = time.monotonic()
            self._conversations.move_to_end(key)
            yield ConversationSession(conversation)

    async def get(self, key: Any) -> list[dict[str, str]]:
        conversation = await self._get_or_create(key)
        async with conversation.lock:
            conversation.last_access = time.monotonic()
            self._conversations.move_to_end(key)
            return [dict(message) for message in conversation.messages]

    async def commit_turn(self, key: Any, user_content: str, assistant_content: str) -> None:
        conversation = await self._get_or_create(key)
        async with conversation.lock:
            ConversationSession(conversation).commit(user_content, assistant_content)

    async def reset(self, key: Any) -> None:
        async with self._index_lock:
            conversation = self._conversations.get(key)
        if conversation is None:
            return
        async with conversation.lock:
            async with self._index_lock:
                self._conversations.pop(key, None)

    async def clear_all(self) -> None:
        async with self._index_lock:
            self._conversations.clear()

    async def count(self) -> int:
        async with self._index_lock:
            self._prune_locked(time.monotonic())
            return len(self._conversations)


@dataclass
class ConversationSession:
    conversation: Conversation

    @property
    def history(self) -> list[dict[str, str]]:
        return [dict(message) for message in self.conversation.messages]

    def commit(self, user_content: str, assistant_content: str) -> None:
        self.conversation.messages.append({"role": "user", "content": user_content})
        self.conversation.messages.append({"role": "assistant", "content": assistant_content})
        self.conversation.last_access = time.monotonic()
