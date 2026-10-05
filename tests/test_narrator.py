"""Tests for the Narrator's prompt and evidence mapping (no LLM calls)."""

import pytest
from pydantic import ValidationError

from inside_the_game.analyst import AnalystReport, Finding
from inside_the_game.generator import generate_match
from inside_the_game.narrator import NarratedSentence, NarratorOutput, build_prompt, resolve_recap

REPORT = AnalystReport(
    findings=[
        Finding(claim="Home won 1-0.", tool="get_match_info", event_ids=[]),
        Finding(claim="H9 scored in the 10th minute.", tool="get_goals", event_ids=[40, 41, 42]),
        Finding(claim="The goal came from a counterattack.", tool="get_counterattacks", event_ids=[40, 41, 42]),
        Finding(claim="Away had 6 shots.", tool="get_shots", event_ids=[99, 7]),
    ]
)


def test_prompt_numbers_findings_and_hides_event_ids() -> None:
    prompt = build_prompt(generate_match(1), REPORT, "fan")
    assert '"id": 2' in prompt and "H9 scored" in prompt
    assert "event_ids" not in prompt and "40" not in prompt


def test_resolve_maps_findings_to_sorted_unique_event_ids() -> None:
    output = NarratorOutput(
        headline=NarratedSentence(text="Home edge it!", finding_ids=[1]),
        sentences=[
            NarratedSentence(text="H9 struck on the break.", finding_ids=[2, 3]),
            NarratedSentence(text="Away kept trying.", finding_ids=[4]),
        ],
    )
    recap = resolve_recap(output, REPORT, "fan")
    assert recap.headline.event_ids == []
    assert recap.sentences[0].event_ids == [40, 41, 42]
    assert recap.sentences[1].event_ids == [7, 99]


def test_resolve_rejects_a_finding_that_does_not_exist() -> None:
    output = NarratorOutput(
        headline=NarratedSentence(text="Big win.", finding_ids=[1]),
        sentences=[NarratedSentence(text="Made up.", finding_ids=[9])],
    )
    with pytest.raises(ValueError, match="finding 9"):
        resolve_recap(output, REPORT, "analyst")


def test_every_sentence_must_cite_a_finding() -> None:
    with pytest.raises(ValidationError):
        NarratedSentence(text="Pure opinion.", finding_ids=[])
