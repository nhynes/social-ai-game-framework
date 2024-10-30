import asyncio
import logging

from typing import Iterable

import discord
from discord.ext import commands

from fun_game.game import GameContext, Frontend
from fun_game.bot import Bot, GuildState

logger = logging.getLogger("bot.cogs.message_handler")
logger.setLevel(logging.DEBUG)


class MessageHandler(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self._processing = False

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild:
            return
        guild_state = self.bot.guild_states.get(message.guild.id)
        if (
            not guild_state
            or not guild_state.game_channel
            or message.channel.id != guild_state.game_channel.id
        ):
            return
        await guild_state.message_queue.put(message)
        if not self._processing:
            self.bot.loop.create_task(self.process_messages(message.guild.id))
            self._processing = True

    async def process_messages(self, guild_id: int):
        guild_state = self.bot.guild_states[guild_id]
        try:
            while True:
                message = await guild_state.message_queue.get()
                logger.debug("processing message")
                try:
                    await self.handle_message(message, guild_state)
                except Exception as e:
                    logger.error(
                        f"error processing message in guild %s: %s",
                        guild_id,
                        e,
                        exc_info=True,
                    )
                finally:
                    guild_state.message_queue.task_done()
        except asyncio.CancelledError:
            pass

    async def handle_message(self, message: discord.Message, guild_state: GuildState):
        if message.author == self.bot.user or message.author.bot:
            return

        logger.debug(
            "received message from %s: %s", message.author.display_name, message.content
        )
        context = GameContext(
            frontend=Frontend.DISCORD,
            user_id=message.author.id,
            user_name=message.author.display_name,
            message_content=message.content,
            message_id=message.id,
            reply_to_message_id=(
                message.reference.message_id if message.reference else None
            ),
            force_feed=(
                self.bot.user is not None
                and (
                    # The bot is mentioned
                    any(mention.id == self.bot.user.id for mention in message.mentions)
                    or (
                        # The bot is replied to
                        message.reference is not None
                        and message.reference.message_id is not None
                        and (
                            await message.channel.fetch_message(
                                message.reference.message_id
                            )
                        ).author
                        == self.bot.user
                    )
                )
            ),
        )
        logger.debug(
            "handling message from %s: %s. force=%s",
            message.author.display_name,
            message.content,
            context.force_feed,
        )

        return await do_handle_message(message, guild_state, context)


async def do_handle_message(
    message: discord.Message, guild_state: GuildState, context: GameContext
):
    game_response = await guild_state.game_engine.process_message(
        context, message.channel.typing
    )
    if not game_response:
        logger.debug("game did not produce a response")
        return
    logger.debug("got game response")

    reply = await message.reply(game_response.response_text)
    game_response.mark_responded(reply.id)
    add_reactions(reply, ["👍", "👎"])


def add_reactions(message: discord.Message, reactions: Iterable[str]):
    async def _add_reactions():
        for reaction in reactions:
            await message.add_reaction(reaction)

    asyncio.create_task(_add_reactions())


async def setup(bot):
    handler = MessageHandler(bot)
    await bot.add_cog(handler)
    return handler
