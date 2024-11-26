from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
import random
import anthropic.types

if TYPE_CHECKING:
    from .engine import GameEngine

class ToolProvider(ABC):

    @property
    @abstractmethod
    def tools(self) -> list:
        pass

    @property
    def tool_choice(self) -> anthropic.types.ToolChoiceParam:
        return {"type": "auto", "disable_parallel_tool_use": True}

    @abstractmethod
    def process_tool(self, tool_name: str, input_data: dict) -> str:
        pass


class JohnToolProvider(ToolProvider):
    def __init__(self, game_engine: "GameEngine"):
        self._game_engine = game_engine
        self._tools = [
            {
                "name": "respond",
                "description": "Call this function to respond to the player.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "response": {
                            "type": "string",
                            "description": "The narrative response or feedback to provide to the player."
                        },
                        "world_state_updates": {
                            "type": "object",
                            "description": "Changes to the world state, if any. The key is the item's content, and the value is a boolean indicating whether to add (true) or remove (false) the item. The changes must be very detailed because the context in which they were created is not saved. Make sure to remove old items when they are no longer true.",
                            "additionalProperties": {
                                "type": "boolean"
                            },
                        },
                        "player_inventory_updates": {
                            "type": "object",
                            "description": "Changes to the player's inventory, if any. The key is the item's content, and the value is a boolean indicating whether to add (true) or remove (false) the item. The changes must be very detailed because the context in which they were created is not saved. Make sure to remove old items when they are no longer true.",
                            "additionalProperties": {
                                "type": "boolean"
                            },
                        }
                    },
                    "required": ["response"]
                }
            },
            {
                "name": "roll_dice",
                "description": "Call this function whenever players instruct John to attempt an action that requires any amount of skill, strenght, or luck, as per the core mechanics. Returns true or false, indicating whether John succeeds or fails the action.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                }
            },
        ]

    @property
    def tools(self):
        return self._tools

    @property
    def tool_choice(self):
        return {"type": "any", "disable_parallel_tool_use": True}

    def process_tool(self, tool_name: str, input_data: dict):
        match tool_name:
            case "roll_dice":
                return self.roll_dice()
            case "respond":
                # AIProvider handles "respond" directly; this should never be called
                return "ToolError"
            case _:
                return "ToolError"

    def roll_dice(self):
        success = random.choice([True, False])
        print("\nCalled ROLL DICE --> ", success)
        if not success:
            self._game_engine.start_bidding(delay=10)
        return f"success: {success}"
