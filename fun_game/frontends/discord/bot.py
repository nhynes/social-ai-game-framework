from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Callable

import discord
from discord.ext import commands

from fun_game.config import DiscordFrontendConfig
from fun_game.game.engine import GameEngine

from .guild_state import GuildState

COMMAND_PREFIX = "/"

logger = logging.getLogger("bot")


class Bot(commands.Bot):
    def __init__(
        self, config: DiscordFrontendConfig, engine_factory: Callable[[str, discord.TextChannel | None], GameEngine]
    ) -> None:
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

        self._config = config
        self.guild_states: dict[int, GuildState] = {}
        self._engine_factory = engine_factory
        self.ensure_data_directory()

    @staticmethod
    def ensure_data_directory():
        Path("data").mkdir(exist_ok=True)

    async def setup_hook(self):
        for ext in [
            "frontends.discord.cogs.message_handler",
            "frontends.discord.cogs.sudo_commands",
            "frontends.discord.cogs.show_commands",
            "frontends.discord.cogs.john_commands",
            "frontends.discord.cogs.reaction_handler",
        ]:
            await self.load_extension(ext)
        await self.tree.sync()

    async def on_ready(self):
        logger.info("Bot connected as %s", self.user)
        for guild in self.guilds:
            await self.on_guild_join(guild)

    async def on_guild_join(self, guild):
        # Look for existing channel
        channel = discord.utils.get(guild.channels, name=self._config.channel_name)
        if not channel:
            try:
                channel = await guild.create_text_channel(self._config.channel_name)
                logger.info(
                    "Created channel #%s in %s", self._config.channel_name, guild.name
                )
            except discord.Forbidden:
                logger.error(
                    "Bot doesn't have permission to create channels in %s",
                    guild.name,
                )
                return

        if not isinstance(channel, discord.TextChannel):
            return

        guild_state = GuildState(
            guild.id, game_engine=self._engine_factory(f"discord_guild_{guild.id}", channel), game_channel=channel
        )

        self.guild_states[guild.id] = guild_state
        logger.info("Initialized guild state for %s (ID: %s)", guild.name, guild.id)
