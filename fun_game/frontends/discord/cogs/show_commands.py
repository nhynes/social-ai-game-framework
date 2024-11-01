from enum import Enum
from typing import Iterable

from discord import app_commands
from discord.ext import commands
import discord

from fun_game.frontends.discord import Bot

from .utils import paginate


class Options(Enum):
    world = "world"
    inventory = "inventory"
    rules = "rules"


class ShowCommands(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    @app_commands.command()
    async def show(self, interaction: discord.Interaction, option: Options):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        items: Iterable[str]
        empty_message: str
        if option == Options.rules:
            items = (
                rule[1].rule
                for rule in guild_state.game_engine.custom_rules
                if not rule[1].secret
            )
            empty_message = "There are no custom rules."
        elif option == Options.inventory:
            items = guild_state.game_engine.player_inventory(interaction.user.id)
            empty_message = "Your inventory is empty."
        else:
            items = guild_state.game_engine.world_state
            empty_message = "The world is empty."

        if not items:
            await interaction.response.send_message(empty_message, ephemeral=True)
            return

        for reply in paginate(items):
            await interaction.response.send_message(reply, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ShowCommands(bot))
