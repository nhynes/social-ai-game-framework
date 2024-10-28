import asyncio
from collections import defaultdict
from contextlib import contextmanager
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

import discord
from discord.ext import commands
from discord import app_commands
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from prompts import *

logger = logging.getLogger("discord_bot")

from database import Database, DatabaseConnection, User


COMMAND_PREFIX = "/"


class GuildState:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.db = Database(f"data/guild_{guild_id}.db")
        self.player_inventories: Dict[int, Set[str]] = defaultdict(set)
        self.world_state: Set[str] = (
            set()
        )  # TODO: track whether the item was created through sudo
        self.game_channel: Optional[discord.TextChannel] = None
        self.message_queue: asyncio.Queue[discord.Message] = asyncio.Queue()

    async def initialize(self):
        with self.db.connect() as db:
            self.world_state = db.load_world_state()


class MessageBot(commands.Bot):
    def __init__(self, anthropic: AsyncAnthropic, openai: AsyncOpenAI):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions

        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            proxy=os.environ.get("HTTPS_PROXY"),
        )
        self.anthropic = anthropic
        self.openai = openai
        self.guild_states: dict[int, GuildState] = {}
        self.ensure_data_directory()

        self.add_command(show)
        self.add_command(sudo)

    @staticmethod
    def ensure_data_directory():
        Path("data").mkdir(exist_ok=True)

    async def initialize_guild(self, guild: discord.Guild):
        guild_state = GuildState(guild.id)
        await guild_state.initialize()

        # Look for existing channel
        channel = discord.utils.get(guild.channels, id=1300287188365475940)
        if not channel:
            print("no rosys-llm-playground channel")
            channel = discord.utils.get(guild.channels, name="fun-game")
            if not channel:
                print("no fun-game channel")
                try:
                    channel = await guild.create_text_channel("fun-game")
                    logger.info(f"Created channel #fun-game in {guild.name}")
                except discord.Forbidden:
                    logger.error(
                        f"Bot doesn't have permission to create channels in {guild.name}"
                    )
                    return

        if not isinstance(channel, discord.TextChannel):
            return
        guild_state.game_channel = channel
        self.guild_states[guild.id] = guild_state
        logger.info(f"Initialized guild state for {guild.name} (ID: {guild.id})")

    async def on_guild_join(self, guild: discord.Guild):
        await self.initialize_guild(guild)
        self.loop.create_task(self.process_messages(guild.id))

    async def on_ready(self):
        logger.info(f"Bot connected as {self.user}")
        for guild in self.guilds:
            await self.initialize_guild(guild)
            self.loop.create_task(self.process_messages(guild.id))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if (
            self.user is None
            or payload.user_id == self.user.id
            or payload.guild_id is None
        ):
            return

        guild_state = self.guild_states.get(payload.guild_id)
        if (
            not guild_state
            or guild_state.game_channel is None
            or payload.channel_id != guild_state.game_channel.id
        ):
            return

        async def _get_discord_message() -> discord.Message:
            channel = self.get_channel(payload.channel_id)
            assert isinstance(channel, discord.TextChannel)
            return await channel.fetch_message(payload.message_id)

        with guild_state.db.connect() as db:
            message = db.get_message(payload.message_id)
            if not message:
                return

            if message.sender_id != 0:
                if str(payload.emoji) == "📤":
                    if message.status != "filtered":
                        db.unfilter_message(message.id)
                    user = db.get_user(payload.user_id)
                    if not user:
                        return
                    await self._handle_game_message(
                        db, guild_state, user, await _get_discord_message()
                    )
                return

            if str(payload.emoji) == "❌":
                # asyncio.create_task((await _get_discord_message()).delete())
                db.mark_message_irrelevant(message.id)
                return

            user = db.get_user(payload.user_id)
            if not user:
                return
            logger.debug(f"{user.name} added reaction {payload.emoji} to message")
            db.add_reaction(message.id, user.id if user else None, str(payload.emoji))

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if (
            self.user is None
            or payload.user_id == self.user.id
            or payload.guild_id is None
        ):
            return

        guild_state = self.guild_states.get(payload.guild_id)
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
            logger.debug(f"{user.name} removed reaction {payload.emoji} to message")
            db.remove_reaction(message.id, user.id, str(payload.emoji))

    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        guild_state = self.guild_states.get(message.guild.id)
        if (
            not guild_state
            or not guild_state.game_channel
            or message.channel.id != guild_state.game_channel.id
        ):
            return
        await guild_state.message_queue.put(message)
        await self.process_commands(message)

    async def process_messages(self, guild_id: int):
        guild_state = self.guild_states[guild_id]
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
        if message.author == self.user or message.author.bot:
            return

        filtered: Optional[bool] = None
        if message.content.startswith(COMMAND_PREFIX) or message.content.startswith(
            "!"
        ):
            filtered = True
        elif self.user and any(
            mention.id == self.user.id for mention in message.mentions
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
            if ref.author == self.user:
                filtered = False

        if filtered is None:
            filter_response = parse_ai_response(
                await self.openai.chat.completions.create(
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
                await self._handle_game_message(db, guild_state, user, message)

    async def _handle_game_message(
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
                await self.anthropic.messages.create(
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

        remove_reactions(self.user, message, ["⏳"])

    def handle_show_command(
        self, guild_id: int, user_id: int, target: str
    ) -> Optional[str]:
        guild_state = self.guild_states.get(guild_id)
        if not guild_state:
            return None

        if target == "world":
            if not guild_state.world_state:
                return "The world is empty."
            return "\n".join(f"- {item}" for item in guild_state.world_state)

        elif target == "inventory":
            with guild_state.db.connect() as db:
                user = db.get_user(user_id)
                if not user:
                    return "Your inventory is empty."
            inventory = guild_state.player_inventories.get(user.id, set())
            if not inventory:
                return "Your inventory is empty."
            return "\n".join(f"- {item}" for item in sorted(inventory))

        return f"Usage: {COMMAND_PREFIX}show <world|inventory>"

    async def handle_sudo_command(
        self,
        guild_id: int,
        author: Union[discord.User, discord.Member],
        message: discord.Message,
    ) -> Optional[str]:
        guild_state = self.guild_states.get(guild_id)
        if not guild_state:
            return None

        with guild_state.db.connect() as db:
            user = db.get_or_create_user(author.id, author.display_name)
            db.add_message(
                message.content,
                user.id,
                message.id,
                message.reference.message_id if message.reference else None,
            )
            async with message.channel.typing():
                await self._handle_game_message(
                    db, guild_state, user, message, sudo=True
                )


@commands.command()
async def show(ctx: commands.Context, target: str):
    if not ctx.guild:
        return
    reply = ctx.bot.handle_show_command(ctx.guild.id, ctx.author.id, target)
    if reply:
        await ctx.reply(reply)


@commands.command()
async def sudo(ctx: commands.Context):
    if not ctx.guild:
        return
    if ctx.author == ctx.guild.owner or any(
        role.id == 1291367449001721888
        for role in (ctx.author.roles if isinstance(ctx.author, discord.Member) else [])
    ):
        await ctx.bot.handle_sudo_command(ctx.guild.id, ctx.author, ctx.message)


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
