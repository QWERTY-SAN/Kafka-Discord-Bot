import asyncio

from groq import AsyncGroq

from persona import KAFKA_SYSTEM_PROMPT


class GroqClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int = 768,
        max_concurrent_requests: int = 3,
    ):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def generate(self, history: list[dict]) -> str:
        messages = [
            {
                "role": "system",
                "content": KAFKA_SYSTEM_PROMPT,
            }
        ]

        messages.extend(history)

        async with self.semaphore:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_output_tokens,
                temperature=0.85,
            )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError("Groq returned an empty response.")

        return content.strip()