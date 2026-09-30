import logging

from bot import create_bot
from config import load_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> None:
    config = load_config()
    bot = create_bot(config)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
