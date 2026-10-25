# luma-feeds

Data feeds for the [Luma](https://github.com/eluz1ve/lg-luma) TV launcher, published to GitHub
Pages every 15 minutes by `.github/workflows/publish.yml`.

- `esports/<game>.json` — running and upcoming matches with lineups for `csgo`, `dota2`, `lol`,
  `valorant`, `r6siege`, `ow`, `rl` and `codmw`. Built by `scripts/esports.py` from PandaScore with
  the `PANDASCORE_KEY` repository secret.

Each file: `{"game", "updated", "matches": [{"id", "running", "begin_at", "teams": [{"id",
"name", "short"} | null], "score", "best_of", "games": [{"position", "state", "winner"}],
"event", "tier", "lineups": [[names], [names]]}]}`.
