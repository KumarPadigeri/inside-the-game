"""Tests for the Commentator prompt and its Commentator ⇄ Verifier loop (agents replaced by fakes)."""

import asyncio

import pytest

from inside_the_game import commentator, verifier
from inside_the_game.analyst import AnalystReport
from inside_the_game.commentator import (
    MAX_LIVE_REWRITES,
    CommentatorOutput,
    MomentRequest,
    as_recap,
    build_prompt,
    run_moment,
)
from inside_the_game.generator import Match, generate_match
from inside_the_game.live import detect_moments, match_until, moment_findings
from inside_the_game.narrator import Language, NarratedSentence, Recap, Style
from inside_the_game.verifier import SentenceVerdict

SO_FAR = match_until(generate_match(2), 16)
GOAL = detect_moments(SO_FAR, set())[2]  # A6 pulls one back: 2-1
REPORT = moment_findings(SO_FAR, GOAL, 16)


def _request() -> MomentRequest:
    return MomentRequest(match=SO_FAR, moment=GOAL, minute=16, report=REPORT, style="broadcaster", language="en")


def test_prompt_has_the_moment_and_numbered_findings_without_event_ids() -> None:
    prompt = build_prompt(SO_FAR, GOAL, REPORT, "broadcaster", "es")
    assert "Moment: goal in minute 16" in prompt
    assert '"id": 1' in prompt and "A6 scored" in prompt
    assert "event_ids" not in prompt
    assert "in Spanish" in prompt


def test_sentences_get_the_evidence_of_their_findings() -> None:
    output = CommentatorOutput(
        sentences=[NarratedSentence(text="A6 makes it 2-1.", finding_ids=[1]), NarratedSentence(text="x", finding_ids=[3])]
    )
    recap = as_recap(output, REPORT, "fan", "en")
    assert recap.headline.event_ids == sorted(GOAL.event_ids)
    assert recap.sentences[0].tools == [REPORT.findings[2].tool]


def _install_fakes(monkeypatch: pytest.MonkeyPatch, rounds: list[list[bool]]) -> list[str]:
    calls: list[str] = []

    async def fake_comment(
        match: Match,
        moment,
        report: AnalystReport,
        style: Style,
        language: Language,
        feedback: str | None = None,
        focus: str = "",
    ) -> Recap:
        calls.append("rewrite" if feedback else "comment")
        output = CommentatorOutput(
            sentences=[NarratedSentence(text=f"Line {i}.", finding_ids=[1]) for i in range(len(rounds[0]))]
        )
        return as_recap(output, report, style, language)

    async def fake_verify(match: Match, recap: Recap, comparisons=None, context: str = "") -> list[SentenceVerdict]:
        calls.append("verify")
        assert "LIVE" in context and "minute 16" in context
        return [SentenceVerdict(sentence=n, supported=ok, problem="" if ok else "wrong") for n, ok in enumerate(rounds.pop(0))]

    monkeypatch.setattr(commentator, "comment", fake_comment)
    monkeypatch.setattr(verifier, "verify", fake_verify)
    return calls


def test_verified_commentary_needs_no_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch, [[True, True]])
    result = asyncio.run(run_moment(_request()))
    assert calls == ["comment", "verify"]
    assert [s.text for s in result.sentences] == ["Line 0.", "Line 1."]
    assert result.stats["get_match_info"]["final_score"] == {"Home": 2, "Away": 1}  # the score at that minute


def test_rejected_sentence_is_rewritten_once_then_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch, [[True, False], [True, False]])
    result = asyncio.run(run_moment(_request()))
    assert calls == ["comment", "verify"] + ["rewrite", "verify"] * MAX_LIVE_REWRITES
    assert [s.text for s in result.sentences] == ["Line 0."]
    assert result.rewrites == MAX_LIVE_REWRITES
    assert [r.problem for r in result.removed] == ["wrong"]


def test_club_focus_changes_the_commentator_voice() -> None:
    prompt = build_prompt(SO_FAR, GOAL, REPORT, "fan", "en", focus="Away")
    assert "supporter of Oakhurst Albion" in prompt
