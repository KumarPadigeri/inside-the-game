"""The recap pipeline as a Microsoft Agent Framework workflow.

    RecapRequest -> [Analyst] -> Analysis -> [Narrator] -> Recap

Each executor is one step: it receives a typed message, runs its agent, and
sends the result along an edge (or yields the final output). Later steps
(Verifier, Retrieval) plug in as new executors and edges.

Usage:
    python -m inside_the_game.workflow --seed 5 --style broadcaster
"""

import argparse
import asyncio
from dataclasses import dataclass

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, WorkflowViz, handler
from typing_extensions import Never

from inside_the_game import analyst, narrator
from inside_the_game.analyst import AnalystReport
from inside_the_game.generator import Match, generate_match
from inside_the_game.narrator import STYLE_GUIDES, Recap, Style


@dataclass
class RecapRequest:
    """Workflow input: which match to recap, and in which style."""

    match: Match
    style: Style


@dataclass
class Analysis:
    """Message from the Analyst step to the Narrator step."""

    match: Match
    style: Style
    report: AnalystReport


class AnalystExecutor(Executor):
    """Runs the Analyst agent and passes its findings on."""

    @handler
    async def analyse(self, request: RecapRequest, ctx: WorkflowContext[Analysis]) -> None:
        report = await analyst.analyse(request.match)
        await ctx.send_message(Analysis(match=request.match, style=request.style, report=report))


class NarratorExecutor(Executor):
    """Runs the Narrator agent and yields the finished recap."""

    @handler
    async def narrate(self, analysis: Analysis, ctx: WorkflowContext[Never, Recap]) -> None:
        recap = await narrator.narrate(analysis.match, analysis.report, analysis.style)
        await ctx.yield_output(recap)


def build_workflow() -> Workflow:
    """Wire the executors together: Analyst -> Narrator."""
    analyst_step = AnalystExecutor(id="analyst")
    narrator_step = NarratorExecutor(id="narrator")
    return WorkflowBuilder(start_executor=analyst_step).add_edge(analyst_step, narrator_step).build()


async def run_recap(match: Match, style: Style, verbose: bool = False) -> Recap:
    """Run the whole pipeline for one match and return the recap."""
    recap: Recap | None = None
    async for event in build_workflow().run(RecapRequest(match=match, style=style), stream=True):
        if verbose and event.type in ("executor_invoked", "executor_completed"):
            print(f"  [{event.executor_id}] {event.type.removeprefix('executor_')}")
        if event.type == "output":
            recap = event.data
    if recap is None:
        raise RuntimeError("Workflow finished without producing a recap")
    return recap


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
    recap = asyncio.run(run_recap(match, args.style, verbose=True))
    print(f"\n# {recap.headline.text}\n")
    for sentence in recap.sentences:
        print(f"{sentence.text}\n    events {sentence.event_ids}")


if __name__ == "__main__":
    main()
