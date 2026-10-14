"""Tests for the quality numbers (pure counting over saved results, no Azure)."""

from inside_the_game.live import Commentary, LiveCommentary, LiveMoment
from inside_the_game.narrator import Recap, RecapSentence
from inside_the_game.quality import describe, kind_of, summarize
from inside_the_game.verifier import MISSING_COMPARISON, Rejection, RemovedSentence, VerifiedRecap

WITH_EVENTS = RecapSentence(text="H9 scored.", finding_ids=[1], event_ids=[4], tools=["get_goals"])
STATS_ONLY = RecapSentence(text="Even possession.", finding_ids=[2], event_ids=[], tools=["get_possession"])


def _recap(language: str, rewrites: int, rejections: list[Rejection], removed: int) -> VerifiedRecap:
    return VerifiedRecap(
        recap=Recap(style="fan", language=language, headline=WITH_EVENTS, sentences=[STATS_ONLY]),
        rewrites=rewrites,
        rejections=rejections,
        removed=[RemovedSentence(text="x", problem="y")] * removed,
    )


def test_rejections_are_sorted_by_why_they_were_sent_back() -> None:
    assert kind_of(Rejection(draft=0, text="x", problem="The minute is 54, not 45.")) == "facts"
    assert kind_of(Rejection(draft=0, text="x", problem="Wording: the sentence mentions an internal id.")) == "wording"
    assert kind_of(Rejection(draft=0, text="(whole recap)", problem=MISSING_COMPARISON)) == "missing_comparison"


def test_summary_counts_what_the_verifier_caught() -> None:
    recaps = [
        _recap("en", 0, [], 0),
        _recap(
            "es",
            2,
            [
                Rejection(draft=0, text="a", problem="Wrong minute."),
                Rejection(draft=0, text="b", problem="Wording: leaked id."),
                Rejection(draft=1, text="(whole recap)", problem=MISSING_COMPARISON),
            ],
            1,
        ),
    ]
    moment = LiveMoment(key="goal-4", kind="goal", minute=1, team="Home", event_ids=[4])
    live = [
        LiveCommentary(
            style="fan",
            lines=[Commentary(moment=moment, sentences=[WITH_EVENTS, STATS_ONLY], stats={}, rewrites=1, removed=[])],
        )
    ]
    q = summarize(recaps, live)
    assert (q.recaps, q.sentences_published, q.sentences_with_events) == (2, 4, 2)
    assert (q.first_draft_passed, q.rewrites, q.sentences_removed) == (1, 2, 1)
    assert (q.claims_caught, q.caught_facts, q.caught_wording, q.caught_missing_comparison) == (3, 1, 1, 1)
    assert q.by_language == {"en": 1, "es": 1}
    assert (q.live_runs, q.live_comments, q.live_rewrites, q.live_removed) == (1, 2, 1, 0)
    assert "Claims the Verifier sent back: 3" in describe(q)
