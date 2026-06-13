from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.cf_client import CodeforcesClient


async def mine(handles: list[str], out_path: Path) -> None:
    rows = []
    async with CodeforcesClient() as client:
        for handle in handles:
            try:
                info = (await client.user_info(handle))[0]
                rating = await client.user_rating(handle)
                submissions = await client.user_status(handle, count=2000)
            except Exception as exc:
                rows.append({"handle": handle, "error": str(exc)})
                continue
            accepted = [item for item in submissions if item.get("verdict") == "OK"]
            rows.append(
                {
                    "handle": handle,
                    "rating": info.get("rating"),
                    "max_rating": info.get("maxRating"),
                    "contests": len(rating),
                    "accepted_submissions": len(accepted),
                    "recent_solved_problem_keys": [
                        f"{item['problem'].get('contestId')}{item['problem'].get('index')}"
                        for item in accepted[:200]
                    ],
                }
            )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine a small similar-user cohort dataset.")
    parser.add_argument("handles", nargs="+", help="Codeforces handles to sample")
    parser.add_argument("--out", default="data/cohort_sample.json", help="Output JSON path")
    args = parser.parse_args()
    asyncio.run(mine(args.handles, Path(args.out)))


if __name__ == "__main__":
    main()

