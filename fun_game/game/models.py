from enum import Enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .engine import GameEngine


@dataclass
class SimpleMessage:
    id: int
    sender: str
    sender_id: int
    content: str


class MessageStatus(Enum):
    FILTERED = "filtered"
    UNFILTERED = "unfiltered"
    IRRELEVANT = "irrelevant"
    SUDO = "sudo"


@dataclass
class Message:
    id: int
    upstream_id: int | None
    sender_id: int
    content: str
    reply_to: int
    created_at: str
    status: MessageStatus


@dataclass
class User:
    id: int
    upstream_id: int
    name: str


@dataclass
class MessageData:
    user: User
    message: Message | None
    message_id: int
    message_context: Iterable[SimpleMessage]
    player_inventory: Iterable[str]


@dataclass
class GameContext:
    user_id: int
    user_name: str
    message_content: str
    message_id: int
    reply_to_message_id: int | None
    sudo: bool = False
    force_feed: bool = False


@dataclass
class GameResponse:
    response_text: str

    _message_id: int
    _engine: "GameEngine"

    def mark_responded(self, upstream_reply_id: int):
        self._engine.mark_message_processed(self._message_id, upstream_reply_id)


@dataclass
class CustomRule:
    id: int
    rule: str
    secret: bool
