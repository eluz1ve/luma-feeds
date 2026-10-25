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
"image"}`).

PandaScore's free plan has no map names, so for running matches and those starting within the
hour the feed looks them up on [Liquipedia](https://liquipedia.net) (Counter-Strike, Valorant,
Rainbow Six, Overwatch, Rocket League and Call of Duty; a Dota 2 or LoL game is one map). When it
finds the match, a game may also carry `map` (its name), `score` (rounds or points, in the teams'
order), `picked_by` (the id of the team that picked it) or `decider: true`, and the match
carries `maps_source: "Liquipedia"` and, when Liquipedia has it, `veto` (`{"type", "team",
"map"}` in veto order; `team` is `null` for the decider). Without Liquipedia the feed is built
as before, just without them.

## Attribution

Map names, round scores, picks and vetoes come from [Liquipedia](https://liquipedia.net) and are
licensed under [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); apps showing them
credit Liquipedia. The script reads them through Liquipedia's MediaWiki API under its
[terms of use](https://liquipedia.net/api-terms-of-use): one request every two seconds over one
connection, gzip, an identifying User-Agent and no HTML pages, about 15 requests a run.
Match lists, teams, logos and lineups come from [PandaScore](https://pandascore.co).

## Setup

The API key is never stored in this repository: the workflow reads it from the
`PANDASCORE_KEY` repository secret (Settings › Secrets and variables › Actions). GitHub Pages must
use **GitHub Actions** as its source (Settings › Pages).
