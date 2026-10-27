"""Tests of the esports feed's Liquipedia lineups. Run: python3 -m unittest scripts/test_esports.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import esports  # noqa: E402

TOURNAMENT = """
==Participants==
{{TeamParticipants
|{{Opponent|FaZe Clan
|players={{Persons
|{{Person|broky|flag=lv}}
|{{Person|karrigan|flag=dk}}
|{{Person|frozen}}
|{{Person|jcobbb|flag=pl}}
|{{Person|Twistzz}}
|{{Person|rain|status=sub}}
|{{Person|role=coach|GruBy|flag=pl}}
}}
}}
|{{Opponent|Imported
|import=true
|players={{Persons
|{{Person|alpha}}
}}
}}
}}
"""


def pandascore(name, real="", nationality="", image=None):
    return {"name": name, "real_name": real, "nationality": nationality, "role": "",
            "age": None, "image": image}


class LiquipediaLineups(unittest.TestCase):
    def test_participants_keep_their_shown_names_flags_and_roles(self):
        faze = esports.lp_rosters(TOURNAMENT)[0]
        self.assertEqual([p["name"] for p in faze["people"]],
                         ["broky", "karrigan", "frozen", "jcobbb", "Twistzz", "rain", "GruBy"])
        self.assertEqual(faze["people"][0]["flag"], "lv")
        self.assertEqual([p["kind"] for p in faze["people"]][-2:], ["bench", "coach"])
        self.assertEqual(len(faze["starters"]), 5)

    def test_a_lineup_comes_from_liquipedia_with_pandascore_details(self):
        faze = esports.lp_rosters(TOURNAMENT)[0]
        listed = [
            pandascore("karrigan", "Finn Andersen", "DK", "https://cdn-api.pandascore.co/k.png"),
            pandascore("broky", "Helvijs Saukants", "LV"),
            pandascore("ropz", "Robin Kool", "EE"),  # left the team; PandaScore still lists him
            pandascore("frozen", "David Čerňanský", "SK"),
            pandascore("Twistzz", "Russel Van Dulken", "CA"),
        ]
        lineup = esports.lp_lineup(listed, faze, 5)
        self.assertEqual([p["name"] for p in lineup],
                         ["broky", "karrigan", "frozen", "jcobbb", "Twistzz", "rain", "GruBy"])
        karrigan = lineup[1]
        self.assertEqual((karrigan["real_name"], karrigan["nationality"], karrigan["image"]),
                         ("Finn Andersen", "DK", "https://cdn-api.pandascore.co/k.png"))
        # Only on Liquipedia: the flag stands in for the nationality.
        self.assertEqual((lineup[3]["real_name"], lineup[3]["nationality"]), ("", "PL"))
        self.assertEqual([p.get("substitute", False) for p in lineup],
                         [False] * 5 + [True, True])
        self.assertEqual(lineup[6]["role"], "coach")

    def test_an_incomplete_roster_leaves_pandascores_lineup(self):
        imported = esports.lp_rosters(TOURNAMENT)[1]
        self.assertIsNone(esports.lp_lineup([pandascore("alpha")], imported, 5))

    def test_a_paired_match_takes_liquipedias_lineup_and_names_its_source(self):
        class Wiki:
            requests = 0

            def query(self, wiki, **params):
                self.requests += 1
                return {"query": {"pages": [{"title": "PGL/2026/Bucharest", "revisions": [
                    {"slots": {"main": {"content": TOURNAMENT}}}]}]}}

        m = {"teams": [{"name": "FaZe Clan", "short": "FaZe"}, {"name": "Imported", "short": "IMP"}],
             "lineups": [[pandascore("karrigan"), pandascore("ropz")], [pandascore("alpha")]]}
        paired = [(m, {"teams": ["FaZe Clan", "Imported"], "page": "PGL/2026/Bucharest"}, False)]
        self.assertEqual(esports.lineups("counterstrike", paired, {}, {}, Wiki()), 1)
        self.assertEqual(m["lineups_source"], ["Liquipedia", ""])
        self.assertEqual(len(m["lineups"][0]), 7)
        self.assertNotIn("ropz", [p["name"] for p in m["lineups"][0]])
        self.assertEqual(m["lineups"][1], [pandascore("alpha")])


if __name__ == "__main__":
    unittest.main()
