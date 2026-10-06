"""Tests for the Cosmos DB document conversions (no Azure calls)."""

from inside_the_game.generator import generate_match
from inside_the_game.narrator import Recap, RecapSentence
from inside_the_game.store import doc_to_match, doc_to_recap, match_to_doc, recap_to_doc
from inside_the_game.verifier import Rejection, VerifiedRecap


def test_match_round_trips_through_a_document() -> None:
    match = generate_match(3)
    doc = match_to_doc(match)
    assert doc["id"] == doc["match_id"] == "match_003"
    assert doc["score"] == match.score()
    assert doc_to_match(doc).to_dict() == match.to_dict()


def test_recap_round_trips_through_a_document() -> None:
    sentence = RecapSentence(text="H9 scored.", finding_ids=[1], event_ids=[42], tools=["get_goals"])
    result = VerifiedRecap(
        recap=Recap(style="analyst", headline=sentence, sentences=[sentence]),
        rewrites=1,
        rejections=[Rejection(draft=0, text="H9 scored twice.", problem="Only one goal.")],
        removed=[],
    )
    doc = recap_to_doc("match_003", result)
    assert doc["id"] == "match_003-analyst"
    assert doc["match_id"] == "match_003"
    assert "created_at" in doc
    assert doc_to_recap(doc) == result
