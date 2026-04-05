from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from tests.resource_manager import ResourceManager

BASE_DIR = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grafana test automation utility CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("prepare", help="Create shared test resources")
    subparsers.add_parser("cleanup", help="Delete shared test resources")

    run_parser = subparsers.add_parser("run", help="Run pytest")
    run_parser.add_argument("--marker", default=None, help="pytest marker expression")
    run_parser.add_argument("--alluredir", default=None, help="Allure output directory")
    run_parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="extra pytest args")

    return parser


def run_pytest(marker: str | None, alluredir: str | None, pytest_args: list[str]) -> int:
    command = [sys.executable, "-m", "pytest", str(BASE_DIR / "tests")]
    if marker:
        command.extend(["-m", marker])
    if alluredir:
        command.append(f"--alluredir={alluredir}")
    if pytest_args:
        command.extend(pytest_args)
    return subprocess.call(command, cwd=BASE_DIR)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "prepare":
        context = ResourceManager.prepare_environment()
        print(json.dumps(context.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "cleanup":
        ResourceManager.cleanup_environment()
        print("cleanup done")
        return 0

    if args.command == "run":
        return run_pytest(args.marker, args.alluredir, args.pytest_args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
