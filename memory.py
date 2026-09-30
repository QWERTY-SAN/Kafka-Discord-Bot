from collections import defaultdict, deque


class ConversationMemory:
    def __init__(self, max_history: int = 16):
        self.max_history = max_history
        self._conversations = defaultdict(
            lambda: deque(maxlen=max_history)
        )

    def get(self, key):
        return list(self._conversations[key])

    def add_user(self, key, content: str):
        self._conversations[key].append(
            {
                "role": "user",
                "content": content,
            }
        )

    def add_assistant(self, key, content: str):
        self._conversations[key].append(
            {
                "role": "assistant",
                "content": content,
            }
        )

    def reset(self, key):
        self._conversations.pop(key, None)

    def clear_all(self):
        self._conversations.clear()