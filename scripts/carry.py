"""Copies the published esports files into site/ on runs that do not rebuild them."""
import os
import sys
import urllib.error
import urllib.request

SITE = "https://eluz1ve.github.io/luma-feeds/"
GAMES = ["csgo", "dota2", "lol", "valorant", "r6siege", "ow", "rl", "codmw"]


def main():
    out = os.path.join(os.path.dirname(__file__), "..", "site", "esports")
    os.makedirs(out, exist_ok=True)
    missing = 0
    for game in GAMES:
        try:
            with urllib.request.urlopen(f"{SITE}esports/{game}.json", timeout=20) as response:
                body = response.read(4 * 1024 * 1024)
        except (urllib.error.URLError, OSError) as error:
            missing += 1
            print(f"{game}: {error}", file=sys.stderr)
            continue
        with open(os.path.join(out, f"{game}.json"), "wb") as file:
            file.write(body)
    print(f"esports: carried {len(GAMES) - missing} of {len(GAMES)}")


if __name__ == "__main__":
    main()
