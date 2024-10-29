from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from guild_state import GuildState

if TYPE_CHECKING:
    from cogs.message_handler import MessageHandler

logger = logging.getLogger("discord_bot")


COMMAND_PREFIX = "/"


class MessageBot(commands.Bot):
    def __init__(self, anthropic: AsyncAnthropic, openai: AsyncOpenAI):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions

        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            proxy=os.environ.get("HTTPS_PROXY"),
        )

        self.anthropic = anthropic
        self.openai = openai
        self.guild_states: dict[int, GuildState] = {}
        self.message_handler: Optional[MessageHandler] = None
        self.ensure_data_directory()

    @staticmethod
    def ensure_data_directory():
        Path("data").mkdir(exist_ok=True)

    async def setup_hook(self):
        self.message_handler = await self.load_extension("cogs.message_handler")
        for ext in [
            "cogs.sudo_commands",
            "cogs.show_commands",
            "cogs.reaction_handler",
        ]:
            await self.load_extension(ext)
        await self.tree.sync()

    async def on_ready(self):
        logger.info(f"Bot connected as {self.user}")
        for guild in self.guilds:
            await self.on_guild_join(guild)

    async def on_guild_join(self, guild):
        await self.initialize_guild(guild)
        if self.message_handler:
            self.loop.create_task(self.message_handler.start_processing(guild.id))

    async def initialize_guild(self, guild: discord.Guild):
        guild_state = GuildState(guild.id)
        await guild_state.initialize()

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
