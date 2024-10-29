from functools import wraps
import logging

from discord.ext import commands
import discord

from fun_game.bot import MessageBot

logger = logging.getLogger("discord_bot.reaction_handler")


def _reaction_handler(func):
    @wraps(func)
    async def wrapper(self, payload: discord.RawReactionActionEvent):
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

        with guild_state.db.connect() as db:
            message = db.get_message(payload.message_id)
            if not message:
                return

            user = db.get_user(payload.user_id)
            if not user:
                return

            await func(self, payload, guild_state, db, message, user)

    return wrapper


class ReactionHandler(commands.Cog):
    def __init__(self, bot):
        self.bot: MessageBot = bot

    @commands.Cog.listener()
    @_reaction_handler
    async def on_raw_reaction_add(self, payload, guild_state, db, message, user):
        if (
            message.sender_id != 0
            and str(payload.emoji) == "📤"
            and message.status == "filtered"
        ):
            db.unfilter_message(message.id)

            channel = self.bot.get_channel(payload.channel_id)
            assert isinstance(channel, discord.TextChannel)
            discord_message = await channel.fetch_message(payload.message_id)

            if not self.bot.message_handler:
                return
            await self.bot.message_handler.handle_game_message(db, guild_state, user, discord_message)
            return

        if str(payload.emoji) == "❌":
            db.mark_message_irrelevant(message.id)
            return

        logger.debug(f"{user.name} added reaction {payload.emoji} to message")
        db.add_reaction(message.id, user.id if user else None, str(payload.emoji))

    @commands.Cog.listener()
    @_reaction_handler
    async def on_raw_reaction_remove(self, payload, _, db, message, user):
        logger.debug(f"{user.name} removed reaction {payload.emoji} to message")
        db.remove_reaction(message.id, user.id, str(payload.emoji))


async def setup(bot):
    await bot.add_cog(ReactionHandler(bot))
