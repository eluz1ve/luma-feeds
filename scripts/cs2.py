"""Builds Luma's Counter-Strike 2 feed from LiquipediaDB: live, upcoming and just-finished matches.

Reads LIQUIPEDIA_KEY from the environment and writes site/cs2/matches.json. The key stays in the
repository's secrets; devices only read the published file. Runs come every 2 minutes: a full run
(four requests: the schedule, the biggest events, results and the teams' coaches) every 10
minutes, and between them a live run (one request: what started in the last hours) that keeps the
rest of the last published feed. 6 × 4 + 24 × 1 = 48 of LiquipediaDB's 60 requests an hour. Liquipedia's data is CC-BY-SA 3.0, so apps
showing the feed credit Liquipedia.
"""
import calendar
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.liquipedia.net/api/v3/match"
STAFF_API = "https://api.liquipedia.net/api/v3/squadplayer"
# Screenshots of the map pool on Liquipedia's commons, 640 px wide, from each map's page on the
# Counter-Strike wiki. Maps outside this list go without a picture.
MAP_IMAGES = {
    "Nuke": "https://liquipedia.net/commons/images/thumb/f/f5/CS2_Nuke_Outside.jpeg/640px-CS2_Nuke_Outside.jpeg",
    "Mirage": "https://liquipedia.net/commons/images/thumb/c/cd/CS2_Mirage_A_site_behind_triple.jpg/640px-CS2_Mirage_A_site_behind_triple.jpg",
    "Ancient": "https://liquipedia.net/commons/images/thumb/5/56/AncientASite.jpg/640px-AncientASite.jpg",
    "Anubis": "https://liquipedia.net/commons/images/thumb/3/39/CS2AnubisWater.jpg/640px-CS2AnubisWater.jpg",
    "Cache": "https://liquipedia.net/commons/images/thumb/b/b6/CS2_de_cache.png/640px-CS2_de_cache.png",
    "Dust II": "https://liquipedia.net/commons/images/thumb/d/d7/CS2_Dust_2_A_Site.jpg/640px-CS2_Dust_2_A_Site.jpg",
    "Inferno": "https://liquipedia.net/commons/images/thumb/f/fb/De_infernoCS2BSite.jpeg/640px-De_infernoCS2BSite.jpeg",
    "Overpass": "https://liquipedia.net/commons/images/thumb/e/ed/CS2OverpassConnector.jpg/640px-CS2OverpassConnector.jpg",
    "Train": "https://liquipedia.net/commons/images/thumb/4/44/CS2_de_train.png/640px-CS2_de_train.png",
    "Vertigo": "https://liquipedia.net/commons/images/thumb/d/d4/CS2VertigoASite.jpeg/640px-CS2VertigoASite.jpeg",
}
# Bracket headers Liquipedia writes as codes, e.g. "!gf" or "!r3!1" (round 3, one round left).
ROUND_CODES = {"gf": "grand_final", "f": "final", "sf": "semifinals", "s": "semifinals",
               "qf": "quarterfinals", "q": "quarterfinals", "tp": "third_place", "3rd": "third_place"}
ROUNDS_LEFT = {1: "final", 2: "semifinals", 3: "quarterfinals"}
STAFF_LIMIT = 60
WIKI = "counterstrike"
USER_AGENT = "luma-feeds/1.0 (https://github.com/eluz1ve/luma-feeds)"
# Open matches from this long ago may still be running; later ones are listed as upcoming.
LIVE_WINDOW = 8 * 3600
AHEAD = 3 * 24 * 3600
# The biggest events (Liquipedia's tiers 1 and 2) are listed a week ahead and always kept.
MAJOR_AHEAD = 7 * 24 * 3600
MAJOR_TIER = 2
# Matches that started this long ago and finished are listed as results, the latest few.
RESULTS = 6 * 3600
RESULT_COUNT = 10
MAX_MATCHES = 80
FIELDS = ",".join([
    "match2id", "date", "dateexact", "finished", "winner", "bestof", "tournament", "tickername",
    "section", "liquipediatier", "extradata", "match2opponents", "match2games", "icon", "iconurl",
    "icondark", "icondarkurl", "match2bracketdata",
])


def get(key, conditions, order, limit, api=API, fields=FIELDS):
    query = urllib.parse.urlencode({
        "wiki": WIKI, "conditions": conditions, "query": fields, "order": order,
        "limit": str(limit),
    })
    request = urllib.request.Request(api + "?" + query, headers={
        "Authorization": "Apikey " + key,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    reply = json.loads(body)
    if reply.get("error"):
        raise ValueError("; ".join(map(str, reply["error"])))
    return reply.get("result") or []


def stamp(seconds):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(seconds))


def start(match):
    """Unix seconds of the match's start: Liquipedia's timestamp, else its UTC date."""
    extra = match.get("extradata") if isinstance(match.get("extradata"), dict) else {}
    if isinstance(extra.get("timestamp"), int) and extra["timestamp"] > 0:
        return extra["timestamp"]
    try:
        return calendar.timegm(time.strptime(str(match.get("date")), "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None


TAGS = re.compile(r"<[^>]*>")


def text(value, limit=80):
    """Plain text: Liquipedia's markup such as "2<sup>nd</sup>" removed, whitespace collapsed."""
    return " ".join(TAGS.sub("", str(value or "")).split())[:limit]


def score(value):
    return value if isinstance(value, int) and value >= 0 else None


def side(value):
    """A winner given as "1"/"2" (or 1/2) as 0 or 1, else None."""
    return {"1": 0, "2": 1}.get(str(value).strip())


LOGOS = "https://liquipedia.net/commons/images/"


def logo(template):
    """The team's logo for dark backgrounds, else its light one; not Liquipedia's placeholders."""
    for key in ("imagedarkurl", "imageurl"):
        url = template.get(key)
        file = str(template.get(key.replace("url", "")) or "").lower()
        if isinstance(url, str) and url.startswith(LOGOS) and len(url) <= 300 and "default" not in file:
            return url
    return None


def team(opponent):
    template = opponent.get("teamtemplate") if isinstance(opponent.get("teamtemplate"), dict) else {}
    name = text(template.get("name") or opponent.get("name"))
    if not name or name.lower() in ("tbd", "definitions"):
        return None
    page = text(template.get("page"), 120).replace(" ", "_") or None
    return {"name": name, "short": text(template.get("shortname") or name, 16),
            "image": logo(template), "page": page}


def round_name(item):
    """Which round a match is, e.g. {"key": "final", "bracket": "upper"} or {"text": "Winners
    Match"}; None when Liquipedia says nothing."""
    data = item.get("match2bracketdata") if isinstance(item.get("match2bracketdata"), dict) else {}
    header = str(data.get("header") or data.get("inheritedheader") or "").strip()
    bracket = data.get("bracketsection") if data.get("bracketsection") in ("upper", "lower") else None
    if str(item.get("match2id", "")).endswith("RxMTP"):
        return {"key": "third_place"}
    if header.startswith("!"):
        parts = [part for part in header.lower().split("!") if part]
        code = re.fullmatch(r"r(\d+)", parts[0]) if parts else None
        if code and len(parts) > 1 and parts[1].isdigit():
            left = int(parts[1])
            key = ROUNDS_LEFT.get(left)
            round_ = {"key": key} if key else {"key": "round_of", "number": 2 ** left}
        elif parts and parts[0] in ROUND_CODES:
            round_ = {"key": ROUND_CODES[parts[0]]}
        else:
            return None
        if bracket and round_["key"] != "grand_final":
            round_["bracket"] = bracket
        return round_
    return {"text": text(header, 40)} if header else None


def players(opponent):
    """The opponent's players as Liquipedia lists them for the match: nickname and country."""
    listed = opponent.get("match2players") if isinstance(opponent.get("match2players"), list) else []
    out = []
    for person in listed[:10]:
        if not isinstance(person, dict):
            continue
        name = text(person.get("displayname") or person.get("name"), 32)
        if name:
            out.append({"name": name, "flag": text(person.get("flag"), 40) or None})
    return out


def game(entry):
    if not isinstance(entry, dict):
        return None
    name = text(entry.get("map"), 40)
    if not name or name.lower() in ("tbd", "unknown"):
        return None
    scores = entry.get("scores") if isinstance(entry.get("scores"), list) else []
    rounds = [score(value) for value in scores[:2]]
    return {
        "map": name,
        "image": MAP_IMAGES.get(name),
        "score": rounds if len(rounds) == 2 and None not in rounds else None,
        "winner": side(entry.get("winner")),
    }


def match(item, now):
    """One feed entry, or None for hidden, undated or malformed matches."""
    extra = item.get("extradata") if isinstance(item.get("extradata"), dict) else {}
    begins = start(item)
    opponents = item.get("match2opponents")
    if extra.get("hidden") or begins is None or not isinstance(opponents, list) or len(opponents) != 2:
        return None
    finished = item.get("finished") in (1, "1", True)
    state = "finished" if finished else ("live" if begins <= now else "upcoming")
    scores = [score(opponent.get("score")) for opponent in opponents]
    try:
        tier = int(item.get("liquipediatier"))
    except (TypeError, ValueError):
        tier = None
    best_of = item.get("bestof")
    return {
        "id": text(item.get("match2id"), 40),
        "begin_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(begins)),
        "exact": item.get("dateexact") in (1, "1", True),
        "state": state,
        "best_of": best_of if isinstance(best_of, int) and best_of > 0 else None,
        "tournament": text(item.get("tickername") or item.get("tournament")),
        "icon": logo({key.replace("icon", "image"): value for key, value in item.items()
                      if key.startswith("icon")}),
        "stage": text(item.get("section"), 40) or None,
        "round": round_name(item),
        "tier": tier,
        "teams": [team(opponent) for opponent in opponents],
        "lineups": [players(opponent) for opponent in opponents],
        "score": scores if state != "upcoming" and None not in scores else None,
        "winner": side(item.get("winner")) if finished else None,
        "maps": [m for m in map(game, item.get("match2games") or []) if m],
    }


def major(entry):
    return entry["tier"] is not None and entry["tier"] <= MAJOR_TIER


def assemble(entries, now, full_at):
    """Live matches, then upcoming ones by start, then the latest results; duplicates dropped.
    Within the cap, the biggest events come before smaller ones."""
    seen, unique = set(), []
    for entry in entries:
        if entry and entry["id"] not in seen:
            seen.add(entry["id"])
            unique.append(entry)
    by_start = sorted(unique, key=lambda m: m["begin_at"])
    finished = [m for m in reversed(by_start) if m["state"] == "finished"][:RESULT_COUNT]
    open_ = [m for m in by_start if m["state"] != "finished"]
    room = MAX_MATCHES - len(finished)
    kept = [m for m in open_ if major(m)][:room]
    kept += [m for m in open_ if not major(m)][:room - len(kept)]
    kept_ids = {m["id"] for m in kept}
    live = [m for m in open_ if m["state"] == "live" and m["id"] in kept_ids]
    upcoming = [m for m in open_ if m["state"] == "upcoming" and m["id"] in kept_ids]
    return {
        "game": "cs2",
        "source": "Liquipedia",
        "license": "CC-BY-SA 3.0",
        "updated": now,
        "full_at": full_at,
        "matches": live + upcoming + finished,
        "staff": {},
    }


def coaches(rows):
    """Coaches by team page from squadplayer rows: head coaches first, then assistants."""
    staff = {}
    for row in rows:
        role = text(row.get("role"), 60)
        name = text(row.get("id"), 32)
        page = text(row.get("pagename"), 120)
        if not name or not page or "coach" not in role.lower():
            continue
        staff.setdefault(page, []).append({"name": name, "role": role})
    for people in staff.values():
        people.sort(key=lambda person: "assistant" in person["role"].lower())
        del people[3:]
    return staff


def staff_pages(built):
    """The team pages to ask coaches for: live and the biggest events first."""
    pages = []
    for entry in sorted(built["matches"], key=lambda m: (m["state"] != "live", not major(m))):
        for side in entry["teams"]:
            if side and side.get("page") and side["page"] not in pages:
                pages.append(side["page"])
    return pages[:STAFF_LIMIT]


def feed(open_matches, results, now):
    """A full run's feed from the schedule and the results."""
    return assemble([match(item, now) for item in list(open_matches) + list(results)], now, now)


def refresh(previous, started, now):
    """A live run's feed: what started in the last hours, fresh from LiquipediaDB, with the last
    published feed's upcoming matches that still lie ahead and its results."""
    fresh = [entry for entry in (match(item, now) for item in started) if entry]
    ids = {entry["id"] for entry in fresh}
    kept = []
    for entry in previous.get("matches", []):
        if not isinstance(entry, dict) or entry.get("id") in ids:
            continue
        begins = entry.get("begin_at", "")
        if entry.get("state") == "upcoming" and begins > time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)):
            kept.append(entry)
        elif entry.get("state") == "finished":
            kept.append(entry)
    built = assemble(fresh + kept, now, previous.get("full_at") or now)
    built["staff"] = previous.get("staff") if isinstance(previous.get("staff"), dict) else {}
    return built


FEED_URL = "https://eluz1ve.github.io/luma-feeds/cs2/matches.json"


def published():
    """The feed as last published, or None."""
    request = urllib.request.Request(FEED_URL + f"?t={int(time.time())}",
                                     headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.load(response)
        return value if isinstance(value.get("matches"), list) else None
    except (urllib.error.URLError, ValueError, OSError):
        return None


def main():
    key = os.environ.get("LIQUIPEDIA_KEY", "").strip()
    if not key:
        sys.exit("LIQUIPEDIA_KEY is not set")
    now = int(time.time())
    previous = None if os.environ.get("FEEDS_FULL") == "true" else published()
    if previous is not None:
        try:
            started = get(
                key,
                f"[[date::>{stamp(now - LIVE_WINDOW)}]] AND [[date::<{stamp(now)}]]",
                "date ASC", 200)
        except (urllib.error.URLError, ValueError, OSError) as error:
            sys.exit(f"cs2: {error}")
        write(refresh(previous, started, now), "live")
        return
    try:
        open_matches = get(
            key,
            f"[[finished::0]] AND [[date::>{stamp(now - LIVE_WINDOW)}]] "
            f"AND [[date::<{stamp(now + AHEAD)}]]",
            "date ASC", 200)
        majors = get(
            key,
            f"[[finished::0]] AND [[date::>{stamp(now - LIVE_WINDOW)}]] "
            f"AND [[date::<{stamp(now + MAJOR_AHEAD)}]] "
            f"AND ([[liquipediatier::1]] OR [[liquipediatier::2]])",
            "date ASC", 100)
        results = get(
            key,
            f"[[finished::1]] AND [[date::>{stamp(now - RESULTS)}]]",
            "date DESC", 40)
    except (urllib.error.URLError, ValueError, OSError) as error:
        sys.exit(f"cs2: {error}")
    built = feed(open_matches + majors, results, now)
    pages = staff_pages(built)
    if pages:
        try:
            rows = get(
                key,
                "[[type::staff]] AND [[status::active]] AND ("
                + " OR ".join(f"[[pagename::{page}]]" for page in pages) + ")",
                "pagename ASC", 500, STAFF_API, "id,role,pagename")
            built["staff"] = coaches(rows)
        except (urllib.error.URLError, ValueError, OSError) as error:
            # Coaches are extra: the feed goes out without them.
            print(f"cs2: no coaches, {error}", file=sys.stderr)
    write(built, "full")


def write(built, mode):
    out = os.path.join(os.path.dirname(__file__), "..", "site", "cs2")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "matches.json"), "w", encoding="utf8") as file:
        json.dump(built, file, ensure_ascii=False, separators=(",", ":"))
    states = [m["state"] for m in built["matches"]]
    print(f"cs2 ({mode}): {states.count('live')} live, {states.count('upcoming')} upcoming, "
          f"{states.count('finished')} finished")


if __name__ == "__main__":
    main()
