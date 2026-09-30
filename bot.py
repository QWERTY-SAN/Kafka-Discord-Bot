import asyncio
import io
import logging
import re
import time

import aiohttp

import discord
from discord.ext import commands

from config import SETTINGS
from gemini_client import AIServiceError, GeminiClient
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
        self.ai = GeminiClient()
        self._cooldowns: dict[tuple[int, int], float] = {}
        self._cooldown_lock = asyncio.Lock()
        self._gif_last_sent: dict[tuple[int, int], float] = {}
        self._gif_lock = asyncio.Lock()
        self._http_session: aiohttp.ClientSession | None = None
        self._emoji_cycle = ("🌹", "🎭", "🎶", "✨", "😉", "😏")

    async def setup_hook(self):
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=min(15, SETTINGS.request_timeout)),
            headers={"User-Agent": "Kafka-Discord-Bot/1.0"},
        )
        logger.info("Kafka bot setup complete.")

    async def close(self):
        await self.ai.close()
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        await super().close()

    async def on_ready(self):
        logger.info(
            "Logged in as %s (%s)",
            self.user,
            self.user.id if self.user else "unknown",
        )
        logger.info("Prefix: %s", SETTINGS.bot_prefix)
        logger.info("Model: %s", SETTINGS.gemini_model)
        logger.info("Kafka is ready.")

        if SETTINGS.gif_enabled:
            logger.info("Kafka GIF mode: %s", SETTINGS.gif_mode)

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
            stale = [
                cooldown_key
                for cooldown_key, timestamp in self._cooldowns.items()
                if timestamp < cutoff
            ]
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

    def decorate_response(self, response: str, seed: str) -> str:
        """Add a small, deterministic Kafka-style emoji without relying on the model to do it."""
        if not SETTINGS.emojis_enabled:
            return response

        emoji_candidates = self._emoji_cycle
        if any(emoji in response for emoji in emoji_candidates):
            return response

        # Keep code blocks and very long technical responses clean.
        if response.count("```") % 2 == 1 or "```" in response:
            return response

        index = sum(ord(ch) for ch in seed) % len(emoji_candidates)
        return f"{response.rstrip()} {emoji_candidates[index]}"

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

    async def send_chunks(
        self,
        destination,
        response: str,
        reply_to: discord.Message | None = None,
    ):
        chunks = self.split_message(response)
        for index, chunk in enumerate(chunks):
            kwargs = {
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if index == 0 and reply_to is not None:
                await reply_to.reply(chunk, mention_author=False, **kwargs)
            else:
                await destination.send(chunk, **kwargs)

    async def maybe_send_gif(
        self,
        message: discord.Message,
        *,
        triggered_by_mention: bool = False,
        triggered_by_command: bool = False,
        force: bool = False,
    ) -> bool:
        if not SETTINGS.gif_enabled or not SETTINGS.gif_url:
            return False

        mode = SETTINGS.gif_mode
        if not force and mode == "off":
            return False

        if not force:
            if mode == "every_mention" and not triggered_by_mention:
                return False
            if mode == "every_command" and not triggered_by_command:
                return False
            if mode == "every_response":
                pass

        key = self.get_memory_key(message)
        now = time.monotonic()

        async with self._gif_lock:
            previous = self._gif_last_sent.get(key, 0.0)
            if not force and now - previous < SETTINGS.gif_cooldown_seconds:
                return False

            # Don't mark it as sent until Discord actually accepts the message.
            stale_cutoff = now - max(SETTINGS.gif_cooldown_seconds, 3600)
            stale = [
                gif_key
                for gif_key, timestamp in self._gif_last_sent.items()
                if timestamp < stale_cutoff
            ]
            for gif_key in stale:
                self._gif_last_sent.pop(gif_key, None)

            try:
                if self._http_session is None or self._http_session.closed:
                    self._http_session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=min(15, SETTINGS.request_timeout)),
                        headers={"User-Agent": "Kafka-Discord-Bot/1.0"},
                    )

                async with self._http_session.get(SETTINGS.gif_url, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.warning("Kafka GIF download returned HTTP %s", response.status)
                        return False

                    content_type = (response.headers.get("Content-Type") or "").lower()
                    if "gif" not in content_type:
                        logger.warning("Kafka GIF URL did not return GIF content: %s", content_type)

                    data = await response.read()

                if not data.startswith((b"GIF87a", b"GIF89a")):
                    logger.warning("Kafka GIF download was not a valid GIF file.")
                    return False

                # Keep a conservative upload size for compatibility across Discord servers.
                if len(data) > 8 * 1024 * 1024:
                    logger.warning("Kafka GIF is too large to upload: %s bytes", len(data))
                    return False

                file = discord.File(io.BytesIO(data), filename="kafka.gif")
                await message.channel.send(
                    content="🎭",
                    file=file,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                self._gif_last_sent[key] = time.monotonic()
                logger.info("Sent Kafka GIF to channel %s", message.channel.id)
                return True

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning("Unable to download Kafka GIF: %s", exc)
                return False
            except (discord.HTTPException, discord.Forbidden) as exc:
                logger.warning("Unable to send Kafka GIF: %s", exc)
                return False

    async def process_ai_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_private = isinstance(
            message.channel,
            (discord.DMChannel, discord.GroupChannel),
        )
        is_mentioned = self.user is not None and self.user in message.mentions
        is_reply = self.is_reply_to_bot(message)

        if not is_private and not is_mentioned and not is_reply:
            return

        if message.content.startswith(SETTINGS.bot_prefix):
            return

        cooldown_key = (message.channel.id, message.author.id)
        if await self.on_cooldown(cooldown_key):
            return

        content = (
            self.strip_bot_mention(message.content)
            if is_mentioned
            else message.content.strip()
        )

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
                response = self.decorate_response(response, content)
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

        if is_mentioned or is_private or is_reply:
            await self.maybe_send_gif(
                message,
                triggered_by_mention=is_mentioned,
            )

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await self.process_ai_message(message)
        await self.process_commands(message)


bot = KafkaBot()


@bot.command(name="kafka")
async def kafka(ctx: commands.Context, *, prompt: str | None = None):
    if not prompt:
        prompt_text = "You called me, but you didn't tell me what you want. Go on."
        if SETTINGS.emojis_enabled:
            prompt_text += " 🌹"
        await ctx.reply(
            prompt_text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    prompt = prompt.strip()
    if len(prompt) > SETTINGS.max_input_chars:
        limit_text = f"Keep it under {SETTINGS.max_input_chars:,} characters. Even I have limits."
        if SETTINGS.emojis_enabled:
            limit_text += " 🎭"
        await ctx.reply(
            limit_text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    cooldown_key = (ctx.channel.id, ctx.author.id)
    if await bot.on_cooldown(cooldown_key):
        return

    async with ctx.typing():
        try:
            response = await bot.generate_reply(ctx.message, prompt)
            response = bot.decorate_response(response, prompt)
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
    await bot.maybe_send_gif(ctx.message, triggered_by_command=True)


@bot.command(name="reset", aliases=["forget"])
async def reset(ctx: commands.Context):
    key = (ctx.channel.id, ctx.author.id)
    await bot.memory.reset(key)
    reset_text = "All right. Consider our conversation a clean slate."
    if SETTINGS.emojis_enabled:
        reset_text += " 🌹"
    await ctx.reply(
        reset_text,
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="gif", aliases=["kafkagif"])
async def gif(ctx: commands.Context):
    sent = await bot.maybe_send_gif(ctx.message, force=True)
    if not sent:
        await ctx.reply(
            "The little performance failed to load. Typical. 🎭",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    latency_ms = round(bot.latency * 1000)
    ping_text = f"Pong. `{latency_ms}ms`"
    if SETTINGS.emojis_enabled:
        ping_text += " 🎶"
    await ctx.reply(
        ping_text,
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="kafkahelp")
async def kafkahelp(ctx: commands.Context):
    prefix = SETTINGS.bot_prefix
    title = "**Kafka — Discord AI**"
    if SETTINGS.emojis_enabled:
        title += " 🌹"
    help_text = (
        title + "\n\n"
        f"`{prefix}kafka <message>` — Talk to Kafka\n"
        f"`{prefix}reset` / `{prefix}forget` — Clear your conversation\n"
        f"`{prefix}gif` — Ask Kafka for a GIF\n"
        f"`{prefix}ping` — Check bot latency\n"
        f"`{prefix}kafkahelp` — Show this help\n\n"
        "You can also mention Kafka, message her directly, or reply to one of her messages."
    )
    await ctx.reply(
        help_text,
        mention_author=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )
