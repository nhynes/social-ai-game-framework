from __future__ import annotations
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

from .guild_state import GuildState

COMMAND_PREFIX = "/"

logger = logging.getLogger("bot")


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        intents.reactions = True

        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            proxy=os.environ.get("HTTPS_PROXY"),
        )

        self.guild_states: dict[int, GuildState] = {}
        self.ensure_data_directory()

    @staticmethod
    def ensure_data_directory():
        Path("data").mkdir(exist_ok=True)

    async def setup_hook(self):
        for ext in [
            "bot.cogs.message_handler",
            "bot.cogs.sudo_commands",
            "bot.cogs.show_commands",
            "bot.cogs.reaction_handler",
        ]:
            await self.load_extension(ext)
        await self.tree.sync()

    async def on_ready(self):
        logger.info(f"Bot connected as {self.user}")
        for guild in self.guilds:
            await self.on_guild_join(guild)

    async def on_guild_join(self, guild):
        guild_state = GuildState(guild.id)

        # Look for existing channel
        channel = discord.utils.get(guild.channels, id=1300287188365475940)
        if not channel:
            print("no rosys-llm-playground channel")
            channel = discord.utils.get(guild.channels, name="fun-game")
            if not channel:
                print("no fun-game channel")
                try:
                    channel = await guild.create_text_channel("fun-game")
                    logger.info(f"Created channel #fun-game in {guild.name}")
                except discord.Forbidden:
                    logger.error(
                        f"Bot doesn't have permission to create channels in {guild.name}"
                    )
                    return

        if not isinstance(channel, discord.TextChannel):
            return
        guild_state.game_channel = channel
        self.guild_states[guild.id] = guild_state
        logger.info(f"Initialized guild state for {guild.name} (ID: {guild.id})")
