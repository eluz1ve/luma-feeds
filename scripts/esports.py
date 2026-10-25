"""Builds Luma's esports feed: running and upcoming matches with lineups for each discipline.

Reads PANDASCORE_KEY from the environment and writes site/esports/<game>.json. Uses about 25
requests per run (two match lists and one teams list per discipline), well inside the free plan's
1000 requests an hour at one run every 15 minutes. Only what the free plan lists is included:
map names, picks and in-game statistics need a paid plan.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.pandascore.co"
IMAGES = "https://cdn-api.pandascore.co/"
GAMES = ["csgo", "dota2", "lol", "valorant", "r6siege", "ow", "rl", "codmw"]
PER_GAME = 20


def get(path, key):
    request = urllib.request.Request(
        API + path,
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "luma-feeds",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ""


def image(*urls):
    """The first of these images on PandaScore's CDN; dark-mode logos come first."""
    for url in urls:
        if isinstance(url, str) and url.startswith(IMAGES):
            return url
    return ""


def team(entry):
    opponent = (entry or {}).get("opponent") or {}
    if not isinstance(opponent.get("id"), int):
        return None
    name = text(opponent.get("name"), 40)
    return {
        "id": opponent["id"],
        "name": name,
        "short": text(opponent.get("acronym"), 12) or name,
        "image": image(opponent.get("dark_mode_image_url"), opponent.get("image_url")),
        "location": text(opponent.get("location"), 8),
    }


def stream(entry):
    url = urllib.parse.urlparse(entry.get("raw_url") or "")
    host = url.hostname or ""
    platform = {"www.twitch.tv": "Twitch", "twitch.tv": "Twitch", "kick.com": "Kick",
                "www.youtube.com": "YouTube", "youtube.com": "YouTube"}.get(host, host)
    return {
        "language": text(entry.get("language"), 8),
        "platform": text(platform, 24),
        "official": bool(entry.get("official")),
        "main": bool(entry.get("main")),
    }


def match(item):
    opponents = (item.get("opponents") or [])[:2]
    teams = [team(entry) for entry in opponents] + [None] * (2 - len(opponents))
    results = item.get("results") or []

    def score(side):
        for result in results:
            if side and result.get("team_id") == side["id"]:
                return result.get("score") or 0
        return 0

    games = sorted(
        (
            {
                "position": game.get("position"),
                "state": {"running": "running", "finished": "finished"}.get(game.get("status"), "waiting"),
                "winner": (game.get("winner") or {}).get("id"),
                "begin_at": game.get("begin_at") or "",
                "length": game.get("length") if isinstance(game.get("length"), int) else None,
            }
            for game in item.get("games") or []
            if isinstance(game.get("position"), int)
        ),
        key=lambda game: game["position"],
    )
    league = item.get("league") or {}
    serie = item.get("serie") or {}
    tournament = item.get("tournament") or {}
    return {
        "id": item.get("id"),
        "running": item.get("status") == "running",
        "begin_at": item.get("begin_at") or item.get("scheduled_at") or "",
        "teams": teams,
        "score": [score(teams[0]), score(teams[1])],
        "best_of": item.get("number_of_games") or 1,
        "games": games,
        "event": f"{text(league.get('name'), 40)} {text(serie.get('full_name'), 40)}".strip()[:60],
        "league_image": image(league.get("image_url")),
        "stage": text(tournament.get("name"), 40),
        "tier": text(tournament.get("tier"), 12).lower(),
        "prizepool": text(tournament.get("prizepool"), 40),
        "online": {"online": True, "offline": False}.get(tournament.get("type")),
        "streams": [stream(s) for s in (item.get("streams_list") or [])[:6]],
    }


def player(entry):
    real = " ".join(text(entry.get(key), 24) for key in ("first_name", "last_name")).strip()
    return {
        "name": text(entry.get("name"), 24),
        "real_name": real[:40],
        "nationality": text(entry.get("nationality"), 8),
        "role": text(entry.get("role"), 16),
        "age": entry.get("age") if isinstance(entry.get("age"), int) else None,
        "image": image(entry.get("image_url")),
    }


def game_feed(game, key):
    running = [match(m) for m in get(f"/{game}/matches/running?per_page=25&sort=begin_at", key)]
    upcoming = [match(m) for m in get(f"/{game}/matches/upcoming?per_page=50&sort=begin_at", key)]
    upcoming.sort(key=lambda m: m["begin_at"])
    matches = [m for m in running + upcoming if isinstance(m["id"], int)][:PER_GAME]
    ids = sorted({t["id"] for m in matches for t in m["teams"] if t})
    lineups = {}
    if ids:
        query = urllib.parse.quote("filter[id]") + "=" + ",".join(map(str, ids[:50]))
        for entry in get(f"/{game}/teams?{query}&per_page=50", key):
            players = [player(p) for p in entry.get("players") or [] if p.get("active", True)]
            lineups[entry.get("id")] = [p for p in players if p["name"]][:7]
    for m in matches:
        m["lineups"] = [lineups.get(t["id"], []) if t else [] for t in m["teams"]]
    return {"game": game, "updated": int(time.time()), "matches": matches}


def main():
    key = os.environ.get("PANDASCORE_KEY", "").strip()
    if not key:
        sys.exit("PANDASCORE_KEY is not set")
    out = os.path.join(os.path.dirname(__file__), "..", "site", "esports")
    os.makedirs(out, exist_ok=True)
    failures = 0
    for game in GAMES:
        try:
            feed = game_feed(game, key)
        except (urllib.error.URLError, ValueError, OSError) as error:
            failures += 1
            print(f"{game}: {error}", file=sys.stderr)
            continue
        with open(os.path.join(out, f"{game}.json"), "w", encoding="utf8") as file:
            json.dump(feed, file, ensure_ascii=False, separators=(",", ":"))
        print(f"{game}: {len(feed['matches'])} matches")
    if failures == len(GAMES):
        sys.exit("every discipline failed")


if __name__ == "__main__":
    main()
