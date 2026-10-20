"""Fictional squad generation (no real clubs, players, or venues).

Two paths produce `Team` objects:
1. `generate_team` - deterministic, seedable, offline. Always available.
2. `agents.squad_author` (services/agents) - a Foundry agent that writes richer teams and storylines
   and returns the same schema. Use it to extend the dataset; the engine does not care which path
   produced the squad.
"""

from __future__ import annotations

import random

from crq_schemas import Player, Team

_FIRST = ["Ade", "Bram", "Cato", "Dev", "Eli", "Finn", "Gus", "Hal", "Ivo", "Jon", "Kai", "Leo", "Mo",
          "Nik", "Oli", "Pax", "Quin", "Rafa", "Sol", "Teo", "Uli", "Vik", "Wes", "Yan", "Zed"]
_LAST = ["Arden", "Blake", "Corr", "Dale", "Ember", "Frost", "Gale", "Hart", "Ives", "Jude", "Kerr",
         "Lane", "Marsh", "North", "Oak", "Pike", "Quill", "Reed", "Stone", "Thorne", "Vale", "Wilde"]
_CLUBS = [("Harbor City", "HAR", "#0b3d91", "possession"), ("Northfield United", "NFU", "#b22222", "press"),
          ("Riverside Athletic", "RVA", "#1b7f3b", "counter"), ("Ironbridge FC", "IRB", "#444444", "direct"),
          ("Lakeshore Rovers", "LKR", "#f28c00", "possession"), ("Summit Town", "SMT", "#5a2d82", "press")]
_VENUES = ["Harbor Park", "The Northfield Ground", "Riverside Arena", "Ironbridge Stadium", "Lakeshore Bowl"]

_FORMATIONS = {"4-3-3": ["GK"] + ["DF"] * 4 + ["MF"] * 3 + ["FW"] * 3,
               "4-2-3-1": ["GK"] + ["DF"] * 4 + ["MF"] * 5 + ["FW"] * 1,
               "3-5-2": ["GK"] + ["DF"] * 3 + ["MF"] * 5 + ["FW"] * 2}


def generate_team(index: int, seed: int) -> Team:
    rng = random.Random(seed * 101 + index)
    name, short, color, style = _CLUBS[index % len(_CLUBS)]
    formation = rng.choice(list(_FORMATIONS))
    positions = _FORMATIONS[formation] + ["DF", "MF", "FW", "GK", "MF"]  # 5 bench
    players: list[Player] = []
    used: set[str] = set()
    for i, pos in enumerate(positions, start=1):
        while True:
            full = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
            if full not in used:
                used.add(full)
                break
        skill = lambda base: round(min(1.0, max(0.2, rng.gauss(base, 0.12))), 2)  # noqa: E731
        players.append(Player(
            player_id=f"{short.lower()}-{i:02d}", name=full, number=i, position=pos,  # type: ignore[arg-type]
            pace=skill(0.7 if pos == "FW" else 0.55),
            passing=skill(0.75 if pos == "MF" else 0.6),
            shooting=skill(0.7 if pos == "FW" else 0.4),
            defending=skill(0.75 if pos == "DF" else 0.45),
        ))
    return Team(team_id=short.lower(), name=name, short_name=short, primary_color=color,
                formation=formation, style=style, players=players)  # type: ignore[arg-type]


def pick_venue(seed: int) -> str:
    return _VENUES[seed % len(_VENUES)]
