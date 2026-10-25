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
"image"}`). Map names, picks and in-game statistics are not part of the free plan.

## Setup

The API key is never stored in this repository: the workflow reads it from the
`PANDASCORE_KEY` repository secret (Settings › Secrets and variables › Actions). GitHub Pages must
use **GitHub Actions** as its source (Settings › Pages).
