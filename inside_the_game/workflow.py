"""The recap pipeline as a Microsoft Agent Framework workflow.

    RecapRequest -> [Analyst] -> Analysis -> [Narrator] -> Draft -> [Verifier] -> VerifiedRecap
                                                 ^                      |
                                                 +------ Revision ------+  (up to MAX_REWRITES)

Each executor is one step: it receives a typed message, runs its agent, and
sends the result along an edge (or yields the final output). The Verifier
either approves the draft, sends it back to the Narrator with the problems it
found, or (after MAX_REWRITES) removes the sentences that still fail.

Usage:
    python -m inside_the_game.workflow --seed 5 --style broadcaster
"""

import argparse
import asyncio
from dataclasses import dataclass, field

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, WorkflowViz, handler
from typing_extensions import Never

from inside_the_game import analyst, narrator, verifier
from inside_the_game.analyst import AnalystReport
from inside_the_game.generator import Match, generate_match
from inside_the_game.narrator import STYLE_GUIDES, Recap, Style
from inside_the_game.verifier import MAX_REWRITES, Rejection, VerifiedRecap


@dataclass
class RecapRequest:
    """Workflow input: which match to recap, and in which style."""

    match: Match
    style: Style


@dataclass
class Analysis:
    """Analyst -> Narrator: the findings to write about."""

    match: Match
    style: Style
    report: AnalystReport


@dataclass
class Draft:
    """Narrator -> Verifier: a recap to fact-check."""

    analysis: Analysis
    recap: Recap
    rewrites: int  # rewrites done so far (0 = first draft)
    rejections: list[Rejection] = field(default_factory=list)  # history from earlier drafts


@dataclass
class Revision:
    """Verifier -> Narrator: rewrite the recap, fixing these problems."""

    analysis: Analysis
    feedback: str
    rewrites: int  # number this rewrite will be
    rejections: list[Rejection] = field(default_factory=list)  # history so far


class AnalystExecutor(Executor):
    """Runs the Analyst agent and passes its findings on."""

    @handler
    async def analyse(self, request: RecapRequest, ctx: WorkflowContext[Analysis]) -> None:
        report = await analyst.analyse(request.match)
        await ctx.send_message(Analysis(match=request.match, style=request.style, report=report))


class NarratorExecutor(Executor):
    """Runs the Narrator agent: a first draft, or a rewrite after Verifier feedback."""

    @handler
    async def first_draft(self, analysis: Analysis, ctx: WorkflowContext[Draft]) -> None:
        recap = await narrator.narrate(analysis.match, analysis.report, analysis.style)
        await ctx.send_message(Draft(analysis=analysis, recap=recap, rewrites=0))

    @handler
    async def rewrite(self, revision: Revision, ctx: WorkflowContext[Draft]) -> None:
        a = revision.analysis
        recap = await narrator.narrate(a.match, a.report, a.style, feedback=revision.feedback)
        await ctx.send_message(
            Draft(analysis=a, recap=recap, rewrites=revision.rewrites, rejections=revision.rejections)
        )


class VerifierExecutor(Executor):
    """Runs the Verifier agent: approve, send back for a rewrite, or remove what still fails."""

    @handler
    async def check(self, draft: Draft, ctx: WorkflowContext[Revision, VerifiedRecap]) -> None:
        match = draft.analysis.match
        verdicts = await verifier.verify(match, draft.recap)
        all_supported = all(v.supported for v in verdicts)
        if not all_supported and draft.rewrites < MAX_REWRITES:
            await ctx.send_message(
                Revision(
                    analysis=draft.analysis,
                    feedback=verifier.feedback_for(draft.recap, verdicts),
                    rewrites=draft.rewrites + 1,
                    rejections=draft.rejections + verifier.rejections_for(draft.recap, verdicts, draft.rewrites),
                )
            )
        else:
            await ctx.yield_output(
                verifier.finalize(match, draft.recap, verdicts, draft.rewrites, draft.rejections)
            )


def build_workflow() -> Workflow:
    """Wire the executors together, including the Verifier -> Narrator rewrite loop."""
    analyst_step = AnalystExecutor(id="analyst")
    narrator_step = NarratorExecutor(id="narrator")
    verifier_step = VerifierExecutor(id="verifier")
    return (
        WorkflowBuilder(start_executor=analyst_step)
        .add_edge(analyst_step, narrator_step)
        .add_edge(narrator_step, verifier_step)
        .add_edge(verifier_step, narrator_step)
        .build()
    )


async def run_recap(match: Match, style: Style, verbose: bool = False) -> VerifiedRecap:
    """Run the whole pipeline for one match and return the verified recap."""
    result: VerifiedRecap | None = None
    async for event in build_workflow().run(RecapRequest(match=match, style=style), stream=True):
        if verbose and event.type == "executor_invoked":
            label = event.executor_id
            if isinstance(event.data, Revision):
                label += f" (rewrite {event.data.rewrites})"
            print(f"  [{label}]")
        if event.type == "output":
            result = event.data
    if result is None:
        raise RuntimeError("Workflow finished without producing a recap")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the recap workflow on a synthetic match.")
    parser.add_argument("--seed", type=int, default=1, help="which synthetic match")
    parser.add_argument("--style", choices=list(STYLE_GUIDES), default="broadcaster")
    parser.add_argument("--diagram", action="store_true", help="print the workflow as a Mermaid diagram and exit")
    args = parser.parse_args()

    if args.diagram:
        print(WorkflowViz(build_workflow()).to_mermaid())
        return

    match = generate_match(args.seed)
    score = match.score()
    print(f"{match.home_team} {score['Home']}-{score['Away']} {match.away_team} ({args.style})")
    result = asyncio.run(run_recap(match, args.style, verbose=True))
    recap = result.recap
    print(f"\n# {recap.headline.text}\n")
    for sentence in recap.sentences:
        print(f"{sentence.text}\n    events {sentence.event_ids}  tools {sentence.tools}")
    print(f"\nRewrites: {result.rewrites}")
    for rejection in result.rejections:
        print(f"Rejected in draft {rejection.draft}: {rejection.text!r}\n    because: {rejection.problem}")
    for removed in result.removed:
        print(f"Removed: {removed.text!r}\n    because: {removed.problem}")


if __name__ == "__main__":
    main()
