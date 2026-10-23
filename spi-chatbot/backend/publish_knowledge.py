"""Prepare approved document knowledge locally before deployment."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

    from published_knowledge import EXPERTS, KnowledgeUnavailable, publish

    parser = argparse.ArgumentParser(
        description="Publish approved document knowledge"
    )
    parser.add_argument(
        "--expert",
        choices=["all", *EXPERTS],
        default="all",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="Prepare backend/published_demo for inclusion in a deployment",
    )
    args = parser.parse_args()

    if args.portable:
        os.environ["SPIA_PUBLISHED_DIR"] = "published_demo"

    names = EXPERTS if args.expert == "all" else (args.expert,)

    try:
        for name in names:
            result = publish(name)
            print(
                f"PUBLISHED: {name}; "
                f"sections={result['published_sections']}; "
                f"reused_documents={result['reused_documents']}; "
                f"rebuilt_documents={result['rebuilt_documents']}; "
                f"removed_documents={result['removed_documents']}"
            )
    except (KnowledgeUnavailable, OSError, ValueError, RuntimeError) as exc:
        print(f"PUBLISH FAILED: {exc}")
        return 1

    print("PASS: requested document experts published")
    if args.portable:
        print("PASS: portable publication prepared in published_demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())