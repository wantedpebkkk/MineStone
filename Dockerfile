FROM python:3.11-slim

# Install FFmpeg (required for audio streaming)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg procps && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user for better security
RUN useradd --system --no-create-home botuser && chown -R botuser /app
USER botuser

# Health-check: verify the bot process is still running.
# When KEEP_ALIVE=true the /health HTTP endpoint is also available.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD pgrep -f "python bot.py" > /dev/null || exit 1

CMD ["python", "bot.py"]
