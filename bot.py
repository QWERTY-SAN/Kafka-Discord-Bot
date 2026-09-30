from __future__ import annotations

import asyncio
import logging
import re
import time
import discord
from discord.ext import commands

from config import Config
from groq_client import GroqClient, GroqClientError, GroqConfigurationError, GroqTemporaryError
from memory import ConversationMemory

logger = logging.getLogger(__name__)


class KafkaBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix=config.bot_prefix,
            intents=intents,
            help_command=None,
        )

        self.config = config
        self.prefix = config.bot_prefix
        self.memory = ConversationMemory(
            max_history=config.max_history,
            max_conversations=config.max_conversations,
            ttl_seconds=config.memory_ttl_seconds,
        )
        self.ai = GroqClient(config)
        self.last_request: dict[tuple[int, int], float] = {}
        self.conversation_locks: dict[tuple[int, int], asyncio.Lock] = {}
        self._cleanup_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        self._cleanup_task = asyncio.create_task(self._memory_cleanup_loop())
        logger.info("Kafka bot setup complete.")

    async def on_ready(self) -> None:
        if self.user is None:
            return

        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info("Prefix: %s", self.prefix)
        logger.info("Kafka is ready.")

    async def close(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        await self.ai.close()
        await super().close()

    async def _memory_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(max(60, min(self.config.memory_ttl_seconds, 900)))
            removed = self.memory.cleanup_expired()
            if removed:
                logger.info("Removed %d expired conversation(s).", removed)

    def get_memory_key(self, message: discord.Message) -> tuple[int, int]:
        return (message.channel.id, message.author.id)

    def _get_conversation_lock(self, key: tuple[int, int]) -> asyncio.Lock:
        lock = self.conversation_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self.conversation_locks[key] = lock
        return lock

    def on_cooldown(self, key: tuple[int, int]) -> bool:
        if self.config.user_cooldown <= 0:
            return False

        now = time.monotonic()
        previous = self.last_request.get(key, 0.0)

        if now - previous < self.config.user_cooldown:
            return True

        self.last_request[key] = now
        return False

    def trim_input(self, content: str) -> str:
        content = content.strip()
        if len(content) <= self.config.max_input_chars:
            return content

        return (
            content[: self.config.max_input_chars].rstrip()
            + "\n\n[The message was truncated because it was too long.]"
        )

    @staticmethod
    def split_message(text: str, limit: int = 2000) -> list[str]:
        if len(text) <= limit:
            return [text]

        chunks: list[str] = []
        remaining = text.strip()

        while len(remaining) > limit:
            split_at = remaining.rfind("\n", 0, limit + 1)
            if split_at <= 0:
                split_at = remaining.rfind(" ", 0, limit + 1)
            if split_at <= 0:
                split_at = limit

            chunk = remaining[:split_at].strip()
            if chunk:
                chunks.append(chunk)

            remaining = remaining[split_at:].lstrip()

        if remaining:
            chunks.append(remaining)

        return chunks

    @staticmethod
    def remove_bot_mention(content: str, bot_id: int) -> str:
        return re.sub(rf"<@!?{bot_id}>", "", content).strip()

    async def generate_reply(self, message: discord.Message, content: str) -> str:
        key = self.get_memory_key(message)
        lock = self._get_conversation_lock(key)

        async with lock:
            history = self.memory.get(key)
            user_message = self.trim_input(content)

            # Only save a turn after a successful API response. A failed request
            # therefore cannot poison or duplicate the conversation history.
            response = await self.ai.generate(
                [
                    *history,
                    {"role": "user", "content": user_message},
                ]
            )

            self.memory.add_turn(key, user_message, response)
            return response

    async def process_ai_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user is not None and self.user in message.mentions

        if not is_dm and not is_mentioned:
            return

        if message.content.startswith(self.prefix):
            return

        key = self.get_memory_key(message)
        if self.on_cooldown(key):
            return

        content = message.content
        if is_mentioned and self.user is not None:
            content = self.remove_bot_mention(content, self.user.id)

        if not content:
            content = "You called for me?"

        async with message.channel.typing():
            try:
                response = await self.generate_reply(message, content)
            except GroqConfigurationError:
                logger.exception("Groq configuration error.")
                await message.reply(
                    "There's a problem with my Groq configuration. Check the bot settings.",
                    mention_author=False,
                )
                return
            except GroqTemporaryError:
                logger.warning("Temporary Groq failure while handling message.", exc_info=True)
                await message.reply(
                    "The connection is being troublesome right now. Try again in a moment.",
                    mention_author=False,
                )
                return
            except GroqClientError:
                logger.exception("Groq request failed.")
                await message.reply(
                    "Something went wrong while I was thinking. Try again.",
                    mention_author=False,
                )
                return
            except Exception:
                logger.exception("Unexpected error while generating a response.")
                await message.reply(
                    "Something unexpected happened. Try again.",
                    mention_author=False,
                )
                return

        chunks = self.split_message(response)
        if not chunks:
            return

        await message.reply(chunks[0], mention_author=False)
        for chunk in chunks[1:]:
            await message.channel.send(chunk)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        await self.process_ai_message(message)
        await self.process_commands(message)


def register_commands(bot: KafkaBot) -> None:
    @bot.command(name="kafka")
    async def kafka(ctx: commands.Context, *, prompt: str | None = None) -> None:
        if not prompt:
            await ctx.reply(
                "Hmm? You summoned me without saying what you wanted.",
                mention_author=False,
            )
            return

        key = (ctx.channel.id, ctx.author.id)
        if bot.on_cooldown(key):
            return

        async with ctx.typing():
            try:
                response = await bot.generate_reply(ctx.message, prompt)
            except GroqConfigurationError:
                logger.exception("Groq configuration error.")
                await ctx.reply(
                    "There's a problem with my Groq configuration. Check the bot settings.",
                    mention_author=False,
                )
                return
            except GroqTemporaryError:
                logger.warning("Temporary Groq failure while handling command.", exc_info=True)
                await ctx.reply(
                    "The connection is being troublesome right now. Try again in a moment.",
                    mention_author=False,
                )
                return
            except GroqClientError:
                logger.exception("Groq command request failed.")
                await ctx.reply(
                    "Something went wrong while I was thinking. Try again.",
                    mention_author=False,
                )
                return
            except Exception:
                logger.exception("Unexpected error while handling command.")
                await ctx.reply(
                    "Something unexpected happened. Try again.",
                    mention_author=False,
                )
                return

        chunks = bot.split_message(response)
        for chunk in chunks:
            await ctx.reply(chunk, mention_author=False)

    @bot.command(name="reset", aliases=("forget",))
    async def reset(ctx: commands.Context) -> None:
        key = (ctx.channel.id, ctx.author.id)
        lock = bot._get_conversation_lock(key)

        async with lock:
            bot.memory.reset(key)

        await ctx.reply(
            "Our little conversation has been forgotten. Shall we begin again?",
            mention_author=False,
        )

    @bot.command(name="ping")
    async def ping(ctx: commands.Context) -> None:
        latency_ms = round(bot.latency * 1000)
        await ctx.reply(
            f"Pong. `{latency_ms}ms`",
            mention_author=False,
        )

    @bot.command(name="kafkahelp")
    async def kafkahelp(ctx: commands.Context) -> None:
        await ctx.reply(
            f"**Kafka — Discord AI**\n\n"
            f"`{bot.prefix}kafka <message>` — Talk to Kafka\n"
            f"`{bot.prefix}reset` — Reset your conversation\n"
            f"`{bot.prefix}forget` — Same as reset\n"
            f"`{bot.prefix}ping` — Check latency\n"
            f"`{bot.prefix}kafkahelp` — Show this help\n\n"
            f"You can also mention me or DM me.",
            mention_author=False,
        )

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        original = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.CommandOnCooldown):
            return

        logger.error(
            "Command '%s' failed: %s",
            getattr(ctx.command, "qualified_name", "unknown"),
            original,
            exc_info=(type(original), original, original.__traceback__),
        )

        await ctx.reply(
            "That command ran into a problem. Try again.",
            mention_author=False,
        )


def create_bot(config: Config) -> KafkaBot:
    bot = KafkaBot(config)
    register_commands(bot)
    return bot
