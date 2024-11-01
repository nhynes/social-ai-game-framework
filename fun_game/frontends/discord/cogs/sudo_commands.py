from discord import app_commands
from discord.ext import commands
import discord


class SudoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    sudo_group = app_commands.Group(name="sudo", description="Admin commands")
    rule_group = app_commands.Group(
        name="rules", parent=sudo_group, description="Manage rules"
    )
    state_group = app_commands.Group(
        name="state", parent=sudo_group, description="Manage state"
    )

    @rule_group.command(name="show")
    async def show_rules(self, interaction: discord.Interaction, rule: str):
        # Show all rules (even hidden ones) in an ephemeral message
        pass

    @rule_group.command(name="edit")
    async def edit_rules(self, interaction: discord.Interaction, rule: str):
        # Replace the current set of rules with what is pasted in (likely based on `/sudo rules show`)
        pass

    @rule_group.command(name="add")
    async def add_rule(self, interaction: discord.Interaction, rule: str):
        # There should be some way to specify whether the rule is public or private
        pass

    @rule_group.command(name="remove")
    async def remove_rule(self, interaction: discord.Interaction, rule: str):
        pass

    @state_group.command(name="add")
    async def add_state(self, interaction: discord.Interaction, state: str):
        pass

    @state_group.command(name="remove")
    async def remove_state(self, interaction: discord.Interaction, state: str):
        pass


async def setup(bot):
    await bot.add_cog(SudoCommands(bot))


# async def handle_sudo_command(
#     self,
#     guild_id: int,
#     author: Union[discord.User, discord.Member],
#     message: discord.Message,
# ) -> Optional[str]:
#     guild_state = self.guild_states.get(guild_id)
#     if not guild_state:
#         return None

#     with guild_state.db.connect() as db:
#         user = db.get_or_create_user(author.id, author.display_name)
#         db.add_message(
#             message.content,
#             user.id,
#             message.id,
#             message.reference.message_id if message.reference else None,
#         )
#         async with message.channel.typing():
#             await self._handle_game_message(
#                 db, guild_state, user, message, sudo=True
#             )
# @commands.command()
# async def sudo(ctx: commands.Context):
# if not ctx.guild:
#     return
# if ctx.author == ctx.guild.owner or any(
#     role.id == 1291367449001721888
#     for role in (ctx.author.roles if isinstance(ctx.author, discord.Member) else [])
# ):
#     assert isinstance(ctx.bot, MessageBot)
#     await ctx.bot.handle_sudo_command(ctx.guild.id, ctx.author, ctx.message)
