"""Pre-generate verified recaps for the demo matches and save them to Cosmos DB.

Visitors then see recaps instantly, and generating live stays behind the
demo passcode. English by default; --languages adds others. Recaps that already exist are skipped, unless --redo-removed
is given and the saved recap had sentences removed by the Verifier.

Usage:
    python -m inside_the_game.pregenerate --count 5
    python -m inside_the_game.pregenerate --count 5 --redo-removed
    python -m inside_the_game.pregenerate --count 3 --languages es fr
"""

from __future__ import annotations

import argparse
import asyncio
import time

from inside_the_game.generator import Match, generate_match
from inside_the_game.narrator import LANGUAGES, STYLE_GUIDES, Language, Style
from inside_the_game.store import Store
from inside_the_game.tracing import setup_tracing
from inside_the_game.workflow import run_recap


async def pregenerate(seeds: range, redo_removed: bool, languages: list[Language]) -> None:
    await setup_tracing()
    async with Store() as store:
        for seed in seeds:
            match = generate_match(seed)
            for language in languages:
                for style in STYLE_GUIDES:
                    await _one(store, match, style, language, redo_removed)


async def _one(store: Store, match: Match, style: Style, language: Language, redo_removed: bool) -> None:
    """Generate and save one recap, unless a good one is already saved."""
    label = f"{match.match_id} {style} {language}"
    saved = await store.get_recap(match.match_id, style, language)
    if saved and not (redo_removed and saved.removed):
        print(f"{label}: already saved", flush=True)
        return
    start = time.time()
    try:
        result = await run_recap(match, style, language)
    except Exception as error:  # noqa: BLE001 - keep going with the other recaps
        print(f"{label}: FAILED {error}", flush=True)
        return
    if saved and len(result.removed) > len(saved.removed):
        print(f"{label}: kept the old recap (new one removed more)", flush=True)
        return
    await store.save_recap(match.match_id, result)
    print(
        f"{label}: saved in {time.time() - start:.0f}s, "
        f"rewrites={result.rewrites}, removed={len(result.removed)}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate verified recaps for the demo matches.")
    parser.add_argument("--count", type=int, default=5, help="number of matches, starting at --seed")
    parser.add_argument("--seed", type=int, default=1, help="seed of the first match")
    parser.add_argument("--redo-removed", action="store_true", help="regenerate saved recaps that lost sentences")
    parser.add_argument("--languages", nargs="+", choices=list(LANGUAGES), default=["en"])
    args = parser.parse_args()
    asyncio.run(pregenerate(range(args.seed, args.seed + args.count), args.redo_removed, args.languages))


if __name__ == "__main__":
    main()
