import asyncio
import logging
import re
import time

import discord
from discord.ext import commands

from config import SETTINGS
from groq_client import AIServiceError, GroqClient
from memory import ConversationMemory

logger = logging.getLogger(__name__)


class KafkaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix=SETTINGS.bot_prefix,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        self.memory = ConversationMemory(
            max_history=SETTINGS.max_history,
            ttl_seconds=SETTINGS.memory_ttl_seconds,
            max_conversations=SETTINGS.max_conversations,
        )
        self.ai = GroqClient()
        self._cooldowns: dict[tuple[int, int], float] = {}
        self._cooldown_lock = asyncio.Lock()

    async def close(self):
        await self.ai.close()
        await super().close()

    async def setup_hook(self):
        logger.info("Kafka bot setup complete.")

    async def on_ready(self):
        logger.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
        logger.info("Prefix: %s", SETTINGS.bot_prefix)
        logger.info("Kafka is ready.")

    @staticmethod
    def get_memory_key(message: discord.Message) -> tuple[int, int]:
        return message.channel.id, message.author.id

    async def on_cooldown(self, key: tuple[int, int]) -> bool:
        if SETTINGS.user_cooldown <= 0:
            return False

        now = time.monotonic()
        async with self._cooldown_lock:
            previous = self._cooldowns.get(key, 0.0)
            if now - previous < SETTINGS.user_cooldown:
                return True
            self._cooldowns[key] = now

            cutoff = now - max(SETTINGS.user_cooldown * 10, 60.0)
            stale = [cooldown_key for cooldown_key, timestamp in self._cooldowns.items() if timestamp < cutoff]
            for cooldown_key in stale:
                self._cooldowns.pop(cooldown_key, None)

        return False

    @staticmethod
    def split_message(text: str, limit: int = 1900) -> list[str]:
        text = text.strip()
        if not text:
            return ["…"]
        if len(text) <= limit:
            return [text]

        chunks: list[str] = []
        remaining = text

        while len(remaining) > limit:
            split_at = remaining.rfind("\n", 0, limit + 1)
            if split_at < 1:
                split_at = remaining.rfind(" ", 0, limit + 1)
            if split_at < 1:
                split_at = limit

            chunk = remaining[:split_at].rstrip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[split_at:].lstrip()

        if remaining:
            chunks.append(remaining)

        return chunks

    def strip_bot_mention(self, content: str) -> str:
        if not self.user:
            return content.strip()
        return re.sub(rf"<@!?{self.user.id}>", "", content).strip()

    def is_reply_to_bot(self, message: discord.Message) -> bool:
        if not self.user or not message.reference:
            return False

        resolved = message.reference.resolved
        return isinstance(resolved, discord.Message) and resolved.author.id == self.user.id

    async def generate_reply(self, message: discord.Message, content: str) -> str:
        key = self.get_memory_key(message)

        async with self.memory.session(key) as session:
            trial_history = [
                *session.history,
                {"role": "user", "content": content},
            ]
            response = await self.ai.generate(trial_history)
            session.commit(content, response)
            return response

    async def send_chunks(self, destination, response: str, reply_to: discord.Message | None = None):
        chunks = self.split_message(response)
        for index, chunk in enumerate(chunks):
            kwargs = {
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if index == 0 and reply_to is not None:
                await destination.reply(chunk, mention_author=False, **kwargs)
            else:
                await destination.send(chunk, **kwargs)

    async def process_ai_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_private = isinstance(message.channel, (discord.DMChannel, discord.GroupChannel))
        is_mentioned = self.user is not None and self.user in message.mentions
        is_reply = self.is_reply_to_bot(message)

        if not is_private and not is_mentioned and not is_reply:
            return

        if message.content.startswith(SETTINGS.bot_prefix):
            return

        cooldown_key = (message.channel.id, message.author.id)
        if await self.on_cooldown(cooldown_key):
            return

        content = self.strip_bot_mention(message.content) if is_mentioned else message.content.strip()

        if not content:
            content = "You called for me?"

        if len(content) > SETTINGS.max_input_chars:
            await message.reply(
                f"That's a little too much at once. Keep your message under {SETTINGS.max_input_chars:,} characters.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        async with message.channel.typing():
            try:
                response = await self.generate_reply(message, content)
            except AIServiceError as exc:
                await message.reply(
                    exc.user_message,
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            except Exception:
                logger.exception("Unexpected error while generating a reply.")
                await message.reply(
                    "Something went wrong on my side. Try again in a moment.",
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

        await self.send_chunks(message.channel, response, reply_to=message)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await self.process_ai_message(message)
        await self.process_commands(message)


bot = KafkaBot()


@bot.command(name="kafka")
async def kafka(ctx: commands.Context, *, prompt: str | None = None):
    if not prompt:
        await ctx.reply(
            "You called me, but you didn't tell me what you want. Go on.",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    if len(prompt) > SETTINGS.max_input_chars:
        await ctx.reply(
            f"Keep it under {SETTINGS.max_input_chars:,} characters. Even I have limits.",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    cooldown_key = (ctx.channel.id, ctx.author.id)
    if await bot.on_cooldown(cooldown_key):
        return

    async with ctx.typing():
        try:
            response = await bot.generate_reply(ctx.message, prompt.strip())
        except AIServiceError as exc:
            await ctx.reply(
                exc.user_message,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        except Exception:
            logger.exception("Unexpected error in k!kafka command.")
            await ctx.reply(
                "Something went wrong on my side. Try again in a moment.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

    await bot.send_chunks(ctx, response)


@bot.command(name="reset", aliases=["forget"])
async def reset(ctx: commands.Context):
    key = (ctx.channel.id, ctx.author.id)
    await bot.memory.reset(key)
    await ctx.reply(
        "All right. Consider our conversation a clean slate.",
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    latency_ms = round(bot.latency * 1000)
    await ctx.reply(
        f"Pong. `{latency_ms}ms`",
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="kafkahelp")
async def kafkahelp(ctx: commands.Context):
    prefix = SETTINGS.bot_prefix
    help_text = (
        "**Kafka — Discord AI**\n\n"
        f"`{prefix}kafka <message>` — Talk to Kafka\n"
        f"`{prefix}reset` / `{prefix}forget` — Clear your conversation\n"
        f"`{prefix}ping` — Check bot latency\n"
        f"`{prefix}kafkahelp` — Show this help\n\n"
        "You can also mention Kafka, message her directly, or reply to one of her messages."
    )
    await ctx.reply(
        help_text,
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )
