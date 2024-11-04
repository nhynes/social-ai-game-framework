from fun_game.config import EngineConfig, InteractionRulesConfig
from fun_game.game.models import SimpleMessage
from fun_game.game.prompts import (
    FilterModelResponse,
    GameModelResponse,
    make_filter_system_prompt,
    make_game_system_prompt,
    _format_list,
)


def test_make_filter_system_prompt():
    positive = ["build a house", "pick up wood"]
    negative = ["hello everyone", "what's up"]

    result = make_filter_system_prompt(positive, negative)

    assert isinstance(result, str)
    assert "build a house" in result
    assert "hello everyone" in result


def test_make_game_system_prompt():
    config = EngineConfig(
        world_properties=["gravity exists"],
        core_mechanics=["players can move"],
        interaction_rules=InteractionRulesConfig(do=["be nice"], dont=["be mean"]),
        response_guidelines=["be clear"],
    )
    world_state = ["tree exists"]
    player_name = "TestPlayer"
    player_inventory = ["axe"]
    context = [SimpleMessage(id=0, sender_id=1, sender="Player1", content="hello")]

    # Test normal mode
    result = make_game_system_prompt(
        config=config,
        world_state=world_state,
        player_name=player_name,
        player_inventory=player_inventory,
        context=context,
    )

    assert isinstance(result, str)
    assert "gravity exists" in result
    assert "TestPlayer" in result

    # Test sudo mode
    sudo_result = make_game_system_prompt(
        config=config,
        world_state=world_state,
        player_name=player_name,
        player_inventory=player_inventory,
        context=context,
        sudo=True,
    )

    assert isinstance(sudo_result, str)
    assert "game designer" in sudo_result


def test_format_list():
    items = ["item1", "item2"]
    result = _format_list(items)

    assert isinstance(result, str)
    assert len(result.split("\n")) == len(items)

    # Test with custom prefix
    custom_result = _format_list(items, prefix="* ")
    assert custom_result.startswith("* ")


def test_model_responses():
    # Test FilterModelResponse
    filter_response = FilterModelResponse(forward=True, confidence=0.9)
    assert filter_response.forward is True
    assert filter_response.confidence == 0.9

    # Test GameModelResponse
    game_response = GameModelResponse(
        response="OK",
        world_state_updates={"tree": True},
        player_inventory_updates={"axe": False},
    )
    assert game_response.response == "OK"
    assert game_response.world_state_updates == {"tree": True}
    assert game_response.player_inventory_updates == {"axe": False}
