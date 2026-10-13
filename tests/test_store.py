"""Tests for the Cosmos DB document conversions (no Azure calls)."""

from inside_the_game.generator import generate_match
from inside_the_game.live import LiveCommentary
from inside_the_game.narrator import Recap, RecapSentence
from inside_the_game.store import (
    attach_recap_styles,
    commentary_to_doc,
    doc_to_match,
    doc_to_recap,
    match_to_doc,
    recap_id,
    recap_to_doc,
)
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
    assert doc["language"] == "en"
    assert "created_at" in doc
    assert doc_to_recap(doc) == result


def test_english_keeps_the_original_recap_id_and_other_languages_add_theirs() -> None:
    assert recap_id("match_003", "fan") == "match_003-fan"
    assert recap_id("match_003", "fan", "en") == "match_003-fan"
    assert recap_id("match_003", "fan", "es") == "match_003-fan-es"


def test_recap_saved_before_languages_existed_reads_as_english() -> None:
    sentence = RecapSentence(text="H9 scored.", finding_ids=[1], event_ids=[42], tools=["get_goals"])
    old = {"recap": {"style": "fan", "headline": sentence.model_dump(), "sentences": []}, "rewrites": 0,
           "rejections": [], "removed": []}
    assert doc_to_recap(old).recap.language == "en"


def test_match_summaries_list_their_saved_recaps() -> None:
    matches = [{"match_id": "match_001"}, {"match_id": "match_002"}]
    rows = [
        {"match_id": "match_001", "style": "fan"},  # saved before languages existed: English
        {"match_id": "match_001", "style": "analyst", "language": "en"},
        {"match_id": "match_001", "style": "fan", "language": "es"},
        {"match_id": "match_009", "style": "fan"},  # a recap for a match not in the list is ignored
    ]
    assert attach_recap_styles(matches, rows) == [
        {
            "match_id": "match_001",
            "recaps": [
                {"style": "analyst", "language": "en"},
                {"style": "fan", "language": "en"},
                {"style": "fan", "language": "es"},
            ],
        },
        {"match_id": "match_002", "recaps": []},
    ]


def test_live_commentary_documents_use_the_recap_ids() -> None:
    doc = commentary_to_doc("match_002", LiveCommentary(style="fan", language="hi", lines=[]))
    assert doc["id"] == "match_002-fan-hi" and doc["match_id"] == "match_002"
    assert LiveCommentary.model_validate(doc).language == "hi"
