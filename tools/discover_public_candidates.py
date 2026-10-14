#!/usr/bin/env python3
"""Search approved metadata APIs and write a developer-exposed candidate registry."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.public_discovery import (
    DEFAULT_CROSSREF_QUERY,
    DEFAULT_EUROPE_PMC_QUERY,
    InvalidSourceResponse,
    PublicSourceClient,
    SourceAccessError,
    empty_registry,
    failed_search_record,
    invalid_response_search_record,
    registry_with_search,
    search_crossref,
    search_europe_pmc,
    summarize_registry,
    merge_candidates,
    validate_registry_document,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temp:
            temp_path = Path(temp.name)
            temp.write(text)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="search one approved metadata API")
    discover.add_argument("--provider", choices=("europe-pmc", "crossref"), required=True)
    discover.add_argument("--query")
    discover.add_argument("--limit", type=int, default=25)
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument("--existing", type=Path, help="merge a previous registry without changing its provenance")

    summarize = sub.add_parser("summarize", help="print aggregate counts from a registry")
    summarize.add_argument("registry", type=Path)

    args = parser.parse_args(argv)
    if args.command == "summarize":
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        validate_registry_document(registry)
        print(json.dumps(summarize_registry(registry), indent=2, sort_keys=True))
        return 0

    query = args.query or (
        DEFAULT_EUROPE_PMC_QUERY if args.provider == "europe-pmc" else DEFAULT_CROSSREF_QUERY
    )
    previous = json.loads(args.existing.read_text(encoding="utf-8")) if args.existing else empty_registry()
    validate_registry_document(previous)
    client = PublicSourceClient()
    try:
        candidates, search = (
            search_europe_pmc(client, query, args.limit)
            if args.provider == "europe-pmc"
            else search_crossref(client, query, args.limit)
        )
    except SourceAccessError as exc:
        provider = "europe_pmc" if args.provider == "europe-pmc" else "crossref"
        failed = failed_search_record(provider, query, exc)
        searches = [*previous.get("searches", []), failed]
        registry = registry_with_search(previous.get("candidates", []), searches)
        if (not previous.get("searches") and not previous.get("candidates")
                and failed["status"] == "transport_failed_before_http_response"):
            registry["workflow_status"] = "blocked_before_source_response"
        _write_json(args.output, registry)
        print(json.dumps({
            "status": failed["status"],
            "host": exc.host,
            "status_code": exc.status_code,
            "reason": exc.reason,
            "retry": False,
            "registry_written": str(args.output),
        }), file=sys.stderr)
        return 2
    except InvalidSourceResponse as exc:
        provider = "europe_pmc" if args.provider == "europe-pmc" else "crossref"
        failed = invalid_response_search_record(provider, query, exc)
        searches = [*previous.get("searches", []), failed]
        registry = registry_with_search(previous.get("candidates", []), searches)
        _write_json(args.output, registry)
        print(json.dumps({
            "status": "invalid_response",
            "host": exc.response["host"],
            "reason": exc.reason,
            "retry": False,
            "registry_written": str(args.output),
        }), file=sys.stderr)
        return 3

    if previous.get("searches") or previous.get("candidates"):
        all_candidates = merge_candidates(previous.get("candidates", []), candidates)
        registry = registry_with_search(
            all_candidates,
            [*(previous.get("searches", [])), search],
        )
    else:
        registry = registry_with_search(candidates, [search])
    _write_json(args.output, registry)
    print(json.dumps(summarize_registry(registry), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
