#!/usr/bin/env bash
# deploy.sh – one-command self-hosted setup for MineStone on a Linux VPS / PC
# Usage:  bash deploy.sh
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BOLD}🎵  MineStone – Self-hosted Setup${NC}"
echo "──────────────────────────────────"

# ── Dependency checks ────────────────────────────────────────────────────────

command -v docker  >/dev/null 2>&1 || { echo -e "${RED}✗ Docker is not installed. Install it first: https://docs.docker.com/engine/install/${NC}"; exit 1; }
command -v docker  >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || { echo -e "${RED}✗ Docker Compose v2 plugin not found. Update Docker Desktop or install the plugin.${NC}"; exit 1; }

echo -e "${GREEN}✓ Docker and Docker Compose found${NC}"

# ── .env configuration ────────────────────────────────────────────────────────

if [[ -f .env ]]; then
    echo -e "${YELLOW}ℹ  .env already exists – skipping interactive setup.${NC}"
    echo "   Edit .env manually if you need to change credentials."
else
    echo ""
    echo -e "${BOLD}Let's configure your bot.${NC}"
    echo ""

    read -rp "  Discord bot token (required): " discord_token
    if [[ -z "$discord_token" ]]; then
        echo -e "${RED}✗ Discord token is required. Aborting.${NC}"
        exit 1
    fi

    read -rp "  Spotify Client ID   (leave blank to skip): " spotify_id
    read -rp "  Spotify Client Secret (leave blank to skip): " spotify_secret
    read -rp "  Command prefix [default: !]: " prefix
    prefix="${prefix:-!}"

    cat > .env <<EOF
# Required
DISCORD_TOKEN=${discord_token}

# Optional – enables Spotify search (recommended)
SPOTIFY_CLIENT_ID=${spotify_id}
SPOTIFY_CLIENT_SECRET=${spotify_secret}

# Command prefix (default: !)
PREFIX=${prefix}

# Set to true only for Replit / UptimeRobot free-tier hosting
KEEP_ALIVE=false
EOF

    echo -e "${GREEN}✓ .env created${NC}"
fi

# ── Build & start ─────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}Building and starting MineStone…${NC}"
docker compose pull --quiet 2>/dev/null || true
docker compose up -d --build

echo ""
echo -e "${GREEN}${BOLD}✅  MineStone is running!${NC}"
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f          – follow live logs"
echo "    docker compose restart          – restart the bot"
echo "    docker compose down             – stop the bot"
echo "    docker compose up -d --build    – rebuild after code changes"
echo ""
echo "  The bot restarts automatically on crash or system reboot."
