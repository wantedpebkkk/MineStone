"""MineStone – 24/7 Discord Music Bot entry point."""

import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
import keep_alive as _keep_alive

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Quiet down noisy third-party loggers
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)

log = logging.getLogger("minestone")


def _require_discord_token() -> str:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is missing or placeholder. "
            "Set DISCORD_TOKEN in .env or environment before starting the bot."
        )
    placeholder_tokens = {
        "your_discord_bot_token_here",
        "your_token_here",
        "changeme",
        "replace_me",
    }
    if token.lower() in placeholder_tokens:
        raise RuntimeError(
            "DISCORD_TOKEN is missing or placeholder. "
            "Set DISCORD_TOKEN in .env or environment before starting the bot."
        )
    return token

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

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
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Connected to %d guild(s)", len(bot.guilds))
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
        log.exception("CommandInvokeError in %s", ctx.command, exc_info=error.original)
    else:
        await ctx.send(f"❌ {error}")


async def main():
    async with bot:
        if os.getenv("KEEP_ALIVE", "false").lower() == "true":
            _keep_alive.keep_alive()
        await bot.load_extension("cogs.music")
        await bot.start(_require_discord_token())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as error:
        log.error("%s", error)
        raise SystemExit(1) from error
