import logging

from bot import bot
from config import SETTINGS


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("Starting Kafka bot with model %s", SETTINGS.groq_model)
    bot.run(SETTINGS.discord_token)


if __name__ == "__main__":
    main()
