"""Commentator agent: live, verified commentary on one key moment.

When the live feed detects a moment (a goal, a counterattack, half-time or
full-time), code writes numbered findings about it and about the match so far.
The Commentator explains in one or two sentences why the moment matters,
citing finding numbers like the Narrator does, so code can attach the evidence.

A small Agent Framework workflow then fact-checks it:

    MomentRequest -> [Commentator] -> LiveDraft -> [Verifier] -> Commentary
                           ^                           |
                           +------ LiveRevision -------+   (at most MAX_LIVE_REWRITES)

The Verifier sees only the evidence as of that minute. Live commentary can't
wait long, so it gets one rewrite; sentences that still fail are dropped.

Usage:
    python -m inside_the_game.live --seed 2 --commentary
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from agent_framework import Agent, Executor, Workflow, WorkflowBuilder, WorkflowContext, handler
from agent_framework.foundry import FoundryChatClient
from pydantic import BaseModel, Field

from inside_the_game import verifier
from inside_the_game.analyst import AnalystReport
from inside_the_game.foundry import make_client
from inside_the_game.generator import Match
from inside_the_game.live import Commentary, Commentator, LiveMoment, moment_findings, tool_results
from inside_the_game.narrator import (
    Language,
    NarratedSentence,
    NarratorOutput,
    Recap,
    RecapSentence,
    Style,
    language_rule,
    resolve_recap,
    style_guide,
)
from inside_the_game.verifier import RemovedSentence, SentenceVerdict

MAX_LIVE_REWRITES = 1

INSTRUCTIONS = """\
You are a live football commentator. A key moment just happened. Using the
numbered findings about it and about the match so far, write 1 or 2 short
sentences (at most 30 words each) that say what happened and WHY IT MATTERS
right now: what it does to the score, whether it goes with or against the
run of play (compare shots and possession so far), or how the game is shaping up.

Rules:
- Use only facts from the findings; never add numbers, players, minutes or
  events. You don't know what happens later in the match: never predict it.
- No rankings or firsts ("best", "first", "only") unless a finding says so.
- Every sentence must cite ALL the findings whose facts it uses in finding_ids.
- Refer to players by their ids exactly as given (e.g. H9) and to teams by name.
- Never mention pitch coordinates, ids or data field names.
- When giving a score, make clear which team leads.
"""


class CommentatorOutput(BaseModel):
    sentences: list[NarratedSentence] = Field(min_length=1, max_length=2)


def build_prompt(
    match: Match,
    moment: LiveMoment,
    report: AnalystReport,
    style: Style,
    language: Language,
    feedback: str | None = None,
    focus: str = "",
) -> str:
    """The message sent to the Commentator: style, language, the moment and numbered findings."""
    findings = [{"id": i, "claim": f.claim} for i, f in enumerate(report.findings, start=1)]
    prompt = (
        f"Style: {style_guide(style, match, focus)}\n"
        f"{language_rule(language)}"
        f"Home team: {match.home_team}. Away team: {match.away_team}.\n"
        f"Moment: {moment.kind} in minute {moment.minute}.\n"
        f"Findings:\n{json.dumps(findings, indent=1)}"
    )
    if feedback:
        prompt += (
            "\n\nA fact-checker rejected some of your sentences:\n"
            f"{feedback}\n"
            "Write the commentary again, fixing or dropping the rejected sentences."
        )
    return prompt


def as_recap(output: CommentatorOutput, report: AnalystReport, style: Style, language: Language) -> Recap:
    """Attach the evidence to each sentence, reusing the Narrator's resolver (first sentence = headline)."""
    first, *rest = output.sentences
    return resolve_recap(NarratorOutput(headline=first, sentences=rest), report, style, language)


def live_context(minute: int) -> str:
    """The note that tells the Verifier the evidence covers only the match so far."""
    return (
        f"This is LIVE commentary written at minute {minute}. Tool results cover only the match so far: "
        "final_score means the score at that minute."
    )


def make_commentator_agent(client: FoundryChatClient | None = None) -> Agent:
    return Agent(
        client=client or make_client(),
        name="Commentator",
        instructions=INSTRUCTIONS,
        default_options={"response_format": CommentatorOutput},
    )


async def comment(
    match: Match,
    moment: LiveMoment,
    report: AnalystReport,
    style: Style,
    language: Language,
    feedback: str | None = None,
    focus: str = "",
) -> Recap:
    """Run the Commentator and return its sentences with evidence attached."""
    response = await make_commentator_agent().run(
        build_prompt(match, moment, report, style, language, feedback, focus)
    )
    output = response.value
    if output is None:
        raise ValueError(f"Commentator returned no structured commentary: {response.text!r}")
    return as_recap(output, report, style, language)


# --- the moment workflow -------------------------------------------------------


@dataclass
class MomentRequest:
    """Workflow input: a moment, the match up to it, and the findings about it."""

    match: Match  # events so far only
    moment: LiveMoment
    minute: int  # the clock when the moment was detected
    report: AnalystReport
    style: Style
    language: Language
    focus: str = ""  # "" or the supported club


@dataclass
class LiveDraft:
    """Commentator -> Verifier."""

    request: MomentRequest
    recap: Recap
    rewrites: int


@dataclass
class LiveRevision:
    """Verifier -> Commentator: fix these problems."""

    request: MomentRequest
    feedback: str
    rewrites: int
    removed: list[RemovedSentence] = field(default_factory=list)


def keep_supported(
    recap: Recap, verdicts: list[SentenceVerdict]
) -> tuple[list[RecapSentence], list[RemovedSentence]]:
    """Split the commentary into verified sentences and removed ones."""
    sentences = verifier.numbered_sentences(recap)
    kept = [s for s, v in zip(sentences, verdicts) if v.supported]
    removed = [RemovedSentence(text=s.text, problem=v.problem) for s, v in zip(sentences, verdicts) if not v.supported]
    return kept, removed


class CommentatorExecutor(Executor):
    @handler
    async def first_draft(self, request: MomentRequest, ctx: WorkflowContext[LiveDraft]) -> None:
        r = request
        recap = await comment(r.match, r.moment, r.report, r.style, r.language, focus=r.focus)
        await ctx.send_message(LiveDraft(request=r, recap=recap, rewrites=0))

    @handler
    async def rewrite(self, revision: LiveRevision, ctx: WorkflowContext[LiveDraft]) -> None:
        r = revision.request
        recap = await comment(
            r.match, r.moment, r.report, r.style, r.language, feedback=revision.feedback, focus=r.focus
        )
        await ctx.send_message(LiveDraft(request=r, recap=recap, rewrites=revision.rewrites))


class LiveVerifierExecutor(Executor):
    @handler
    async def check(self, draft: LiveDraft, ctx: WorkflowContext[LiveRevision, Commentary]) -> None:
        r = draft.request
        verdicts = await verifier.verify(r.match, draft.recap, context=live_context(r.minute))
        verdicts = verifier.apply_style_checks(draft.recap, verdicts)
        if not all(v.supported for v in verdicts) and draft.rewrites < MAX_LIVE_REWRITES:
            feedback = verifier.feedback_for(draft.recap, verdicts)
            await ctx.send_message(LiveRevision(request=r, feedback=feedback, rewrites=draft.rewrites + 1))
            return
        kept, removed = keep_supported(draft.recap, verdicts)
        await ctx.yield_output(
            Commentary(
                moment=r.moment,
                sentences=kept,
                stats=tool_results(r.match),
                rewrites=draft.rewrites,
                removed=removed,
            )
        )


def build_moment_workflow() -> Workflow:
    commentator_step = CommentatorExecutor(id="commentator")
    verifier_step = LiveVerifierExecutor(id="live_verifier")
    return (
        WorkflowBuilder(start_executor=commentator_step)
        .add_edge(commentator_step, verifier_step)
        .add_edge(verifier_step, commentator_step)
        .build()
    )


async def run_moment(request: MomentRequest) -> Commentary:
    """Run the Commentator ⇄ Verifier workflow for one moment."""
    result = await build_moment_workflow().run(request)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError(f"No commentary produced for {request.moment.key}")
    return outputs[-1]


def make_commentator(style: Style, language: Language = "en", focus: str = "") -> Commentator:
    """A live commentator: findings by code, words by the Commentator, checks by the Verifier."""

    async def commentate(match_so_far: Match, moment: LiveMoment) -> Commentary | None:
        minute = match_so_far.events[-1].minute if match_so_far.events else moment.minute
        report = moment_findings(match_so_far, moment, minute)
        request = MomentRequest(
            match=match_so_far,
            moment=moment,
            minute=minute,
            report=report,
            style=style,
            language=language,
            focus=focus,
        )
        return await run_moment(request)

    return commentate
