import logging
from typing import AsyncContextManager, Callable, Iterable, Optional

from fun_game.config import GameConfig
from .database import Database, DatabaseConnection, SimpleMessage
from .ai import AIProvider
from .models import CustomRule, GameContext, GameResponse
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
            return cls(config, instance_id)

        return _factory

    def __init__(self, config: GameConfig, instance_id: str):
        self._config = config
        self._ai = AIProvider.default()
        self._db = Database(f"data/{instance_id}.sqlite")
        self._world_state: set[str] = set()
        self._custom_rules: dict[int, CustomRule] = {}
        self._player_inventories: dict[int, set[str]] = {}

        with self._db.connect() as db:
            self._world_state = db.load_world_state()
            self._custom_rules = {rule.id: rule for rule in db.load_custom_rules()}

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
            user = db.get_or_create_user(context.user_id, context.user_name)
            message = db.get_message(context.message_id)

            reply_to_message_id: Optional[int] = None
            if context.reply_to_message_id:
                reply_to_message = db.get_message(context.reply_to_message_id)
                if reply_to_message:
                    reply_to_message_id = reply_to_message.id

            if message:
                message_id = message.id
                if message.status == "filtered" and context.force_feed:
                    db.unfilter_message(message_id)
            else:
                message_id = db.add_message(
                    context.message_content,
                    sender_id=user.id,
                    upstream_id=context.message_id,
                    reply_to_id=reply_to_message_id,
                )

            message_context = db.get_message_context(context.reply_to_message_id)

            player_inventory = self._load_player_inventory(user.id, db)

            logger.debug("generating response")
            game_response = await self.process_game_action(
                message=context.message_content,
                world_state=self.world_state,
                player_inventory=player_inventory,
                player_name=user.name,
                message_context=message_context,
                sudo=context.sudo,
            )

            logger.debug("updating persistent game state")
            db.update_game_state(
                user_id=user.id,
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

        self._update_cached_state(game_response, user.id)

        logger.debug("returning game response: %s", game_response.response)
        return GameResponse(
            response_text=game_response.response,
            _engine=self,
            _message_id=reply_id,
        )

    async def is_game_action(self, message: str) -> bool:
        examples = self._config.filter.examples
        filter_response = await self._ai.prompt_mini(
            message,
            make_filter_system_prompt(
                positive_examples=examples.accept, negative_examples=examples.reject
            ),
            FilterModelResponse,
        )
        logger.debug("filter response: %s", filter_response)
        if filter_response.confidence < 0.5:
            return self._config.filter.default_behavior == "accept"
        return filter_response.forward

    async def process_game_action(
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
