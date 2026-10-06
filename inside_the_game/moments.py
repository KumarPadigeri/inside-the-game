"""Key moments: goals and counterattacks, described in plain text for vector search.

Each moment's description is written by code from its events (no AI), then
embedded with the Foundry embedding model and stored in the Cosmos DB
`moments` container, so similar moments can be found across matches.
Descriptions never mention teams, so similarity is about how the play
happened, not who was playing.

Usage:
    python -m inside_the_game.moments --count 30          # index matches 1-30
    python -m inside_the_game.moments --similar match_005-p227
"""

from __future__ import annotations

import argparse
import asyncio
from itertools import groupby
from typing import Literal

from pydantic import BaseModel

from inside_the_game.generator import Event, Match, Team, generate_match
from inside_the_game.stats import COUNTER_MAX_PASSES

MomentKind = Literal["goal", "counterattack", "counterattack goal"]


class Moment(BaseModel):
    moment_id: str  # "<match_id>-p<possession_id>"
    match_id: str
    home_team: str
    away_team: str
    team: Team
    kind: MomentKind
    minute: int
    score_before: str  # Home-Away
    score_after: str  # Home-Away
    description: str
    event_ids: list[int]


def _phase(minute: int) -> str:
    if minute < 15:
        return "early in the first half"
    if minute < 45:
        return "in the first half"
    if minute < 60:
        return "early in the second half"
    if minute < 75:
        return "in the second half"
    if minute < 90:
        return "late in the game"
    return "in stoppage time"


def _start(first: Event) -> str:
    if first.type == "kickoff":
        return "from a kickoff"
    if first.type in ("tackle", "interception"):
        if first.x < 25:
            where = "deep in its own half"
        elif first.x < 50:
            where = "in its own half"
        else:
            where = "high in the opponent's half"
        article = "an" if first.type == "interception" else "a"
        return f"after winning the ball with {article} {first.type} {where}"
    return "from a goal kick" if first.x < 15 else "from open play"


def _shot(shot: Event) -> str:
    if shot.x >= 94:
        distance = "from close range"
    elif shot.x >= 83:
        distance = "from inside the box"
    else:
        distance = "from outside the box"
    angle = "a central position" if abs(shot.y - 50) <= 15 else "a wide angle"
    return f"shot {distance}, from {angle}"


def _goal_effect(team: Team, before: dict[str, int], after: dict[str, int]) -> str:
    other = "Away" if team == "Home" else "Home"
    diff_before = before[team] - before[other]
    diff_after = after[team] - after[other]
    if diff_after == 0:
        return "that made the score level"
    if diff_before == 0:
        return "that put the team ahead"
    if diff_before > 0:
        return "that extended the lead"
    return "that pulled one back while still trailing"


def _state(team: Team, score: dict[str, int]) -> str:
    other = "Away" if team == "Home" else "Home"
    diff = score[team] - score[other]
    return "with the score level" if diff == 0 else "while leading" if diff > 0 else "while trailing"


def extract_moments(match: Match) -> list[Moment]:
    """Every goal and counterattack in a match, with a code-written description."""
    moments: list[Moment] = []
    score = {"Home": 0, "Away": 0}
    for possession_id, group in groupby(match.events, key=lambda e: e.possession_id):
        events = list(group)
        first, last = events[0], events[-1]
        if last.type != "shot":
            continue
        passes = sum(e.type == "pass" for e in events)
        is_goal = last.outcome == "goal"
        is_counter = (
            first.type in ("tackle", "interception") and first.x < 50 and passes <= COUNTER_MAX_PASSES
        )
        if not (is_goal or is_counter):
            continue

        before = dict(score)
        if is_goal:
            score[last.team] += 1
        kind: MomentKind = "counterattack goal" if is_goal and is_counter else "goal" if is_goal else "counterattack"
        # Most distinctive facts first (timing, game state, outcome), so they weigh
        # more in the embedding than the shared sentence template.
        outcome = _goal_effect(last.team, before, score) if is_goal else f"that ended with the shot {last.outcome}"
        description = (
            f"{_phase(last.minute).capitalize()}, minute {last.minute}, {_state(last.team, before)}: "
            f"a {kind} {outcome}. "
            f"The attack started {_start(first)}, then {passes} pass{'es' if passes != 1 else ''} "
            f"before a {_shot(last)}."
        )
        moments.append(
            Moment(
                moment_id=f"{match.match_id}-p{possession_id}",
                match_id=match.match_id,
                home_team=match.home_team,
                away_team=match.away_team,
                team=last.team,
                kind=kind,
                minute=last.minute,
                score_before=f"{before['Home']}-{before['Away']}",
                score_after=f"{score['Home']}-{score['Away']}",
                description=description,
                event_ids=[e.event_id for e in events],
            )
        )
    return moments


async def index_matches(seeds: range) -> None:
    """Generate matches, embed their moments, and store both in Cosmos DB."""
    from inside_the_game.foundry import embed_texts
    from inside_the_game.store import Store

    async with Store() as store:
        for seed in seeds:
            match = generate_match(seed)
            moments = extract_moments(match)
            vectors = await embed_texts([m.description for m in moments])
            await store.save_match(match)
            for moment, vector in zip(moments, vectors):
                await store.save_moment(moment, vector)
            print(f"{match.match_id}: {len(moments)} moments indexed")


async def show_similar(moment_id: str) -> None:
    from inside_the_game.store import Store

    async with Store() as store:
        moment = await store.get_moment(moment_id)
        if moment is None:
            raise SystemExit(f"No moment {moment_id!r}; index matches first.")
        print(f"{moment.moment_id} ({moment.minute}'): {moment.description}\n")
        for similar in await store.similar_moments(moment_id, top_k=3):
            print(f"  {similar['similarity']:.3f}  {similar['moment_id']} ({similar['minute']}'): {similar['description']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Index key moments for vector search, or query them.")
    parser.add_argument("--count", type=int, default=30, help="number of matches to index")
    parser.add_argument("--seed", type=int, default=1, help="seed of the first match")
    parser.add_argument("--similar", metavar="MOMENT_ID", help="show the moments most similar to this one")
    args = parser.parse_args()
    if args.similar:
        asyncio.run(show_similar(args.similar))
    else:
        asyncio.run(index_matches(range(args.seed, args.seed + args.count)))


if __name__ == "__main__":
    main()
