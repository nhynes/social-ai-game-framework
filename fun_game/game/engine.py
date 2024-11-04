import logging
from typing import AsyncContextManager, Callable, Iterable, Optional

from fun_game.config import GameConfig
from .database import Database, DatabaseConnection
from .ai import AIProvider
from .models import (
    CustomRule,
    GameContext,
    GameResponse,
    Message,
    MessageData,
    SimpleMessage,
)
from .prompts import (
    FilterModelResponse,
    GameModelResponse,
    make_filter_system_prompt,
    make_game_system_prompt,
)

logger = logging.getLogger("game.engine")
logger.setLevel(logging.DEBUG)


class GameEngine:
    @classmethod
    def make_factory(cls, config: GameConfig) -> Callable[[str], "GameEngine"]:
        def _factory(instance_id: str) -> "GameEngine":
            db = Database(f"data/{instance_id}.sqlite")
            ai = AIProvider.default()
            return cls(config, instance_id, ai=ai, db=db)

        return _factory

    def __init__(
        self,
        config: GameConfig,
        instance_id: str,
        *,
        ai: Optional[AIProvider] = None,
        db: Optional[Database] = None,
    ):
        self._config = config
        self._ai = ai if ai else AIProvider.default()
        self._db = db if db else Database(f"data/{instance_id}.sqlite")
        self._world_state: set[str] = set()
        self._custom_rules: dict[int, CustomRule] = {}
        self._player_inventories: dict[int, set[str]] = {}

        with self._db.connect() as dbc:
            self._world_state = dbc.load_world_state()
            self._custom_rules = {rule.id: rule for rule in dbc.load_custom_rules()}

    @property
    def world_state(self) -> Iterable[str]:
        return list(self._world_state)

    @property
    def custom_rules(self) -> Iterable[tuple[int, CustomRule]]:
        return list(self._custom_rules.items())

    async def process_message(
        self,
        context: GameContext,
        contextmanager: Optional[Callable[[], AsyncContextManager]] = None,
    ) -> Optional[GameResponse]:
        # Check if message is for the game
        if not context.force_feed:
            if not await self.is_game_action(context.message_content):
                logger.debug("message has been filtered")
                return None

        if contextmanager:
            async with contextmanager():
                return await self._do_process_message(context)
        else:
            return await self._do_process_message(context)

    async def _do_process_message(self, context: GameContext) -> Optional[GameResponse]:
        with self._db.connect() as db:
            message_data = self._prepare_message_data(db, context)
            game_response = await self._generate_game_response(context, message_data)
            reply_id = self._persist_response(db, context, message_data, game_response)

        self._update_cached_state(game_response, message_data.user.id)
        return GameResponse(
            response_text=game_response.response, _engine=self, _message_id=reply_id
        )

    def _prepare_message_data(
        self, db: DatabaseConnection, context: GameContext
    ) -> MessageData:
        user = db.get_or_create_user(context.user_id, context.user_name)
        message = db.get_message(context.message_id)
        reply_to_message = (
            db.get_message(context.reply_to_message_id)
            if context.reply_to_message_id
            else None
        )

        message_id = self._ensure_message_exists(db, context, user.id, reply_to_message)
        message_context = db.get_message_context(message_id)
        player_inventory = self._load_player_inventory(user.id, db)

        return MessageData(user, message, message_id, message_context, player_inventory)

    async def _generate_game_response(
        self, context: GameContext, message_data: MessageData
    ) -> GameModelResponse:
        return await self._process_game_action(
            message=context.message_content,
            world_state=self.world_state,
            player_inventory=message_data.player_inventory,
            player_name=message_data.user.name,
            message_context=message_data.message_context,
            sudo=context.sudo,
        )

    def _persist_response(
        self,
        db: DatabaseConnection,
        context: GameContext,
        message_data: MessageData,
        game_response: GameModelResponse,
    ) -> int:
        db.update_game_state(
            user_id=message_data.user.id,
            world_changes=game_response.world_state_updates,
            inventory_changes=game_response.player_inventory_updates,
            trigger_message_id=context.message_id,
        )
        return db.add_message(
            game_response.response,
            sender_id=0,
            upstream_id=None,
            reply_to_id=message_data.message_id,
        )

    def _ensure_message_exists(
        self,
        db: DatabaseConnection,
        context: GameContext,
        user_id: int,
        reply_to_message: Optional[Message],
    ) -> int:
        message = db.get_message(context.message_id)
        if message:
            if message.status == "filtered" and context.force_feed:
                db.unfilter_message(message.id)
            return message.id

        reply_to_id = reply_to_message.id if reply_to_message else None
        return db.add_message(
            context.message_content,
            sender_id=user_id,
            upstream_id=context.message_id,
            reply_to_id=reply_to_id,
        )

    async def is_game_action(self, message: str) -> bool:
        filter_response = await self._filter_message(message)
        logger.debug("filter response: %s", filter_response)
        if filter_response.confidence < 0.5:
            return self._config.filter.default_behavior == "accept"
        return filter_response.forward

    async def _filter_message(self, message: str) -> FilterModelResponse:
        examples = self._config.filter.examples
        return await self._ai.prompt_mini(
            message,
            make_filter_system_prompt(
                positive_examples=examples.accept, negative_examples=examples.reject
            ),
            FilterModelResponse,
        )

    async def _process_game_action(
        self,
        message: str,
        world_state: Iterable[str],
        player_inventory: Iterable[str],
        player_name: str,
        message_context: Iterable[SimpleMessage],
        sudo: bool = False,
    ) -> GameModelResponse:
        system_prompt = make_game_system_prompt(
            config=self._config.engine,
            world_state=world_state,
            player_name=player_name,
            player_inventory=player_inventory,
            context=message_context,
            custom_rules=(rule.rule for rule in self._custom_rules.values()),
            sudo=sudo,
        )
        return await self._ai.prompt(message, system_prompt, GameModelResponse)

    def add_custom_rule(
        self, rule: str, creator_id: int, secret: bool
    ) -> Optional[int]:
        with self._db.connect() as db:
            user = db.get_user(creator_id)
            if not user:
                return None
            custom_rule = db.add_custom_rule(rule, user.id, secret)
        self._custom_rules[custom_rule.id] = custom_rule
        return custom_rule.id

    def remove_custom_rule(self, rule_id: int):
        with self._db.connect() as db:
            db.remove_custom_rule(rule_id)
        del self._custom_rules[rule_id]

    def record_response_reaction(
        self,
        upstream_message_id: int,
        upstream_user_id: int,
        user_name: str,
        reaction: str,
    ):
        with self._db.connect() as db:
            message = db.get_message(upstream_message_id)
            user = db.get_or_create_user(upstream_user_id, user_name)
            if not message or not user:
                return
            logger.info("%s added reaction %s to message", user_name, reaction)
            db.add_reaction(message.id, user.id, reaction)

    def unrecord_response_reaction(
        self,
        upstream_message_id: int,
        upstream_user_id: int,
        user_name: str,
        reaction: str,
    ):
        with self._db.connect() as db:
            message = db.get_message(upstream_message_id)
            user = db.get_or_create_user(upstream_user_id, user_name)
            if not message or not user:
                return
            logger.info("%s removed reaction %s from message", user_name, reaction)
            db.remove_reaction(message.id, user.id, reaction)

    def player_inventory(self, user_id: int) -> Iterable[str]:
        with self._db.connect() as db:
            user = db.get_user(user_id)
            if not user:
                return []
            return self._load_player_inventory(user.id, db)

    def _load_player_inventory(
        self, user_id: int, db: DatabaseConnection
    ) -> Iterable[str]:
        player_inventory = self._player_inventories.get(user_id)
        if player_inventory is None:
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

    def mark_message_processed(self, message_id: int, upstream_message_id: int):
        with self._db.connect() as db:
            db.mark_message_sent(message_id=message_id, upstream_id=upstream_message_id)
        logger.debug("marked message as processed")
