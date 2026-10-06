"""Tests for the workflow wiring and rewrite loop, with the agents replaced by fakes (no LLM calls)."""

import asyncio

import pytest

from inside_the_game import analyst, narrator, retrieval, verifier
from inside_the_game.analyst import AnalystReport, Finding
from inside_the_game.generator import Match, generate_match
from inside_the_game.moments import Comparison, extract_moments
from inside_the_game.narrator import Recap, RecapSentence, Style
from inside_the_game.verifier import MAX_REWRITES, SentenceVerdict
from inside_the_game.workflow import run_recap

FAKE_REPORT = AnalystReport(findings=[Finding(claim="Home won.", tool="get_match_info", event_ids=[])])
MATCH = generate_match(5)
MOMENT = extract_moments(MATCH)[0]
COMPARISON = Comparison(claim="Like another match.", moment=MOMENT, similar=[], event_ids=MOMENT.event_ids)


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    verdict_rounds: list[list[bool]],
    comparisons: list[Comparison] | Exception | None = None,
    narrator_cites_comparisons: bool = True,
) -> tuple[list[str], dict[str, object]]:
    """Replace the four agents with fakes. Each verify call uses the next round of verdicts.

    Returns the order of agent calls, and what the fakes received.
    """
    calls: list[str] = []
    seen: dict[str, object] = {}

    async def fake_retrieve(match: Match) -> list[Comparison]:
        calls.append("retrieve")
        if isinstance(comparisons, Exception):
            raise comparisons
        return comparisons or []

    async def fake_analyse(match: Match) -> AnalystReport:
        calls.append("analyse")
        return FAKE_REPORT

    async def fake_narrate(match: Match, report: AnalystReport, style: Style, feedback: str | None = None) -> Recap:
        calls.append("rewrite" if feedback else "narrate")
        assert report.findings[0] == FAKE_REPORT.findings[0]  # the Analyst's output reached the Narrator
        seen["findings"] = [f.claim for f in report.findings]
        n = calls.count("narrate") + calls.count("rewrite")
        tools = ["get_match_info"]
        if narrator_cites_comparisons and any(f.tool == retrieval.TOOL_NAME for f in report.findings):
            tools.append(retrieval.TOOL_NAME)
        sentence = RecapSentence(text=f"Draft {n}.", finding_ids=[1], event_ids=[], tools=tools)
        return Recap(style=style, headline=sentence, sentences=[sentence])

    async def fake_verify(match: Match, recap: Recap, comparisons: list[Comparison] | None = None) -> list[SentenceVerdict]:
        calls.append("verify")
        seen["verifier_comparisons"] = comparisons
        supported = verdict_rounds.pop(0)
        return [SentenceVerdict(sentence=n, supported=ok, problem="" if ok else "wrong") for n, ok in enumerate(supported)]

    monkeypatch.setattr(analyst, "analyse", fake_analyse)
    monkeypatch.setattr(narrator, "narrate", fake_narrate)
    monkeypatch.setattr(verifier, "verify", fake_verify)
    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
    return calls, seen


def test_approved_first_draft_needs_no_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, _ = _install_fakes(monkeypatch, [[True, True]])
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert sorted(calls[:2]) == ["analyse", "retrieve"]  # parallel, so either order
    assert calls[2:] == ["narrate", "verify"]
    assert result.rewrites == 0
    assert result.removed == []
    assert result.rejections == []
    assert result.recap.headline.text == "Draft 1."


def test_rejected_draft_goes_back_to_the_narrator(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, _ = _install_fakes(monkeypatch, [[True, False], [True, True]])
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert calls[2:] == ["narrate", "verify", "rewrite", "verify"]
    assert result.rewrites == 1
    assert result.recap.sentences[0].text == "Draft 2."
    assert [(r.draft, r.text) for r in result.rejections] == [(0, "Draft 1.")]


def test_loop_stops_after_max_rewrites_and_drops_what_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, _ = _install_fakes(monkeypatch, [[True, False]] * (MAX_REWRITES + 1))
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert calls.count("rewrite") == MAX_REWRITES
    assert calls.count("verify") == MAX_REWRITES + 1
    assert result.rewrites == MAX_REWRITES
    assert result.recap.sentences == []
    assert [r.problem for r in result.removed] == ["wrong"]
    # Every draft except the last was sent back; the last one's failures were removed instead.
    assert [r.draft for r in result.rejections] == list(range(MAX_REWRITES))


def test_comparisons_reach_the_narrator_verifier_and_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _, seen = _install_fakes(monkeypatch, [[True, True]], comparisons=[COMPARISON])
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert seen["findings"] == ["Home won.", "Like another match."]
    assert seen["verifier_comparisons"] == [COMPARISON]
    assert result.comparisons == [COMPARISON]


def test_retrieval_failure_still_produces_a_recap(monkeypatch: pytest.MonkeyPatch) -> None:
    _, seen = _install_fakes(monkeypatch, [[True, True]], comparisons=RuntimeError("Cosmos is down"))
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert seen["findings"] == ["Home won."]
    assert result.comparisons == []
    assert result.recap.headline.text == "Draft 1."


def test_recap_without_any_comparison_is_sent_back(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, _ = _install_fakes(
        monkeypatch, [[True, True]] * (MAX_REWRITES + 1), comparisons=[COMPARISON], narrator_cites_comparisons=False
    )
    result = asyncio.run(run_recap(MATCH, "fan"))
    assert calls.count("rewrite") == MAX_REWRITES  # sent back each time, then accepted as is
    assert [r.text for r in result.rejections] == ["(whole recap)"] * MAX_REWRITES
    assert result.removed == []  # every sentence was still true
