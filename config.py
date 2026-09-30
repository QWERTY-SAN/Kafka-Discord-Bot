from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-120b"
VALID_REASONING = {"low", "medium", "high"}


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
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
    if raw is None or not raw.strip():
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
    reasoning_effort: str
    user_cooldown: float
    max_concurrent_requests: int
    request_timeout: float
    groq_max_retries: int
    max_input_chars: int
    memory_ttl_seconds: int
    max_conversations: int


def load_config() -> Config:
    discord_token = os.getenv("DISCORD_TOKEN", "").strip()
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    prefix = os.getenv("BOT_PREFIX", "k!").strip() or "k!"
    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    reasoning_effort = os.getenv("REASONING_EFFORT", "medium").strip().lower()

    if reasoning_effort not in VALID_REASONING:
        raise RuntimeError("REASONING_EFFORT must be low, medium, or high.")

    return Config(
        discord_token=discord_token,
        groq_api_key=groq_api_key,
        bot_prefix=prefix,
        groq_model=model,
        max_history=_int_env("MAX_HISTORY", 16, 2),
        max_output_tokens=_int_env("MAX_OUTPUT_TOKENS", 1024, 1),
        reasoning_effort=reasoning_effort,
        user_cooldown=_float_env("USER_COOLDOWN", 2.0, 0.0),
        max_concurrent_requests=_int_env("MAX_CONCURRENT_REQUESTS", 3, 1),
        request_timeout=_float_env("REQUEST_TIMEOUT", 45.0, 1.0),
        groq_max_retries=_int_env("GROQ_MAX_RETRIES", 3, 0),
        max_input_chars=_int_env("MAX_INPUT_CHARS", 6000, 100),
        memory_ttl_seconds=_int_env("MEMORY_TTL_SECONDS", 21600, 60),
        max_conversations=_int_env("MAX_CONVERSATIONS", 500, 1),
    )
