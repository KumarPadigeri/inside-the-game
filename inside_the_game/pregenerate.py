"""Pre-generate verified recaps for the demo matches and save them to Cosmos DB.

Visitors then see recaps instantly, and generating live stays behind the
demo passcode. English by default; --languages adds others, --styles picks
personas and --focus personalizes (Home / Away or a player id).

Recaps that already exist are skipped, unless --refresh (regenerate them all)
or --redo-removed (only those that lost sentences) is given. Either way, a new
recap that removed more sentences than the saved one is thrown away.

Usage:
    python -m inside_the_game.pregenerate --count 5
    python -m inside_the_game.pregenerate --count 10 --refresh
    python -m inside_the_game.pregenerate --seed 5 --count 1 --languages es fr
    python -m inside_the_game.pregenerate --seed 5 --count 1 --styles fan --focus Away
"""

from __future__ import annotations

import argparse
import asyncio
import time

from inside_the_game.generator import Match, generate_match
from inside_the_game.narrator import LANGUAGES, STYLE_GUIDES, Language, Style
from inside_the_game.verifier import VerifiedRecap
from inside_the_game.store import Store
from inside_the_game.tracing import setup_tracing
from inside_the_game.workflow import run_recap


def keep_saved(saved: VerifiedRecap | None, new: VerifiedRecap) -> bool:
    """True if the saved recap is better: the new one had to remove more unproven sentences."""
    return saved is not None and len(new.removed) > len(saved.removed)


async def pregenerate(
    seeds: range,
    styles: list[Style],
    languages: list[Language],
    focus: str,
    refresh: bool,
    redo_removed: bool,
) -> None:
    await setup_tracing()
    async with Store() as store:
        for seed in seeds:
            match = generate_match(seed)
            for language in languages:
                for style in styles:
                    await _one(store, match, style, language, focus, refresh, redo_removed)


async def _one(
    store: Store, match: Match, style: Style, language: Language, focus: str, refresh: bool, redo_removed: bool
) -> None:
    """Generate and save one recap, unless a good one is already saved."""
    label = f"{match.match_id} {style} {language}{f' {focus}' if focus else ''}"
    saved = await store.get_recap(match.match_id, style, language, focus)
    if saved and not refresh and not (redo_removed and saved.removed):
        print(f"{label}: already saved", flush=True)
        return
    start = time.time()
    try:
        result = await run_recap(match, style, language, focus=focus)
    except Exception as error:  # noqa: BLE001 - keep going with the other recaps
        print(f"{label}: FAILED {error}", flush=True)
        return
    if keep_saved(saved, result):
        print(f"{label}: kept the old recap (new one removed more)", flush=True)
        return
    await store.save_recap(match.match_id, result)
    print(
        f"{label}: saved in {time.time() - start:.0f}s, rewrites={result.rewrites}, removed={len(result.removed)}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate verified recaps for the demo matches.")
    parser.add_argument("--count", type=int, default=5, help="number of matches, starting at --seed")
    parser.add_argument("--seed", type=int, default=1, help="seed of the first match")
    parser.add_argument("--styles", nargs="+", choices=list(STYLE_GUIDES), default=list(STYLE_GUIDES))
    parser.add_argument("--languages", nargs="+", choices=list(LANGUAGES), default=["en"])
    parser.add_argument("--focus", default="", help='personalize: "Home" / "Away" or a player id like H9')
    parser.add_argument("--refresh", action="store_true", help="regenerate recaps that are already saved")
    parser.add_argument("--redo-removed", action="store_true", help="regenerate saved recaps that lost sentences")
    args = parser.parse_args()
    asyncio.run(
        pregenerate(
            range(args.seed, args.seed + args.count),
            args.styles,
            args.languages,
            args.focus,
            args.refresh,
            args.redo_removed,
        )
    )


if __name__ == "__main__":
    main()
