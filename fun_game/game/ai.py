from abc import ABC, abstractmethod
import logging
import os
from typing import Type, Union

from anthropic import AsyncAnthropic
import anthropic.types
from openai import AsyncOpenAI
import openai.types.chat
from pydantic import BaseModel

logger = logging.getLogger("game.ai")
logger.setLevel(logging.DEBUG)


class AIProvider(ABC):
    @classmethod
    def default(cls):
        return DefaultAIProvider(
            AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
            AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]),
        )

    @abstractmethod
    async def prompt_mini[
        T: BaseModel
    ](self, user: str, system: str, model: Type[T], temperature: int | None = 0) -> T:
        pass

    @abstractmethod
    async def prompt[T: BaseModel](self, user: str, system: str, model: Type[T]) -> T:
        pass


class DefaultAIProvider(AIProvider):
    def __init__(self, anthropic_client: AsyncAnthropic, openai_client: AsyncOpenAI):
        self.anthropic = anthropic_client
        self.openai = openai_client

    async def prompt_dalle[
    T: BaseModel
    ](
            self, prompt: str
    ) -> str:
        """Generates an image with Dall-E 3 and returns the URL."""
        response = await self.openai.images.generate(
            model="dall-e-3",
            prompt="""
            Digital objective illustration of the top down view of the current state in this prompt:
            """ + \
                   prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url

    async def prompt_mini[
        T: BaseModel
    ](self, user: str, system: str, model: Type[T], temperature: int | None = 0) -> T:
        response = await self.openai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return parse_ai_response(response, model)

    async def prompt[T: BaseModel](self, user: str, system: str, model: Type[T]) -> T:
        response = await self.anthropic.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return parse_ai_response(response, model)


def parse_ai_response[
    T: BaseModel
](
    response: Union[anthropic.types.Message, openai.types.chat.ChatCompletion],
    struct: Type[T],
) -> T:
    if isinstance(response, openai.types.chat.ChatCompletion):
        response_message = response.choices[0].message.content or ""
    else:
        response_content = response.content[0]
        assert isinstance(response_content, anthropic.types.TextBlock)
        response_message = response_content.text

    return struct.model_validate_json(response_message)
