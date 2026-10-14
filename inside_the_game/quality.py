"""Quality numbers: what the Verifier caught across every saved recap and live commentary.

Counts come straight from the saved results (code, not AI): how many recaps
passed on the first draft, how many claims the Verifier sent back (wrong facts
vs wording problems like leaked ids or missing comparisons), and how many
sentences were finally removed because they couldn't be proven.

Usage:
    python -m inside_the_game.quality          # a readable summary
    python -m inside_the_game.quality --json   # the same numbers as JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter

from pydantic import BaseModel

from inside_the_game.live import LiveCommentary
from inside_the_game.verifier import MISSING_COMPARISON, Rejection, VerifiedRecap


class QualityReport(BaseModel):
    recaps: int
    sentences_published: int  # headlines included
    sentences_with_events: int  # backed by specific match events (the rest by stats)
    first_draft_passed: int  # recaps the Verifier approved without a rewrite
    rewrites: int
    claims_caught: int  # sentences sent back for a rewrite
    caught_facts: int  # ...because a fact didn't match the evidence
    caught_wording: int  # ...because of wording (leaked ids, untranslated text, unnamed comparisons)
    caught_missing_comparison: int  # ...because the recap ignored the similar-moments search
    sentences_removed: int  # still unproven after the last rewrite, so never shown
    by_language: dict[str, int]
    by_style: dict[str, int]
    live_runs: int
    live_comments: int
    live_rewrites: int
    live_removed: int


def kind_of(rejection: Rejection) -> str:
    """Why the Verifier (or a code check) sent a sentence back."""
    if rejection.problem == MISSING_COMPARISON:
        return "missing_comparison"
    if rejection.problem.startswith("Wording:"):
        return "wording"
    return "facts"


def summarize(recaps: list[VerifiedRecap], live: list[LiveCommentary]) -> QualityReport:
    """The quality numbers for a set of saved recaps and live runs."""
    kinds = Counter(kind_of(r) for result in recaps for r in result.rejections)
    sentences = [s for result in recaps for s in [result.recap.headline, *result.recap.sentences]]
    comments = [line for run in live for line in run.lines]
    return QualityReport(
        recaps=len(recaps),
        sentences_published=len(sentences),
        sentences_with_events=sum(bool(s.event_ids) for s in sentences),
        first_draft_passed=sum(result.rewrites == 0 for result in recaps),
        rewrites=sum(result.rewrites for result in recaps),
        claims_caught=sum(kinds.values()),
        caught_facts=kinds["facts"],
        caught_wording=kinds["wording"],
        caught_missing_comparison=kinds["missing_comparison"],
        sentences_removed=sum(len(result.removed) for result in recaps),
        by_language=dict(Counter(result.recap.language for result in recaps)),
        by_style=dict(Counter(result.recap.style for result in recaps)),
        live_runs=len(live),
        live_comments=sum(len(line.sentences) for line in comments),
        live_rewrites=sum(line.rewrites for line in comments),
        live_removed=sum(len(line.removed) for line in comments),
    )


def describe(q: QualityReport) -> str:
    """A short readable summary, the way it's quoted in the README."""
    return "\n".join(
        [
            f"{q.recaps} verified recaps, {q.sentences_published} published sentences "
            f"({q.sentences_with_events} linked to specific match events, the rest to stats).",
            f"First draft approved: {q.first_draft_passed} of {q.recaps} recaps; {q.rewrites} rewrites in total.",
            f"Claims the Verifier sent back: {q.claims_caught} "
            f"({q.caught_facts} wrong or unsupported facts, {q.caught_wording} wording problems, "
            f"{q.caught_missing_comparison} recaps missing a comparison).",
            f"Sentences removed because they stayed unproven: {q.sentences_removed}.",
            f"Languages: {q.by_language}. Personas: {q.by_style}.",
            f"Live: {q.live_runs} runs, {q.live_comments} verified comments, {q.live_rewrites} rewrites, "
            f"{q.live_removed} sentences removed.",
        ]
    )


async def load() -> tuple[list[VerifiedRecap], list[LiveCommentary]]:
    from inside_the_game.store import Store  # needs COSMOS_* settings

    async with Store() as store:
        recaps = [VerifiedRecap.model_validate(doc) async for doc in store.recaps.query_items("SELECT * FROM c")]
        live = [LiveCommentary.model_validate(doc) async for doc in store.commentary.query_items("SELECT * FROM c")]
    return recaps, live


def main() -> None:
    parser = argparse.ArgumentParser(description="What the Verifier caught across all saved recaps.")
    parser.add_argument("--json", action="store_true", help="print the numbers as JSON")
    args = parser.parse_args()
    report = summarize(*asyncio.run(load()))
    print(json.dumps(report.model_dump(), indent=2) if args.json else describe(report))


if __name__ == "__main__":
    main()
