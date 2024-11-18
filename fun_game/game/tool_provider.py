from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
import random

if TYPE_CHECKING:
    from .engine import GameEngine

class ToolProvider(ABC):

    @property
    @abstractmethod
    def tools(self) -> list:
        pass

    @abstractmethod
    def process_tool(self, tool_name: str, input_data: object):
        pass


class JohnToolProvider(ToolProvider):
    def __init__(self, game_engine: "GameEngine"):
        self._game_engine = game_engine
        self._tools = [
            {
                "name": "roll_dice",
                "description": "Call this whenever John is attempting an action requiring any amount of skill, strenght, or luck, as per the core mechanics. Returns true or false, indicating whether John succeeds or fails the action. After calling this tool, make sure to respond in a valid json response format - ModelResponse",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                }
            },
        ]

    @property
    def tools(self):
        return self._tools

    def process_tool(self, tool_name: str, input_data: object):
        match tool_name:
            case "roll_dice":
                return self.roll_dice()
            case _:
                return None

    def roll_dice(self):
        success = random.choice([True, False])
        print("\nCalled ROLL DICE --> ", success)
        if not success:
            self._game_engine.start_bidding(delay=10)
        return {"success": success}
