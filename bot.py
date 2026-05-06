"""MineStone – 24/7 Discord Music Bot entry point."""

import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import keep_alive as _keep_alive

load_dotenv()

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.voice_states = True

bot = commands.Bot(
    command_prefix=os.getenv("PREFIX", "!"),
    intents=INTENTS,
    description="MineStone – 24/7 Discord Music Bot 🎵",
)


@bot.event
async def on_ready():
    print(f"✅  Logged in as {bot.user}  (ID: {bot.user.id})")
    print("─" * 40)
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=f"music | {bot.command_prefix}help",
        )
    )


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Bad argument: {error}")
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.send(f"❌ An error occurred: {error.original}")
        raise error
    else:
        await ctx.send(f"❌ {error}")


async def main():
    async with bot:
        _keep_alive.keep_alive()
        await bot.load_extension("cogs.music")
        await bot.start(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    asyncio.run(main())
