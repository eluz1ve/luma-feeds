# luma-feeds

Test data feeds for the [Luma](https://github.com/eluz1ve/lg-luma) TV launcher, published to
GitHub Pages every 15 minutes by `.github/workflows/publish.yml`.

> [!IMPORTANT]
> These feeds are provided **for testing only**. For personal use, sign up at
> [pandascore.co](https://pandascore.co) (free) and enter your own access token in Luma's esports
> widget settings; with your own key the widget also shows live scores.

## Feeds

- `esports/<game>.json` — running and upcoming matches with lineups for `csgo`, `dota2`, `lol`,
  `valorant`, `r6siege`, `ow`, `rl` and `codmw`, built by `scripts/esports.py` from the PandaScore
  API.

Each file: `{"game", "updated", "matches": [...]}`. A match: `id`, `running`, `begin_at`,
`teams` (two of `{"id", "name", "short", "image", "location"}` or `null`), `score`, `best_of`,
`games` (`{"position", "state", "winner", "begin_at", "length"}`), `event`, `league_image`,
`stage`, `tier`, `prizepool`, `online`, `streams` (`{"language", "platform", "official",
"main"}`) and `lineups` (two lists of `{"name", "real_name", "nationality", "role", "age",
"image"}`, up to ten people; from PandaScore, a team's whole active roster).

PandaScore's free plan has no map names, so for running matches and those starting within the
hour the feed looks them up on [Liquipedia](https://liquipedia.net) (Counter-Strike, Valorant,
Rainbow Six, Overwatch, Rocket League and Call of Duty; a Dota 2 or LoL game is one map). When it
finds the match, a game may also carry `map` (its name), `score` (rounds or points, in the teams'
order), `picked_by` (the id of the team that picked it) or `decider: true`, and the match
carries `maps_source: "Liquipedia"` and, when Liquipedia has it, `veto` (`{"type", "team",
"map"}` in veto order; `team` is `null` for the decider).

The tournament's participants on Liquipedia also give the lineups. When Liquipedia lists a team's
whole roster for the tournament, its lineup is Liquipedia's: the starters, then the substitutes
and coaches (`substitute: true`, a coach's `role` is `"coach"`), each with PandaScore's real name,
nationality, age and photo when PandaScore lists the same nickname (else the Liquipedia flag as
nationality); players PandaScore still lists who left the team are not in it, and the match
carries `lineups_source` (`["Liquipedia", ""]` per side). When Liquipedia lists only part of the
roster, the lineup stays PandaScore's with the people Liquipedia names as substitutes or coaches
marked. Valorant's matches on their own Match: pages name no tournament, so they go without.
Without Liquipedia the feed is built as before, just without them.

- `cs2/matches.json` — Counter-Strike 2's live, upcoming (three days ahead) and latest finished
  matches from [LiquipediaDB](https://api.liquipedia.net), built by `scripts/cs2.py`. The file:
  `{"game", "source", "license", "updated" (Unix seconds), "matches": [...]}`. A match: `id`, `begin_at` (UTC),
  `exact` (whether the time is confirmed), `state` (`live`, `upcoming` or `finished`), `best_of`,
  `tournament`, `stage`, `tier` (Liquipedia's 1–5, 1 the biggest), `teams` (two of `{"name",
  "short"}` or `null` while unknown), `lineups` (two lists of `{"name", "flag"}`, the players
  Liquipedia lists for the match, possibly empty), `score` (maps won, from the start), `winner` (0 or 1 once
  finished) and `maps` (`{"map", "score", "winner"}` in play order; rounds when Liquipedia has
  them). Live matches come first, then upcoming ones by start, then the ten latest results; at
  most 80, keeping Liquipedia's tier 1 and 2 matches (listed a week ahead) before smaller ones.
  Three LiquipediaDB requests a run, 12 an hour of its 60.

## Attribution

Map names, round scores, picks, vetoes and lineups marked as Liquipedia's come from
[Liquipedia](https://liquipedia.net) and are licensed under
[CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); apps showing them credit
Liquipedia. The script reads them through Liquipedia's MediaWiki API under its
[terms of use](https://liquipedia.net/api-terms-of-use): one request every two seconds over one
connection, gzip, an identifying User-Agent and no HTML pages, about 15–20 requests a run.
Match lists, teams, logos, photos and the other lineups come from
[PandaScore](https://pandascore.co). The Counter-Strike 2 feed comes entirely from LiquipediaDB, read with
`LIQUIPEDIA_KEY` under the same terms (CC-BY-SA 3.0, credit Liquipedia).

## Setup

The API keys are never stored in this repository: the workflow reads them from the
`PANDASCORE_KEY` and `LIQUIPEDIA_KEY` repository secrets (Settings › Secrets and variables › Actions). GitHub Pages must
use **GitHub Actions** as its source (Settings › Pages).
