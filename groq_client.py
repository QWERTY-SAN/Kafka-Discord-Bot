from __future__ import annotations

import asyncio
from collections.abc import Sequence

from groq import AsyncGroq

from config import Config
from persona import KAFKA_SYSTEM_PROMPT


class GroqClientError(RuntimeError):
    """Safe, user-facing Groq failure."""


class GroqTemporaryError(GroqClientError):
    """Temporary connection, timeout, or rate-limit failure."""


class GroqConfigurationError(GroqClientError):
    """Authentication or model configuration failure."""


class GroqClient:
    def __init__(self, config: Config):
        self._client = AsyncGroq(api_key=config.groq_api_key)
        self.client = self._client
        self.model = config.groq_model
        self.max_output_tokens = config.max_output_tokens
        self.reasoning_effort = config.reasoning_effort
        self.request_timeout = config.request_timeout
        self.max_retries = config.groq_max_retries
        self.semaphore = asyncio.Semaphore(config.max_concurrent_requests)

    async def generate(self, history: Sequence[dict[str, str]]) -> str:
        messages = [
            {"role": "system", "content": KAFKA_SYSTEM_PROMPT},
            *history,
        ]

        async with self.semaphore:
            attempts = self.max_retries + 1

            for attempt in range(attempts):
                try:
                    response = await asyncio.wait_for(
                        self.client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                            max_completion_tokens=self.max_output_tokens,
                            reasoning_effort=self.reasoning_effort,
                            reasoning_format="hidden",
                            temperature=0.7,
                        ),
                        timeout=self.request_timeout,
                    )

                    text = response.choices[0].message.content
                    if not text:
                        raise GroqClientError("Groq returned an empty response.")

                    return text.strip()

                except asyncio.TimeoutError as exc:
                    if attempt >= attempts - 1:
                        raise GroqTemporaryError(
                            "Groq did not respond in time."
                        ) from exc

                except (ConnectionError, OSError) as exc:
                    if attempt >= attempts - 1:
                        raise GroqTemporaryError(
                            "The connection to Groq failed."
                        ) from exc

                except Exception as exc:
                    status = getattr(exc, "status_code", None)
                    if status is None:
                        response = getattr(exc, "response", None)
                        status = getattr(response, "status_code", None)

                    if status in {401, 403, 404}:
                        raise GroqConfigurationError(
                            "Groq rejected the configured credentials or model."
                        ) from exc

                    retryable = status == 429 or (
                        isinstance(status, int) and status >= 500
                    )

                    if isinstance(exc, GroqClientError):
                        raise

                    if not retryable or attempt >= attempts - 1:
                        raise GroqClientError(
                            "The Groq request failed."
                        ) from exc

                await asyncio.sleep(min(2 ** attempt, 8))

        raise GroqClientError("The Groq request failed.")

    async def close(self) -> None:
        await self.client.close()
