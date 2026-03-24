from __future__ import annotations

import argparse
import json

from tests.resource_manager import ResourceManager


def main():
    parser = argparse.ArgumentParser(description="testing_xuexi utility CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("prepare")
    subparsers.add_parser("cleanup")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--marker", default="smoke")

    args = parser.parse_args()

    if args.command == "prepare":
        context = ResourceManager.prepare_environment()
        print(json.dumps(context.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "cleanup":
        ResourceManager.cleanup_environment()
        print("cleanup done")
    elif args.command == "run":
        print(f"Use pytest -m {args.marker}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
