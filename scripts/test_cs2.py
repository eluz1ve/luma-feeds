"""Tests of the Counter-Strike 2 feed. Run: python3 -m unittest scripts/test_cs2.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import cs2  # noqa: E402
import mode  # noqa: E402

NOW = 1_793_400_000


def opponent(name, short, score=-1, players=()):
    return {"name": name, "score": score,
            "teamtemplate": {"name": name, "shortname": short},
            "match2players": [{"name": p, "displayname": p, "flag": "France"} for p in players]}


def item(match_id, begins, finished=0, **extra):
    base = {
        "match2id": match_id, "date": "2026-10-30 21:00:00", "dateexact": 1,
        "finished": finished, "winner": "", "bestof": 3, "tournament": "NSTLGA Texas Open 2026",
        "tickername": "", "section": "Group B", "liquipediatier": "4",
        "extradata": {"timestamp": begins, "hidden": False},
        "match2opponents": [opponent("Sutti's Money Crew", "SMC"), opponent("OG", "OG")],
        "match2games": [{}],
    }
    base.update(extra)
    return base


class Feed(unittest.TestCase):
    def test_states_order_and_fields(self):
        live = item("live", NOW - 600, match2opponents=[
            opponent("Vitality", "VIT", 1), opponent("FaZe Clan", "FaZe", 0)],
            match2games=[{"map": "Mirage", "scores": [13, 9], "winner": "1"},
                         {"map": "Inferno", "scores": [4, 6], "winner": ""}, {"map": "TBD"}],
            tickername="IEM Chengdu", liquipediatier="1")
        soon = item("soon", NOW + 3600)
        later = item("later", NOW + 7200)
        done = item("done", NOW - 9000, finished=1, winner="2", match2opponents=[
            opponent("NAVI", "NAVI", 0), opponent("G2 Esports", "G2", 2)])
        built = cs2.feed([later, live, soon], [done], NOW)
        self.assertEqual([m["id"] for m in built["matches"]], ["live", "soon", "later", "done"])
        first = built["matches"][0]
        self.assertEqual(first["state"], "live")
        self.assertEqual(first["tournament"], "IEM Chengdu")
        self.assertEqual(first["tier"], 1)
        self.assertEqual(first["score"], [1, 0])
        self.assertEqual(first["teams"][1], {"name": "FaZe Clan", "short": "FaZe", "image": None})
        self.assertEqual(first["maps"], [
            {"map": "Mirage", "score": [13, 9], "winner": 0},
            {"map": "Inferno", "score": [4, 6], "winner": None}])
        self.assertEqual(built["matches"][1]["score"], None, "upcoming has no score")
        self.assertEqual(built["matches"][3]["winner"], 1)
        self.assertEqual(built["source"], "Liquipedia")
        self.assertEqual(built["updated"], NOW)

    def test_hidden_duplicate_and_malformed_matches_are_dropped(self):
        hidden = item("hidden", NOW + 60, extradata={"timestamp": NOW + 60, "hidden": True})
        undated = item("undated", NOW, date="soon", extradata={})
        solo = item("solo", NOW + 60, match2opponents=[opponent("OG", "OG")])
        tbd = item("tbd", NOW + 60, match2opponents=[
            {"name": "TBD", "score": -1}, opponent("OG", "OG")])
        built = cs2.feed([hidden, undated, solo, tbd, tbd], [], NOW)
        self.assertEqual([m["id"] for m in built["matches"]], ["tbd"])
        self.assertEqual(built["matches"][0]["teams"][0], None)

    def test_date_without_timestamp_is_utc(self):
        entry = cs2.match(item("x", 0, extradata={}, date="2026-10-30 21:00:00"), NOW)
        self.assertEqual(entry["begin_at"], "2026-10-30T21:00:00Z")

    def test_results_are_capped_and_newest_first(self):
        results = [item(f"r{i}", NOW - 3600 - i * 60, finished=1) for i in range(15)]
        built = cs2.feed([], results, NOW)
        ids = [m["id"] for m in built["matches"]]
        self.assertEqual(len(ids), cs2.RESULT_COUNT)
        self.assertEqual(ids[0], "r0")


    def test_major_events_are_kept_within_the_cap(self):
        small = [item(f"s{i}", NOW + 60 + i, liquipediatier="4") for i in range(cs2.MAX_MATCHES)]
        big = item("major", NOW + 5 * 24 * 3600, liquipediatier="1")
        ids = [m["id"] for m in cs2.feed(small + [big], [], NOW)["matches"]]
        self.assertEqual(len(ids), cs2.MAX_MATCHES)
        self.assertEqual(ids[-1], "major", "kept, and still in start order")


    def test_markup_is_removed_from_names(self):
        seed = cs2.match(item("seed", NOW + 60, match2opponents=[
            opponent("Group B 2<sup>nd", "Group B 2<sup>nd"), opponent("OG", "OG")]), NOW)
        self.assertEqual(seed["teams"][0], {"name": "Group B 2nd", "short": "Group B 2nd", "image": None})


    def test_lineups_come_from_the_match(self):
        entry = cs2.match(item("x", NOW + 60, match2opponents=[
            opponent("Vitality", "VIT", players=["apEX", "ZywOo", ""]), opponent("OG", "OG")]), NOW)
        self.assertEqual(entry["lineups"][0],
                         [{"name": "apEX", "flag": "France"}, {"name": "ZywOo", "flag": "France"}])
        self.assertEqual(entry["lineups"][1], [])


    def test_logos_prefer_dark_and_skip_placeholders(self):
        base = "https://liquipedia.net/commons/images/thumb/a/ab/"
        real = {"name": "Vitality", "teamtemplate": {
            "name": "Team Vitality", "shortname": "VIT",
            "image": "Vitality lightmode.png", "imageurl": base + "light.png",
            "imagedark": "Vitality darkmode.png", "imagedarkurl": base + "dark.png"}}
        placeholder = {"name": "YHTR", "teamtemplate": {
            "name": "YHTR", "imagedark": "Counter-Strike 2 default darkmode.png",
            "imagedarkurl": base + "default.png", "image": "Counter-Strike 2 default lightmode.png",
            "imageurl": base + "default-light.png"}}
        elsewhere = {"name": "X", "teamtemplate": {"name": "X", "imagedark": "x.png",
                                                    "imagedarkurl": "https://example.com/x.png"}}
        self.assertEqual(cs2.team(real)["image"], base + "dark.png")
        self.assertIsNone(cs2.team(placeholder)["image"])
        self.assertIsNone(cs2.team(elsewhere)["image"])


    def test_a_live_run_refreshes_started_matches_and_keeps_the_rest(self):
        previous = cs2.feed([item("live", NOW - 600), item("ahead", NOW + 3600),
                             item("started", NOW - 120 + 0, )],
                            [item("old", NOW - 9000, finished=1, winner="1")], NOW - 120)
        previous["full_at"] = NOW - 300
        # "started" was upcoming a run ago; "live" has just finished.
        started = [item("live", NOW - 600, finished=1, winner="2", match2opponents=[
                       opponent("NAVI", "NAVI", 0), opponent("G2", "G2", 2)]),
                   item("started", NOW - 60)]
        built = cs2.refresh(previous, started, NOW)
        states = {m["id"]: m["state"] for m in built["matches"]}
        self.assertEqual(states, {"started": "live", "ahead": "upcoming",
                                  "live": "finished", "old": "finished"})
        self.assertEqual(built["full_at"], NOW - 300, "a live run keeps the full run's time")
        self.assertEqual(built["updated"], NOW)

    def test_full_runs_come_every_ten_minutes(self):
        self.assertEqual(mode.due(None, NOW), (True, NOW))
        self.assertEqual(mode.due({"full_at": NOW - 120}, NOW), (False, NOW - 120))
        self.assertEqual(mode.due({"full_at": NOW - 560}, NOW), (True, NOW))
        self.assertEqual(mode.due({"full_at": "x"}, NOW), (True, NOW))


if __name__ == "__main__":
    unittest.main()
