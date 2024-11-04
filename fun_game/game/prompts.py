from textwrap import dedent
from typing import Iterable, Optional

from pydantic import BaseModel

from fun_game.config import EngineConfig

from .models import SimpleMessage

# pylint: disable=line-too-long
_FILTER_SYSTEM_PROMPT = """The user message is from a general discussion channel.

The channel contains messages meant for either:

a) a simulation game that responds to natural language, or
b) other users in the channel who may be talking with each other about the game or any other topic

Your task is to determine whether to forward the message to the (somewhat expensive) simulator or not forward the message and do nothing. Message in category (a) must be forwarded while messages in category (b) must not be forwarded.

Respond with ONLY valid JSON in the following format WITHOUT code fence or anything else:

```
type Response = {{
    // Whether the message is in category (a) and should be forwarded
    forward: boolean;

    // A float from 0-1 describing how confident you are in your decision. 1 is perfectly certain, 0 is perfectly uncertain.
    confidence: number;
}}
```

EXAMPLES:

Forward things like these:
{positive_examples}

Do not forward things like these:
{negative_examples}
"""


def make_filter_system_prompt(
    positive_examples: list[str], negative_examples: list[str]
) -> str:
    return _FILTER_SYSTEM_PROMPT.format(
        positive_examples=_format_list(positive_examples),
        negative_examples=_format_list(negative_examples),
    )


class FilterModelResponse(BaseModel):
    forward: bool
    confidence: float


# pylint: disable=line-too-long
_GAME_SYSTEM_PROMPT = """You are a multiplayer simulation game engine that processes commands to advance game state in a manner consistent with the world properties, core mechanics, and interaction rules.

WORLD PROPERTIES:
{world_properties}

CORE MECHANICS:
{core_mechanics}

INTERACTION RULES:
1. DO:
{interaction_dos}

2. DO NOT:
{interaction_donts}

PLAYER RESPONSES:
{response_guidelines}

ADDITIONAL RULES:
{custom_rules}

RESPONSE FORMAT:
Respond in JSON according to the following schema WITHOUT a code fence or anything else.
```
// A patch set.
// The key is the contents of an item to add or remove.
// The value is whether to add or remove the item.
// The changes must be very detailed because the context in which they were created is not saved.
type Changes = Record<string, boolean>;

type ModelResponse = {{
    // The response to the player.
    response: string;

    // Changes to apply to the world state, if any.
    // The changes must be very detailed because the context in which they were created is not saved.
    world_state_updates: Changes | null;

    // Changes to apply to the player's inventory, if any.
    // The changes must be very detailed because the context in which they were created is not saved.
    player_inventory_updates: Changes | null;
}};
```
"""


def make_game_system_prompt(
    config: EngineConfig,
    world_state: Iterable[str],
    player_name: str,
    player_inventory: Iterable[str],
    context: Iterable[SimpleMessage],
    custom_rules: Optional[Iterable[str]] = None,
    sudo: bool = False,
) -> str:
    components = [
        _GAME_SYSTEM_PROMPT.format(
            world_properties=_format_list(config.world_properties),
            core_mechanics=_format_list(config.core_mechanics),
            interaction_dos=_format_list(config.interaction_rules.do),
            interaction_donts=_format_list(
                f"DO NOT {s[0].lower()}{s[1:]}" for s in config.interaction_rules.dont
            ),
            additional_rules=(_format_list(custom_rules) if custom_rules else None)
            or "None yet.",
            response_guidelines=_format_list(config.response_guidelines),
        )
    ]

    components.append(
        dedent(
            f"""
            Here is a selection messages sent by yourself and players, which you may find helpful:

            {"\n\n".join(f"{"You" if message.sender_id == 0 else "Player " + message.sender}: {message.content}" for message in context)}
            """
        )
        if context
        else ""
    )

    components.append(
        dedent(
            f"""
            The world has the following state:
            {_format_list(world_state)}
            """
        )
        if world_state
        else "The world is empty."
    )

    if not sudo:
        components.append(
            dedent(
                f"""
                The player's inventory contains the following and nothing else:
                {_format_list(player_inventory)}
                """
            )
            if player_inventory
            else "The player's inventory is empty."
        )

    if sudo:
        components.append(
            dedent(
                """
                You are currently processing messages from the game designer.
                The game designer is allowed to request arbitary changes to the world.
                Accommodate the requests in the most seamless way possible given the existing world state.
                """
            )
        )
    else:
        components.append(
            f"You are currently processing messages from the player named {player_name}."
        )

    return "\n\n---\n\n".join(components)


def _format_list(items: Iterable[str], prefix: Optional[str] = "- ") -> str:
    return "\n".join(f"{prefix}{item}" for item in items)


# A patch set.
# The key is the contents of an item to add or remove.
# The corresponding value is whether to add or remove the item.
Changes = dict[str, bool]


class GameModelResponse(BaseModel):
    # The response to the player
    response: str
    # Changes to apply to the world state, if any
    world_state_updates: Optional[Changes]
    # Changes to apply to the player's inventory, if any
    player_inventory_updates: Optional[Changes]
