"""The recap pipeline as a Microsoft Agent Framework workflow.

                  +-> [Analyst] --- Analysis ---+
    RecapRequest -+                             +-> [Narrator] -> Draft -> [Verifier] -> VerifiedRecap
      [start]     +-> [Retrieval] - Retrieved --+        ^                      |
                                                         +------ Revision ------+  (up to MAX_REWRITES)

Each executor is one step: it receives a typed message, runs its agent, and
sends the result along an edge (or yields the final output). The Analyst and
Retrieval agents run in parallel (fan-out); the Narrator waits for both
(fan-in). The Verifier either approves the draft, sends it back to the
Narrator with the problems it found, or (after MAX_REWRITES) removes the
sentences that still fail.

Usage:
    python -m inside_the_game.workflow --seed 5 --style broadcaster [--save]
"""

import argparse
import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, WorkflowViz, handler
from typing_extensions import Never

from inside_the_game import analyst, narrator, retrieval, verifier
from inside_the_game.analyst import AnalystReport
from inside_the_game.generator import Match, generate_match
from inside_the_game.moments import Comparison
from inside_the_game.narrator import STYLE_GUIDES, Recap, Style
from inside_the_game.tracing import setup_tracing
from inside_the_game.verifier import MAX_REWRITES, Rejection, VerifiedRecap


@dataclass
class RecapRequest:
    """Workflow input: which match to recap, and in which style."""

    match: Match
    style: Style


@dataclass
class Analysis:
    """Analyst -> Narrator: the findings to write about.

    After fan-in, the Narrator adds the Retrieval comparisons to it.
    """

    match: Match
    style: Style
    report: AnalystReport
    comparisons: list[Comparison] = field(default_factory=list)


@dataclass
class Retrieved:
    """Retrieval -> Narrator: comparisons with similar moments in other matches."""

    comparisons: list[Comparison]


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


class StartExecutor(Executor):
    """Hands the request to the Analyst and Retrieval steps at the same time."""

    @handler
    async def start(self, request: RecapRequest, ctx: WorkflowContext[RecapRequest]) -> None:
        await ctx.send_message(request)


class AnalystExecutor(Executor):
    """Runs the Analyst agent and passes its findings on."""

    @handler
    async def analyse(self, request: RecapRequest, ctx: WorkflowContext[Analysis]) -> None:
        report = await analyst.analyse(request.match)
        await ctx.send_message(Analysis(match=request.match, style=request.style, report=report))


class RetrievalExecutor(Executor):
    """Runs the Retrieval agent. Comparisons are optional extras: on failure, carry on without them."""

    @handler
    async def retrieve(self, request: RecapRequest, ctx: WorkflowContext[Retrieved]) -> None:
        try:
            comparisons = await retrieval.retrieve(request.match)
        except Exception as error:  # noqa: BLE001 - a recap without comparisons is still a recap
            logging.warning("Retrieval failed, continuing without comparisons: %s", error)
            comparisons = []
        await ctx.send_message(Retrieved(comparisons=comparisons))


class NarratorExecutor(Executor):
    """Runs the Narrator agent: a first draft, or a rewrite after Verifier feedback."""

    @handler
    async def first_draft(self, inputs: list[Analysis | Retrieved], ctx: WorkflowContext[Draft]) -> None:
        """Fan-in: combine the Analyst's findings with the Retrieval comparisons."""
        analysis = next(i for i in inputs if isinstance(i, Analysis))
        comparisons = [c for i in inputs if isinstance(i, Retrieved) for c in i.comparisons]
        combined = Analysis(
            match=analysis.match,
            style=analysis.style,
            report=AnalystReport(
                findings=analysis.report.findings + retrieval.comparisons_as_findings(comparisons)
            ),
            comparisons=comparisons,
        )
        recap = await narrator.narrate(combined.match, combined.report, combined.style)
        await ctx.send_message(Draft(analysis=combined, recap=recap, rewrites=0))

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
        comparisons = draft.analysis.comparisons
        verdicts = await verifier.verify(match, draft.recap, comparisons)
        verdicts = verifier.apply_style_checks(draft.recap, verdicts, comparisons)
        all_supported = all(v.supported for v in verdicts)
        missing_comparison = verifier.missing_comparison(draft.recap, comparisons)
        if (not all_supported or missing_comparison) and draft.rewrites < MAX_REWRITES:
            feedback = verifier.feedback_for(draft.recap, verdicts)
            rejections = verifier.rejections_for(draft.recap, verdicts, draft.rewrites)
            if missing_comparison:
                feedback = "\n".join(filter(None, [feedback, f"- {verifier.MISSING_COMPARISON}"]))
                rejections.append(
                    Rejection(draft=draft.rewrites, text="(whole recap)", problem=verifier.MISSING_COMPARISON)
                )
            await ctx.send_message(
                Revision(
                    analysis=draft.analysis,
                    feedback=feedback,
                    rewrites=draft.rewrites + 1,
                    rejections=draft.rejections + rejections,
                )
            )
        else:
            await ctx.yield_output(
                verifier.finalize(match, draft.recap, verdicts, draft.rewrites, draft.rejections, comparisons)
            )


def build_workflow() -> Workflow:
    """Wire the executors together: fan-out, fan-in, and the Verifier -> Narrator rewrite loop."""
    start_step = StartExecutor(id="start")
    analyst_step = AnalystExecutor(id="analyst")
    retrieval_step = RetrievalExecutor(id="retrieval")
    narrator_step = NarratorExecutor(id="narrator")
    verifier_step = VerifierExecutor(id="verifier")
    return (
        WorkflowBuilder(start_executor=start_step)
        .add_fan_out_edges(start_step, [analyst_step, retrieval_step])
        .add_fan_in_edges([analyst_step, retrieval_step], narrator_step)
        .add_edge(narrator_step, verifier_step)
        .add_edge(verifier_step, narrator_step)
        .build()
    )


@dataclass
class Progress:
    """A step starting or finishing, for live progress in the CLI and UI."""

    step: str  # executor id: start, analyst, retrieval, narrator, verifier
    status: Literal["started", "finished"]
    detail: str = ""  # e.g. "rewrite 1"


async def stream_recap(match: Match, style: Style) -> AsyncIterator[Progress | VerifiedRecap]:
    """Run the pipeline, yielding Progress as steps run and the VerifiedRecap at the end."""
    async for event in build_workflow().run(RecapRequest(match=match, style=style), stream=True):
        if event.type == "executor_invoked":
            detail = f"rewrite {event.data.rewrites}" if isinstance(event.data, Revision) else ""
            yield Progress(step=event.executor_id, status="started", detail=detail)
        elif event.type == "executor_completed":
            yield Progress(step=event.executor_id, status="finished")
        elif event.type == "output":
            yield event.data


async def run_recap(match: Match, style: Style, verbose: bool = False) -> VerifiedRecap:
    """Run the whole pipeline for one match and return the verified recap."""
    result: VerifiedRecap | None = None
    async for item in stream_recap(match, style):
        if isinstance(item, VerifiedRecap):
            result = item
        elif verbose and item.status == "started":
            print(f"  [{item.step}{f' ({item.detail})' if item.detail else ''}]")
    if result is None:
        raise RuntimeError("Workflow finished without producing a recap")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the recap workflow on a synthetic match.")
    parser.add_argument("--seed", type=int, default=1, help="which synthetic match")
    parser.add_argument("--style", choices=list(STYLE_GUIDES), default="broadcaster")
    parser.add_argument("--diagram", action="store_true", help="print the workflow as a Mermaid diagram and exit")
    parser.add_argument("--save", action="store_true", help="save the match and verified recap to Cosmos DB")
    args = parser.parse_args()

    if args.diagram:
        print(WorkflowViz(build_workflow()).to_mermaid())
        return

    match = generate_match(args.seed)
    score = match.score()
    print(f"{match.home_team} {score['Home']}-{score['Away']} {match.away_team} ({args.style})")
    async def run() -> VerifiedRecap:
        if await setup_tracing():
            print("  (tracing to Azure Monitor)")
        return await run_recap(match, args.style, verbose=True)

    result = asyncio.run(run())
    recap = result.recap
    print(f"\n# {recap.headline.text}\n")
    for sentence in recap.sentences:
        print(f"{sentence.text}\n    events {sentence.event_ids}  tools {sentence.tools}")
    print(f"\nComparisons from Retrieval: {len(result.comparisons)}")
    for comparison in result.comparisons:
        print(f"  - {comparison.claim}")
    print(f"Rewrites: {result.rewrites}")
    for rejection in result.rejections:
        print(f"Rejected in draft {rejection.draft}: {rejection.text!r}\n    because: {rejection.problem}")
    for removed in result.removed:
        print(f"Removed: {removed.text!r}\n    because: {removed.problem}")

    if args.save:
        from inside_the_game.store import Store  # only needed (and configured) when saving

        async def save() -> None:
            async with Store() as store:
                await store.save_match(match)
                await store.save_recap(match.match_id, result)

        asyncio.run(save())
        print(f"\nSaved to Cosmos DB as {match.match_id}-{args.style}")


if __name__ == "__main__":
    main()
