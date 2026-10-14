"""Tests for the pre-generation rule that never replaces a saved recap with a worse one."""

from inside_the_game.narrator import Recap, RecapSentence
from inside_the_game.pregenerate import keep_saved
from inside_the_game.verifier import RemovedSentence, VerifiedRecap

SENTENCE = RecapSentence(text="H9 scored.", finding_ids=[1], event_ids=[4], tools=["get_goals"])


def _result(removed: int) -> VerifiedRecap:
    return VerifiedRecap(
        recap=Recap(style="fan", headline=SENTENCE, sentences=[SENTENCE]),
        rewrites=0,
        rejections=[],
        removed=[RemovedSentence(text="x", problem="y")] * removed,
    )


def test_a_new_recap_replaces_one_that_removed_as_much_or_more() -> None:
    assert not keep_saved(None, _result(2))
    assert not keep_saved(_result(1), _result(1))
    assert not keep_saved(_result(2), _result(0))


def test_the_saved_recap_stays_when_the_new_one_removed_more() -> None:
    assert keep_saved(_result(0), _result(1))
