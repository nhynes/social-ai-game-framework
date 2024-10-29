import asyncio
from collections import defaultdict
from typing import Dict, Optional, Set

import discord

from database import Database


class GuildState:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.db = Database(f"data/guild_{guild_id}.db")
        self.player_inventories: Dict[int, Set[str]] = defaultdict(set)
        self.world_state: Set[str] = (
            set()
        )  # TODO: track whether the item was created through sudo
        self.game_channel: Optional[discord.TextChannel] = None
        self.message_queue: asyncio.Queue[discord.Message] = asyncio.Queue()

    async def initialize(self):
        with self.db.connect() as db:
            self.world_state = db.load_world_state()
