"""Narrator agent: writes a match recap from the Analyst's findings.

The Narrator sees findings numbered 1, 2, 3... (without event_ids) and cites
those numbers for every sentence it writes. Code then maps each sentence to
the event_ids behind its findings, so evidence links can never be invented.

Usage:
    python -m inside_the_game.narrator --seed 5 --style fan
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Literal

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from pydantic import BaseModel, Field

from inside_the_game.analyst import AnalystReport, analyse
from inside_the_game.foundry import make_client
from inside_the_game.generator import Match, generate_match
from inside_the_game.moments import SIMILAR_MOMENTS_TOOL

Style = Literal["fan", "analyst", "broadcaster"]

STYLE_GUIDES: dict[Style, str] = {
    "fan": "Write as a passionate supporter of the winning team (or the home team after a draw): "
    "emotional, vivid, proud, but still factual.",
    "analyst": "Write as a calm tactical analyst: precise, measured, focused on why things happened.",
    "broadcaster": "Write as a TV broadcaster wrapping up the match: lively, balanced between both teams.",
}

INSTRUCTIONS = """\
You are a football writer. You turn numbered findings about a match into a
short recap: one headline and 4-7 sentences.

Rules:
- Use only facts from the findings. Never add numbers, players, minutes or
  events that are not in them. Style may change the words, never the facts.
- Don't add details a finding doesn't state: no rankings or firsts ("best",
  "first", "only", "biggest") and no extra description of how a move happened
  ("short build-up", "high up the pitch") unless the finding says so.
- Every sentence (and the headline) must cite ALL the findings whose facts it
  uses in finding_ids; a fact from an uncited finding counts as unsupported.
  A sentence with no supporting finding is not allowed.
- Refer to players by their ids exactly as given (e.g. H9), never by a bare
  team letter ("H" or "A").
- Never mention pitch coordinates (x, y), event or match ids, or other data
  field names; describe positions in words ("in its own half").
- One idea per sentence, at most 35 words. In a comparison, name at most two
  other matches.
- Findings marked "about": "other matches" compare this match with similar
  moments elsewhere. If there are any, include at least one of them, and
  name the other match exactly as the finding writes it, keeping home and away
  in the same order (e.g. "as in Westfield Wanderers v Oakhurst Albion").
- When giving a score, make clear which team leads (e.g. "put the visitors 2-1 up").
"""


class NarratedSentence(BaseModel):
    text: str = Field(description="One sentence of the recap.")
    finding_ids: list[int] = Field(min_length=1, description="Numbers of the findings this sentence relies on.")


class NarratorOutput(BaseModel):
    headline: NarratedSentence
    sentences: list[NarratedSentence]


class RecapSentence(BaseModel):
    text: str
    finding_ids: list[int]
    # Evidence, resolved by code from the cited findings:
    event_ids: list[int]  # specific moments (goals, counterattacks, ...)
    tools: list[str]  # tool results backing counts and percentages


class Recap(BaseModel):
    style: Style
    headline: RecapSentence
    sentences: list[RecapSentence]


def build_prompt(match: Match, report: AnalystReport, style: Style, feedback: str | None = None) -> str:
    """The message sent to the Narrator: style, teams and numbered findings (no event_ids).

    `feedback` is the Verifier's list of problems, when asking for a rewrite.
    """
    findings = [
        {"id": i, "claim": f.claim, **({"about": "other matches"} if f.tool == SIMILAR_MOMENTS_TOOL else {})}
        for i, f in enumerate(report.findings, start=1)
    ]
    prompt = (
        f"Style: {STYLE_GUIDES[style]}\n"
        f"Home team: {match.home_team}. Away team: {match.away_team}.\n"
        f"Findings:\n{json.dumps(findings, indent=1)}"
    )
    if feedback:
        prompt += (
            "\n\nA fact-checker rejected some sentences of your previous recap:\n"
            f"{feedback}\n"
            "Write the full recap again. Keep the sentences that passed, and fix or drop the rejected ones."
        )
    return prompt


def resolve_recap(output: NarratorOutput, report: AnalystReport, style: Style) -> Recap:
    """Attach the real evidence (event_ids and tools) to each sentence, via the findings it cites."""

    def resolve(sentence: NarratedSentence) -> RecapSentence:
        event_ids: set[int] = set()
        tools: list[str] = []
        for finding_id in sentence.finding_ids:
            if not 1 <= finding_id <= len(report.findings):
                raise ValueError(f"Sentence cites finding {finding_id}, which does not exist: {sentence.text!r}")
            finding = report.findings[finding_id - 1]
            event_ids.update(finding.event_ids)
            if finding.tool not in tools:
                tools.append(finding.tool)
        # Sorted, so the UI can show the evidence in match order.
        return RecapSentence(
            text=sentence.text, finding_ids=sentence.finding_ids, event_ids=sorted(event_ids), tools=tools
        )

    return Recap(
        style=style,
        headline=resolve(output.headline),
        sentences=[resolve(s) for s in output.sentences],
    )


def make_narrator(client: FoundryChatClient | None = None) -> Agent:
    """Create the Narrator agent (it has no tools: it only writes)."""
    return Agent(
        client=client or make_client(),
        name="Narrator",
        instructions=INSTRUCTIONS,
        default_options={"response_format": NarratorOutput},
    )


async def narrate(match: Match, report: AnalystReport, style: Style, feedback: str | None = None) -> Recap:
    """Run the Narrator and return a recap with evidence attached to every sentence."""
    response = await make_narrator().run(build_prompt(match, report, style, feedback))
    output = response.value
    if output is None:
        raise ValueError(f"Narrator returned no structured recap: {response.text!r}")
    return resolve_recap(output, report, style)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse a synthetic match, then narrate it.")
    parser.add_argument("--seed", type=int, default=1, help="which synthetic match")
    parser.add_argument("--style", choices=list(STYLE_GUIDES), default="broadcaster")
    args = parser.parse_args()

    match = generate_match(args.seed)

    async def run() -> Recap:
        report = await analyse(match)
        return await narrate(match, report, args.style)

    recap = asyncio.run(run())
    print(f"# {recap.headline.text}\n")
    for sentence in recap.sentences:
        print(f"{sentence.text}\n    findings {sentence.finding_ids} -> events {sentence.event_ids}")


if __name__ == "__main__":
    main()
