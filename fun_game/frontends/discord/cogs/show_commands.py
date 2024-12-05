from enum import Enum
from typing import Iterable

from discord import app_commands
from discord.ext import commands
import discord

from fun_game.frontends.discord import Bot

from .utils import paginate


_instructions_message = """**Welcome to Everyone is Agent John!** An AI-powered, turn-based, competitive role-playing game, inspired by the classic tabletop game "Everyone is John".

John is an insane AI agent with multiple personality disorder.
Each player acts as a distinct personality, instructing John to take actions in pursuit of their own secret objectives.

**Objectives**
Each player can register one or more objectives that they will attempt to fulfill during the game. Final scores are calculated by counting the number of times each objective has been fulfilled, multiplied by the objective's difficulty.

Objectives are registered before the game begins, and additional objectives can be registered during the game. Players can join mid-game by registering an objective.

Use ``/register`` to register an objective.

**Fight for Control**
The game will have multiple _Fight for Control_ phases, during which players place secret bids to take control of John.

All players start with 10 bidding points and passively gain 1 point after every turn.
Use ``/bid`` to place your bids. All bids remain secret.
The highest bidder takes control of John. Ties are resolved randomly.

**Turns**
During a player's turn, the bot will only accept messages from that player. Each turn lasts 3 minutes, but may end sooner if John attempts and fails a risky action that requires luck or skill to complete. John has a 50% chance of successfully completing such actions.

**Gameplay**
Start by registering initial objectives with ``/register``. Then use ``/sudo game start`` to wake up John. In every game, John will wake up in a different situation, making each game unique. End the game with ``/sudo game clear`` to reveal player objectives and their scores. You can then start a new game.
"""

class Options(Enum):
    world = "world"
    inventory = "inventory"
    rules = "rules"
    points = "points"
    instructions = "instructions"


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

        if option == Options.points:
            points = guild_state.game_engine.player_points(interaction.user.id)
            message = f"You have {points} points available."
            await interaction.response.send_message(message, ephemeral=True)
            return

        if option == Options.instructions:
            await interaction.response.send_message(_instructions_message, ephemeral=True)
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
            items = guild_state.game_engine.player_inventory(user_id=0) # HACK to share inventory
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
