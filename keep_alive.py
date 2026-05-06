"""Keep-alive web server for 24/7 hosting on platforms like Replit.

Start the bot and pair it with an uptime monitor such as UptimeRobot
(free tier) to keep it online around the clock.
"""

from threading import Thread

from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "MineStone Music Bot is alive! 🎵"


@app.route("/health")
def health():
    return {"status": "ok"}, 200


def _run():
    app.run(host="0.0.0.0", port=8080, use_reloader=False)


def keep_alive():
    """Start the keep-alive web server in a background daemon thread."""
    thread = Thread(target=_run, daemon=True)
    thread.start()
