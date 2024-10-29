from enum import Enum
from typing import Iterable, List

from discord import app_commands
from discord.ext import commands
import discord

from bot import MessageBot
from guild_state import GuildState


class Options(Enum):
    world = "world"
    inventory = "inventory"


class ShowCommands(commands.Cog):
    def __init__(self, bot):
        self.bot: MessageBot = bot

    @app_commands.command()
    async def show(self, interaction: discord.Interaction, option: Options):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        items = (
            _get_inventory_items(guild_state, interaction.user.id)
            if option == Options.inventory
            else _get_world_state_items(guild_state)
        )
        if not items:
            await interaction.response.send_message(
                f"{"Your" if option == Options.inventory else "The"} {option.value} is empty.",
                ephemeral=True,
            )
            return
        replies = _paginate(items)
        for reply in replies:
            await interaction.response.send_message(reply, ephemeral=True)


def _get_world_state_items(guild_state: GuildState) -> Iterable[str]:
    return guild_state.world_state


def _get_inventory_items(
    guild_state: GuildState, upstream_user_id: int
) -> Iterable[str]:
    with guild_state.db.connect() as db:
        user = db.get_user(upstream_user_id)
        if not user:
            return []
    return guild_state.player_inventories.get(user.id, set())


def _paginate(items: Iterable[str], max_chars=4000) -> List[str]:
    pages, current_page = [], []
    current_length = 0

    for item in items:
        formatted_item = f"- {item}\n"
        if current_length + len(formatted_item) > max_chars:
            pages.append("".join(current_page))
            current_page = [formatted_item]
            current_length = len(formatted_item)
        else:
            current_page.append(formatted_item)
            current_length += len(formatted_item)

    if current_page:
        pages.append("".join(current_page))

    return pages


async def setup(bot):
    await bot.add_cog(ShowCommands(bot))
