import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


DEFAULT_MODEL = "openai/gpt-oss-120b"


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc

    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}.")

    return value


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc

    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}.")

    return value


@dataclass(frozen=True, slots=True)
class Config:
    discord_token: str
    groq_api_key: str
    bot_prefix: str
    groq_model: str
    max_history: int
    max_output_tokens: int
    user_cooldown: float
    max_concurrent_requests: int
    request_timeout: float
    groq_max_retries: int
    max_input_chars: int
    memory_ttl_seconds: int
    max_conversations: int
    temperature: float
    reasoning_effort: str


def load_config() -> Config:
    discord_token = os.getenv("DISCORD_TOKEN", "").strip()
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    prefix = os.getenv("BOT_PREFIX", "k!").strip() or "k!"
    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    reasoning_effort = os.getenv("REASONING_EFFORT", "low").strip().lower()

    if reasoning_effort not in {"low", "medium", "high"}:
        raise RuntimeError("REASONING_EFFORT must be low, medium, or high.")

    temperature = _float_env("TEMPERATURE", 0.9, 0.0)
    if temperature > 2.0:
        raise RuntimeError("TEMPERATURE must be <= 2.0.")

    return Config(
        discord_token=discord_token,
        groq_api_key=groq_api_key,
        bot_prefix=prefix,
        groq_model=model,
        max_history=_int_env("MAX_HISTORY", 16, 2),
        max_output_tokens=_int_env("MAX_OUTPUT_TOKENS", 768, 1),
        user_cooldown=_float_env("USER_COOLDOWN", 2.0, 0.0),
        max_concurrent_requests=_int_env("MAX_CONCURRENT_REQUESTS", 3, 1),
        request_timeout=_float_env("REQUEST_TIMEOUT", 45.0, 1.0),
        groq_max_retries=_int_env("GROQ_MAX_RETRIES", 2, 0),
        max_input_chars=_int_env("MAX_INPUT_CHARS", 4000, 100),
        memory_ttl_seconds=_int_env("MEMORY_TTL_SECONDS", 21600, 60),
        max_conversations=_int_env("MAX_CONVERSATIONS", 500, 1),
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )
