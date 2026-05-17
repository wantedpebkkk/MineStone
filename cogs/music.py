"""Music cog – Spotify search, YouTube streaming, HD audio, 24/7 mode."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from typing import List, Optional
from urllib.parse import urlparse

import discord
import yt_dlp
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    _SPOTIPY_AVAILABLE = True
except ImportError:
    _SPOTIPY_AVAILABLE = False

# ---------------------------------------------------------------------------
# Audio configuration – HD quality
# ---------------------------------------------------------------------------

#: yt-dlp options: pick the best audio format available.
YDL_OPTIONS: dict = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "noplaylist": True,
    "source_address": "0.0.0.0",
}

#: FFmpeg reconnection flags ensure streams recover from network blips.
FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
)

#: No-video flag + 48 kHz stereo for the best Discord-compatible quality.
FFMPEG_OPTIONS = "-vn -samplerate 48000 -ac 2"

# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------

#: How often (seconds) the reconnect loop checks 24/7 channels.
RECONNECT_INTERVAL_SECONDS = 30

#: Seconds of silence before the bot auto-disconnects when the queue empties.
IDLE_DISCONNECT_SECONDS = 180

#: Seconds to wait after being left alone before disconnecting.
ALONE_DISCONNECT_SECONDS = 60

# ---------------------------------------------------------------------------
# Spotify / search limits
# ---------------------------------------------------------------------------

#: Maximum tracks pulled from a Spotify playlist or album.
MAX_PLAYLIST_ITEMS = 50

#: Number of Spotify search results shown by !search.
SEARCH_RESULT_LIMIT = 5

# ---------------------------------------------------------------------------
# URL detection helpers (use proper hostname checks, not substring matching)
# ---------------------------------------------------------------------------

_SPOTIFY_HOSTS = {"open.spotify.com"}
_YOUTUBE_HOSTS = {"www.youtube.com", "youtube.com", "youtu.be", "m.youtube.com"}


def _is_spotify_url(text: str) -> bool:
    """Return True only when *text* is a URL whose host is open.spotify.com."""
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and parsed.netloc in _SPOTIFY_HOSTS
    except Exception:
        return False


def _is_youtube_url(text: str) -> bool:
    """Return True only when *text* is a URL whose host is youtube.com / youtu.be."""
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and parsed.netloc in _YOUTUBE_HOSTS
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Spotify URL patterns
# ---------------------------------------------------------------------------

_SP_TRACK = re.compile(
    r"https?://open\.spotify\.com/(?:[a-z]{2}/)?track/([A-Za-z0-9]+)"
)
_SP_PLAYLIST = re.compile(
    r"https?://open\.spotify\.com/(?:[a-z]{2}/)?playlist/([A-Za-z0-9]+)"
)
_SP_ALBUM = re.compile(
    r"https?://open\.spotify\.com/(?:[a-z]{2}/)?album/([A-Za-z0-9]+)"
)

# ---------------------------------------------------------------------------
# Spotify client (optional – falls back to plain YouTube search)
# ---------------------------------------------------------------------------


def _build_spotify() -> Optional["spotipy.Spotify"]:
    if not _SPOTIPY_AVAILABLE:
        return None
    cid = os.getenv("SPOTIFY_CLIENT_ID", "")
    csecret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    if not (cid and csecret):
        return None
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=cid, client_secret=csecret
        )
    )


sp: Optional["spotipy.Spotify"] = _build_spotify()


def _spotify_queries(url: str) -> List[str]:
    """Return a list of '<title> <artist>' search strings from a Spotify URL."""
    if sp is None:
        return []

    m = _SP_TRACK.search(url)
    if m:
        t = sp.track(m.group(1))
        artists = ", ".join(a["name"] for a in t["artists"])
        return [f"{t['name']} {artists}"]

    m = _SP_PLAYLIST.search(url)
    if m:
        items = sp.playlist_tracks(m.group(1))["items"]
        out = []
        for item in items[:MAX_PLAYLIST_ITEMS]:
            t = item.get("track")
            if t:
                artists = ", ".join(a["name"] for a in t["artists"])
                out.append(f"{t['name']} {artists}")
        return out

    m = _SP_ALBUM.search(url)
    if m:
        tracks = sp.album_tracks(m.group(1))["items"]
        out = []
        for t in tracks[:MAX_PLAYLIST_ITEMS]:
            artists = ", ".join(a["name"] for a in t["artists"])
            out.append(f"{t['name']} {artists}")
        return out

    return []


def _spotify_search_query(text: str) -> str:
    """Return '<title> <artist>' for the top Spotify hit, or *text* unchanged."""
    if sp is None:
        return text
    try:
        res = sp.search(q=text, type="track", limit=1)
        items = res["tracks"]["items"]
        if items:
            t = items[0]
            artists = ", ".join(a["name"] for a in t["artists"])
            return f"{t['name']} {artists}"
    except Exception:
        pass
    return text


# ---------------------------------------------------------------------------
# yt-dlp helpers (run in executor to avoid blocking the event loop)
# ---------------------------------------------------------------------------


def _ytdl_extract(query: str) -> Optional[dict]:
    """
    Synchronously run yt-dlp and return a dict with:
        title, webpage_url, stream_url, duration, thumbnail
    Returns *None* on failure.
    """
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
        except Exception as exc:
            log.error("[yt-dlp] extract_info failed for %r: %s", query, exc)
            return None

    if info is None:
        return None

    # ytsearch wraps results in an 'entries' list
    if "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            return None
        info = entries[0]

    return {
        "title": info.get("title") or "Unknown",
        "webpage_url": info.get("webpage_url") or query,
        "stream_url": info.get("url") or "",
        "duration": int(info.get("duration") or 0),
        "thumbnail": info.get("thumbnail") or "",
    }


async def _async_extract(query: str) -> Optional[dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _ytdl_extract, query)


async def _resolve_stream(webpage_url: str) -> Optional[str]:
    """Re-extract a fresh, non-expired stream URL for a YouTube page."""
    data = await _async_extract(webpage_url)
    return data["stream_url"] if data else None


# ---------------------------------------------------------------------------
# Song dataclass
# ---------------------------------------------------------------------------


class Song:
    """Holds metadata and the current stream URL for one track."""

    __slots__ = ("title", "webpage_url", "stream_url", "duration", "thumbnail", "requester")

    def __init__(
        self,
        title: str,
        webpage_url: str,
        stream_url: str,
        duration: int,
        thumbnail: str,
        requester: discord.Member,
    ) -> None:
        self.title = title
        self.webpage_url = webpage_url
        self.stream_url = stream_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester

    @classmethod
    def from_ytdl(cls, data: dict, requester: discord.Member) -> "Song":
        return cls(
            title=data["title"],
            webpage_url=data["webpage_url"],
            stream_url=data["stream_url"],
            duration=data["duration"],
            thumbnail=data.get("thumbnail", ""),
            requester=requester,
        )

    def fmt_duration(self) -> str:
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def embed(
        self,
        title: str = "Now Playing 🎵",
        color: discord.Color = discord.Color.green(),
    ) -> discord.Embed:
        e = discord.Embed(
            title=title,
            description=f"[{self.title}]({self.webpage_url})",
            color=color,
        )
        e.add_field(name="⏱ Duration", value=self.fmt_duration(), inline=True)
        e.add_field(name="👤 Requested by", value=self.requester.mention, inline=True)
        if self.thumbnail:
            e.set_thumbnail(url=self.thumbnail)
        return e


# ---------------------------------------------------------------------------
# Per-guild music state
# ---------------------------------------------------------------------------


class GuildState:
    def __init__(self) -> None:
        self.queue: List[Song] = []
        self.current: Optional[Song] = None
        self.loop: str = "none"       # "none" | "song" | "queue"
        self.volume: float = 1.0      # 0.0 – 2.0
        self.always_on: bool = False
        self.always_channel: Optional[discord.VoiceChannel] = None
        self.text_channel: Optional[discord.abc.Messageable] = None
        self._skip: bool = False      # set by !skip to override loop
        self.history: List[Song] = []  # last 10 played tracks
        self._alone_task: Optional[asyncio.Task] = None  # cancelable alone-disconnect


# ---------------------------------------------------------------------------
# Music Cog
# ---------------------------------------------------------------------------


class Music(commands.Cog, name="Music 🎵"):
    """
    Full-featured music bot commands.

    Supports Spotify URLs (track / playlist / album), YouTube URLs and
    plain search queries.  Audio is streamed at the highest available
    quality via yt-dlp + FFmpeg.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._states: dict[int, GuildState] = {}
        self._reconnect_loop.start()

    def cog_unload(self) -> None:
        self._reconnect_loop.cancel()

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _state(self, guild_id: int) -> GuildState:
        if guild_id not in self._states:
            self._states[guild_id] = GuildState()
        return self._states[guild_id]

    async def _ensure_voice(self, ctx: commands.Context) -> bool:
        """Move/join the author's voice channel.  Returns False on failure."""
        if not ctx.author.voice:
            await ctx.send("❌ You must be in a voice channel first!")
            return False
        ch = ctx.author.voice.channel
        vc: Optional[discord.VoiceClient] = ctx.voice_client
        if vc:
            if vc.channel.id != ch.id:
                await vc.move_to(ch)
        else:
            await ch.connect()
        return True

    async def _play_next(self, ctx: commands.Context) -> None:
        """Advance to the next track; called from the after-play callback."""
        st = self._state(ctx.guild.id)
        vc: Optional[discord.VoiceClient] = ctx.voice_client

        if vc is None or not vc.is_connected():
            return

        # Handle loop modes (skip flag bypasses re-queuing)
        if st.current and not st._skip:
            if st.loop == "song":
                st.queue.insert(0, st.current)
            elif st.loop == "queue":
                st.queue.append(st.current)
        st._skip = False

        if not st.queue:
            st.current = None
            if not st.always_on:
                # Disconnect after 3 minutes of silence
                await asyncio.sleep(IDLE_DISCONNECT_SECONDS)
                vc2: Optional[discord.VoiceClient] = ctx.voice_client
                if (
                    vc2
                    and vc2.is_connected()
                    and not vc2.is_playing()
                    and not st.queue
                ):
                    await vc2.disconnect()
            return

        song = st.queue.pop(0)

        # Always re-extract a fresh stream URL (YouTube URLs expire)
        fresh_url = await _resolve_stream(song.webpage_url)
        if not fresh_url:
            if st.text_channel:
                await st.text_channel.send(
                    f"❌ Could not load **{song.title}**, skipping…"
                )
            await self._play_next(ctx)
            return

        song.stream_url = fresh_url
        st.current = song

        # Record in per-guild history (keep last 10 tracks)
        st.history.append(song)
        if len(st.history) > 10:
            st.history.pop(0)

        source: discord.AudioSource = discord.FFmpegPCMAudio(
            fresh_url,
            before_options=FFMPEG_BEFORE_OPTIONS,
            options=FFMPEG_OPTIONS,
        )
        source = discord.PCMVolumeTransformer(source, volume=st.volume)

        def _after(error: Optional[Exception]) -> None:
            if error:
                log.error("Player error: %s", error)
            asyncio.run_coroutine_threadsafe(
                self._play_next(ctx), self.bot.loop
            )

        vc.play(source, after=_after)

        if st.text_channel:
            await st.text_channel.send(embed=song.embed())

    # ------------------------------------------------------------------ #
    # 24/7 reconnect task                                                  #
    # ------------------------------------------------------------------ #

    @tasks.loop(seconds=RECONNECT_INTERVAL_SECONDS)
    async def _reconnect_loop(self) -> None:
        """Re-join always-on channels if the bot was disconnected."""
        for guild_id, st in list(self._states.items()):
            if not st.always_on or st.always_channel is None:
                continue
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            vc: Optional[discord.VoiceClient] = guild.voice_client
            if vc and vc.is_connected():
                continue
            try:
                await st.always_channel.connect()
            except Exception as exc:
                log.error("24/7 reconnect failed (guild %s): %s", guild_id, exc)

    @_reconnect_loop.before_loop
    async def _before_reconnect(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ #
    # Voice commands                                                       #
    # ------------------------------------------------------------------ #

    @commands.command(name="join", aliases=["connect", "j"])
    async def join(self, ctx: commands.Context) -> None:
        """Join your current voice channel and enable 24/7 mode there."""
        if not ctx.author.voice:
            return await ctx.send("❌ You must be in a voice channel!")
        ch = ctx.author.voice.channel
        try:
            if ctx.voice_client:
                await ctx.voice_client.move_to(ch)
            else:
                await ch.connect()
        except (discord.ClientException, discord.Forbidden, asyncio.TimeoutError) as exc:
            log.warning("Failed to join voice channel %s in guild %s: %s", ch.id, ctx.guild.id, exc)
            return await ctx.send("❌ I couldn't join that voice channel. Check permissions and try again.")

        vc = ctx.voice_client
        if not vc or not vc.is_connected() or vc.channel.id != ch.id:
            return await ctx.send("❌ I couldn't join that voice channel. Try again.")
        st = self._state(ctx.guild.id)
        st.always_on = True
        st.always_channel = ch
        await ctx.send(f"✅ Joined **{ch.name}** and enabled **24/7 mode**!")

    @commands.command(name="leave", aliases=["disconnect", "dc"])
    async def leave(self, ctx: commands.Context) -> None:
        """Stop playback and leave the voice channel."""
        if not ctx.voice_client:
            return await ctx.send("❌ I'm not in a voice channel!")
        st = self._state(ctx.guild.id)
        st.queue.clear()
        st.current = None
        st.always_on = False
        st.always_channel = None
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Disconnected!")

    # ------------------------------------------------------------------ #
    # Playback commands                                                    #
    # ------------------------------------------------------------------ #

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """Play a song.

        Accepts:
        • A song name          → `!play Blinding Lights`
        • A Spotify track URL  → `!play https://open.spotify.com/track/…`
        • A Spotify playlist   → `!play https://open.spotify.com/playlist/…`
        • A Spotify album      → `!play https://open.spotify.com/album/…`
        • A YouTube URL        → `!play https://www.youtube.com/watch?v=…`
        """
        st = self._state(ctx.guild.id)
        st.text_channel = ctx.channel

        if not await self._ensure_voice(ctx):
            return

        async with ctx.typing():
            songs_added: List[Song] = []

            # ── Spotify URL ─────────────────────────────────────────────
            if _is_spotify_url(query):
                if sp is None:
                    return await ctx.send(
                        "❌ Spotify credentials are not set. "
                        "Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to your `.env`."
                    )
                queries = _spotify_queries(query)
                if not queries:
                    return await ctx.send("❌ Could not read that Spotify link.")
                for q in queries:
                    data = await _async_extract(f"ytsearch:{q}")
                    if data:
                        songs_added.append(Song.from_ytdl(data, ctx.author))

            # ── YouTube URL ─────────────────────────────────────────────
            elif _is_youtube_url(query):
                data = await _async_extract(query)
                if data:
                    songs_added.append(Song.from_ytdl(data, ctx.author))

            # ── Plain search query ───────────────────────────────────────
            else:
                # Resolve via Spotify first for accurate metadata
                yt_query = f"ytsearch:{_spotify_search_query(query)}"
                data = await _async_extract(yt_query)
                if data:
                    songs_added.append(Song.from_ytdl(data, ctx.author))

            if not songs_added:
                return await ctx.send("❌ Nothing found for that query.")

            for song in songs_added:
                st.queue.append(song)

            already_playing = ctx.voice_client.is_playing() or ctx.voice_client.is_paused()

            if len(songs_added) == 1:
                if already_playing:
                    await ctx.send(
                        embed=songs_added[0].embed(
                            "Added to Queue ✅", discord.Color.blue()
                        )
                    )
            else:
                await ctx.send(
                    f"✅ Added **{len(songs_added)}** songs to the queue!"
                )

            if not already_playing:
                await self._play_next(ctx)

    @commands.command(name="search", aliases=["find"])
    async def search(self, ctx: commands.Context, *, query: str) -> None:
        """Search Spotify and display the top 5 results."""
        if sp is None:
            return await ctx.send(
                "❌ Spotify credentials are not configured. "
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET."
            )
        async with ctx.typing():
            res = sp.search(q=query, type="track", limit=SEARCH_RESULT_LIMIT)
            tracks = res["tracks"]["items"]
            if not tracks:
                return await ctx.send("❌ No results found on Spotify.")

            embed = discord.Embed(
                title=f"🔍 Spotify Search: {query}",
                color=discord.Color.green(),
            )
            for i, t in enumerate(tracks, 1):
                artists = ", ".join(a["name"] for a in t["artists"])
                dur_s = t["duration_ms"] // 1000
                m, s = divmod(dur_s, 60)
                embed.add_field(
                    name=f"{i}. {t['name']}",
                    value=f"👤 {artists}  |  ⏱ {m:02d}:{s:02d}",
                    inline=False,
                )
            embed.set_footer(text="Use !play <song name> to play any of these.")
            await ctx.send(embed=embed)

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context) -> None:
        """Pause the current song."""
        vc = ctx.voice_client
        if not vc or not vc.is_playing():
            return await ctx.send("❌ Nothing is playing.")
        vc.pause()
        await ctx.send("⏸ Paused.")

    @commands.command(name="resume", aliases=["unpause"])
    async def resume(self, ctx: commands.Context) -> None:
        """Resume the paused song."""
        vc = ctx.voice_client
        if not vc or not vc.is_paused():
            return await ctx.send("❌ Nothing is paused.")
        vc.resume()
        await ctx.send("▶️ Resumed.")

    @commands.command(name="skip", aliases=["next", "sk"])
    async def skip(self, ctx: commands.Context) -> None:
        """Skip the currently playing song."""
        vc = ctx.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await ctx.send("❌ Nothing is playing.")
        st = self._state(ctx.guild.id)
        st._skip = True
        vc.stop()
        await ctx.send("⏭ Skipped!")

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context) -> None:
        """Stop playback and clear the entire queue."""
        vc = ctx.voice_client
        if not vc:
            return await ctx.send("❌ I'm not in a voice channel.")
        st = self._state(ctx.guild.id)
        st.queue.clear()
        st.current = None
        st.loop = "none"
        vc.stop()
        await ctx.send("⏹ Stopped and cleared the queue.")

    # ------------------------------------------------------------------ #
    # Queue commands                                                       #
    # ------------------------------------------------------------------ #

    @commands.command(name="queue", aliases=["q", "list"])
    async def queue_cmd(self, ctx: commands.Context) -> None:
        """Display the current music queue."""
        st = self._state(ctx.guild.id)
        if not st.current and not st.queue:
            return await ctx.send("❌ The queue is empty.")

        embed = discord.Embed(title="Music Queue 🎵", color=discord.Color.blue())

        if st.current:
            embed.add_field(
                name="▶️ Now Playing",
                value=(
                    f"[{st.current.title}]({st.current.webpage_url}) "
                    f"`{st.current.fmt_duration()}`"
                ),
                inline=False,
            )

        if st.queue:
            lines = []
            for i, s in enumerate(st.queue[:10], 1):
                lines.append(
                    f"`{i}.` [{s.title}]({s.webpage_url}) `{s.fmt_duration()}`"
                )
            if len(st.queue) > 10:
                lines.append(f"… and **{len(st.queue) - 10}** more")
            embed.add_field(
                name=f"Up Next ({len(st.queue)} songs)",
                value="\n".join(lines),
                inline=False,
            )

        loop_icon = {"none": "➡️ Off", "song": "🔂 Song", "queue": "🔁 Queue"}
        embed.set_footer(
            text=(
                f"Loop: {loop_icon.get(st.loop, st.loop)}  |  "
                f"Volume: {int(st.volume * 100)}%  |  "
                f"24/7: {'✅' if st.always_on else '❌'}"
            )
        )
        await ctx.send(embed=embed)

    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def nowplaying(self, ctx: commands.Context) -> None:
        """Show details about the currently playing song."""
        st = self._state(ctx.guild.id)
        if not st.current:
            return await ctx.send("❌ Nothing is playing.")
        await ctx.send(embed=st.current.embed())

    @commands.command(name="remove", aliases=["rm"])
    async def remove(self, ctx: commands.Context, index: int) -> None:
        """Remove a song from the queue by position number."""
        st = self._state(ctx.guild.id)
        if not st.queue:
            return await ctx.send("❌ The queue is empty.")
        if index < 1 or index > len(st.queue):
            return await ctx.send(
                f"❌ Index must be between 1 and {len(st.queue)}."
            )
        removed = st.queue.pop(index - 1)
        await ctx.send(f"✅ Removed **{removed.title}**.")

    @commands.command(name="shuffle")
    async def shuffle(self, ctx: commands.Context) -> None:
        """Shuffle the queue."""
        st = self._state(ctx.guild.id)
        if not st.queue:
            return await ctx.send("❌ The queue is empty.")
        random.shuffle(st.queue)
        await ctx.send("🔀 Queue shuffled!")

    @commands.command(name="clearqueue", aliases=["cq", "clear"])
    async def clear_queue(self, ctx: commands.Context) -> None:
        """Clear all songs from the queue (keeps current track playing)."""
        st = self._state(ctx.guild.id)
        if not st.queue:
            return await ctx.send("❌ The queue is already empty.")
        count = len(st.queue)
        st.queue.clear()
        await ctx.send(f"🗑️ Cleared **{count}** songs from the queue.")

    @commands.command(name="playtop", aliases=["pt"])
    async def playtop(self, ctx: commands.Context, *, query: str) -> None:
        """Add a song to the top of the queue so it plays next.

        Accepts the same input as ``!play`` (name, Spotify URL, YouTube URL).
        """
        st = self._state(ctx.guild.id)
        st.text_channel = ctx.channel

        if not await self._ensure_voice(ctx):
            return

        async with ctx.typing():
            # ── Spotify URL ─────────────────────────────────────────────
            if _is_spotify_url(query):
                if sp is None:
                    return await ctx.send(
                        "❌ Spotify credentials are not set. "
                        "Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to your `.env`."
                    )
                queries = _spotify_queries(query)
                if not queries:
                    return await ctx.send("❌ Could not read that Spotify link.")
                # For playtop insert in reverse so first track ends up at front
                songs_to_insert: List[Song] = []
                for q in queries:
                    data = await _async_extract(f"ytsearch:{q}")
                    if data:
                        songs_to_insert.append(Song.from_ytdl(data, ctx.author))
                for song in reversed(songs_to_insert):
                    st.queue.insert(0, song)
                added = len(songs_to_insert)

            # ── YouTube URL ─────────────────────────────────────────────
            elif _is_youtube_url(query):
                data = await _async_extract(query)
                if not data:
                    return await ctx.send("❌ Nothing found for that query.")
                st.queue.insert(0, Song.from_ytdl(data, ctx.author))
                added = 1

            # ── Plain search query ───────────────────────────────────────
            else:
                yt_query = f"ytsearch:{_spotify_search_query(query)}"
                data = await _async_extract(yt_query)
                if not data:
                    return await ctx.send("❌ Nothing found for that query.")
                st.queue.insert(0, Song.from_ytdl(data, ctx.author))
                added = 1

            if added == 0:
                return await ctx.send("❌ Nothing found for that query.")

            if added == 1:
                song = st.queue[0]
                await ctx.send(
                    embed=song.embed("Queued Next ⏭️", discord.Color.orange())
                )
            else:
                await ctx.send(f"⏭️ Added **{added}** songs to the top of the queue!")

            already_playing = ctx.voice_client.is_playing() or ctx.voice_client.is_paused()
            if not already_playing:
                await self._play_next(ctx)

    @commands.command(name="history", aliases=["recent"])
    async def history(self, ctx: commands.Context) -> None:
        """Show the last 10 songs that were played."""
        st = self._state(ctx.guild.id)
        if not st.history:
            return await ctx.send("❌ No songs have been played yet.")

        embed = discord.Embed(title="Recently Played 🕓", color=discord.Color.purple())
        lines = []
        for i, song in enumerate(reversed(st.history), 1):
            lines.append(
                f"`{i}.` [{song.title}]({song.webpage_url}) `{song.fmt_duration()}`"
            )
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    # Settings commands                                                    #
    # ------------------------------------------------------------------ #

    @commands.command(name="volume", aliases=["vol", "v"])
    async def volume(self, ctx: commands.Context, level: int) -> None:
        """Set playback volume (0–200).  100 = normal, 200 = maximum boost."""
        if level < 0 or level > 200:
            return await ctx.send("❌ Volume must be between 0 and 200.")
        st = self._state(ctx.guild.id)
        st.volume = level / 100.0
        vc = ctx.voice_client
        if vc and vc.source:
            vc.source.volume = st.volume
        await ctx.send(f"🔊 Volume set to **{level}%**.")

    @commands.command(name="loop", aliases=["repeat"])
    async def loop(self, ctx: commands.Context, mode: Optional[str] = None) -> None:
        """Set loop mode: `none`, `song`, or `queue`.  No argument cycles through modes."""
        st = self._state(ctx.guild.id)
        modes = ["none", "song", "queue"]
        if mode is None:
            st.loop = modes[(modes.index(st.loop) + 1) % len(modes)]
        else:
            mode = mode.lower()
            if mode == "off":
                mode = "none"
            if mode not in modes:
                return await ctx.send(
                    "❌ Mode must be `none`, `song`, or `queue`."
                )
            st.loop = mode
        icons = {"none": "➡️ Off", "song": "🔂 Song", "queue": "🔁 Queue"}
        await ctx.send(f"Loop mode → **{icons[st.loop]}**")

    @commands.command(name="247", aliases=["always", "nonstop"])
    async def always_on(self, ctx: commands.Context) -> None:
        """Toggle 24/7 mode – the bot stays in VC permanently and auto-reconnects."""
        if not ctx.author.voice:
            return await ctx.send("❌ You must be in a voice channel first!")
        st = self._state(ctx.guild.id)
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        st.always_on = not st.always_on
        if st.always_on:
            st.always_channel = ctx.author.voice.channel
            await ctx.send(
                f"✅ 24/7 mode **enabled** – I'll stay in **{st.always_channel.name}** forever!"
            )
        else:
            st.always_channel = None
            await ctx.send("✅ 24/7 mode **disabled**.")

    # ------------------------------------------------------------------ #
    # Listeners                                                            #
    # ------------------------------------------------------------------ #

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Auto-join the channel set in AUTO_JOIN_CHANNEL_ID and enable 24/7 mode."""
        raw = os.getenv("AUTO_JOIN_CHANNEL_ID", "").strip()
        if not raw:
            return
        try:
            channel_id = int(raw)
        except ValueError:
            log.warning("AUTO_JOIN_CHANNEL_ID=%r is not a valid integer – skipping auto-join.", raw)
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            log.warning("AUTO_JOIN_CHANNEL_ID=%s not found – the bot may lack access.", channel_id)
            return
        if not isinstance(channel, discord.VoiceChannel):
            log.warning("AUTO_JOIN_CHANNEL_ID=%s is not a voice channel.", channel_id)
            return

        guild = channel.guild
        vc: Optional[discord.VoiceClient] = guild.voice_client
        try:
            if vc and vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
            else:
                await channel.connect()
        except Exception as exc:
            log.error("Auto-join failed for channel %s: %s", channel_id, exc)
            return

        st = self._state(guild.id)
        st.always_on = True
        st.always_channel = channel
        log.info("Auto-joined voice channel '%s' in guild '%s' with 24/7 mode enabled.", channel.name, guild.name)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Auto-disconnect 60 s after being left alone (skipped in 24/7 mode)."""
        if member.bot:
            return
        guild = member.guild
        vc: Optional[discord.VoiceClient] = guild.voice_client
        if not vc or not vc.is_connected():
            return
        st = self._state(guild.id)
        if st.always_on:
            return

        # If someone joined our channel, cancel any pending alone-disconnect
        if after.channel and after.channel.id == vc.channel.id:
            if st._alone_task and not st._alone_task.done():
                st._alone_task.cancel()
                st._alone_task = None
            return

        # Still humans present – nothing to do
        if any(not m.bot for m in vc.channel.members):
            return

        # Cancel any previously scheduled disconnect before creating a new one
        if st._alone_task and not st._alone_task.done():
            st._alone_task.cancel()

        async def _do_alone_disconnect() -> None:
            await asyncio.sleep(ALONE_DISCONNECT_SECONDS)
            vc2: Optional[discord.VoiceClient] = guild.voice_client
            if vc2 and vc2.is_connected():
                if not any(not m.bot for m in vc2.channel.members):
                    st.queue.clear()
                    st.current = None
                    await vc2.disconnect()

        st._alone_task = asyncio.create_task(_do_alone_disconnect())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
