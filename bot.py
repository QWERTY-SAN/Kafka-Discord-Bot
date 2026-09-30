import os
import re
import time

import discord
from discord.ext import commands

from groq_client import GroqClient
from memory import ConversationMemory


class KafkaBot(commands.Bot):
    def __init__(self):
        self.prefix = os.getenv("BOT_PREFIX", "k!")

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix=self.prefix,
            intents=intents,
            help_command=None,
        )

        self.memory = ConversationMemory(
            max_history=int(os.getenv("MAX_HISTORY", "16"))
        )

        self.ai = GroqClient(
            api_key=os.environ["GROQ_API_KEY"],
            model=os.getenv(
                "GROQ_MODEL",
                "openai/gpt-oss-120b",
            ),
            max_output_tokens=int(
                os.getenv("MAX_OUTPUT_TOKENS", "768")
            ),
            max_concurrent_requests=int(
                os.getenv("MAX_CONCURRENT_REQUESTS", "3")
            ),
        )

        self.cooldown = float(
            os.getenv("USER_COOLDOWN", "2.0")
        )

        self.last_request = {}

    async def setup_hook(self):
        print("Kafka bot setup complete.")

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")
        print(f"Prefix: {self.prefix}")
        print("Kafka is ready.")

    def get_memory_key(self, message: discord.Message):
        return (message.channel.id, message.author.id)

    def on_cooldown(self, user_id: int) -> bool:
        now = time.monotonic()
        previous = self.last_request.get(user_id, 0.0)

        if now - previous < self.cooldown:
            return True

        self.last_request[user_id] = now
        return False

    @staticmethod
    def split_message(text: str, limit: int = 2000):
        if len(text) <= limit:
            return [text]

        chunks = []

        while len(text) > limit:
            split_at = text.rfind("\n", 0, limit)

            if split_at <= 0:
                split_at = text.rfind(" ", 0, limit)

            if split_at <= 0:
                split_at = limit

            chunks.append(text[:split_at].strip())
            text = text[split_at:].strip()

        if text:
            chunks.append(text)

        return chunks

    @staticmethod
    def clean_mention(message: discord.Message, content: str):
        mention_patterns = [
            rf"<@!?{message.guild.me.id}>" if message.guild and message.guild.me else None
        ]

        for pattern in mention_patterns:
            if pattern:
                content = re.sub(pattern, "", content)

        return content.strip()

    async def generate_reply(
        self,
        message: discord.Message,
        content: str,
    ):
        key = self.get_memory_key(message)

        self.memory.add_user(key, content)

        history = self.memory.get(key)

        try:
            response = await self.ai.generate(history)
        except Exception:
            self.memory.reset(key)
            raise

        self.memory.add_assistant(key, response)

        return response

    async def process_ai_message(self, message: discord.Message):
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user and self.user in message.mentions

        if not is_dm and not is_mentioned:
            return

        if message.content.startswith(self.prefix):
            return

        if self.on_cooldown(message.author.id):
            return

        content = message.content

        if is_mentioned:
            content = re.sub(
                rf"<@!?{self.user.id}>",
                "",
                content,
            ).strip()

        if not content:
            content = "You called for me?"

        async with message.channel.typing():
            try:
                response = await self.generate_reply(
                    message,
                    content,
                )
            except Exception as exc:
                print(f"Groq error: {exc}")
                await message.reply(
                    "Something went wrong with the connection. "
                    "How inconvenient.",
                    mention_author=False,
                )
                return

        chunks = self.split_message(response)

        for index, chunk in enumerate(chunks):
            if index == 0:
                await message.reply(
                    chunk,
                    mention_author=False,
                )
            else:
                await message.channel.send(chunk)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        await self.process_ai_message(message)
        await self.process_commands(message)


bot = KafkaBot()


@bot.command(name="kafka")
async def kafka(ctx, *, prompt: str = None):
    if not prompt:
        await ctx.reply(
            "Hmm? You summoned me without saying what you wanted.",
            mention_author=False,
        )
        return

    if bot.on_cooldown(ctx.author.id):
        return

    key = (ctx.channel.id, ctx.author.id)

    async with ctx.typing():
        try:
            response = await bot.generate_reply(ctx.message, prompt)
        except Exception as exc:
            print(f"Groq error: {exc}")
            await ctx.reply(
                "The connection failed. Try again in a moment.",
                mention_author=False,
            )
            return

    for chunk in bot.split_message(response):
        await ctx.reply(
            chunk,
            mention_author=False,
        )


@bot.command(name="reset")
async def reset(ctx):
    key = (ctx.channel.id, ctx.author.id)
    bot.memory.reset(key)

    await ctx.reply(
        "Our little conversation has been forgotten. "
        "Shall we begin again?",
        mention_author=False,
    )


@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(
        f"Pong. `{round(bot.latency * 1000)}ms`",
        mention_author=False,
    )


@bot.command(name="kafkahelp")
async def kafkahelp(ctx):
    await ctx.reply(
        f"**Kafka — Discord AI**\n\n"
        f"`{bot.prefix}kafka <message>` — Talk to Kafka\n"
        f"`{bot.prefix}reset` — Reset your conversation\n"
        f"`{bot.prefix}ping` — Check latency\n"
        f"`{bot.prefix}kafkahelp` — Show this help\n\n"
        f"You can also simply mention me.",
        mention_author=False,
    )