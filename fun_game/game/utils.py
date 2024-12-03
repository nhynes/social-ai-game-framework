import asyncio
import inspect
from typing import Callable, Coroutine, Any


async def timer(timeout: float,
                handler: Callable[[], None] | Callable[[], Coroutine[None, None, Any]]):
    await asyncio.sleep(timeout)
    if inspect.iscoroutinefunction(handler):
        await handler()
    else:
        handler()
