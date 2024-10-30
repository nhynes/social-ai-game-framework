import asyncio
from dataclasses import dataclass, field
from typing import Optional

import discord

from fun_game.game import Frontend, GameEngine


@dataclass
class GuildState:
    guild_id: int
    game_channel: Optional[discord.TextChannel] = None
    message_queue: asyncio.Queue[discord.Message] = field(default_factory=asyncio.Queue)
    game_engine: GameEngine = field(init=False)

    def __post_init__(self):
        self.game_engine = GameEngine(Frontend.DISCORD, self.guild_id)
