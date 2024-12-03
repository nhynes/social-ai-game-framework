from discord.ext import commands
from discord import app_commands
import discord

from .utils import paginate

class JohnCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register", description="Register a new objective")
    async def register(self, interaction: discord.Interaction, objective: str):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        if not objective:
            await interaction.response.send_message("You need to specify an objective.", ephemeral=True)
            return

        response = await guild_state.game_engine.add_objective(objective, interaction.user.id, interaction.user.display_name)
        await interaction.response.send_message(response, ephemeral=True)

    @app_commands.command(name="bid", description="Bid to take control of John")
    async def bid(self, interaction: discord.Interaction, value: int):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        response = await guild_state.game_engine.add_bid(value, interaction.user.id)
        await interaction.response.send_message(response, ephemeral=True)

async def setup(bot):
    await bot.add_cog(JohnCommands(bot))
