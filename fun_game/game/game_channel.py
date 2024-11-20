import logging
from abc import ABC, abstractmethod
from typing import AsyncContextManager
from contextlib import asynccontextmanager


class GameChannel(ABC):
    @classmethod
    def default(cls):
        return LoggingGameChannel()

    @abstractmethod
    async def send(self, message: str) -> None:
        pass

    @abstractmethod
    def typing(self) -> AsyncContextManager:
        pass

class LoggingGameChannel(GameChannel):
    def __init__(self):
        self.logger = logging.getLogger("game.game_channel")

    async def send(self, message: str) -> None:
        self.logger.info(message)

    def typing(self) -> AsyncContextManager:
        @asynccontextmanager
        async def noop():
            yield
        return noop()
