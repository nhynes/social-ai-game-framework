import tomllib as toml
from typing import Literal

from pydantic import BaseModel


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


class Config(BaseModel):
    frontend: Literal["discord"]

    game: GameConfig

    @classmethod
    def load(cls, file_path: str) -> "Config":
        with open(file_path, "rb") as f_config:
            toml_config = toml.load(f_config)
        return Config.model_validate(toml_config)
