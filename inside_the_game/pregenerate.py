"""Pre-generate verified recaps for the demo matches and save them to Cosmos DB.

Visitors then see recaps instantly, and generating live stays behind the
demo passcode. Recaps that already exist are skipped, unless --redo-removed
is given and the saved recap had sentences removed by the Verifier.

Usage:
    python -m inside_the_game.pregenerate --count 5
    python -m inside_the_game.pregenerate --count 5 --redo-removed
"""

from __future__ import annotations

import argparse
import asyncio
import time

from inside_the_game.generator import generate_match
from inside_the_game.narrator import STYLE_GUIDES
from inside_the_game.store import Store
from inside_the_game.tracing import setup_tracing
from inside_the_game.workflow import run_recap


async def pregenerate(seeds: range, redo_removed: bool) -> None:
    await setup_tracing()
    async with Store() as store:
        for seed in seeds:
            match = generate_match(seed)
            for style in STYLE_GUIDES:
                saved = await store.get_recap(match.match_id, style)
                if saved and not (redo_removed and saved.removed):
                    print(f"{match.match_id} {style}: already saved", flush=True)
                    continue
                start = time.time()
                try:
                    result = await run_recap(match, style)
                except Exception as error:  # noqa: BLE001 - keep going with the other recaps
                    print(f"{match.match_id} {style}: FAILED {error}", flush=True)
                    continue
                if saved and len(result.removed) > len(saved.removed):
                    print(f"{match.match_id} {style}: kept the old recap (new one removed more)", flush=True)
                    continue
                await store.save_recap(match.match_id, result)
                print(
                    f"{match.match_id} {style}: saved in {time.time() - start:.0f}s, "
                    f"rewrites={result.rewrites}, removed={len(result.removed)}",
                    flush=True,
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate verified recaps for the demo matches.")
    parser.add_argument("--count", type=int, default=5, help="number of matches, starting at --seed")
    parser.add_argument("--seed", type=int, default=1, help="seed of the first match")
    parser.add_argument("--redo-removed", action="store_true", help="regenerate saved recaps that lost sentences")
    args = parser.parse_args()
    asyncio.run(pregenerate(range(args.seed, args.seed + args.count), args.redo_removed))


if __name__ == "__main__":
    main()
