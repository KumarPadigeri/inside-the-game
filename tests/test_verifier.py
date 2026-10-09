"""Tests for the Verifier's prompt, feedback and final clean-up (no LLM calls)."""

import json

from inside_the_game.generator import generate_match
from inside_the_game.moments import Comparison, SimilarMoment, extract_moments
from inside_the_game.narrator import Recap, RecapSentence
from inside_the_game.verifier import (
    SentenceVerdict,
    VerifierOutput,
    apply_style_checks,
    build_prompt,
    feedback_for,
    finalize,
    normalize_verdicts,
    rejections_for,
    style_problems,
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


def test_rejections_record_the_draft_and_problem() -> None:
    rejections = rejections_for(RECAP, _verdicts(False, True, True), draft=1)
    assert [(r.draft, r.text, r.problem) for r in rejections] == [(1, "Great win!", "problem 0")]


def _recap_of(*texts: str) -> Recap:
    sentences = [_sentence(t) for t in texts]
    return Recap(style="fan", headline=sentences[0], sentences=sentences[1:])


def test_style_checks_catch_leaked_internals() -> None:
    recap = _recap_of(
        "Great win!",
        "The break started near x=41.",
        "H won the ball and scored.",
        "See match_005 for details.",
        "Its event_ids prove it.",
    )
    problems = style_problems(recap)
    assert sorted(problems) == [1, 2, 3, 4]
    assert "coordinate" in problems[1]
    assert "team letter" in problems[2]
    assert "match id" in problems[3]
    assert "field name" in problems[4]


def test_style_checks_allow_normal_football_sentences() -> None:
    recap = _recap_of(
        "Ashvale Town edge a 3-2 thriller!",
        "A late goal from H11 settled it in the 80th minute.",
        "A10 scored twice for the visitors.",
        "H9 struck after a counterattack from their own half.",
    )
    assert style_problems(recap) == {}


def test_style_checks_flag_overlong_sentences() -> None:
    long_sentence = " ".join(["word"] * 46) + "."
    assert "too long (46 words" in style_problems(_recap_of("Fine.", long_sentence))[1]


def test_style_problems_turn_verdicts_into_rewrites() -> None:
    recap = _recap_of("Great win!", "Won near x=41.", "H10 opened the scoring.")
    verdicts = apply_style_checks(recap, _verdicts(True, True, True))
    assert [v.supported for v in verdicts] == [True, False, True]
    assert verdicts[1].problem.startswith("Wording:")


def test_comparison_sentences_must_name_another_match() -> None:
    other = SimilarMoment(**extract_moments(generate_match(9))[0].model_dump(), similarity=0.9)
    name = f"{other.home_team} v {other.away_team}"
    moment = extract_moments(MATCH)[0]
    comparison = Comparison(claim="Similar.", moment=moment, similar=[other], event_ids=moment.event_ids)
    vague = _sentence("It fit a pattern seen elsewhere.", tools=["find_similar_moments"])
    named = _sentence(f"It echoed a goal in {name}.", tools=["find_similar_moments"])
    recap = Recap(style="fan", headline=_sentence("Great win!"), sentences=[vague, named])
    problems = style_problems(recap, [comparison])
    assert list(problems) == [1]
    assert "without naming" in problems[1]
