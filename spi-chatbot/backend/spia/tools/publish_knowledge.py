"""Prepare approved document knowledge locally before deployment."""

from spia.core.paths import BACKEND_DIR

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(BACKEND_DIR / ".env", override=True)

    from spia.services.knowledge import EXPERTS, KnowledgeUnavailable, publish

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
        help="Prepare backend/data/published_knowledge for inclusion in a deployment",
    )

    review = parser.add_mutually_exclusive_group()
    review.add_argument("--inspect-upload")
    review.add_argument("--review-upload")

    parser.add_argument("--review-token")
    parser.add_argument(
        "--decision",
        choices=["approve", "block"],
    )
    parser.add_argument(
        "--classifications",
        nargs="+",
        default=[],
    )

    review.add_argument("--prepare-upload")
    args = parser.parse_args()


    if args.prepare_upload:
        if (
            args.portable
            or args.expert != "all"
            or args.review_token
            or args.decision
            or args.classifications
        ):
            parser.error(
                "Use --prepare-upload on its own"
            )

        from spia.services.knowledge import (
            prepare_uploaded_document,
        )

        try:
            result = prepare_uploaded_document(
                args.prepare_upload
            )

            print(json.dumps(result, indent=2))
            return 0

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ) as exc:
            print(f"PREPARATION FAILED: {exc}")
            return 1

    if args.inspect_upload or args.review_upload:
        if args.portable or args.expert != "all":
            parser.error(
                "Upload review cannot be combined "
                "with expert publishing"
            )

        from spia.services.knowledge import (
            inspect_uploaded_document,
            review_uploaded_document,
        )

        try:
            if args.inspect_upload:
                result = inspect_uploaded_document(
                    args.inspect_upload
                )
            else:
                if not args.review_token or not args.decision:
                    parser.error(
                        "Review requires --review-token "
                        "and --decision"
                    )

                result = review_uploaded_document(
                    args.review_upload,
                    args.review_token,
                    args.decision,
                    args.classifications,
                )

            print(json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            ))
            return 0

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ) as exc:
            print(f"REVIEW FAILED: {exc}")
            return 1

    if (
        args.review_token
        or args.decision
        or args.classifications
    ):
        parser.error(
            "Review options require --review-upload"
        )


    if args.portable:
        os.environ["SPIA_PUBLISHED_DIR"] = "data/published_knowledge"

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
        print("PASS: portable publication prepared in data/published_knowledge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())