# 🎵 MineStone – 24/7 Discord Music Bot

A fully-featured Discord music bot that:

- **Searches songs via Spotify** – type a song name and it resolves the best match through Spotify before streaming HD audio from YouTube.
- **HD audio quality** – uses yt-dlp `bestaudio/best` + FFmpeg at 48 kHz stereo for crystal-clear sound.
- **24/7 mode** – bot stays in your voice channel permanently and auto-reconnects if it ever drops.
- **Standard music commands** – play, pause, resume, skip, stop, queue, volume, loop, shuffle and more.

---

## Requirements

- Python 3.9+ **or** Docker
- [FFmpeg](https://ffmpeg.org/download.html) installed and on your `PATH` (not needed with Docker)
- A [Discord bot token](https://discord.com/developers/applications)
- *(Optional but recommended)* [Spotify API credentials](https://developer.spotify.com/dashboard)

---

## 🖥️ Self-Hosting (PC / VPS / Linux server)

### Option A – Docker (recommended, no setup needed)

```bash
# 1. Clone the repo
git clone https://github.com/wantedpebkkk/MineStone.git
cd MineStone

# 2. Copy and fill in your secrets
cp .env.example .env
# Edit .env – set DISCORD_TOKEN (and Spotify keys if you want Spotify search)

# 3. Start the bot
docker compose up -d
```

The bot restarts automatically on crash or system reboot (`restart: unless-stopped`).

To view logs: `docker compose logs -f`  
To stop: `docker compose down`

---

### Option B – Plain Python

```bash
# 1. Clone and enter the project
git clone https://github.com/wantedpebkkk/MineStone.git
cd MineStone

# 2. Install FFmpeg
#    Ubuntu/Debian: sudo apt install ffmpeg
#    Windows: download from https://ffmpeg.org/download.html and add to PATH

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure secrets
cp .env.example .env
# Edit .env and fill in DISCORD_TOKEN (+ Spotify keys if you want Spotify search)

# 5. Run
python bot.py
```

#### Keep it running with systemd (Linux)

Create `/etc/systemd/system/minestone.service`:

```ini
[Unit]
Description=MineStone Discord Music Bot
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/path/to/MineStone
EnvironmentFile=/path/to/MineStone/.env
ExecStart=/usr/bin/python3 /path/to/MineStone/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now minestone
sudo journalctl -u minestone -f   # view logs
```

---

## ☁️ Replit / UptimeRobot (free-tier cloud hosting)

Set `KEEP_ALIVE=true` in your `.env` (or Replit Secrets) to start the built-in Flask web server on port 8080.  
Then point a free **UptimeRobot** monitor at `http://<your-replit-url>:8080/` to prevent the project from sleeping.

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

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | ✅ | Your Discord bot token |
| `SPOTIFY_CLIENT_ID` | ⚡ recommended | Spotify API client ID |
| `SPOTIFY_CLIENT_SECRET` | ⚡ recommended | Spotify API client secret |
| `PREFIX` | ❌ | Command prefix (default: `!`) |
| `KEEP_ALIVE` | ❌ | Set to `true` only for Replit/UptimeRobot hosting (default: `false`) |

