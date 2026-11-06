"""工程检查必须拒绝实际失败，并覆盖声明的源码域。"""
from __future__ import annotations

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_network_isolation as network  # noqa: E402
import ci  # noqa: E402


class EngineeringGatesTest(unittest.TestCase):
    def test_network_check_fails_for_failed_tests_without_outbound_requests(self) -> None:
        for failed in (False, True):
            result = unittest.TestResult()
            result.testsRun = 1
            if failed:
                result.failures.append((self, "simulated assertion failure"))
            with mock.patch.object(network, "run_suite", return_value=result), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(network.main([]), int(failed))

    def test_ci_timeout_is_a_failed_step(self) -> None:
        with mock.patch.object(ci.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("fixture", 60)):
            status, message = ci._run("timeout fixture", ["fixture"], 1)
        self.assertEqual(status, "failed")
        self.assertIn("时限", message)

    def test_coverage_configuration_includes_all_handwritten_domains(self) -> None:
        import coverage

        config = coverage.Coverage(config_file=str(ROOT / "pyproject.toml"))
        self.assertEqual(set(config.get_option("run:source")), {"agent", "plugins", "scripts"})
        self.assertTrue(config.get_option("run:branch"))
