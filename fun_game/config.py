import tomllib as toml
from typing import Literal
from typing_extensions import Self

from pydantic import BaseModel, model_validator


class FilterExamples(BaseModel):
    accept: list[str]
    reject: list[str]


class FilterConfig(BaseModel):
    default_behavior: Literal["accept", "reject"]
    examples: FilterExamples


class InteractionRulesConfig(BaseModel):
    do: list[str]
    dont: list[str]


class EngineConfig(BaseModel):
    world_properties: list[str]
    core_mechanics: list[str]
    interaction_rules: InteractionRulesConfig
    response_guidelines: list[str]


class GameConfig(BaseModel):
    filter: FilterConfig
    engine: EngineConfig


class DiscordFrontendConfig(BaseModel):
    channel_name: str


class FrontendConfig(BaseModel):
    discord: DiscordFrontendConfig | None = None

    @model_validator(mode="after")
    def check_only_one(self) -> Self:
        if len(self.model_dump(exclude_unset=True)) != 1:
            raise ValueError("Frontend config must be set. Available options: discord")
        return self


class Config(BaseModel):
    frontend: FrontendConfig

    game: GameConfig

    @classmethod
    def load(cls, file_path: str) -> "Config":
        with open(file_path, "rb") as f_config:
            toml_config = toml.load(f_config)
        return Config.model_validate(toml_config)
