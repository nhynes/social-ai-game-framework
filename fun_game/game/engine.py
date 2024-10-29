import logging
from dataclasses import dataclass
from enum import Enum
from typing import AsyncContextManager, Callable, Dict, Iterable, Optional, Set

from .ai import AIProvider
from .database import Database

logger = logging.getLogger("game.engine")
logger.setLevel(logging.DEBUG)


class Frontend(Enum):
    none = 0
    discord = 1


@dataclass
class GameContext:
    format: Frontend
    user_id: int
    user_name: str
    message_content: str
    message_id: int
    reply_to_message_id: Optional[int]
    sudo: bool = False
    force_feed: bool = False


@dataclass
class GameResponse:
    response_text: str

    _message_id: int
    _engine: "GameEngine"

    def mark_responded(self, upstream_reply_id: int):
        self._engine._mark_message_processed(self._message_id, upstream_reply_id)


class GameEngine:
    def __init__(self, frontend: Frontend, frontend_instance_id: int):
        assert frontend == Frontend.discord
        self._ai = AIProvider.default()
        self._db = Database(
            f"data/{"guild" if frontend == Frontend.discord else frontend.value}_{frontend_instance_id}.db"
        )
        self._world_state: Set[str] = set()
        self._player_inventories: Dict[int, Set[str]] = {}

        with self._db.connect() as db:
            self._world_state = db.load_world_state()

    @property
    def world_state(self) -> Iterable[str]:
        return list(self._world_state)

    async def process_message(
        self,
        context: GameContext,
        contextmanager: Optional[Callable[[], AsyncContextManager]] = None,
    ) -> Optional[GameResponse]:
        # Check if message is for the game
        if not context.force_feed:
            if not await self._ai.is_game_action(context.message_content):
                logger.debug("message has been filtered")
                return None

        if contextmanager:
            async with contextmanager():
                return await self._do_process_message(context)
        else:
            return await self._do_process_message(context)

    async def _do_process_message(self, context: GameContext) -> Optional[GameResponse]:
        with self._db.connect() as db:
            if context.format != Frontend.none:
                user = db.get_or_create_user(context.user_id, context.user_name)
                user_id = user.id
                user_name = user.name
                message = db.get_message(context.message_id)

                reply_to_message = None
                if context.reply_to_message_id:
                    reply_to_message = db.get_message(context.reply_to_message_id)

                if message:
                    message_id = message.id
                    if message.status == "filtered" and context.force_feed:
                        db.unfilter_message(message_id)
                else:
                    message_id = db.add_message(
                        context.message_content,
                        sender_id=user_id,
                        upstream_id=context.message_id,
                        reply_to_id=reply_to_message.id if reply_to_message else None,
                    )
            else:
                user_id = context.user_id
                user_name = context.user_name
                message_id = context.message_id
                reply_to_message = context.reply_to_message_id

            message_context = db.get_message_context(context.reply_to_message_id)

            player_inventory = self._load_player_inventory(user_id)

            logger.debug("generating response")
            game_response = await self._ai.process_game_action(
                message=context.message_content,
                world_state=self.world_state,
                player_inventory=player_inventory,
                player_name=user_name,
                message_context=message_context,
                sudo=context.sudo,
            )

            logger.debug("updating persistent game state")
            db.update_game_state(
                user_id=context.user_id,
                world_changes=game_response.world_state_updates,
                inventory_changes=game_response.player_inventory_updates,
                trigger_message_id=context.message_id,
            )
            reply_id = db.add_message(
                game_response.response,
                sender_id=0,
                upstream_id=None,
                reply_to_id=message_id,
            )

        self._update_cached_state(game_response, context.user_id)

        logger.debug("returning game response: %s", game_response.response)
        return GameResponse(
            response_text=game_response.response,
            _engine=self,
            _message_id=reply_id,
        )

    def add_reaction(
        self,
        frontend: Frontend,
        message_id: int,
        user_id: int,
        user_name: str,
        reaction: str,
    ):
        with self._db.connect() as db:
            if frontend != Frontend.none:
                message = db.get_message(message_id)
                user = db.get_or_create_user(user_id, user_name)
                if not message or not user:
                    return None
                message_id = message.id
                user_id = user.id
            logger.info(f"{user_name} added reaction {reaction} to message")
            db.add_reaction(message_id, user_id, reaction)

    def remove_reaction(
        self,
        frontend: Frontend,
        message_id: int,
        user_id: int,
        user_name: str,
        reaction: str,
    ):
        with self._db.connect() as db:
            if frontend != Frontend.none:
                message = db.get_message(message_id)
                user = db.get_or_create_user(user_id, user_name)
                if not message or not user:
                    return None
                message_id = message.id
                user_id = user.id
            logger.info(f"{user_name} removed reaction {reaction} from message")
            db.remove_reaction(message_id, user_id, reaction)

    def player_inventory(self, frontend: Frontend, user_id: int) -> Iterable[str]:
        if frontend != Frontend.none:
            with self._db.connect() as db:
                user = db.get_user(user_id)
            if not user:
                return []
            user_id = user.id
        return self._load_player_inventory(user_id)

    def _load_player_inventory(self, user_id: int) -> Iterable[str]:
        player_inventory = self._player_inventories.get(user_id)
        if player_inventory is None:
            with self._db.connect() as db:
                self._player_inventories[user_id] = db.load_player_inventory(user_id)
        return self._player_inventories[user_id]

    def _update_cached_state(self, game_response, user_id):
        # Update world state
        if game_response.world_state_updates:
            for item, should_add in game_response.world_state_updates.items():
                if should_add:
                    self._world_state.add(item)
                else:
                    self._world_state.discard(item)

        # Update player inventory
        if game_response.player_inventory_updates:
            for item, should_add in game_response.player_inventory_updates.items():
                if should_add:
                    self._player_inventories[user_id].add(item)
                else:
                    self._player_inventories[user_id].discard(item)

    def _mark_message_processed(self, message_id: int, upstream_message_id: int):
        with self._db.connect() as db:
            db.mark_message_sent(id=message_id, upstream_id=upstream_message_id)
        logger.debug("marked message as processed")
