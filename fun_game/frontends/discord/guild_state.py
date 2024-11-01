import asyncio
from dataclasses import dataclass, field
from typing import Optional

import discord

from fun_game.game import GameEngine


@dataclass
class GuildState:
    guild_id: int
    game_engine: GameEngine
    game_channel: Optional[discord.TextChannel] = None
    message_queue: asyncio.Queue[discord.Message] = field(default_factory=asyncio.Queue)
