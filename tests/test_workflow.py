"""Tests for the workflow wiring and rewrite loop, with the agents replaced by fakes (no LLM calls)."""

import asyncio

import pytest

from inside_the_game import analyst, narrator, verifier
from inside_the_game.analyst import AnalystReport, Finding
from inside_the_game.generator import Match, generate_match
from inside_the_game.narrator import Recap, RecapSentence, Style
from inside_the_game.verifier import MAX_REWRITES, SentenceVerdict
from inside_the_game.workflow import run_recap

FAKE_REPORT = AnalystReport(findings=[Finding(claim="Home won.", tool="get_match_info", event_ids=[])])
MATCH = generate_match(5)


def _install_fakes(monkeypatch: pytest.MonkeyPatch, verdict_rounds: list[list[bool]]) -> list[str]:
    """Replace the three agents with fakes. Each verify call uses the next round of verdicts."""
    calls: list[str] = []

    async def fake_analyse(match: Match) -> AnalystReport:
        calls.append("analyse")
        return FAKE_REPORT

    async def fake_narrate(match: Match, report: AnalystReport, style: Style, feedback: str | None = None) -> Recap:
        calls.append("rewrite" if feedback else "narrate")
        assert report is FAKE_REPORT  # the Analyst's output reached the Narrator
        n = calls.count("narrate") + calls.count("rewrite")
        sentence = RecapSentence(text=f"Draft {n}.", finding_ids=[1], event_ids=[], tools=["get_match_info"])
        return Recap(style=style, headline=sentence, sentences=[sentence])

    async def fake_verify(match: Match, recap: Recap) -> list[SentenceVerdict]:
        calls.append("verify")
        supported = verdict_rounds.pop(0)
        return [SentenceVerdict(sentence=n, supported=ok, problem="" if ok else "wrong") for n, ok in enumerate(supported)]

    monkeypatch.setattr(analyst, "analyse", fake_analyse)
    monkeypatch.setattr(narrator, "narrate", fake_narrate)
    monkeypatch.setattr(verifier, "verify", fake_verify)
    return calls


def test_approved_first_draft_needs_no_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch, [[True, True]])
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert calls == ["analyse", "narrate", "verify"]
    assert result.rewrites == 0
    assert result.removed == []
    assert result.rejections == []
    assert result.recap.headline.text == "Draft 1."


def test_rejected_draft_goes_back_to_the_narrator(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch, [[True, False], [True, True]])
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert calls == ["analyse", "narrate", "verify", "rewrite", "verify"]
    assert result.rewrites == 1
    assert result.recap.sentences[0].text == "Draft 2."
    assert [(r.draft, r.text) for r in result.rejections] == [(0, "Draft 1.")]


def test_loop_stops_after_max_rewrites_and_drops_what_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fakes(monkeypatch, [[True, False]] * (MAX_REWRITES + 1))
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert calls.count("rewrite") == MAX_REWRITES
    assert calls.count("verify") == MAX_REWRITES + 1
    assert result.rewrites == MAX_REWRITES
    assert result.recap.sentences == []
    assert [r.problem for r in result.removed] == ["wrong"]
    # Every draft except the last was sent back; the last one's failures were removed instead.
    assert [r.draft for r in result.rejections] == list(range(MAX_REWRITES))
