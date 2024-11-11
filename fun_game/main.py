import argparse
import os
import asyncio
import logging

from dotenv import load_dotenv
import discord

from fun_game.config import Config
from fun_game.frontends import Discord
from fun_game.game import GameEngine

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, help="Path to config file", required=True)
    args = parser.parse_args()

    config = Config.load(args.config)

    if config.frontend.discord:
        async with Discord(
            config.frontend.discord, engine_factory=GameEngine.make_factory(config.game)
        ) as bot:
            try:
                await bot.start(os.environ["DISCORD_TOKEN"])
            except discord.LoginFailure:
                logger.error("Invalid token")
            except Exception as e:
                logger.error("Error running bot: %s", e)
    else:
        raise TypeError("no frontend specified")


if __name__ == "__main__":
    asyncio.run(main())
