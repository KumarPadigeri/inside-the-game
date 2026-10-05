"""Tests for the Verifier's prompt, feedback and final clean-up (no LLM calls)."""

import json

from inside_the_game.generator import generate_match
from inside_the_game.narrator import Recap, RecapSentence
from inside_the_game.verifier import (
    SentenceVerdict,
    VerifierOutput,
    build_prompt,
    feedback_for,
    finalize,
    normalize_verdicts,
)

MATCH = generate_match(5)


def _sentence(text: str, event_ids: list[int] | None = None, tools: list[str] | None = None) -> RecapSentence:
    return RecapSentence(text=text, finding_ids=[1], event_ids=event_ids or [], tools=tools or [])


RECAP = Recap(
    style="fan",
    headline=_sentence("Great win!", tools=["get_match_info"]),
    sentences=[
        _sentence("H10 opened the scoring.", event_ids=[198]),
        _sentence("Possession was even.", tools=["get_possession"]),
    ],
)


def _verdicts(*supported: bool) -> list[SentenceVerdict]:
    return [
        SentenceVerdict(sentence=n, supported=ok, problem="" if ok else f"problem {n}")
        for n, ok in enumerate(supported)
    ]


def test_prompt_gives_each_sentence_only_its_own_evidence() -> None:
    blocks = build_prompt(MATCH, RECAP).split("\n\n")
    assert blocks[1].startswith("Sentence 0: Great win!")
    headline_evidence = json.loads(blocks[1].split("Evidence: ")[1])
    assert list(headline_evidence["tool_results"]) == ["get_match_info"]
    assert headline_evidence["events"] == []

    goal_evidence = json.loads(blocks[2].split("Evidence: ")[1])
    assert goal_evidence["tool_results"] == {}
    assert [e["event_id"] for e in goal_evidence["events"]] == [198]
    assert goal_evidence["events"][0]["outcome"] == "goal"


def test_missing_verdicts_count_as_unsupported() -> None:
    output = VerifierOutput(verdicts=[SentenceVerdict(sentence=0, supported=True)])
    verdicts = normalize_verdicts(output, RECAP)
    assert [v.supported for v in verdicts] == [True, False, False]


def test_feedback_lists_only_rejected_sentences() -> None:
    feedback = feedback_for(RECAP, _verdicts(True, False, True))
    assert feedback == '- Sentence 1: "H10 opened the scoring." -> problem 1'


def test_finalize_keeps_everything_when_all_supported() -> None:
    result = finalize(MATCH, RECAP, _verdicts(True, True, True), rewrites=0)
    assert result.recap == RECAP
    assert result.removed == []


def test_finalize_drops_failed_sentences_and_replaces_a_failed_headline() -> None:
    result = finalize(MATCH, RECAP, _verdicts(False, True, False), rewrites=2)
    assert result.recap.headline.text == "Ashvale Town 3-2 Harbourside City"
    assert [s.text for s in result.recap.sentences] == ["H10 opened the scoring."]
    assert [r.text for r in result.removed] == ["Great win!", "Possession was even."]
    assert result.rewrites == 2
