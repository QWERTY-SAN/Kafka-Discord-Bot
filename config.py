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


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false.")


@dataclass(frozen=True)
class Settings:
    discord_token: str
    gemini_api_key: str
    bot_prefix: str
    gemini_model: str
    max_history: int
    max_output_tokens: int
    thinking_level: str
    user_cooldown: float
    max_concurrent_requests: int
    request_timeout: float
    max_retries: int
    memory_ttl_seconds: int
    max_conversations: int
    max_input_chars: int
    port: int
    emojis_enabled: bool
    gif_enabled: bool
    gif_mode: str
    gif_url: str
    gif_cooldown_seconds: int

    @classmethod
    def load(cls) -> "Settings":
        discord_token = os.getenv("DISCORD_TOKEN", "").strip()
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

        if not discord_token:
            raise RuntimeError("DISCORD_TOKEN is not configured.")
        if not gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        thinking_level = os.getenv("THINKING_LEVEL", "medium").strip().lower()
        if thinking_level not in {"minimal", "low", "medium", "high"}:
            raise RuntimeError("THINKING_LEVEL must be minimal, low, medium, or high.")

        gif_mode = os.getenv("KAFKA_GIF_MODE", "first_reply").strip().lower()
        if gif_mode not in {"off", "first_reply", "every_mention", "every_command", "every_response"}:
            raise RuntimeError(
                "KAFKA_GIF_MODE must be off, first_reply, every_mention, every_command, or every_response."
            )

        gif_url = os.getenv(
            "KAFKA_GIF_URL",
            "https://www.gifcen.com/wp-content/uploads/2023/08/kafka-gif-6.gif",
        ).strip()

        return cls(
            discord_token=discord_token,
            gemini_api_key=gemini_api_key,
            bot_prefix=os.getenv("BOT_PREFIX", "k!").strip() or "k!",
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
            max_history=_int("MAX_HISTORY", 16, 2),
            max_output_tokens=_int("MAX_OUTPUT_TOKENS", 1536, 128),
            thinking_level=thinking_level,
            user_cooldown=_float("USER_COOLDOWN", 2.0, 0.0),
            max_concurrent_requests=_int("MAX_CONCURRENT_REQUESTS", 3, 1),
            request_timeout=_float("REQUEST_TIMEOUT", 45.0, 5.0),
            max_retries=_int("MAX_RETRIES", 3, 0),
            memory_ttl_seconds=_int("MEMORY_TTL_SECONDS", 21600, 60),
            max_conversations=_int("MAX_CONVERSATIONS", 500, 1),
            max_input_chars=_int("MAX_INPUT_CHARS", 6000, 100),
            port=_int("PORT", 10000, 1),
            emojis_enabled=_bool("EMOJIS_ENABLED", True),
            gif_enabled=_bool("KAFKA_GIF_ENABLED", True),
            gif_mode=gif_mode,
            gif_url=gif_url,
            gif_cooldown_seconds=_int("KAFKA_GIF_COOLDOWN_SECONDS", 21600, 0),
        )


SETTINGS = Settings.load()
