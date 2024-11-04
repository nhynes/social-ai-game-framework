from typing import Optional

from discord import app_commands
from discord.ext import commands
import discord

from fun_game.frontends.discord.bot import Bot

from .utils import paginate


class SudoCommands(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    sudo_group = app_commands.Group(name="sudo", description="Admin commands")
    rule_group = app_commands.Group(
        name="rules", parent=sudo_group, description="Manage rules"
    )
    state_group = app_commands.Group(
        name="state", parent=sudo_group, description="Manage state"
    )

    @rule_group.command(name="show")
    async def show_rules(self, interaction: discord.Interaction):
        # TODO: restrict this to admins?
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        replies = paginate(
            (
                f"{rule_id}. {rule}"
                for rule_id, rule in guild_state.game_engine.custom_rules
            ),
            prefix="",
        )
        if not replies:
            await interaction.response.send_message(
                "There are no custom rules yet.", ephemeral=True
            )
            return

        for reply in replies:
            await interaction.response.send_message(reply, ephemeral=True)

    @rule_group.command(name="add")
    async def add_rule(
        self,
        interaction: discord.Interaction,
        rule: str,
        secret: Optional[bool] = False,
    ):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        rule_id = guild_state.game_engine.add_custom_rule(
            rule, interaction.user.id, secret or False
        )
        if rule_id:
            await interaction.response.send_message(
                f"Successfully created rule #{rule_id}", ephemeral=True
            )

    @rule_group.command(name="remove")
    async def remove_rule(self, interaction: discord.Interaction, rule_id: int):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        guild_state.game_engine.remove_custom_rule(rule_id)

    @state_group.command(name="add")
    async def add_state(self, interaction: discord.Interaction, state: str):
        pass

    @state_group.command(name="remove")
    async def remove_state(self, interaction: discord.Interaction, state: str):
        pass


async def setup(bot):
    await bot.add_cog(SudoCommands(bot))
