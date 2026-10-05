"""Tests for the workflow wiring, with the agents replaced by fakes (no LLM calls)."""

import asyncio

import pytest

from inside_the_game import analyst, narrator
from inside_the_game.analyst import AnalystReport, Finding
from inside_the_game.generator import Match, generate_match
from inside_the_game.narrator import Recap, RecapSentence, Style
from inside_the_game.workflow import run_recap

FAKE_REPORT = AnalystReport(findings=[Finding(claim="Home won.", tool="get_match_info", event_ids=[1])])


def test_workflow_runs_analyst_then_narrator(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_analyse(match: Match) -> AnalystReport:
        calls.append(f"analyse {match.match_id}")
        return FAKE_REPORT

    async def fake_narrate(match: Match, report: AnalystReport, style: Style) -> Recap:
        calls.append(f"narrate {match.match_id} {style}")
        assert report is FAKE_REPORT  # the Analyst's output reached the Narrator
        sentence = RecapSentence(text="Home won.", finding_ids=[1], event_ids=[1])
        return Recap(style=style, headline=sentence, sentences=[sentence])

    monkeypatch.setattr(analyst, "analyse", fake_analyse)
    monkeypatch.setattr(narrator, "narrate", fake_narrate)

    recap = asyncio.run(run_recap(generate_match(5), "fan"))

    assert calls == ["analyse match_005", "narrate match_005 fan"]
    assert recap.style == "fan"
    assert recap.headline.text == "Home won."
