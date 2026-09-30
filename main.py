import os

from dotenv import load_dotenv

from bot import bot


def main():
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN")

    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not configured."
        )

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    bot.run(token)


if __name__ == "__main__":
    main()