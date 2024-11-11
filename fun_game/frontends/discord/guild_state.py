import asyncio
from dataclasses import dataclass, field

import discord

from fun_game.game import GameEngine


@dataclass
class GuildState:
    guild_id: int
    game_engine: GameEngine
    game_channel: discord.TextChannel | None = None
    message_queue: asyncio.Queue[discord.Message] = field(default_factory=asyncio.Queue)
