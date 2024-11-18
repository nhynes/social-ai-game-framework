import asyncio
import inspect
from typing import Callable, Coroutine

async def timer(timeout: float,
                handler: Callable[[], None] | Callable[[], Coroutine[None, None, None]]):
    try:
        await asyncio.sleep(timeout)
        if inspect.iscoroutinefunction(handler):
            await handler()
        else:
            handler()
    except asyncio.CancelledError:
        print("Timer was cancelled.")
        raise
