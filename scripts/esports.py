"""Builds Luma's esports feed: running and upcoming matches with lineups for each discipline.

Reads PANDASCORE_KEY from the environment and writes site/esports/<game>.json. Uses about 25
requests per run (two match lists and one teams list per discipline), well inside the free plan's
1000 requests an hour at one run every 15 minutes. Only what the free plan lists comes from
PandaScore; map names, round scores, picks and lineups of live matches come from Liquipedia
(see maps()).
"""
import calendar
import gzip
import http.client
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.pandascore.co"
IMAGES = "https://cdn-api.pandascore.co/"
GAMES = ["csgo", "dota2", "lol", "valorant", "r6siege", "ow", "rl", "codmw"]
PER_GAME = 20

# Liquipedia's MediaWiki API: at most one request every 2 seconds over one connection, gzip, an
# identifying User-Agent, no action=parse and no HTML pages. Its content is CC-BY-SA 3.0.
LIQUIPEDIA = "liquipedia.net"
USER_AGENT = "luma-feeds/1.0 (https://github.com/eluz1ve/luma-feeds)"
INTERVAL = 2.2
# Liquipedia's share of a run, so the feed stays inside its 15 minutes.
BUDGET = 240
# The wiki of each discipline played on several maps; a Dota 2 or LoL game has a single map.
WIKIS = {"csgo": "counterstrike", "valorant": "valorant", "r6siege": "rainbowsix",
         "ow": "overwatch", "rl": "rocketleague", "codmw": "callofduty"}
# How many players a team starts a game with on each wiki.
STARTING = {"counterstrike": 5, "valorant": 5, "rainbowsix": 5, "overwatch": 5,
            "rocketleague": 3, "callofduty": 4}
# Upcoming matches this close to their start may already have their maps picked.
SOON = 3600
# Hours from UTC of the zones Liquipedia writes after match times, e.g. {{Abbr/CEST}}.
ZONES = {"utc": 0, "gmt": 0, "wet": 0, "bst": 1, "west": 1, "cet": 1, "cest": 2, "eet": 2,
         "sast": 2, "eest": 3, "msk": 3, "trt": 3, "ast": 3, "eat": 3, "gst": 4, "pkt": 5,
         "ist": 5.5, "ict": 7, "wib": 7, "sgt": 8, "pht": 8, "hkt": 8, "awst": 8, "jst": 9,
         "kst": 9, "aest": 10, "aedt": 11, "nzst": 12, "nzdt": 13, "brt": -3, "art": -3,
         "clt": -4, "edt": -4, "est": -5, "cdt": -5, "cst": -6, "mdt": -6, "mst": -7,
         "pdt": -7, "pst": -8}
MONTHS = {name: number for number, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], 1)}
# Words team names are written with or without, e.g. "FURIA Esports" and "FURIA".
FILLER = re.compile(r"\b(e-?sports?|gaming|team|club|clan|gg)\b")
# Roles of a team's staff on Liquipedia, e.g. {{Person|role=Head Coach|type=staff}}.
STAFF = re.compile(r"coach|analyst|manager|director|psycholog|staff|owner|founder|ceo", re.I)


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


class Liquipedia:
    """Liquipedia's MediaWiki API over one connection, one request every INTERVAL seconds."""

    def __init__(self, budget=BUDGET):
        self.connection = None
        self.last = 0.0
        self.deadline = time.monotonic() + budget
        self.requests = 0
        # Set when Liquipedia refuses or throttles: no more requests this run.
        self.stopped = False

    def query(self, wiki, **params):
        if self.stopped or time.monotonic() > self.deadline:
            raise TimeoutError("Liquipedia is done for this run")
        wait = self.last + INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        params.update(format="json", formatversion="2")
        path = f"/{wiki}/api.php?" + urllib.parse.urlencode(params)
        if self.connection is None:
            self.connection = http.client.HTTPSConnection(LIQUIPEDIA, timeout=20)
        try:
            self.connection.request("GET", path, headers={
                "User-Agent": USER_AGENT, "Accept-Encoding": "gzip", "Accept": "application/json"})
            response = self.connection.getresponse()
            body = response.read()
        except (OSError, http.client.HTTPException):
            self.connection.close()
            self.connection = None
            raise
        finally:
            self.last = time.monotonic()
            self.requests += 1
        if response.status != 200:
            self.stopped = response.status in (403, 429) or response.status >= 500
            raise OSError(f"Liquipedia {wiki}: HTTP {response.status}")
        if response.getheader("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        reply = json.loads(body)
        if "error" in reply:
            raise ValueError(f"Liquipedia {wiki}: {reply['error'].get('code')}")
        return reply

    def close(self):
        if self.connection is not None:
            self.connection.close()


def balanced(source, start):
    """The end of the template opening at `start`, past its closing braces."""
    depth = 0
    index = start
    while index < len(source) - 1:
        pair = source[index:index + 2]
        if pair == "{{":
            depth += 1
            index += 2
        elif pair == "}}":
            depth -= 1
            index += 2
            if depth == 0:
                return index
        else:
            index += 1
    return None


def templates(source, names):
    """Every `{{Name ...}}` of these names in wikitext, as its text between the braces."""
    pattern = re.compile(r"\{\{\s*(?:" + "|".join(names) + r")\s*(?=[|}])", re.I)
    found = []
    for opening in pattern.finditer(source):
        end = balanced(source, opening.start())
        if end:
            found.append(source[opening.start() + 2:end - 2])
    return found


def fields(body):
    """A template's positional and named parameters, split at its own `|` only."""
    parts, depth, start = [], 0, 0
    index = 0
    while index < len(body):
        pair = body[index:index + 2]
        if pair in ("{{", "[["):
            depth += 1
            index += 2
            continue
        if pair in ("}}", "]]"):
            depth -= 1
            index += 2
            continue
        if body[index] == "|" and depth == 0:
            parts.append(body[start:index])
            start = index + 1
        index += 1
    parts.append(body[start:])
    positional, named = [], {}
    for part in parts[1:]:
        name, equals, value = part.partition("=")
        if equals and re.fullmatch(r"\s*[\w ]+\s*", name):
            named[name.strip().lower()] = value.strip()
        else:
            positional.append(part.strip())
    return positional, named


def plain(value, limit):
    """Wikitext without links' targets, templates or markup, e.g. "[[Dust II (map)|Dust II]]"."""
    value = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", value or "")
    value = re.sub(r"\{\{.*?\}\}|'{2,}|<[^>]*>", "", value)
    return " ".join(value.split())[:limit]


def number(value):
    value = (value or "").strip()
    if re.fullmatch(r"\d+", value):
        return int(value)
    if re.fullmatch(r"\d+\.\d+", value):
        return float(value)
    return None


def map_score(named):
    """Both sides' score of one map: `score1`, else the halves, e.g. CS's `t1t` and `o1t1ct`."""
    def side(team):
        direct = number(named.get(f"score{team}"))
        if direct is not None:
            return direct
        halves = [number(value) for key, value in named.items()
                  if re.fullmatch(rf"(o\d+)?t{team}(ot)?(t|ct|atk|def)", key)]
        halves = [half for half in halves if half is not None]
        return sum(halves) if halves else None

    score = [side(1), side(2)]
    return score if None not in score else None


def lp_time(value):
    """Unix seconds of a Liquipedia match date and whether it has a time of day."""
    value = value or ""
    date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if date:
        year, month, day = (int(part) for part in date.groups())
    else:
        date = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", value)
        if not date or date.group(1).lower() not in MONTHS:
            return None, False
        year, month, day = int(date.group(3)), MONTHS[date.group(1).lower()], int(date.group(2))
    clock = re.search(r"(\d{1,2}):(\d{2})", value[date.end():])
    zone = re.search(r"\{\{\s*abbr/(\w+)\s*\}\}", value, re.I)
    offset = ZONES.get(zone.group(1).lower(), 0) if zone else 0
    try:
        seconds = calendar.timegm((year, month, day, 0, 0, 0))
    except (ValueError, OverflowError):
        return None, False
    if not clock:
        return seconds, False
    return seconds + int(clock.group(1)) * 3600 + int(clock.group(2)) * 60 - int(offset * 3600), True


def opponent(value):
    """The team template or literal name of `{{TeamOpponent|navi|score=2}}`."""
    found = templates(value or "", ["TeamOpponent", "LiteralOpponent"])
    if not found:
        return ""
    positional, named = fields(found[0])
    return plain(named.get("template") or (positional[0] if positional else ""), 60)


def veto(value):
    """`{{MapVeto}}` as (kind, side, map) in veto order, side 0 for the decider."""
    found = templates(value or "", ["MapVeto"])
    if not found:
        return []
    _, named = fields(found[0])
    first = 2 if named.get("firstpick", "").strip() == "2" else 1
    kinds = [kind.strip().lower() for kind in named.get("types", "").split(",")]
    steps = []
    for row, kind in enumerate(kinds, 1):
        if kind == "decider":
            name = plain(named.get("decider"), 32)
            if name:
                steps.append(("decider", 0, name))
            continue
        for side in (first, 3 - first):
            name = plain(named.get(f"t{side}map{row}"), 32)
            if name and kind:
                steps.append((kind[:12], side, name))
    return steps


def lp_matches(source):
    """The Match2 matches of a page: `{{Match}}` in brackets and lists, `{{MatchPage}}` alone."""
    source = re.sub(r"<!--.*?-->", "", source, flags=re.S)
    found = []
    for body in templates(source, ["Match", "MatchPage"]):
        _, named = fields(body)
        teams = [opponent(named.get("opponent1")), opponent(named.get("opponent2"))]
        when, clock = lp_time(named.get("date"))
        if not all(teams) or when is None:
            continue
        steps = veto(named.get("mapveto"))
        maps = {}
        for key, value in named.items():
            position = re.fullmatch(r"map(\d+)", key)
            entry = templates(value, ["Map", "ApiMap"])
            if not position or not entry:
                continue
            _, details = fields(entry[0])
            maps[int(position.group(1))] = {
                "map": plain(details.get("map"), 32),
                "score": map_score(details),
            }
        # Maps not written yet are the picks in veto order, then the decider.
        picks = [(side, name) for kind, side, name in steps if kind in ("pick", "decider")]
        for position, (side, name) in enumerate(picks, 1):
            entry = maps.setdefault(position, {"map": "", "score": None})
            entry["map"] = entry["map"] or name
        for entry in maps.values():
            entry["side"] = next((side for side, name in picks
                                  if name.lower() == entry["map"].lower()), None)
        found.append({
            "teams": teams,
            "time": when,
            "clock": clock,
            "finished": named.get("finished", "").strip().lower() in ("true", "1", "yes"),
            "maps": maps,
            "veto": steps,
        })
    return found


def names(*values):
    """Ways a team name is written: lower-case letters and digits, with and without filler."""
    found = set()
    for value in values:
        value = unicodedata.normalize("NFKD", value or "").lower()
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        for variant in (value, FILLER.sub(" ", value)):
            variant = re.sub(r"[\W_]+", "", variant)
            if variant:
                found.add(variant)
    return found


def likeness(ours, theirs):
    """2 when a name is the same, 1 when one holds the other, else 0."""
    if ours & theirs:
        return 2
    if any(len(a) >= 3 and len(b) >= 3 and (a in b or b in a) for a in ours for b in theirs):
        return 1
    return 0


def pair(m, candidate, pages):
    """How well a Liquipedia match fits a feed match, and whether its teams are the other way."""
    ours = [names(team["name"], team["short"]) for team in m["teams"]]
    theirs = [names(name, pages.get(name.lower(), "")) for name in candidate["teams"]]
    straight = likeness(ours[0], theirs[0]), likeness(ours[1], theirs[1])
    crossed = likeness(ours[0], theirs[1]), likeness(ours[1], theirs[0])
    best = max((straight, False), (crossed, True), key=lambda option: sum(option[0]))
    (first, second), swapped = best
    if min(first, second) == 0 or first + second < 3:
        return None
    return first + second, swapped


def apply_maps(m, candidate, swapped):
    """Adds Liquipedia's map names, round scores, picks and veto to a feed match."""
    ids = [team["id"] for team in m["teams"]]
    if swapped:
        ids.reverse()
    side_id = {1: ids[0], 2: ids[1]}
    games = {game["position"]: game for game in m["games"]}
    named = False
    for position, entry in sorted(candidate["maps"].items()):
        if position > max(m["best_of"], len(m["games"])) or not (entry["map"] or entry["score"]):
            continue
        game = games.get(position)
        if game is None:
            game = {"position": position, "state": "waiting", "winner": None, "begin_at": "",
                    "length": None}
            m["games"].append(game)
        if entry["map"]:
            game["map"] = entry["map"]
            named = True
        score = entry["score"]
        if score and (any(score) or game["state"] != "waiting"):
            game["score"] = score[::-1] if swapped else score
        if entry["side"] == 0:
            game["decider"] = True
        elif entry["side"]:
            game["picked_by"] = side_id[entry["side"]]
    m["games"].sort(key=lambda game: game["position"])
    if candidate["veto"]:
        m["veto"] = [{"type": kind, "team": side_id.get(side), "map": name}
                     for kind, side, name in candidate["veto"]]
    if named:
        m["maps_source"] = "Liquipedia"
    return named


def nick(value):
    """A nickname as both sites may write it: lower-case letters and digits, no accents."""
    value = unicodedata.normalize("NFKD", value or "").lower()
    return re.sub(r"[\W_]+", "", "".join(ch for ch in value if not unicodedata.combining(ch)))


def lp_rosters(source):
    """The teams of a tournament's `{{TeamParticipants}}` with the nicknames of their starters,
    bench and coaches, each a set of the name shown and the player page's, and its people in
    that order with the name shown and their flag.

    A starter has no `status` (substitutes have `sub`, players who left `former`), is not staff
    and has not `played=false`. A team with `import=true` takes its players from Liquipedia's
    database and lists only some of them, so its roster isn't complete.
    """
    source = re.sub(r"<!--.*?-->", "", source, flags=re.S)
    rosters = []
    for block in templates(source, ["TeamParticipants"]):
        for body in templates(block, ["Opponent"]):
            positional, named = fields(body)
            team = plain(positional[0] if positional else named.get("1"), 60)
            persons = templates(named.get("players", ""), ["Persons"])
            if not team or not persons:
                continue
            starters, bench, coaches = [], [], []
            people = {"starter": [], "bench": [], "coach": []}
            for person in templates(persons[0], ["Person"]):
                given, details = fields(person)
                shown = plain(given[0] if given else details.get("1"), 24)
                handles = {nick(shown), nick(re.sub(r"\(.*\)", "", details.get("link", "")))} - {""}
                role = details.get("role", "")
                if not handles:
                    continue
                if details.get("type", "").lower() == "staff" or STAFF.search(role):
                    if "coach" not in role.lower():
                        continue
                    kind, group = "coach", coaches
                elif details.get("status") or details.get("played", "").lower() in (
                        "false", "no", "n", "0"):
                    kind, group = "bench", bench
                else:
                    kind, group = "starter", starters
                group.append(handles)
                people[kind].append({"name": shown, "flag": plain(details.get("flag", ""), 8),
                                     "kind": kind, "handles": handles})
            imported = named.get("import", "").lower() in ("true", "yes", "1")
            rosters.append({"team": team, "starters": starters, "bench": bench,
                            "coaches": coaches, "complete": not imported,
                            "people": people["starter"] + people["bench"] + people["coach"]})
    return rosters


def roster_of(team, rosters):
    """The entry of a team (a set of `names()`) among a tournament's participants, unless
    several teams fit it as well."""
    scored = [(likeness(team, names(roster["team"])), roster) for roster in rosters]
    best = max((score for score, _ in scored), default=0)
    found = [roster for score, roster in scored if score == best]
    if not best or len({nick(roster["team"]) for roster in found}) > 1:
        return None
    return found[0]


def among(players, handles, fuzzy=True):
    """The indices of feed players who are among these Liquipedia people, each found once: by
    nickname, then by one nickname holding the other ("snow" and "Snowzin")."""
    keys = [nick(player["name"]) for player in players]
    found, left = set(), list(range(len(handles)))
    for exact in (True, False) if fuzzy else (True,):
        for index, key in enumerate(keys):
            if index in found or len(key) < (1 if exact else 3):
                continue
            fits = [person for person in left if key in handles[person]] if exact else [
                person for person in left
                if any(len(handle) >= 3 and (key in handle or handle in key)
                       for handle in handles[person])]
            if len(fits) == 1:
                found.add(index)
                left.remove(fits[0])
    return found


def apply_lineup(players, roster, size):
    """A feed lineup with `substitute: true` on the players who don't start and a coach's empty
    role filled in, or None when Liquipedia doesn't tell.

    With a complete roster of at least `size` starters, of whom the lineup has all but one or
    more, everyone else in the lineup is a substitute; otherwise only those Liquipedia lists as
    substitutes, players who left or coaches are.
    """
    starters = among(players, roster["starters"])
    full = (roster["complete"] and len(roster["starters"]) >= size
            and len(starters) >= size - 1)
    coaches = among(players, roster["coaches"], fuzzy=False) - starters
    bench = among(players, roster["bench"], fuzzy=False) - starters | coaches
    if not full and not bench:
        return None
    marked = []
    for index, player in enumerate(players):
        player = dict(player)
        if index in bench or (full and index not in starters):
            player["substitute"] = True
            if index in coaches and not player["role"]:
                player["role"] = "coach"
        marked.append(player)
    return marked


def matched(players, people):
    """Liquipedia's people (by index) mapped to the feed players they are, each found once: by
    nickname, then by one nickname holding the other ("snow" and "Snowzin")."""
    keys = [nick(player["name"]) for player in players]
    found, free = {}, set(range(len(players)))
    for exact in (True, False):
        for index, person in enumerate(people):
            if index in found:
                continue
            fits = [player for player in free if keys[player] and (
                keys[player] in person["handles"] if exact else len(keys[player]) >= 3 and any(
                    len(handle) >= 3 and (keys[player] in handle or handle in keys[player])
                    for handle in person["handles"]))]
            if len(fits) == 1:
                found[index] = fits[0]
                free.discard(fits[0])
    return found


def lp_lineup(players, roster, size):
    """The team's lineup for the tournament as Liquipedia lists it: its starters, then its bench
    and coaches, each with PandaScore's details (real name, nationality, photo) when PandaScore
    lists the same person. People PandaScore lists who aren't on Liquipedia (players who left)
    are not in it. None unless Liquipedia lists the whole roster with at least `size` starters.
    """
    if not roster.get("complete") or len(roster.get("starters", [])) < size:
        return None
    people = roster["people"]
    found = matched(players, people)
    lineup = []
    for index, person in enumerate(people[:10]):
        if index in found:
            player = dict(players[found[index]])
        else:
            player = {"name": "", "real_name": "", "nationality": person["flag"].upper(),
                      "role": "", "age": None, "image": None}
        player["name"] = person["name"]
        if person["kind"] != "starter":
            player["substitute"] = True
            if person["kind"] == "coach" and not player["role"]:
                player["role"] = "coach"
        lineup.append(player)
    return lineup


def lineups(wiki, paired, rosters, pages, liquipedia):
    """Paired matches' lineups from their tournament's participants: Liquipedia's own lineup
    where it lists the whole team (`lineups_source` then names it for that side), else
    PandaScore's with its substitutes marked.

    `paired` holds (feed match, Liquipedia match, teams swapped); `rosters` the participants of
    each page read so far. A stage's page often lists none, so the pages above it are read too.
    Valorant's Match: pages don't name their tournament.
    """
    def chain(title):
        titles = [] if title.startswith("Match:") else [title]
        while titles and "/" in titles[-1] and len(titles) < 3:
            titles.append(titles[-1].rpartition("/")[0])
        return titles

    def find(titles, team):
        """The team's roster, the title to read next, or None."""
        for title in titles:
            if title not in rosters:
                return title
            roster = roster_of(team, rosters[title])
            if roster:
                return roster
        return None

    sides = []
    for m, c, swapped in paired:
        theirs = c["teams"][::-1] if swapped else c["teams"]
        for side, (team, name) in enumerate(zip(m["teams"], theirs)):
            known = names(team["name"], team["short"], name, pages.get(name.lower(), ""))
            sides.append((m, side, chain(c["page"]), known))
    for _ in range(2):
        missing = sorted({found for _, _, titles, team in sides
                          if isinstance(found := find(titles, team), str)})
        for batch in range(0, len(missing), 20):
            chunk = missing[batch:batch + 20]
            rosters.update((title, []) for title in chunk)
            params = {"action": "query", "prop": "revisions", "rvprop": "content",
                      "rvslots": "main", "titles": "|".join(chunk)}
            for _ in range(3):
                reply = liquipedia.query(wiki, **params)
                for page in reply.get("query", {}).get("pages", []):
                    for revision in page.get("revisions", []):
                        rosters[page["title"]] = lp_rosters(
                            revision.get("slots", {}).get("main", {}).get("content", ""))
                if "continue" not in reply:
                    break
                params.update(reply["continue"])
    marked = set()
    for m, side, titles, team in sides:
        roster = find(titles, team)
        if not isinstance(roster, dict):
            continue
        size = STARTING.get(wiki, 5)
        lineup = lp_lineup(m["lineups"][side], roster, size)
        if lineup:
            m["lineups"][side] = lineup
            m.setdefault("lineups_source", ["", ""])[side] = "Liquipedia"
            marked.add(id(m))
            continue
        lineup = apply_lineup(m["lineups"][side], roster, size)
        if lineup and any(player.get("substitute") for player in lineup):
            m["lineups"][side] = lineup
            marked.add(id(m))
    return len(marked)


def maps(game, matches, liquipedia, now=None):
    """Map names and lineups for running and soon-starting matches from the discipline's
    Liquipedia wiki; how many matches got map names and how many lineups.

    Recent edits on the wiki (tournament pages and Valorant's Match: pages) name the pages with
    Match2 matches; each page is read once per run, its team templates resolved to team names in
    one more request, and a match is paired by both teams and its start time. Its tournament's
    participants then give its lineups (see lineups()).
    """
    wiki = WIKIS.get(game)
    now = now or time.time()

    def start(m):
        try:
            return calendar.timegm(time.strptime(m["begin_at"][:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return None

    targets = [m for m in matches if all(m["teams"]) and start(m) is not None
               and (m["running"] or start(m) - now < SOON)]
    if not wiki or not targets:
        return 0, 0
    earliest = min(start(m) for m in targets)
    back = min(max(now - earliest + 3 * 3600, 3 * 3600), 12 * 3600)
    titles = set()
    params = {"action": "query", "generator": "recentchanges", "grcnamespace": "0|130",
              "grctoponly": 1, "grclimit": 500, "grctype": "edit|new",
              "grcend": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - back)),
              "prop": "templates", "tltemplates": "Template:Match|Template:MatchPage",
              "tllimit": "max"}
    for _ in range(4):
        reply = liquipedia.query(wiki, **params)
        titles.update(page["title"] for page in reply.get("query", {}).get("pages", [])
                      if page.get("templates"))
        if "continue" not in reply:
            break
        params.update(reply["continue"])
    candidates = []
    rosters = {}
    ordered = sorted(titles)
    for batch in range(0, len(ordered), 20):
        params = {"action": "query", "prop": "revisions", "rvprop": "content",
                  "rvslots": "main", "titles": "|".join(ordered[batch:batch + 20])}
        for _ in range(3):
            reply = liquipedia.query(wiki, **params)
            for page in reply.get("query", {}).get("pages", []):
                for revision in page.get("revisions", []):
                    content = revision.get("slots", {}).get("main", {}).get("content", "")
                    for c in lp_matches(content):
                        c["page"] = page["title"]
                        candidates.append(c)
                    rosters[page["title"]] = lp_rosters(content)
            if "continue" not in reply:
                break
            params.update(reply["continue"])
    def near(c, m):
        return abs(c["time"] - start(m)) <= (6 * 3600 if c["clock"] else 24 * 3600)

    candidates = [c for c in candidates if any(near(c, m) for m in targets)]
    # Team templates are often short ("ttg", "spirit black"): their team pages name them.
    teams = sorted({name for c in candidates for name in c["teams"]})
    pages = {}
    for batch in range(0, min(len(teams), 180), 60):
        chunk = teams[batch:batch + 60]
        reply = liquipedia.query(wiki, action="expandtemplates", prop="wikitext",
                                 text="\n".join(f"{{{{TeamPage|1={name}}}}}" for name in chunk))
        lines = reply.get("expandtemplates", {}).get("wikitext", "").strip("\n").split("\n")
        if len(lines) == len(chunk):
            pages.update((name.lower(), plain(line, 60)) for name, line in zip(chunk, lines))
    found = 0
    paired = []
    for m in targets:
        best = None
        for c in candidates:
            fit = pair(m, c, pages)
            off = abs(c["time"] - start(m))
            if not fit or not near(c, m):
                continue
            rank = (fit[0], not (m["running"] and c["finished"]), -off)
            if best is None or rank > best[0]:
                best = (rank, c, fit[1])
        if best:
            paired.append((m, best[1], best[2]))
            found += apply_maps(m, best[1], best[2])
    try:
        return found, lineups(wiki, paired, rosters, pages, liquipedia)
    except (OSError, ValueError, http.client.HTTPException) as error:
        print(f"{game}: no substitutes, {error!r}", file=sys.stderr)
        return found, 0


def main():
    key = os.environ.get("PANDASCORE_KEY", "").strip()
    if not key:
        sys.exit("PANDASCORE_KEY is not set")
    out = os.path.join(os.path.dirname(__file__), "..", "site", "esports")
    os.makedirs(out, exist_ok=True)
    failures = 0
    liquipedia = Liquipedia()
    for game in GAMES:
        try:
            feed = game_feed(game, key)
        except (urllib.error.URLError, ValueError, OSError) as error:
            failures += 1
            print(f"{game}: {error}", file=sys.stderr)
            continue
        named = subs = 0
        try:
            named, subs = maps(game, feed["matches"], liquipedia)
        except Exception as error:  # Map names are extra: the feed goes out without them.
            print(f"{game}: no map names, {error!r}", file=sys.stderr)
        with open(os.path.join(out, f"{game}.json"), "w", encoding="utf8") as file:
            json.dump(feed, file, ensure_ascii=False, separators=(",", ":"))
        print(f"{game}: {len(feed['matches'])} matches, {named} with map names, "
              f"{subs} with lineups from Liquipedia")
    liquipedia.close()
    print(f"Liquipedia: {liquipedia.requests} requests")
    if failures == len(GAMES):
        sys.exit("every discipline failed")


if __name__ == "__main__":
    main()
