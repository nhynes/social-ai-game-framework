from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Callable

import discord
from discord.ext import commands

from fun_game.game.engine import GameEngine

from .guild_state import GuildState

COMMAND_PREFIX = "/"

logger = logging.getLogger("bot")


class Bot(commands.Bot):
    def __init__(self, engine_factory: Callable[[int], GameEngine]) -> None:
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
        self._engine_factory = engine_factory
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
        logger.info("Bot connected as %s", self.user)
        for guild in self.guilds:
            await self.on_guild_join(guild)

    async def on_guild_join(self, guild):
        guild_state = GuildState(guild.id, game_engine=self._engine_factory(guild.id))

        # Look for existing channel
        channel = discord.utils.get(guild.channels, id=1300287188365475940)
        if not channel:
            print("no rosys-llm-playground channel")
            channel = discord.utils.get(guild.channels, name="fun-game")
            if not channel:
                print("no fun-game channel")
                try:
                    channel = await guild.create_text_channel("fun-game")
                    logger.info("Created channel #fun-game in %s", guild.name)
                except discord.Forbidden:
                    logger.error(
                        "Bot doesn't have permission to create channels in %s",
                        guild.name,
                    )
                    return

        if not isinstance(channel, discord.TextChannel):
            return
        guild_state.game_channel = channel
        self.guild_states[guild.id] = guild_state
        logger.info("Initialized guild state for %s (ID: %s)", guild.name, guild.id)
