import pytest
from unittest.mock import AsyncMock, Mock, MagicMock

from fun_game.config import (
    GameConfig,
    FilterConfig,
    EngineConfig,
    FilterExamples,
    InteractionRulesConfig,
)
from fun_game.game.engine import GameEngine
from fun_game.game.models import GameContext, User
from fun_game.game.prompts import GameModelResponse


@pytest.fixture
def mock_config():
    return GameConfig(
        filter=FilterConfig(
            default_behavior="accept",
            examples=FilterExamples(
                accept=["take sword", "go north"], reject=["hello", "what's up"]
            ),
        ),
        engine=EngineConfig(
            world_properties=["dark room"],
            core_mechanics=["movement", "inventory"],
            interaction_rules=InteractionRulesConfig(
                do=["be specific"], dont=["be rude"]
            ),
            response_guidelines=["be concise"],
        ),
    )


@pytest.fixture
def mock_db_connection():
    connection = MagicMock()
    connection.load_world_state.return_value = set(["room", "sword"])
    connection.load_custom_rules.return_value = []
    connection.get_or_create_user.return_value = User(
        id=1, upstream_id=1, name="test_user"
    )
    connection.get_message.return_value = None
    connection.add_message.return_value = 1
    connection.get_message_context.return_value = []
    connection.load_player_inventory.return_value = set()
    return connection


@pytest.fixture
def mock_db(mock_db_connection):
    db = MagicMock()
    db.connect.return_value.__enter__.return_value = mock_db_connection
    return db


@pytest.fixture
def mock_ai():
    ai = Mock()
    ai.prompt = AsyncMock()
    ai.prompt_mini = AsyncMock()
    return ai


@pytest.fixture
def game_engine(mock_config, mock_db, mock_ai):
    return GameEngine(mock_config, "test_instance", ai=mock_ai, db=mock_db)


@pytest.mark.asyncio
async def test_is_game_action_accepts_valid_action(game_engine):
    game_engine._ai.prompt_mini.return_value = Mock(confidence=0.8, forward=True)

    result = await game_engine.is_game_action("take sword")

    assert result is True
    game_engine._ai.prompt_mini.assert_called_once()


@pytest.mark.asyncio
async def test_is_game_action_rejects_invalid_action(game_engine):
    game_engine._ai.prompt_mini.return_value = Mock(confidence=0.8, forward=False)

    result = await game_engine.is_game_action("hello everyone")

    assert result is False
    game_engine._ai.prompt_mini.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_filtered_message(game_engine):
    game_engine.is_game_action = AsyncMock(return_value=False)
    context = GameContext(
        user_id=1,
        user_name="test_user",
        message_content="hello",
        message_id=1,
        reply_to_message_id=None,
    )

    result = await game_engine.process_message(context)

    assert result is None
    game_engine.is_game_action.assert_called_once_with("hello")


@pytest.mark.asyncio
async def test_process_message_valid_game_action(game_engine):
    # Setup mocks
    game_engine.is_game_action = AsyncMock(return_value=True)
    game_engine._ai.prompt.return_value = GameModelResponse(
        response="You took the sword",
        world_state_updates={"sword": False},
        player_inventory_updates={"sword": True},
    )

    # Create test context
    context = GameContext(
        user_id=1,
        user_name="test_user",
        message_content="take sword",
        message_id=1,
        reply_to_message_id=None,
    )

    # Execute
    result = await game_engine.process_message(context)

    # Assert
    assert result is not None
    assert result.response_text == "You took the sword"
    assert "sword" not in game_engine._world_state
    assert "sword" in game_engine._player_inventories[1]


@pytest.mark.asyncio
async def test_process_message_with_force_feed(game_engine):
    # Setup mocks
    game_engine._ai.prompt.return_value = GameModelResponse(
        response="Forced action processed",
        world_state_updates={},
        player_inventory_updates={},
    )

    # Create test context with force_feed=True
    context = GameContext(
        user_id=1,
        user_name="test_user",
        message_content="forced action",
        message_id=1,
        reply_to_message_id=None,
        force_feed=True,
    )

    # Execute
    result = await game_engine.process_message(context)

    # Assert
    assert result is not None
    assert result.response_text == "Forced action processed"
    # Verify is_game_action wasn't called due to force_feed
    assert not hasattr(game_engine, "is_game_action.called")


def test_update_cached_state(game_engine):
    # Test world state updates
    game_response = GameModelResponse(
        response="Test response",
        world_state_updates={"new_item": True, "removed_item": False},
        player_inventory_updates={"sword": True, "shield": False},
    )

    game_engine._world_state.add("removed_item")
    game_engine._player_inventories[1] = {"shield"}

    game_engine._update_cached_state(game_response, 1)

    assert "new_item" in game_engine._world_state
    assert "removed_item" not in game_engine._world_state
    assert "sword" in game_engine._player_inventories[1]
    assert "shield" not in game_engine._player_inventories[1]
