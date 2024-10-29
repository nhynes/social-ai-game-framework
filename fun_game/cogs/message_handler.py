import asyncio
import logging

from typing import Iterable, Optional

import discord
from discord.ext import commands

from fun_game.bot import COMMAND_PREFIX
from fun_game.database import DatabaseConnection, User
from fun_game.prompts import *
from guild_state import GuildState

logger = logging.getLogger("discord_bot.message_handler")


class MessageHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    async def start_processing(self, guild_id: int):
        await self.process_messages(guild_id)

    async def process_messages(self, guild_id: int):
        guild_state = self.bot.guild_states[guild_id]
        try:
            while True:
                message = await guild_state.message_queue.get()
                try:
                    await self.handle_message(message, guild_state)
                except Exception as e:
                    logger.error(f"Error processing message in guild {guild_id}: {e}")
                finally:
                    guild_state.message_queue.task_done()
        except asyncio.CancelledError:
            pass

    async def handle_message(self, message: discord.Message, guild_state: GuildState):
        if message.author == self.bot.user or message.author.bot:
            return

        filtered: Optional[bool] = None
        if message.content.startswith(COMMAND_PREFIX) or message.content.startswith(
            "!"
        ):
            filtered = True
        elif self.bot.user and any(
            mention.id == self.bot.user.id for mention in message.mentions
        ):
            filtered = False
        elif (
            message.reference
            and message.reference.message_id
            and guild_state.game_channel
        ):
            ref = await guild_state.game_channel.fetch_message(
                message.reference.message_id
            )
            if ref.author == self.bot.user:
                filtered = False

        if filtered is None:
            filter_response = parse_ai_response(
                await self.bot.openai.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=512,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": FILTER_SYSTEM_PROMPT},
                        {"role": "user", "content": message.content},
                    ],
                ),
                FilterModelResponse,
            )
            print("filter response", filter_response)
            filtered = not filter_response.forward and filter_response.confidence > 0.5

        with guild_state.db.connect() as db:
            user = db.get_or_create_user(message.author.id, message.author.display_name)

            db.add_message(
                message.content,
                user.id,
                message.id,
                message.reference.message_id if message.reference else None,
                filtered=filtered,
            )
            if filtered:
                return

            async with message.channel.typing():
                await self.handle_game_message(db, guild_state, user, message)

    async def handle_game_message(
        self,
        db: DatabaseConnection,
        guild_state: GuildState,
        user: User,
        message: discord.Message,
        sudo: Optional[bool] = False,
    ):
        if user.id not in guild_state.player_inventories:
            guild_state.player_inventories[user.id] = db.load_player_inventory(user.id)

        reply_message_id = None
        if message.reference and message.reference.message_id:
            reply_message = db.get_message(message.reference.message_id)
            if reply_message:
                reply_message_id = reply_message.id

        system_prompt = make_game_system_prompt(
            guild_state.world_state,
            user.name,
            guild_state.player_inventories[user.id],
            db.get_message_context(reply_message_id),
            sudo=sudo,
        )

        try:
            model_response = parse_ai_response(
                await self.bot.anthropic.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": message.content}],
                ),
                GameModelResponse,
            )
        except Exception as e:
            logger.error(f"Failed to fetch game model response: {e}")
            return

        trigger_message_id = db.add_message(
            message.content,
            user.id,
            message.id,
            message.reference.message_id if message.reference else None,
        )

        db.update_game_state(
            user_id=user.id,
            world_changes=model_response.world_state_updates,
            inventory_changes=model_response.player_inventory_updates,
            trigger_message_id=trigger_message_id,
        )

        # Update in-memory state
        if model_response.player_inventory_updates:
            for (
                item,
                should_add,
            ) in model_response.player_inventory_updates.items():
                if should_add:
                    guild_state.player_inventories[user.id].add(item)
                else:
                    guild_state.player_inventories[user.id].discard(item)

        if model_response.world_state_updates:
            for item, should_add in model_response.world_state_updates.items():
                if should_add:
                    guild_state.world_state.add(item)
                else:
                    guild_state.world_state.discard(item)

        try:
            reply_id = db.add_message(model_response.response, 0, None, message.id)
            reply = await message.reply(model_response.response)
            db.mark_message_sent(reply_id, reply.id)
            add_reactions(reply, ["👍", "👎", "❌"])
        except Exception as e:
            logger.error(f"Failed to make reply:", e)

        remove_reactions(self.bot.user, message, ["⏳"])


def add_reactions(message: discord.Message, reactions: Iterable[str]):
    async def _add_reactions():
        for reaction in reactions:
            await message.add_reaction(reaction)

    asyncio.create_task(_add_reactions())


def remove_reactions(
    user: Optional[discord.user.ClientUser],
    message: discord.Message,
    reactions: Iterable[str],
):
    if not user:
        return

    async def _remove_reactions():
        for reaction in reactions:
            try:
                await message.remove_reaction(reaction, user)
            except Exception as e:
                logger.error(f"Failed to add {reaction} reaction: {e}")

    asyncio.create_task(_remove_reactions())


async def setup(bot):
    handler = MessageHandler(bot)
    await bot.add_cog(handler)
    return handler
