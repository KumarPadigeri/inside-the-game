"""Live mode: replay a match minute by minute, as if its events were arriving now.

Each match minute the feed ingests that minute's events, recomputes the stats
on everything so far (the same deterministic tools the Analyst uses), and
detects key moments: goals, counterattacks, half-time and full-time. Nothing
from later in the match is ever used.

For each moment a commentator (the Commentator agent, or a saved run being
replayed) can add one or two verified sentences. Everything is emitted as
timed, machine-readable messages, ready to drive on-screen overlays:

    tick        every minute: the minute's events, score and running stats
    moment      a key moment was detected (kind, team, event_ids)
    commentary  verified sentences about a moment, with their evidence
    done        the final whistle

Usage:
    python -m inside_the_game.live --seed 2 --speed 0.3            # stats only, no AI
    python -m inside_the_game.live --seed 2 --commentary [--save]  # with the agents
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, replace
from typing import Any, Literal

from pydantic import BaseModel

from inside_the_game import stats
from inside_the_game.analyst import AnalystReport, Finding, build_tools
from inside_the_game.generator import Match, Team, generate_match
from inside_the_game.narrator import LANGUAGES, STYLE_GUIDES, Language, RecapSentence, Style
from inside_the_game.verifier import RemovedSentence

HALF_TIME_MINUTE = 45  # the second half kicks off at minute 45
MAX_PARALLEL_COMMENTARY = 2  # moments being commented on at once (keeps model load and cost down)

MomentKind = Literal["goal", "counterattack", "half-time", "full-time"]


class LiveMoment(BaseModel):
    """A key moment, detected by code from the events so far."""

    key: str  # stable id within the match, e.g. "goal-198", "counterattack-47"
    kind: MomentKind
    minute: int
    team: Team | None = None  # None for half-time and full-time
    event_ids: list[int] = []


class Commentary(BaseModel):
    """Verified sentences about one moment, with the evidence as of that minute."""

    moment: LiveMoment
    sentences: list[RecapSentence]  # only sentences that passed the Verifier
    stats: dict[str, Any]  # tool results at that minute: the evidence behind stats-based sentences
    rewrites: int = 0
    removed: list[RemovedSentence] = []


class LiveCommentary(BaseModel):
    """A whole live run's commentary, saved so it can be replayed without the agents."""

    style: Style
    language: Language = "en"
    lines: list[Commentary]


# A commentator turns (the match so far, a moment) into commentary, or None to stay quiet.
Commentator = Callable[[Match, LiveMoment], Awaitable[Commentary | None]]


# --- the match so far (pure, no AI) ----------------------------------------


def match_until(match: Match, minute: int) -> Match:
    """The match as it stood at the end of `minute`: only events up to then."""
    return replace(match, events=[e for e in match.events if e.minute <= minute])


def tool_results(match: Match) -> dict[str, Any]:
    """The Analyst's tool results, computed on (part of) a match."""
    return {t.name: t.func() for t in build_tools(match)}


def tick(match_so_far: Match, minute: int) -> dict[str, Any]:
    """The per-minute overlay message: this minute's events and the running stats."""
    possession = stats.possession(match_so_far)
    shots = stats.shots(match_so_far)
    return {
        "minute": minute,
        "score": match_so_far.score(),
        "possession": {team: possession[team]["percent"] for team in possession},
        "passes_completed": {team: possession[team]["passes_completed"] for team in possession},
        "shots": {team: shots[team]["total"] for team in shots},
        "on_target": {team: shots[team]["on_target"] for team in shots},
        "events": [asdict(e) for e in match_so_far.events if e.minute == minute],
    }


def detect_moments(match_so_far: Match, seen: set[str]) -> list[LiveMoment]:
    """Goals and counterattacks completed so far that are not in `seen` (which is updated).

    A counterattack that ended in a goal is reported once, as the goal.
    """
    found: list[LiveMoment] = []
    for goal in stats.goals(match_so_far):
        found.append(
            LiveMoment(
                key=f"goal-{goal['event_id']}",
                kind="goal",
                minute=goal["minute"],
                team=goal["team"],
                event_ids=goal["buildup_event_ids"],
            )
        )
    for counter in stats.counterattacks(match_so_far):
        if counter["outcome"] != "goal":
            found.append(
                LiveMoment(
                    key=f"counterattack-{counter['possession_id']}",
                    kind="counterattack",
                    minute=counter["minute"],
                    team=counter["team"],
                    event_ids=counter["event_ids"],
                )
            )
    new = [m for m in found if m.key not in seen]
    seen.update(m.key for m in new)
    return sorted(new, key=lambda m: (m.minute, m.event_ids[-1] if m.event_ids else 0))


def _name(match: Match, team: Team) -> str:
    return match.home_team if team == "Home" else match.away_team


def _scoreline(match: Match, score: dict[str, int]) -> str:
    return f"{match.home_team} {score['Home']}-{score['Away']} {match.away_team}"


def moment_findings(match_so_far: Match, moment: LiveMoment, minute: int) -> AnalystReport:
    """Numbered facts about a moment and the match so far, written by code from the tools.

    Live commentary can't wait for the Analyst agent, so code writes the
    findings; the Commentator explains them and the Verifier checks them.
    """
    m = match_so_far
    findings: list[Finding] = []
    goals = stats.goals(m)
    counters = {c["possession_id"]: c for c in stats.counterattacks(m)}

    if moment.kind == "goal":
        goal = next(g for g in goals if moment.key == f"goal-{g['event_id']}")
        home, away = (int(n) for n in goal["score_after"].split("-"))
        findings.append(
            Finding(
                claim=f"{goal['player']} scored for {_name(m, goal['team'])} in minute {goal['minute']}, "
                f"making it {_scoreline(m, {'Home': home, 'Away': away})}.",
                tool="get_goals",
                event_ids=goal["buildup_event_ids"],
            )
        )
        possession_id = next(e.possession_id for e in m.events if e.event_id == goal["event_id"])
        if possession_id in counters:
            c = counters[possession_id]
            findings.append(
                Finding(
                    claim=f"The goal came from a counterattack: {_name(m, c['team'])} won the ball with "
                    f"{'a tackle' if c['won_by'] == 'tackle' else 'an interception'} in its own half "
                    f"and scored after {c['passes']} passes.",
                    tool="get_counterattacks",
                    event_ids=c["event_ids"],
                )
            )
        earlier = [g for g in goals if g["event_id"] < goal["event_id"]]
        if earlier:
            findings.append(
                Finding(
                    claim="Earlier goals: "
                    + "; ".join(f"{g['player']} in minute {g['minute']} ({g['score_after']})" for g in earlier)
                    + " (scores in home-away order).",
                    tool="get_goals",
                    event_ids=[g["event_id"] for g in earlier],
                )
            )
    elif moment.kind == "counterattack":
        c = next(c for c in counters.values() if moment.key == f"counterattack-{c['possession_id']}")
        findings.append(
            Finding(
                claim=f"{_name(m, c['team'])} counterattacked in minute {c['minute']}: won the ball with "
                f"{'a tackle' if c['won_by'] == 'tackle' else 'an interception'} in its own half, "
                f"then shot after {c['passes']} passes; the shot was {c['outcome']}.",
                tool="get_counterattacks",
                event_ids=c["event_ids"],
            )
        )
    else:
        findings.append(
            Finding(
                claim=f"{'Half-time' if moment.kind == 'half-time' else 'Full-time'}: "
                f"{_scoreline(m, m.score())}.",
                tool="get_match_info",
                event_ids=[],
            )
        )
        if goals:
            findings.append(
                Finding(
                    claim="Goals: "
                    + "; ".join(
                        f"{g['player']} ({_name(m, g['team'])}) in minute {g['minute']}, {g['score_after']}"
                        for g in goals
                    )
                    + " (scores in home-away order).",
                    tool="get_goals",
                    event_ids=[g["event_id"] for g in goals],
                )
            )

    # Context for every moment: where the match stands right now.
    if moment.kind in ("goal", "counterattack"):
        findings.append(
            Finding(claim=f"After {minute} minutes: {_scoreline(m, m.score())}.", tool="get_match_info", event_ids=[])
        )
    possession = stats.possession(m)
    shots = stats.shots(m)
    findings.append(
        Finding(
            claim=f"Possession so far (share of passes): {m.home_team} {possession['Home']['percent']}%, "
            f"{m.away_team} {possession['Away']['percent']}%.",
            tool="get_possession",
            event_ids=[],
        )
    )
    findings.append(
        Finding(
            claim=f"Shots so far: {m.home_team} {shots['Home']['total']} ({shots['Home']['on_target']} on target), "
            f"{m.away_team} {shots['Away']['total']} ({shots['Away']['on_target']} on target).",
            tool="get_shots",
            event_ids=[],
        )
    )
    if moment.kind in ("half-time", "full-time"):
        by_team = {t: sum(c["team"] == t for c in counters.values()) for t in ("Home", "Away")}
        findings.append(
            Finding(
                claim=f"Counterattacks so far: {m.home_team} {by_team['Home']}, {m.away_team} {by_team['Away']}.",
                tool="get_counterattacks",
                event_ids=[],
            )
        )
    return AnalystReport(findings=findings)


# --- the live feed ------------------------------------------------------------


async def run_live(
    match: Match, commentator: Commentator | None = None, seconds_per_minute: float = 1.0
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Play the match minute by minute, yielding (message type, data) overlay messages.

    The clock never waits for the commentator: commentary is written in the
    background and sent as soon as it is ready, a little after its moment.
    """
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    limit = asyncio.Semaphore(MAX_PARALLEL_COMMENTARY)
    tasks: set[asyncio.Task[None]] = set()

    async def comment(match_so_far: Match, moment: LiveMoment) -> None:
        assert commentator is not None
        try:
            async with limit:
                line = await commentator(match_so_far, moment)
        except Exception:  # noqa: BLE001 - one failed comment must not stop the match
            logging.exception("Commentary failed for %s", moment.key)
            return
        if line and line.sentences:
            await queue.put(("commentary", line.model_dump()))

    def announce(match_so_far: Match, moment: LiveMoment) -> None:
        queue.put_nowait(("moment", moment.model_dump()))
        if commentator:
            tasks.add(asyncio.create_task(comment(match_so_far, moment)))

    async def play() -> None:
        seen: set[str] = set()
        last_minute = match.events[-1].minute if match.events else 0
        for minute in range(last_minute + 1):
            so_far = match_until(match, minute)
            await queue.put(("tick", tick(so_far, minute)))
            for moment in detect_moments(so_far, seen):
                announce(so_far, moment)
            if minute == HALF_TIME_MINUTE - 1:
                announce(so_far, LiveMoment(key="half-time", kind="half-time", minute=minute))
            await asyncio.sleep(seconds_per_minute)
        announce(match, LiveMoment(key="full-time", kind="full-time", minute=last_minute))
        await asyncio.gather(*tasks)
        await queue.put(("done", {"minute": last_minute, "score": match.score()}))
        await queue.put(None)

    player = asyncio.create_task(play())
    try:
        while (message := await queue.get()) is not None:
            yield message
        await player  # re-raise anything that went wrong in the feed
    finally:
        player.cancel()
        for task in tasks:
            task.cancel()


def replay_commentator(saved: LiveCommentary) -> Commentator:
    """A commentator that replays a saved run: no agents, no cost."""
    by_key = {line.moment.key: line for line in saved.lines}

    async def replay(match_so_far: Match, moment: LiveMoment) -> Commentary | None:
        return by_key.get(moment.key)

    return replay


def collect(lines: list[dict[str, Any]], style: Style, language: Language) -> LiveCommentary:
    """Gather the commentary messages of a run, in match order, for saving."""
    parsed = sorted((Commentary.model_validate(line) for line in lines), key=lambda c: c.moment.minute)
    return LiveCommentary(style=style, language=language, lines=parsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Play a synthetic match live, minute by minute.")
    parser.add_argument("--seed", type=int, default=2, help="which synthetic match")
    parser.add_argument("--speed", type=float, default=0.2, help="seconds per match minute")
    parser.add_argument("--commentary", action="store_true", help="run the Commentator and Verifier agents")
    parser.add_argument("--style", choices=list(STYLE_GUIDES), default="broadcaster")
    parser.add_argument("--language", choices=list(LANGUAGES), default="en")
    parser.add_argument("--save", action="store_true", help="save the commentary to Cosmos DB")
    args = parser.parse_args()

    match = generate_match(args.seed)
    print(f"{match.home_team} v {match.away_team}")

    # Use the imported module, not this __main__ copy, so its classes match the Commentator's.
    from inside_the_game import live

    async def run() -> None:
        commentator: Commentator | None = None
        if args.commentary:
            from inside_the_game.commentator import make_commentator

            commentator = make_commentator(args.style, args.language)
        lines: list[dict[str, Any]] = []
        async for kind, data in live.run_live(match, commentator, args.speed):
            if kind == "tick" and data["minute"] % 15 == 0:
                print(f"  {data['minute']:>2}'  score {data['score']}  shots {data['shots']}  possession {data['possession']}")
            elif kind == "moment":
                print(f"  {data['minute']:>2}'  MOMENT {data['kind']} {data['team'] or ''}")
            elif kind == "commentary":
                lines.append(data)
                for sentence in data["sentences"]:
                    print(f"       >> {sentence['text']}")
            elif kind == "done":
                print(f"  full time {data['score']}")
        if args.save and lines:
            from inside_the_game.store import Store

            async with Store() as store:
                await store.save_commentary(match.match_id, live.collect(lines, args.style, args.language))
            print("Saved the commentary to Cosmos DB")

    asyncio.run(run())


if __name__ == "__main__":
    main()
