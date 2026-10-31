"""Decides whether this run is a full one: every 10 minutes, the feeds are rebuilt in full; in
between, only the Counter-Strike 2 feed's live matches are, and the other files are carried over
from what is published. Writes `full=true|false` and `full_at=<Unix seconds>` to $GITHUB_OUTPUT.
"""
import json
import os
import time
import urllib.error
import urllib.request

INDEX = "https://eluz1ve.github.io/luma-feeds/index.json"
FULL_EVERY = 10 * 60
# Runs start a little late or early; a run this close to the interval is a full one.
SLACK = 45


def due(index, now):
    full_at = index.get("full_at") if isinstance(index, dict) else None
    if not isinstance(full_at, int) or now - full_at >= FULL_EVERY - SLACK:
        return True, now
    return False, full_at


def main():
    now = int(time.time())
    try:
        request = urllib.request.Request(f"{INDEX}?t={now}", headers={"User-Agent": "luma-feeds"})
        with urllib.request.urlopen(request, timeout=20) as response:
            index = json.load(response)
    except (urllib.error.URLError, ValueError, OSError):
        index = None
    full, full_at = due(index, now)
    print(f"full={'true' if full else 'false'}")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf8") as out:
        out.write(f"full={'true' if full else 'false'}\nfull_at={full_at}\n")


if __name__ == "__main__":
    main()
