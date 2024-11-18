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

        await guild_state.game_engine.add_objective(objective, interaction.user.id, interaction.user.display_name)
        await interaction.response.send_message("Objective noted!", ephemeral=True)

    @app_commands.command(name="leaderboard", description="View the leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        user_scores = guild_state.game_engine.leaderboard()
        replies = paginate(user_scores, prefix="")

        if not replies:
            await interaction.response.send_message("Leaderboard is empty.", ephemeral=False)
            return

        for reply in replies:
            await interaction.response.send_message(reply, ephemeral=False)

    @app_commands.command(name="start", description="Start the game")
    async def start(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        success, response = await guild_state.game_engine.start_game()
        if success:
            await interaction.response.send_message("Waking up John...", ephemeral=False)
        else:
            await interaction.response.send_message(response, ephemeral=True)

    @app_commands.command(name="bid", description="Bid to take control of John.")
    async def bid(self, interaction: discord.Interaction, value: int):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        _, response = await guild_state.game_engine.add_bid(value, interaction.user.id)
        await interaction.response.send_message(response, ephemeral=True)

async def setup(bot):
    await bot.add_cog(JohnCommands(bot))
