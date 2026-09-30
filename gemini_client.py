import asyncio
import logging

from google import genai
from google.genai import errors, types

from config import SETTINGS
from persona import KAFKA_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    def __init__(self, user_message: str, status_code: int | None = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


class GeminiClient:
    def __init__(self):
        retry_options = types.HttpRetryOptions(
            attempts=3,
            initial_delay=1.0,
            max_delay=8.0,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        )
        http_options = types.HttpOptions(
            timeout=int(SETTINGS.request_timeout * 1000),
            retry_options=retry_options,
        )
        self.client = genai.Client(
            api_key=SETTINGS.gemini_api_key,
            http_options=http_options,
        )
        self.semaphore = asyncio.Semaphore(SETTINGS.max_concurrent_requests)

    @staticmethod
    def _build_contents(history: list[dict[str, str]]) -> list[types.Content]:
        contents: list[types.Content] = []
        for message in history:
            role = "model" if message["role"] == "assistant" else "user"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=message["content"])],
                )
            )
        return contents

    async def generate(self, history: list[dict[str, str]]) -> str:
        contents = self._build_contents(history)
        config = types.GenerateContentConfig(
            system_instruction=KAFKA_SYSTEM_PROMPT,
            max_output_tokens=SETTINGS.max_output_tokens,
            thinking_config=types.ThinkingConfig(
                thinking_level=SETTINGS.thinking_level,
            ),
        )

        async with self.semaphore:
            try:
                response = await self.client.aio.models.generate_content(
                    model=SETTINGS.gemini_model,
                    contents=contents,
                    config=config,
                )
            except errors.ClientError as exc:
                status = getattr(exc, "status_code", None)
                logger.error("Gemini client error %s: %s", status, exc)
                if status == 400:
                    message = "The request was rejected. Check the bot configuration."
                elif status == 401 or status == 403:
                    message = "My Gemini API key isn't working right now."
                elif status == 404:
                    message = "That Gemini model isn't available right now."
                elif status == 429:
                    message = "Too many requests at once. Give me a moment."
                else:
                    message = "Gemini rejected the request. Try again shortly."
                raise AIServiceError(message, status) from exc
            except errors.ServerError as exc:
                status = getattr(exc, "status_code", None)
                logger.warning("Gemini server error %s: %s", status, exc)
                raise AIServiceError("Gemini is having trouble right now. Try again shortly.", status) from exc
            except (TimeoutError, asyncio.TimeoutError) as exc:
                logger.warning("Gemini request timed out: %s", exc)
                raise AIServiceError("That took too long. Try again in a moment.") from exc
            except Exception as exc:
                logger.exception("Unexpected Gemini error: %s", exc)
                raise AIServiceError("Something went wrong with the AI service.") from exc

        content = response.text
        if not content or not content.strip():
            logger.warning("Gemini returned an empty response.")
            raise AIServiceError("I received an empty response. Try again.")

        return content.strip()

    async def close(self) -> None:
        await self.client.aio.aclose()
