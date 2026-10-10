from __future__ import annotations

import unittest
from unittest.mock import patch

from benchmarks import run_performance


class PerformanceHarnessTests(unittest.TestCase):
    def test_stable_but_wrong_checker_status_is_rejected(self):
        with patch.object(run_performance, "check", return_value={"status": "WRONG_BUT_STABLE"}):
            with self.assertRaisesRegex(RuntimeError, "unexpected warm-up status"):
                run_performance.run(repeats=1)

    def test_workload_registry_has_a_frozen_expected_status_for_every_workload(self):
        self.assertEqual(set(run_performance.workloads()), set(run_performance.EXPECTED_RESULT_STATUS))
        self.assertTrue(all(status == "REFUTED_FOR_FORMALIZATION"
                            for status in run_performance.EXPECTED_RESULT_STATUS.values()))


if __name__ == "__main__":
    unittest.main()
