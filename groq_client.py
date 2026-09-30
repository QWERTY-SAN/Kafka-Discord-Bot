import asyncio
import logging

import groq
from groq import AsyncGroq

from config import SETTINGS
from persona import KAFKA_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    def __init__(self, user_message: str, status_code: int | None = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


class GroqClient:
    def __init__(self):
        self.client = AsyncGroq(
            api_key=SETTINGS.groq_api_key,
            timeout=SETTINGS.request_timeout,
            max_retries=SETTINGS.max_retries,
        )
        self.semaphore = asyncio.Semaphore(SETTINGS.max_concurrent_requests)

    async def generate(self, history: list[dict[str, str]]) -> str:
        messages = [
            {"role": "system", "content": KAFKA_SYSTEM_PROMPT},
            *history,
        ]

        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=SETTINGS.groq_model,
                    messages=messages,
                    max_completion_tokens=SETTINGS.max_output_tokens,
                    temperature=SETTINGS.temperature,
                    reasoning_effort=SETTINGS.reasoning_effort,
                    reasoning_format=SETTINGS.reasoning_format,
                )
            except groq.AuthenticationError as exc:
                logger.error("Groq authentication failed: %s", exc)
                raise AIServiceError("My API key isn't working right now.", 401) from exc
            except groq.RateLimitError as exc:
                logger.warning("Groq rate limit reached: %s", exc)
                raise AIServiceError("Too many requests at once. Give me a moment.", 429) from exc
            except groq.APITimeoutError as exc:
                logger.warning("Groq request timed out: %s", exc)
                raise AIServiceError("That took too long. Try again in a moment.") from exc
            except groq.APIConnectionError as exc:
                logger.warning("Groq connection error: %s", exc)
                raise AIServiceError("I lost the connection for a moment. Try again.") from exc
            except groq.APIStatusError as exc:
                logger.error("Groq API error %s: %s", exc.status_code, exc)
                if exc.status_code == 404:
                    message = "That model isn't available right now."
                elif exc.status_code == 400:
                    message = "The request was rejected. Check the bot configuration."
                elif exc.status_code >= 500:
                    message = "Groq is having trouble right now. Try again shortly."
                else:
                    message = "The AI service returned an error. Try again shortly."
                raise AIServiceError(message, exc.status_code) from exc
            except groq.APIError as exc:
                logger.error("Unexpected Groq error: %s", exc)
                raise AIServiceError("Something went wrong with the AI service.") from exc

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise AIServiceError("I received an empty response. Try again.")

        return content.strip()

    async def close(self) -> None:
        await self.client.close()
