"""Synthetic football match generator.

Creates fake match events (no real teams, players or data) by simulating a
match as a series of possessions. The same seed always produces the same match.

Coordinates: x and y run from 0 to 100. x is measured from the acting team's
own goal (0) toward the opponent's goal (100), so a shot always has a high x.
When the ball changes teams, the position is mirrored (x -> 100 - x).

Usage:
    python -m inside_the_game.generator --count 5 --seed 1 --out data/matches
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Team = Literal["Home", "Away"]

EVENT_OUTCOMES: dict[str, set[str]] = {
    "kickoff": {"complete"},
    "pass": {"complete", "incomplete"},
    "shot": {"goal", "saved", "missed", "blocked"},
    "tackle": {"won"},
    "interception": {"won"},
}

# Fictional club names only: never real Premier League clubs.
FICTIONAL_TEAMS: list[str] = [
    "Northbridge FC",
    "Riverside Athletic",
    "Eastmoor United",
    "Kingsford Rovers",
    "Ashvale Town",
    "Harbourside City",
    "Westfield Wanderers",
    "Oakhurst Albion",
]

# Shirt numbers by role: 1 = goalkeeper, 2-5 defenders, 6-8 midfield, 9-11 forwards.
_DEFENDERS = [2, 3, 4, 5]
_MIDFIELDERS = [6, 7, 8]
_FORWARDS = [9, 10, 11]

_HALF_SECONDS = 45 * 60


@dataclass
class Event:
    """One thing that happened on the pitch."""

    event_id: int
    minute: int
    team: Team
    player: str
    type: str
    x: int
    y: int
    outcome: str
    possession_id: int


@dataclass
class Match:
    """A full synthetic match: metadata plus its ordered list of events."""

    match_id: str
    seed: int
    home_team: str
    away_team: str
    events: list[Event] = field(default_factory=list)

    def score(self) -> dict[str, int]:
        """Goals per side, counted from the shot events."""
        goals = {"Home": 0, "Away": 0}
        for event in self.events:
            if event.type == "shot" and event.outcome == "goal":
                goals[event.team] += 1
        return goals

    def to_dict(self) -> dict[str, Any]:
        """Plain dict, ready for JSON."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Match:
        """Rebuild a Match from the dict produced by to_dict()."""
        events = [Event(**event) for event in data["events"]]
        return cls(
            match_id=data["match_id"],
            seed=data["seed"],
            home_team=data["home_team"],
            away_team=data["away_team"],
            events=events,
        )


def _other(team: Team) -> Team:
    return "Away" if team == "Home" else "Home"


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


class _MatchSimulator:
    """Runs the possession-by-possession simulation for one match."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.events: list[Event] = []
        self.clock = 0.0  # seconds since kickoff
        self.possession_id = 0
        # Each side gets a hidden "quality" so matches are not all identical.
        self.quality: dict[Team, float] = {
            "Home": self.rng.uniform(-0.04, 0.06),  # small home advantage
            "Away": self.rng.uniform(-0.05, 0.05),
        }
        self.full_time = 2 * _HALF_SECONDS + self.rng.randint(60, 300)

    # --- helpers -------------------------------------------------------

    def _player(self, team: Team, x: float, shooting: bool = False) -> str:
        """Pick a plausible player for this pitch position."""
        if shooting:
            pool = self.rng.choices([_FORWARDS, _MIDFIELDERS], weights=[0.75, 0.25])[0]
        elif x < 20:
            pool = self.rng.choices([[1], _DEFENDERS], weights=[0.3, 0.7])[0]
        elif x < 45:
            pool = self.rng.choices([_DEFENDERS, _MIDFIELDERS], weights=[0.6, 0.4])[0]
        elif x < 70:
            pool = self.rng.choices([_MIDFIELDERS, _DEFENDERS, _FORWARDS], weights=[0.6, 0.2, 0.2])[0]
        else:
            pool = self.rng.choices([_FORWARDS, _MIDFIELDERS], weights=[0.55, 0.45])[0]
        prefix = "H" if team == "Home" else "A"
        return f"{prefix}{self.rng.choice(pool)}"

    def _add(self, team: Team, player: str, type_: str, x: float, y: float, outcome: str) -> None:
        self.events.append(
            Event(
                event_id=len(self.events) + 1,
                minute=int(self.clock // 60),
                team=team,
                player=player,
                type=type_,
                x=round(_clamp(x)),
                y=round(_clamp(y)),
                outcome=outcome,
                possession_id=self.possession_id,
            )
        )

    def _shot_chance(self, x: float) -> float:
        """Chance the team shoots now instead of passing again."""
        if x >= 88:
            return 0.2
        if x >= 80:
            return 0.12
        if x >= 72:
            return 0.04
        return 0.0

    def _goal_probability(self, team: Team, x: float, y: float) -> float:
        """A simple expected-goals idea: closer and more central = better."""
        closeness = _clamp((x - 70) / 30, 0, 1)
        centrality = 1 - abs(y - 50) / 50
        return 0.02 + 0.32 * closeness**2 * centrality + self.quality[team] * 0.15

    # --- simulation ----------------------------------------------------

    def _play_possession(
        self, team: Team, x: float, y: float, start: str | None
    ) -> tuple[Team, float, float, str | None]:
        """Simulate one possession. Returns who starts the next one, where, and how.

        `start` is the event that begins it: "kickoff", "tackle" or
        "interception". None means a goal kick, which simply starts with a pass.
        """
        self.possession_id += 1
        if start == "kickoff":
            self._add(team, self._player(team, x), "kickoff", x, y, "complete")
        elif start is not None:
            self._add(team, self._player(team, x), start, x, y, "won")

        # Winning the ball in your own half sometimes triggers a fast break:
        # a few quick, long, forward passes before the defence can recover.
        won_ball = start in ("tackle", "interception")
        fast_break_passes = 3 if won_ball and x < 50 and self.rng.random() < 0.3 else 0

        opponent = _other(team)
        while True:
            fast_break = fast_break_passes > 0
            self.clock += self.rng.uniform(1.5, 3) if fast_break else self.rng.uniform(2.5, 7)

            # 1. Shoot?
            if self.rng.random() < self._shot_chance(x):
                shooter = self._player(team, x, shooting=True)
                if self.rng.random() < self._goal_probability(team, x, y):
                    self._add(team, shooter, "shot", x, y, "goal")
                    self.clock += self.rng.uniform(45, 90)  # celebration
                    return opponent, 50, 50, "kickoff"
                outcome = self.rng.choices(["saved", "missed", "blocked"], weights=[0.35, 0.4, 0.25])[0]
                self._add(team, shooter, "shot", x, y, outcome)
                self.clock += self.rng.uniform(15, 40)
                if outcome == "blocked" and self.rng.random() < 0.5:
                    # Defender blocks and wins the ball near their own goal.
                    return opponent, 100 - x, 100 - y, "interception"
                # Saved or missed: keeper restarts from their own box.
                return opponent, self.rng.uniform(5, 12), self.rng.uniform(30, 70), None

            # 2. Get tackled while on the ball?
            tackle_risk = 0.04 + 0.08 * (x / 100) - self.quality[team] * 0.2
            if self.rng.random() < tackle_risk:
                return opponent, 100 - x, 100 - y, "tackle"

            # 3. Pass: harder the further forward you are.
            passer = self._player(team, x)
            success = 0.92 - 0.3 * (x / 100) + self.quality[team]
            forward = self.rng.gauss(18, 7) if fast_break else self.rng.gauss(7, 11)
            fast_break_passes -= 1
            target_x = _clamp(x + forward, 2, 99)
            target_y = _clamp(y + self.rng.gauss(0, 18), 2, 98)
            if self.rng.random() < success:
                self._add(team, passer, "pass", x, y, "complete")
                x, y = target_x, target_y
            else:
                self._add(team, passer, "pass", x, y, "incomplete")
                return opponent, 100 - target_x, 100 - target_y, "interception"

    def run(self) -> list[Event]:
        """Play the whole match and return its events."""
        first_kickoff: Team = self.rng.choice(["Home", "Away"])
        team: Team = first_kickoff
        x, y = 50.0, 50.0
        start: str | None = "kickoff"
        second_half_started = False

        while self.clock < self.full_time:
            if not second_half_started and self.clock >= _HALF_SECONDS:
                second_half_started = True
                self.clock = _HALF_SECONDS
                team, x, y, start = _other(first_kickoff), 50.0, 50.0, "kickoff"

            team, x, y, start = self._play_possession(team, x, y, start)
        return self.events


def generate_match(seed: int, match_id: str | None = None) -> Match:
    """Generate one synthetic match. The same seed always gives the same match."""
    rng = random.Random(seed)
    home, away = rng.sample(FICTIONAL_TEAMS, 2)
    events = _MatchSimulator(seed).run()
    return Match(
        match_id=match_id or f"match_{seed:03d}",
        seed=seed,
        home_team=home,
        away_team=away,
        events=events,
    )


def save_match(match: Match, out_dir: Path) -> Path:
    """Write a match to <out_dir>/<match_id>.json and return the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{match.match_id}.json"
    path.write_text(json.dumps(match.to_dict(), indent=1))
    return path


def load_match(path: Path) -> Match:
    """Read a match JSON file written by save_match()."""
    return Match.from_dict(json.loads(path.read_text()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic football matches.")
    parser.add_argument("--count", type=int, default=5, help="number of matches")
    parser.add_argument("--seed", type=int, default=1, help="seed of the first match")
    parser.add_argument("--out", type=Path, default=Path("data/matches"), help="output folder")
    args = parser.parse_args()

    for seed in range(args.seed, args.seed + args.count):
        match = generate_match(seed)
        path = save_match(match, args.out)
        score = match.score()
        print(
            f"{path}: {match.home_team} {score['Home']}-{score['Away']} {match.away_team}"
            f" ({len(match.events)} events)"
        )


if __name__ == "__main__":
    main()
