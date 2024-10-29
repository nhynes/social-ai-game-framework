import asyncio
from typing import Optional

import discord

from fun_game.game import Frontend, GameEngine


class GuildState:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.game_channel: Optional[discord.TextChannel] = None
        self.message_queue: asyncio.Queue[discord.Message] = asyncio.Queue()
        self.game_engine = GameEngine(Frontend.discord, guild_id)
