from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import discover_public_candidates
from tools.public_discovery import (
    MAX_REGISTRY_CANDIDATES,
    MAX_REGISTRY_INPUT_BYTES,
    MAX_REGISTRY_SEARCHES,
    merge_candidates,
    registry_with_search,
    validate_registry_document,
)


def empty_registry() -> dict[str, object]:
    return {
        "schema_version": 1,
        "updated_utc": "2026-10-16T00:00:00Z",
        "workflow_status": "not_run",
        "scope": "developer_exposed_public_source_candidates_only",
        "searches": [],
        "candidates": [],
    }


class RegistryInputBoundsTests(unittest.TestCase):
    def test_validator_and_merger_bound_candidate_and_search_counts(self) -> None:
        too_many_candidates = empty_registry()
        too_many_candidates["candidates"] = [None] * (MAX_REGISTRY_CANDIDATES + 1)
        with self.assertRaisesRegex(ValueError, "candidate limit"):
            validate_registry_document(too_many_candidates)
        with self.assertRaisesRegex(ValueError, "candidate limit"):
            merge_candidates([{}] * (MAX_REGISTRY_CANDIDATES + 1))

        too_many_searches = empty_registry()
        too_many_searches["searches"] = [None] * (MAX_REGISTRY_SEARCHES + 1)
        with self.assertRaisesRegex(ValueError, "search limit"):
            validate_registry_document(too_many_searches)
        with self.assertRaisesRegex(ValueError, "search limit"):
            registry_with_search([], [{}] * (MAX_REGISTRY_SEARCHES + 1))

    def test_registry_schema_matches_runtime_count_limits(self) -> None:
        schema_path = Path(__file__).parents[1] / "researchwitness" / "schemas" / "scientific-candidate-registry.v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["candidates"]["maxItems"], MAX_REGISTRY_CANDIDATES)
        self.assertEqual(schema["properties"]["searches"]["maxItems"], MAX_REGISTRY_SEARCHES)

    def test_oversized_existing_registry_is_rejected_before_source_client_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            oversized = Path(directory) / "oversized.json"
            oversized.write_bytes(b" " * (MAX_REGISTRY_INPUT_BYTES + 1))
            with (
                patch.object(discover_public_candidates, "PublicSourceClient") as client,
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                discover_public_candidates.main([
                    "discover", "--provider", "europe-pmc", "--output",
                    str(Path(directory) / "output.json"), "--existing", str(oversized),
                ])
            self.assertEqual(raised.exception.code, 2)
            client.assert_not_called()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO inputs are POSIX-specific")
    def test_fifo_existing_registry_is_rejected_without_blocking_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "registry.fifo"
            os.mkfifo(fifo)
            with (
                patch.object(discover_public_candidates, "PublicSourceClient") as client,
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                discover_public_candidates.main([
                    "discover", "--provider", "europe-pmc", "--output",
                    str(Path(directory) / "output.json"), "--existing", str(fifo),
                ])
            self.assertEqual(raised.exception.code, 2)
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
