"""Tests for the Retrieval agent's citation checks and evidence (no LLM or Azure calls)."""

import json

import pytest

from inside_the_game.generator import generate_match
from inside_the_game.moments import Comparison, SimilarMoment, extract_moments
from inside_the_game.narrator import Recap, RecapSentence
from inside_the_game.retrieval import (
    TOOL_NAME,
    ComparisonDraft,
    RetrievalOutput,
    comparisons_as_findings,
    resolve_comparisons,
)
from inside_the_game.verifier import build_prompt

MATCH = generate_match(5)
WINNER = next(m for m in extract_moments(MATCH) if m.minute == 80)
OTHER = SimilarMoment(**extract_moments(generate_match(9))[0].model_dump(), similarity=0.9)
FOUND = {OTHER.moment_id: OTHER}


def _output(moment_id: str, similar_ids: list[str]) -> RetrievalOutput:
    return RetrievalOutput(
        comparisons=[ComparisonDraft(claim="Similar.", moment_id=moment_id, similar_moment_ids=similar_ids)]
    )


def test_resolve_attaches_the_real_moments() -> None:
    [comparison] = resolve_comparisons(_output(WINNER.moment_id, [OTHER.moment_id]), MATCH, FOUND)
    assert comparison.moment == WINNER
    assert comparison.similar == [OTHER]
    assert comparison.event_ids == WINNER.event_ids


def test_resolve_rejects_a_moment_not_in_this_match() -> None:
    with pytest.raises(ValueError, match="unknown moment"):
        resolve_comparisons(_output("match_005-p999", [OTHER.moment_id]), MATCH, FOUND)


def test_resolve_rejects_similar_moments_no_search_returned() -> None:
    with pytest.raises(ValueError, match="no search returned"):
        resolve_comparisons(_output(WINNER.moment_id, ["match_042-p1"]), MATCH, FOUND)


def test_comparisons_become_findings_with_this_matchs_events() -> None:
    comparison = Comparison(claim="Echoed.", moment=WINNER, similar=[OTHER], event_ids=WINNER.event_ids)
    [finding] = comparisons_as_findings([comparison])
    assert (finding.claim, finding.tool, finding.event_ids) == ("Echoed.", TOOL_NAME, WINNER.event_ids)


def test_verifier_sees_the_similar_moments_as_evidence() -> None:
    comparison = Comparison(claim="Echoed.", moment=WINNER, similar=[OTHER], event_ids=WINNER.event_ids)
    sentence = RecapSentence(text="Echoed.", finding_ids=[1], event_ids=WINNER.event_ids, tools=[TOOL_NAME])
    recap = Recap(style="fan", headline=sentence, sentences=[])
    evidence = json.loads(build_prompt(MATCH, recap, [comparison]).split("Evidence: ")[1])
    [entry] = evidence["tool_results"][TOOL_NAME]
    assert entry["this_match_moment"]["minute"] == 80
    assert entry["similar_moments_in_other_matches"][0]["match_id"] == "match_009"
