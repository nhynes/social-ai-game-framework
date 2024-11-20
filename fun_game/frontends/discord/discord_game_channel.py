from fun_game.game.game_channel import GameChannel
import discord

class DiscordGameChannel(GameChannel):
    def __init__(self, channel):
        self.channel: discord.TextChannel = channel

    async def send(self, message: str):
        await self.channel.send(message)

    def typing(self):
        return self.channel.typing()
