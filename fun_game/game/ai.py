import os
from typing import Iterable, Optional
import logging

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from .prompts import (
    FILTER_SYSTEM_PROMPT,
    FilterModelResponse,
    GameModelResponse,
    SimpleMessage,
    make_game_system_prompt,
    parse_ai_response,
)

logger = logging.getLogger("game.ai")
logger.setLevel(logging.DEBUG)


class AIProvider:
    @staticmethod
    def default() -> "AIProvider":
        return AIProvider(
            AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
            AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]),
        )

    def __init__(self, anthropic: AsyncAnthropic, openai: AsyncOpenAI):
        self.anthropic = anthropic
        self.openai = openai

    async def is_game_action(self, message: str) -> bool:
        response = await self.openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=512,
            temperature=0,
            messages=[
                {"role": "system", "content": FILTER_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
        )
        filter_response = parse_ai_response(response, FilterModelResponse)
        logger.debug("filter response: %s", filter_response)
        return filter_response.forward and filter_response.confidence > 0.5

    async def process_game_action(
        self,
        message: str,
        world_state: Iterable[str],
        player_inventory: Iterable[str],
        player_name: str,
        message_context: Iterable[SimpleMessage],
        sudo: Optional[bool] = False,
    ) -> GameModelResponse:
        system_prompt = make_game_system_prompt(
            world_state, player_name, player_inventory, message_context, sudo=sudo
        )

        response = await self.anthropic.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": message}],
        )
        return parse_ai_response(response, GameModelResponse)
