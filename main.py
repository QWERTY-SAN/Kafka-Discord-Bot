import asyncio
import logging

from aiohttp import web

from bot import bot
from config import SETTINGS

logger = logging.getLogger(__name__)


async def health(request: web.Request) -> web.Response:
    return web.Response(text="Kafka is online.")


async def start_health_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", SETTINGS.port)
    await site.start()

    logger.info("Health server listening on 0.0.0.0:%s", SETTINGS.port)
    return runner


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def async_main() -> None:
    health_runner = await start_health_server()
    try:
        logger.info("Starting Kafka bot with model %s", SETTINGS.gemini_model)
        await bot.start(SETTINGS.discord_token)
    finally:
        await health_runner.cleanup()


def main() -> None:
    configure_logging()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
