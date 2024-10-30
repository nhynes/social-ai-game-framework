from enum import Enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .engine import GameEngine


@dataclass
class SimpleMessage:
    id: int
    sender: str
    sender_id: int
    content: str


class Frontend(Enum):
    NONE = 0
    DISCORD = 1


class MessageStatus(Enum):
    FILTERED = "filtered"
    UNFILTERED = "unfiltered"
    IRRELEVANT = "irrelevant"
    SUDO = "sudo"


@dataclass
class Message:
    id: int
    frontend: Frontend
    upstream_id: Optional[int]
    sender_id: int
    content: str
    reply_to: int
    created_at: str
    status: MessageStatus


@dataclass
class User:
    frontend: Frontend
    id: int
    upstream_id: int
    name: str


@dataclass
class GameContext:
    frontend: Frontend
    user_id: int
    user_name: str
    message_content: str
    message_id: int
    reply_to_message_id: Optional[int]
    sudo: bool = False
    force_feed: bool = False


@dataclass
class GameResponse:
    response_text: str

    _message_id: int
    _engine: GameEngine  # pylint: disable=used-before-assignment

    def mark_responded(self, upstream_reply_id: int):
        self._engine.mark_message_processed(self._message_id, upstream_reply_id)
