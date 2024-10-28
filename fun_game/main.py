import asyncio
import logging
from dotenv import load_dotenv
import os

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
import discord

from bot import MessageBot

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord_bot")


async def main():
    anthropic = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    openai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    async with MessageBot(anthropic=anthropic, openai=openai) as bot:
        try:
            await bot.start(os.environ["DISCORD_TOKEN"])
        except discord.LoginFailure:
            logger.error("Invalid token")
        except Exception as e:
            logger.error(f"Error running bot: {e}")


if __name__ == "__main__":
    asyncio.run(main())
