import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int, minimum: int = 0) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if parsed < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}.")
    return parsed


def _float(name: str, default: float, minimum: float = 0.0) -> float:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc
    if parsed < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}.")
    return parsed


@dataclass(frozen=True)
class Settings:
    discord_token: str
    groq_api_key: str
    bot_prefix: str
    groq_model: str
    max_history: int
    max_output_tokens: int
    reasoning_effort: str
    reasoning_format: str
    temperature: float
    user_cooldown: float
    max_concurrent_requests: int
    request_timeout: float
    max_retries: int
    memory_ttl_seconds: int
    max_conversations: int
    max_input_chars: int

    @classmethod
    def load(cls) -> "Settings":
        discord_token = os.getenv("DISCORD_TOKEN", "").strip()
        groq_api_key = os.getenv("GROQ_API_KEY", "").strip()

        if not discord_token:
            raise RuntimeError("DISCORD_TOKEN is not configured.")
        if not groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured.")

        reasoning_effort = os.getenv("REASONING_EFFORT", "medium").strip().lower()
        if reasoning_effort not in {"low", "medium", "high"}:
            raise RuntimeError("REASONING_EFFORT must be low, medium, or high.")

        reasoning_format = os.getenv("REASONING_FORMAT", "hidden").strip().lower()
        if reasoning_format not in {"hidden", "raw", "parsed"}:
            raise RuntimeError("REASONING_FORMAT must be hidden, raw, or parsed.")

        temperature = _float("TEMPERATURE", 0.85, 0.0)
        if temperature > 2.0:
            raise RuntimeError("TEMPERATURE must be <= 2.0.")

        return cls(
            discord_token=discord_token,
            groq_api_key=groq_api_key,
            bot_prefix=os.getenv("BOT_PREFIX", "k!").strip() or "k!",
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
            max_history=_int("MAX_HISTORY", 16, 2),
            max_output_tokens=_int("MAX_OUTPUT_TOKENS", 1536, 128),
            reasoning_effort=reasoning_effort,
            reasoning_format=reasoning_format,
            temperature=temperature,
            user_cooldown=_float("USER_COOLDOWN", 2.0, 0.0),
            max_concurrent_requests=_int("MAX_CONCURRENT_REQUESTS", 3, 1),
            request_timeout=_float("REQUEST_TIMEOUT", 45.0, 5.0),
            max_retries=_int("MAX_RETRIES", 2, 0),
            memory_ttl_seconds=_int("MEMORY_TTL_SECONDS", 21600, 60),
            max_conversations=_int("MAX_CONVERSATIONS", 500, 1),
            max_input_chars=_int("MAX_INPUT_CHARS", 6000, 100),
        )


SETTINGS = Settings.load()
