"""Keep-alive web server for 24/7 hosting on platforms like Replit.

Start the bot and pair it with an uptime monitor such as UptimeRobot
(free tier) to keep it online around the clock.
"""

import time
from threading import Thread

from flask import Flask, jsonify

app = Flask(__name__)

_start_time: float = time.time()


@app.route("/")
def home():
    return "MineStone Music Bot is alive! 🎵"


@app.route("/health")
def health():
    uptime_seconds = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return jsonify(
        status="ok",
        uptime=f"{hours:02d}:{minutes:02d}:{seconds:02d}",
        uptime_seconds=uptime_seconds,
    ), 200


def _run():
    app.run(host="0.0.0.0", port=8080, use_reloader=False)


def keep_alive():
    """Start the keep-alive web server in a background daemon thread."""
    thread = Thread(target=_run, daemon=True)
    thread.start()
