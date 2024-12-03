import asyncio
import logging
import random

from .utils import timer
from .game_channel import GameChannel

logger = logging.getLogger("game.bidding_manager")
logger.setLevel(logging.DEBUG)


class BiddingManager:
    def __init__(self, game_channel: GameChannel):
        self._game_channel = game_channel
        self._active_player: int = 0
        self._messages_in_turn: int = 0
        self._bidding_in_progress: bool = False
        self._bids: dict[int, int] = {}
        self._points: dict[int, int] = {}
        self._bidding_timer: asyncio.Task | None = None
        self._turn_timer: asyncio.Task | None = None
        self._bidding_timeout: int = 70
        self._turn_timeout: int = 150
        self._starting_points: int = 10
        self._disabled: bool = False

    @property
    def in_progress(self) -> bool:
        return self._bidding_in_progress

    @property
    def active_player(self) -> int:
        return self._active_player

    def player_points(self, user_upstream_id: int) -> int:
        return self._points.get(user_upstream_id, self._starting_points)

    def add_player(self, user_upstream_id: int):
        if user_upstream_id not in self._points:
            self._points[user_upstream_id] = self._starting_points

    async def increment_turn_progress(self):
        if not self._disabled:
            self._messages_in_turn += 1
            if self._messages_in_turn > 4:
                asyncio.create_task(timer(timeout=1, handler=self.start_bidding))

    def is_message_allowed(self, user_upstream_id: int) -> bool:
        if self._disabled:
            return True
        if self._bidding_in_progress or user_upstream_id != self._active_player:
            return False
        return True

    def reset(self, hard=False):
        if hard:
            self._points.clear()
        self._bids.clear()
        self._bidding_in_progress = False
        self._messages_in_turn = 0
        self._active_player = 0
        if self._bidding_timer:
            self._bidding_timer.cancel()
        self._bidding_timer = None
        if self._turn_timer:
            self._turn_timer.cancel()
        self._turn_timer = None

    async def start_bidding(self) -> str:
        if self._disabled or self._bidding_in_progress:
            return "Bidding is disabled or in progress."

        self.reset()
        self._bidding_in_progress = True
        self.add_passive_points()
        self._bidding_timer=asyncio.create_task(timer(self._bidding_timeout, self._last_call_resolve_bidding))

        await self._game_channel.send(f"Bidding is now open! Use ``/bid`` to place a bid to take control of John.")
        logger.debug("Bidding started")
        return "Starting bidding auction."

    async def add_bid(self, bid_value: int, upstream_user_id: int) -> str:
        if not self._bidding_in_progress:
                return "Bidding is closed."
        if upstream_user_id not in self._points:
            return "You need to register an objective first."
        if bid_value < 0:
            return "Invalid bid. Please enter a non-negative value."
        available_points = self._points[upstream_user_id]
        if available_points < bid_value:
            return f"Insufficient points. You have {available_points} points available."

        first_bid = True
        if upstream_user_id in self._bids:
            first_bid = False
        self._bids[upstream_user_id] = bid_value

        resolve_required = False
        if len(self._bids) == len(self._points):
            if self._bidding_timer:
                self._bidding_timer.cancel()
            resolve_required = True
        elif not self._bidding_timer or self._bidding_timer.done():
            self._bidding_timer=asyncio.create_task(timer(timeout=1, handler=self._last_call_resolve_bidding))

        if first_bid:
            await self._game_channel.send(f"<@{upstream_user_id}> submitted a bid!")
        if resolve_required:
            await self.resolve_bidding()
        return f"Bid {bid_value} accepted."

    async def _last_call_resolve_bidding(self):
       if not self._bids:
           logger.debug("Last call Resolve bidding: no bids")
           return

       if len(self._bids) < len(self._points):
           await self._game_channel.send(f"Last call! Bidding closes in 10 seconds.")
           await asyncio.sleep(10)

       asyncio.create_task(self.resolve_bidding())

    async def resolve_bidding(self) -> str:
       if not self._bidding_in_progress:
            logger.debug("Resolve bidding: bidding is closed")
            return "Bidding is closed."

       if not self._bids:
           logger.debug("Resolve bidding: no bids")
           return "No bids."

       max_bid = max(self._bids.values())
       highest_bidders = [
            user_name for user_name, bid in self._bids.items()
            if bid == max_bid
       ]

       if len(highest_bidders) > 1:
           winner_upstream_id = random.choice(highest_bidders)
       else:
           winner_upstream_id = highest_bidders[0]

       self._points[winner_upstream_id] -= self._bids[winner_upstream_id]

       self.reset()
       self._active_player = winner_upstream_id
       self._turn_timer = asyncio.create_task(timer(self._turn_timeout, self.turn_timeout_handler))

       await self._game_channel.send(f"<@{winner_upstream_id}> takes control of John!")
       logger.debug("Bidding resolved")
       return "Bidding resolved."

    def toggle_bidding(self) -> bool:
        self._disabled = not self._disabled
        if self._disabled:
            self.reset()
        return self._disabled

    async def turn_timeout_handler(self):
        await self._game_channel.send(f"Hurry up <@{self._active_player}>! Your turn will end in 30 seconds.")
        await asyncio.sleep(30)
        asyncio.create_task(self.start_bidding())

    def add_passive_points(self):
        self._points = {player_id: min(points + 1, 10) for player_id, points in self._points.items()}

    def describe_state(self):
        return f"""Disabled: {self._disabled}
Bidding in progress: {self._bidding_in_progress}
Active player: {self._active_player}
Messages in turn: {self._messages_in_turn}
Points: {self._points}
"""
