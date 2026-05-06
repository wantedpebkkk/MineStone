# 🎵 MineStone – 24/7 Discord Music Bot

A fully-featured Discord music bot that:

- **Searches songs via Spotify** – type a song name and it resolves the best match through Spotify before streaming HD audio from YouTube.
- **HD audio quality** – uses yt-dlp `bestaudio/best` + FFmpeg at 48 kHz stereo for crystal-clear sound.
- **24/7 mode** – bot stays in your voice channel permanently and auto-reconnects if it ever drops.
- **Standard music commands** – play, pause, resume, skip, stop, queue, volume, loop, shuffle and more.

---

## Requirements

- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) installed and on your `PATH`
- A [Discord bot token](https://discord.com/developers/applications)
- *(Optional but recommended)* [Spotify API credentials](https://developer.spotify.com/dashboard)

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/wantedpebkkk/MineStone.git
cd MineStone

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
# Edit .env and fill in DISCORD_TOKEN (+ Spotify keys if you want Spotify search)

# 4. Run
python bot.py
```

---

## Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `!play <query/URL>` | `!p` | Play a song by name, Spotify URL, or YouTube URL |
| `!search <query>` | `!find` | Search Spotify and show top 5 results |
| `!pause` | – | Pause the current song |
| `!resume` | `!unpause` | Resume a paused song |
| `!skip` | `!next`, `!sk` | Skip to the next song |
| `!stop` | – | Stop playback and clear the queue |
| `!queue` | `!q`, `!list` | Show the music queue |
| `!nowplaying` | `!np`, `!current` | Show the currently playing song |
| `!volume <0-200>` | `!vol`, `!v` | Set the volume (100 = normal) |
| `!loop [mode]` | `!repeat` | Cycle / set loop mode: `none`, `song`, `queue` |
| `!shuffle` | – | Shuffle the queue |
| `!remove <#>` | `!rm` | Remove a song from the queue by position |
| `!clearqueue` | `!cq`, `!clear` | Clear all queued songs |
| `!join` | `!connect`, `!j` | Join your voice channel |
| `!leave` | `!disconnect`, `!dc` | Leave the voice channel |
| `!247` | `!always`, `!nonstop` | Toggle 24/7 mode (stays in VC permanently) |

---

## 24/7 Hosting

The bot ships with `keep_alive.py` – a tiny Flask web server (port 8080).  
Point a free uptime monitor such as **UptimeRobot** at `http://<your-host>:8080/` 
to keep the bot alive on free-tier platforms like Replit.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | ✅ | Your Discord bot token |
| `SPOTIFY_CLIENT_ID` | ⚡ recommended | Spotify API client ID |
| `SPOTIFY_CLIENT_SECRET` | ⚡ recommended | Spotify API client secret |
| `PREFIX` | ❌ | Command prefix (default: `!`) |

