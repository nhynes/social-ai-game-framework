from abc import ABC, abstractmethod
import logging
import os
from typing import Type, Union, Iterable, get_args

from anthropic import AsyncAnthropic
import anthropic.types
from openai import AsyncOpenAI
import openai.types.chat
from pydantic import BaseModel

from .tool_provider import ToolProvider

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
    async def prompt[T: BaseModel](self, user: str, system: str, model: Type[T], tool_provider: ToolProvider | None = None) -> T:
        pass


class DefaultAIProvider(AIProvider):
    def __init__(self, anthropic_client: AsyncAnthropic, openai_client: AsyncOpenAI):
        self.anthropic = anthropic_client
        self.openai = openai_client

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

    async def prompt[T: BaseModel](self, user: str, system: str, model: Type[T], tool_provider: ToolProvider | None = None) -> T:
        if not tool_provider:
            response = await self.anthropic.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=8000,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return parse_ai_response(response, model)

        messages: Iterable[anthropic.types.MessageParam] = [{"role": "user", "content": user}]
        response = await self.anthropic.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=8000,
            system=system,
            tools=tool_provider.tools,
            messages=messages,
            tool_choice=tool_provider.tool_choice,
        )

        tool_use = next((block for block in response.content if block.type == "tool_use"), None)
        while tool_use:
            tool_name = tool_use.name
            tool_input = tool_use.input

            if not isinstance(tool_input, dict):
                raise TypeError("Expected tool_input to be a dictionary, but got: {}".format(type(tool_input)))

            if tool_name == "respond":
                for field_name, field_info in model.model_fields.items():
                    if field_name not in tool_input or tool_input[field_name] == "null":
                        if type(None) in get_args(field_info.annotation):
                            tool_input[field_name] = None
                return model.model_validate(tool_input)

            tool_result = tool_provider.process_tool(tool_name, tool_input)

            messages.extend([
                {
                    "role": "assistant",
                    "content": [tool_use],
                }, # discard chain of thought and only keep tool invocation
                {
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": tool_result,
                    }],
                },
            ])

            response = await self.anthropic.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=8000,
                system=system,
                tools=tool_provider.tools,
                messages=messages,
                tool_choice=tool_provider.tool_choice,
            )
            tool_use = next((block for block in response.content if block.type == "tool_use"), None)

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
