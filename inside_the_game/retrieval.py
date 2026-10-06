"""Retrieval agent: compares this match's key moments with similar moments elsewhere.

The agent calls two tools: one lists this match's goals and counterattacks,
the other runs a Cosmos DB vector search for similar moments in other
synthetic matches. It cites moment_ids; code checks that each one was really
returned by a tool and attaches the moments as evidence.

Usage:
    python -m inside_the_game.retrieval --seed 5
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Annotated, Any

from agent_framework import Agent, FunctionTool, tool
from pydantic import BaseModel, Field

from inside_the_game.analyst import Finding
from inside_the_game.foundry import embed_texts, make_client
from inside_the_game.generator import Match, generate_match
from inside_the_game.moments import SIMILAR_MOMENTS_TOOL, Comparison, Moment, SimilarMoment, extract_moments
from inside_the_game.store import Store

TOOL_NAME = SIMILAR_MOMENTS_TOOL

INSTRUCTIONS = """\
You add historical context to a football match recap by comparing its key
moments with similar moments from other (synthetic) matches.

1. Call list_key_moments to see this match's goals and counterattacks.
2. Pick the 2-3 moments that mattered most (goals that changed the result
   first, then counterattacks) and call find_similar_moments for each.
3. Write 1-3 comparisons, each one short sentence linking a moment of this
   match to one or more similar moments, e.g. "H11's 80th-minute counterattack
   winner echoed a similar break in Westfield Wanderers v Oakhurst Albion (38')."

Rules:
- Use only facts from the tool results. Name other matches as "Home v Away".
- Never write moment_ids in the sentence itself; cite them in the fields.
- Describe each similar moment only with facts from ITS OWN result: do not
  call it "late", a "winner" or "lead-changing" unless its minute, kind and
  score show that. Give the minute of each similar moment you mention.
- Do not claim records, trends or frequencies ("the most", "often", "always").
- Cite the moment_id from list_key_moments and the similar_moment_ids from
  find_similar_moments that the sentence relies on.
- If nothing is meaningfully similar, return no comparisons.
"""


class ComparisonDraft(BaseModel):
    claim: str = Field(description="One short sentence comparing a moment with similar ones.")
    moment_id: str = Field(description="The moment_id from list_key_moments.")
    similar_moment_ids: list[str] = Field(min_length=1, description="moment_ids from find_similar_moments.")


class RetrievalOutput(BaseModel):
    comparisons: list[ComparisonDraft]


def _team_name(moment: Moment) -> str:
    return moment.home_team if moment.team == "Home" else moment.away_team


def _moment_view(moment: Moment) -> dict[str, Any]:
    """What the agent sees of a moment (team names resolved, no event lists)."""
    return {
        "moment_id": moment.moment_id,
        "match": f"{moment.home_team} v {moment.away_team}",
        "team": _team_name(moment),
        "kind": moment.kind,
        "minute": moment.minute,
        "score_after": moment.score_after,
        "description": moment.description,
    }


def build_tools(match: Match, store: Store, found: dict[str, SimilarMoment]) -> list[FunctionTool]:
    """Tools for one match. Every similar moment returned is recorded in `found`."""
    moments = {m.moment_id: m for m in extract_moments(match)}

    def list_key_moments() -> list[dict[str, Any]]:
        """This match's goals and counterattacks, in order, with moment_ids."""
        return [_moment_view(m) for m in moments.values()]

    async def find_similar_moments(
        moment_id: Annotated[str, "A moment_id from list_key_moments."],
    ) -> list[dict[str, Any]] | dict[str, str]:
        """The 3 most similar moments of the same kind from other synthetic matches."""
        moment = moments.get(moment_id)
        if moment is None:
            return {"error": f"Unknown moment_id {moment_id!r}. Use one from list_key_moments."}
        [vector] = await embed_texts([moment.description])
        results = [
            SimilarMoment.model_validate(r)
            for r in await store.similar_to(vector, kind=moment.kind, exclude_match_id=match.match_id)
        ]
        found.update({r.moment_id: r for r in results})
        return [{**_moment_view(r), "similarity": round(r.similarity, 3)} for r in results]

    return [tool(list_key_moments), tool(find_similar_moments, name=TOOL_NAME)]


def resolve_comparisons(output: RetrievalOutput, match: Match, found: dict[str, SimilarMoment]) -> list[Comparison]:
    """Attach the real moments to each comparison; reject ids no tool returned."""
    moments = {m.moment_id: m for m in extract_moments(match)}
    comparisons: list[Comparison] = []
    for draft in output.comparisons:
        if draft.moment_id not in moments:
            raise ValueError(f"Comparison cites unknown moment {draft.moment_id!r}: {draft.claim!r}")
        unknown = [i for i in draft.similar_moment_ids if i not in found]
        if unknown:
            raise ValueError(f"Comparison cites moments no search returned {unknown}: {draft.claim!r}")
        moment = moments[draft.moment_id]
        comparisons.append(
            Comparison(
                claim=draft.claim,
                moment=moment,
                similar=[found[i] for i in draft.similar_moment_ids],
                event_ids=moment.event_ids,
            )
        )
    return comparisons


def comparisons_as_findings(comparisons: list[Comparison]) -> list[Finding]:
    """Comparisons in the same shape as the Analyst's findings, for the Narrator."""
    return [Finding(claim=c.claim, tool=TOOL_NAME, event_ids=c.event_ids) for c in comparisons]


async def retrieve(match: Match) -> list[Comparison]:
    """Run the Retrieval agent on a match and return its validated comparisons."""
    found: dict[str, SimilarMoment] = {}
    async with Store() as store:
        agent = Agent(
            client=make_client(),
            name="Retrieval",
            instructions=INSTRUCTIONS,
            tools=build_tools(match, store, found),
            default_options={"response_format": RetrievalOutput},
        )
        response = await agent.run("Find comparisons for this match.")
    output = response.value
    if output is None:
        raise ValueError(f"Retrieval returned no structured comparisons: {response.text!r}")
    return resolve_comparisons(output, match, found)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Retrieval agent on a synthetic match.")
    parser.add_argument("--seed", type=int, default=1, help="which synthetic match")
    args = parser.parse_args()

    match = generate_match(args.seed)
    for comparison in asyncio.run(retrieve(match)):
        print(f"- {comparison.claim}\n    this match: {comparison.moment.moment_id} events {comparison.event_ids}")
        for similar in comparison.similar:
            print(f"    similar ({similar.similarity:.3f}): {similar.moment_id} {similar.home_team} v {similar.away_team}")


if __name__ == "__main__":
    main()
