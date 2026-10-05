"""Verifier agent: fact-checks every recap sentence against its own evidence.

For each sentence the Verifier sees only the raw evidence linked to it: the
tool results it cites and the events behind its event_ids. It never sees the
Analyst's findings, so mistakes by either earlier agent get caught.

If sentences fail, the workflow sends them back to the Narrator for a rewrite.
After MAX_REWRITES, finalize() drops whatever is still unsupported, so nothing
unverified reaches the reader.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from pydantic import BaseModel, Field

from inside_the_game.analyst import build_tools
from inside_the_game.foundry import make_client
from inside_the_game.generator import Match
from inside_the_game.narrator import Recap, RecapSentence

MAX_REWRITES = 2

INSTRUCTIONS = """\
You are a careful football fact-checker. For each numbered sentence of a match
recap you get the evidence linked to it: tool results and match events.

For each sentence, first write your reasoning: list every factual detail in
it (teams, players, minutes, scores, counts, percentages, order of events,
how a goal or attack happened) and check each one against ITS OWN evidence.
Only then decide. Do not use evidence from other sentences or outside knowledge.

A sentence is UNSUPPORTED only if a factual detail is wrong, or is not shown
by its evidence. Check every number against the full tool result: if a tool
lists five counterattacks, "three counterattacks" is wrong.

These are fine and must NOT be rejected:
- Style and emotion ("a thrilling win", "they never gave up").
- Ordinary football phrasing that follows directly from the facts: "equaliser"
  when the goal made the score level, "won it" or "settled it" for the goal
  that made the final score, "turned it around" for going from behind to ahead.
- Scores from either team's point of view: "the visitors led 2-1" is the same
  as a 1-2 score in Home-Away order.
- Mild interpretation that the numbers clearly back ("dominated possession"
  with 65%), but not when they don't ("dominated" with 51%).

Event fields: x and y are 0-100; x is measured from the acting team's own
goal (0) toward the goal it attacks (100), so x < 50 is the team's own half.
minute counts from 0; the second half starts at minute 45. Goal scores in
tool results (score_after) are in Home-Away order.

For an unsupported sentence, state in "problem" exactly what is wrong and what
the evidence actually shows.
"""


class SentenceVerdict(BaseModel):
    # Field order matters: the model writes its reasoning before deciding.
    sentence: int = Field(description="The sentence number (0 = headline).")
    reasoning: str = Field(default="", description="Each factual detail checked against the evidence.")
    supported: bool
    problem: str = Field(default="", description="If unsupported: what is wrong and what the evidence shows.")


class VerifierOutput(BaseModel):
    verdicts: list[SentenceVerdict]


class RemovedSentence(BaseModel):
    text: str
    problem: str


class Rejection(BaseModel):
    """A sentence the Verifier sent back to the Narrator."""

    draft: int  # 0 = first draft, 1 = first rewrite, ...
    text: str
    problem: str


class VerifiedRecap(BaseModel):
    """The workflow's final output: a recap where every sentence passed the Verifier."""

    recap: Recap
    rewrites: int  # how many times the Narrator had to rewrite
    rejections: list[Rejection]  # what the Verifier sent back along the way
    removed: list[RemovedSentence]  # sentences still unsupported after the last rewrite


def numbered_sentences(recap: Recap) -> list[RecapSentence]:
    """Headline is sentence 0, then the body sentences from 1."""
    return [recap.headline, *recap.sentences]


def build_prompt(match: Match, recap: Recap) -> str:
    """Each sentence with only its own evidence: cited tool results and events."""
    tool_results: dict[str, Any] = {t.name: t.func() for t in build_tools(match)}
    events = {e.event_id: asdict(e) for e in match.events}
    blocks = [f"Home team: {match.home_team}. Away team: {match.away_team}."]
    for number, sentence in enumerate(numbered_sentences(recap)):
        evidence = {
            "tool_results": {name: tool_results[name] for name in sentence.tools if name in tool_results},
            "events": [events[i] for i in sentence.event_ids if i in events],
        }
        blocks.append(f"Sentence {number}: {sentence.text}\nEvidence: {json.dumps(evidence)}")
    return "\n\n".join(blocks)


def normalize_verdicts(output: VerifierOutput, recap: Recap) -> list[SentenceVerdict]:
    """Exactly one verdict per sentence, in order. A missing verdict counts as unsupported."""
    by_number = {v.sentence: v for v in output.verdicts}
    return [
        by_number.get(n) or SentenceVerdict(sentence=n, supported=False, problem="The Verifier gave no verdict.")
        for n in range(len(numbered_sentences(recap)))
    ]


def feedback_for(recap: Recap, verdicts: list[SentenceVerdict]) -> str:
    """The rejected sentences and their problems, for the Narrator's rewrite."""
    sentences = numbered_sentences(recap)
    return "\n".join(
        f'- {"Headline" if v.sentence == 0 else f"Sentence {v.sentence}"}: '
        f'"{sentences[v.sentence].text}" -> {v.problem}'
        for v in verdicts
        if not v.supported
    )


def rejections_for(recap: Recap, verdicts: list[SentenceVerdict], draft: int) -> list[Rejection]:
    """The unsupported sentences of one draft, to keep as rewrite history."""
    sentences = numbered_sentences(recap)
    return [
        Rejection(draft=draft, text=sentences[v.sentence].text, problem=v.problem) for v in verdicts if not v.supported
    ]


def finalize(
    match: Match,
    recap: Recap,
    verdicts: list[SentenceVerdict],
    rewrites: int,
    rejections: list[Rejection] | None = None,
) -> VerifiedRecap:
    """Keep only supported sentences. A failed headline becomes the plain scoreline."""
    removed: list[RemovedSentence] = []
    headline = recap.headline
    if not verdicts[0].supported:
        removed.append(RemovedSentence(text=headline.text, problem=verdicts[0].problem))
        score = match.score()
        headline = RecapSentence(
            text=f"{match.home_team} {score['Home']}-{score['Away']} {match.away_team}",
            finding_ids=[],
            event_ids=[],
            tools=["get_match_info"],
        )
    kept: list[RecapSentence] = []
    for sentence, verdict in zip(recap.sentences, verdicts[1:]):
        if verdict.supported:
            kept.append(sentence)
        else:
            removed.append(RemovedSentence(text=sentence.text, problem=verdict.problem))
    return VerifiedRecap(
        recap=Recap(style=recap.style, headline=headline, sentences=kept),
        rewrites=rewrites,
        rejections=rejections or [],
        removed=removed,
    )


def make_verifier(client: FoundryChatClient | None = None) -> Agent:
    """Create the Verifier agent (no tools: all evidence is in the prompt)."""
    return Agent(
        client=client or make_client(),
        name="Verifier",
        instructions=INSTRUCTIONS,
        default_options={"response_format": VerifierOutput},
    )


async def verify(match: Match, recap: Recap) -> list[SentenceVerdict]:
    """Run the Verifier and return one verdict per sentence (headline first)."""
    response = await make_verifier().run(build_prompt(match, recap))
    output = response.value
    if output is None:
        raise ValueError(f"Verifier returned no structured verdicts: {response.text!r}")
    return normalize_verdicts(output, recap)
