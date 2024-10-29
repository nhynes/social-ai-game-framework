import os
import asyncio
import logging

from dotenv import load_dotenv
import discord

from bot import Bot

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


async def main():
    async with Bot() as bot:
        try:
            await bot.start(os.environ["DISCORD_TOKEN"])
        except discord.LoginFailure:
            logger.error("Invalid token")
        except Exception as e:
            logger.error(f"Error running bot: {e}")


if __name__ == "__main__":
    asyncio.run(main())
