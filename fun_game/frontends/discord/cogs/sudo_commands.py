from typing import Iterable
from discord import app_commands
from discord.ext import commands
import discord

from fun_game.frontends.discord.bot import Bot

from .utils import paginate


def check_sudo():
    async def predicate(interaction: discord.Interaction) -> bool:
        if (interaction.user.guild_permissions.administrator or
            any(role.permissions.manage_guild or role.name == "Privileged Player"
                for role in interaction.user.roles)):
            return True
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

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
    bidding_group = app_commands.Group(
        name="bidding", parent=sudo_group, description="Manage bidding"
    )
    game_group = app_commands.Group(
        name="game", parent=sudo_group, description="Manage game"
    )

    @check_sudo()
    @game_group.command(name="clear", description="Reset game state")
    async def clear_game(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        success, response = guild_state.game_engine.clear_game()
        await interaction.response.send_message(response, ephemeral=not success)

    #@check_sudo()
    @game_group.command(name="start", description="Start game")
    async def start_game(self, interaction: discord.Interaction):
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

    @check_sudo()
    @game_group.command(name="leaderboard", description="Show player objectives")
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

        await interaction.response.send_message(replies[0], ephemeral=False)
        for reply in replies[1:]:
            await interaction.followup.send(reply, ephemeral=False)

    @check_sudo()
    @bidding_group.command(name="start", description="Start bidding auction")
    async def start_bidding(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        response = await guild_state.game_engine.start_bidding()
        await interaction.response.send_message(response, ephemeral=False)

    @check_sudo()
    @bidding_group.command(name="resolve", description="Resolve bidding auction")
    async def resolve_bidding(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        response = await guild_state.game_engine.resolve_bidding()
        await interaction.response.send_message(response, ephemeral=True)

    @check_sudo()
    @bidding_group.command(name="toggle", description="Enable or disable bidding")
    async def bidding_toggle(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        response = await guild_state.game_engine.toggle_bidding()
        await interaction.response.send_message(response, ephemeral=False)

    @check_sudo()
    @rule_group.command(name="show")
    async def show_rules(self, interaction: discord.Interaction):
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

    @check_sudo()
    @rule_group.command(name="add")
    async def add_rule(
        self,
        interaction: discord.Interaction,
        rule: str,
        secret: bool | None = False,
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

    @check_sudo()
    @rule_group.command(name="remove")
    async def remove_rule(self, interaction: discord.Interaction, rules: str):
        if not interaction.guild:
            return

        guild_state = self.bot.guild_states.get(interaction.guild.id)
        if not guild_state:
            return

        try:
            rule_ids = parse_range_csv(rules)
            guild_state.game_engine.remove_custom_rules(rule_ids)
            await interaction.response.send_message(
                f"Successfully removed {len(rules)} rules"
            )
        except ValueError:
            await interaction.response.send_message(
                f"Failed to understand rules. Please format as comma-separated numbers or ranges"
            )

    @check_sudo()
    @state_group.command(name="add")
    async def add_state(self, interaction: discord.Interaction, state: str):
        await interaction.response.send_message("Unimplemented")

    @check_sudo()
    @state_group.command(name="remove")
    async def remove_state(self, interaction: discord.Interaction, state: str):
        await interaction.response.send_message("Unimplemented")


def parse_range_csv(page_string) -> Iterable[int]:
    """
    Parses print job page numbers format into a list of integers.
    """
    items: set[int] = set()
    for part in page_string.split(","):
        if "-" in part:
            start, end = map(int, part.split("-"))
            if start <= end:
                for i in range(start, end + 1):
                    items.add(i)
        else:
            items.add(part)
    return items


async def setup(bot):
    await bot.add_cog(SudoCommands(bot))
