from __future__ import annotations

import asyncio
from collections.abc import Sequence

import groq
from groq import AsyncGroq

from config import Config
from persona import KAFKA_SYSTEM_PROMPT


class GroqClientError(RuntimeError):
    """Safe, user-facing Groq failure."""


class GroqTemporaryError(GroqClientError):
    """A temporary problem such as a timeout, connection failure, or rate limit."""


class GroqConfigurationError(GroqClientError):
    """A configuration/authentication/model error that needs fixing."""


class GroqClient:
    def __init__(self, config: Config):
        self.client = AsyncGroq(
            api_key=config.groq_api_key,
            timeout=config.request_timeout,
            max_retries=config.groq_max_retries,
        )
        self.model = config.groq_model
        self.max_output_tokens = config.max_output_tokens
        self.temperature = config.temperature
        self.reasoning_effort = config.reasoning_effort
        self.semaphore = asyncio.Semaphore(config.max_concurrent_requests)

    async def generate(self, history: Sequence[dict[str, str]]) -> str:
        messages = [
            {
                "role": "system",
                "content": KAFKA_SYSTEM_PROMPT,
            },
            *history,
        ]

        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=self.max_output_tokens,
                    temperature=self.temperature,
                    reasoning_effort=self.reasoning_effort,
                )
            except groq.RateLimitError as exc:
                raise GroqTemporaryError(
                    "Groq is rate-limiting requests right now."
                ) from exc
            except (groq.APITimeoutError, groq.APIConnectionError) as exc:
                raise GroqTemporaryError(
                    "Groq did not respond in time."
                ) from exc
            except groq.APIStatusError as exc:
                if exc.status_code in {401, 403}:
                    raise GroqConfigurationError(
                        "The Groq API key was rejected."
                    ) from exc

                if exc.status_code == 404:
                    raise GroqConfigurationError(
                        f"The configured Groq model '{self.model}' was not found."
                    ) from exc

                if exc.status_code >= 500:
                    raise GroqTemporaryError(
                        "Groq is temporarily unavailable."
                    ) from exc

                raise GroqClientError(
                    "Groq rejected the request."
                ) from exc
            except groq.APIError as exc:
                raise GroqTemporaryError(
                    "The Groq request failed."
                ) from exc

        content = response.choices[0].message.content

        if not content:
            raise GroqClientError("Groq returned an empty response.")

        return content.strip()

    async def close(self) -> None:
        await self.client.close()
