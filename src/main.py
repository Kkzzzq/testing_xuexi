from __future__ import annotations

import argparse
import json

import pytest

from tests.context import TestContext
from tests.resource_manager import prepare_session_resources, safe_cleanup


def context_to_dict(context: TestContext) -> dict:
    return {
        "organization": {
            "org_id": context.organizations.org_id,
            "org_name": context.organizations.org_name,
        },
        "dashboard": {
            "folder_uid": context.dashboards.folder_uid,
            "dashboard_uid": context.dashboards.dashboard_uid,
            "title": context.dashboards.title,
        },
        "users": {
            "existing_user_id": context.users.existing_user_id,
            "low_access_user_id": context.users.low_access_user_id,
            "organizations_user_id": context.users.organizations_user_id,
        },
    }


def prepare_resources(cleanup: bool = False) -> dict:
    context = TestContext()
    prepare_session_resources(context)
    prepared = context_to_dict(context)

    if cleanup:
        safe_cleanup(context)

    return prepared


def run_tests(marker: str | None = None, keyword: str | None = None) -> int:
    args = ["tests", "-v", "-s", "--tb=short"]

    if marker:
        args.extend(["-m", marker])

    if keyword:
        args.extend(["-k", keyword])

    return pytest.main(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="testing_xuexi CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run pytest suites")
    run_parser.add_argument(
        "--marker",
        help="pytest marker, e.g. PositiveApi / NegativeApi / sql / NegativeDashboard",
    )
    run_parser.add_argument(
        "--keyword",
        help="pytest -k expression",
    )

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Prepare base API test data and print created ids",
    )
    prepare_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean created resources after printing ids",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        return run_tests(marker=args.marker, keyword=args.keyword)

    if args.command == "prepare":
        prepared = prepare_resources(cleanup=args.cleanup)
        print(json.dumps(prepared, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
