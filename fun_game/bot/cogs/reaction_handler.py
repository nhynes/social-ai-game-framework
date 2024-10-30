from functools import wraps
import logging

from discord.ext import commands
import discord

from ..bot import Bot
from ..guild_state import GuildState
from .message_handler import do_handle_message
from fun_game.game import Frontend, GameContext

logger = logging.getLogger("bot.cogs.reaction_handler")


def _reaction_handler(func):
    @wraps(func)
    async def wrapper(self, payload: discord.RawReactionActionEvent):
        assert isinstance(self.bot, Bot)
        if (
            self.bot.user is None
            or payload.user_id == self.bot.user.id
            or payload.guild_id is None
        ):
            return

        guild_state = self.bot.guild_states.get(payload.guild_id)
        if (
            not guild_state
            or guild_state.game_channel is None
            or payload.channel_id != guild_state.game_channel.id
        ):
            return

        await func(self, payload, guild_state)

    return wrapper


class ReactionHandler(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    @commands.Cog.listener()
    @_reaction_handler
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent,
        guild_state: GuildState,
    ):
        if str(payload.emoji) == "📤":
            channel = self.bot.get_channel(payload.channel_id)
            assert isinstance(channel, discord.TextChannel)
            message = await channel.fetch_message(payload.message_id)

            context = GameContext(
                frontend=Frontend.DISCORD,
                user_id=payload.message_id,
                user_name=message.author.display_name,
                message_content=message.content,
                message_id=message.id,
                reply_to_message_id=(
                    message.reference.message_id if message.reference else None
                ),
                force_feed=True,
            )

            await do_handle_message(message, guild_state, context)
            return

        user = await self.bot.fetch_user(payload.user_id)
        guild_state.game_engine.add_reaction(
            Frontend.DISCORD,
            payload.message_id,
            user.id,
            user.display_name,
            str(payload.emoji),
        )

    @commands.Cog.listener()
    @_reaction_handler
    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent,
        guild_state: GuildState,
    ):
        user = await self.bot.fetch_user(payload.user_id)
        guild_state.game_engine.remove_reaction(
            Frontend.DISCORD,
            payload.message_id,
            user.id,
            user.display_name,
            str(payload.emoji),
        )


async def setup(bot):
    await bot.add_cog(ReactionHandler(bot))
