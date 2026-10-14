"""Tests for the Narrator's prompt and evidence mapping (no LLM calls)."""

import pytest
from pydantic import ValidationError

from inside_the_game.analyst import AnalystReport, Finding
from inside_the_game.generator import generate_match
from inside_the_game.narrator import (
    NarratedSentence,
    NarratorOutput,
    build_prompt,
    focus_player,
    resolve_recap,
    style_guide,
)

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
    assert recap.headline.tools == ["get_match_info"]
    assert recap.sentences[0].event_ids == [40, 41, 42]
    assert recap.sentences[0].tools == ["get_goals", "get_counterattacks"]
    assert recap.sentences[1].event_ids == [7, 99]


def test_prompt_asks_for_the_language_but_keeps_names_untranslated() -> None:
    match = generate_match(1)
    assert "Language:" not in build_prompt(match, REPORT, "fan")
    spanish = build_prompt(match, REPORT, "fan", language="es")
    assert "in Spanish" in spanish
    assert "untranslated" in spanish and "0-9" in spanish


def test_prompt_includes_verifier_feedback_only_when_rewriting() -> None:
    match = generate_match(1)
    assert "fact-checker" not in build_prompt(match, REPORT, "fan")
    rewrite = build_prompt(match, REPORT, "fan", feedback="Sentence 2: wrong minute.")
    assert "fact-checker" in rewrite and "Sentence 2: wrong minute." in rewrite


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


def test_prompt_marks_comparisons_with_other_matches() -> None:
    report = AnalystReport(
        findings=[
            Finding(claim="Home won.", tool="get_match_info", event_ids=[]),
            Finding(claim="Like a goal elsewhere.", tool="find_similar_moments", event_ids=[3]),
        ]
    )
    prompt = build_prompt(generate_match(1), report, "fan")
    assert prompt.count('"about": "other matches"') == 1


def test_personalized_voices_for_a_club_and_a_player() -> None:
    match = generate_match(1)  # Eastmoor United v Ashvale Town
    assert "supporter of Eastmoor United" in style_guide("fan", match, "Home")
    assert "Ashvale Town's own tactical analyst" in style_guide("analyst", match, "Away")
    assert "club channel" in style_guide("broadcaster", match, "Home")
    follows = style_guide("analyst", match, "A11")
    assert "follows player A11 of Ashvale Town" in follows and "headline" in follows
    assert "A11" in build_prompt(match, REPORT, "analyst", focus="A11")
    assert (focus_player(""), focus_player("Home"), focus_player("A11")) == (None, None, "A11")
