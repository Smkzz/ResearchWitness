"""Command line interface. No network or model calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .policy import CustodyError, preflight
from .store import (
    make_store, import_batch, verify_all, record_review, seal_inventory,
    summarize, export_public_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rw-custody", description="Offline source-only ResearchWitness custody tool")
    parser.add_argument("--dev-root", type=Path, metavar="SYNTHETIC_DIRECTORY",
                        help="synthetic tests only; must be a marked child of the system temp directory")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "init", "verify", "seal", "summary", "export-summary"):
        commands.add_parser(name)
    imp = commands.add_parser("import")
    imp.add_argument("--batch-id", required=True)
    rev = commands.add_parser("record-review")
    rev.add_argument("--review-id", required=True)
    try:
        args = parser.parse_args(argv)
        root = preflight(dev_root=args.dev_root)
        if args.command == "doctor":
            result = {"preflight": "PASS",
                      "mode": "SYNTHETIC_DEVELOPMENT" if args.dev_root else "CUSTODIAN_PRODUCTION",
                      "network_calls": "NOT_IMPLEMENTED",
                      "host_egress": "MUST_BE_VERIFIED_EXTERNALLY",
                      "detector_execution": "NOT_IMPLEMENTED"}
        elif args.command == "init":
            make_store(root)
            result = {"status": "INITIALIZED"}
        elif args.command == "import":
            result = import_batch(root, args.batch_id)
        elif args.command == "record-review":
            result = record_review(root, args.review_id)
        elif args.command == "verify":
            result = {"status": "VERIFIED", **verify_all(root)}
        elif args.command == "seal":
            result = seal_inventory(root)
        elif args.command == "summary":
            result = summarize(root)
        else:
            result = export_public_summary(root)
    except CustodyError as exc:
        print(json.dumps({"status": "ERROR", "code": str(exc)}, sort_keys=True))
        return 2
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        # Never put private identifiers, file paths or source data in logs.
        print(json.dumps({"status": "ERROR", "code": "INTERNAL_OPERATION_FAILED"}))
        return 3
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
