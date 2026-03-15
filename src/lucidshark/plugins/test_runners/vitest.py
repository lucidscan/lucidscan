"""Vitest test runner plugin.

Vitest is a blazing fast unit test framework powered by Vite.
https://vitest.dev/
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext, SkipReason, ToolDomain
from lucidshark.plugins.test_runners.base import TestRunnerPlugin, TestResult
from lucidshark.plugins.utils import ensure_node_binary

LOGGER = get_logger(__name__)


class VitestRunner(TestRunnerPlugin):
    """Vitest test runner plugin for JavaScript/TypeScript test execution."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize VitestRunner.

        Args:
            project_root: Optional project root for finding Vitest installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "vitest"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    def ensure_binary(self) -> Path:
        """Ensure Vitest is available."""
        return ensure_node_binary(
            self._project_root,
            "vitest",
            "Vitest is not installed. Install it with:\n"
            "  npm install vitest --save-dev\n"
            "  OR\n"
            "  npm install -g vitest",
        )

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run Vitest on the specified paths.

        Always runs with --coverage to generate coverage data.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "vitest-results.json"

            cmd = [
                str(binary),
                "run",  # Non-watch mode
                "--reporter=json",
                f"--outputFile={report_file}",
                "--passWithNoTests",  # Don't fail if no tests found
                "--coverage",  # Always generate coverage data
            ]

            if context.paths:
                paths = [str(p) for p in context.paths]
                cmd.extend(paths)

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(context.project_root),
                    timeout=600,
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("Vitest timed out after 600 seconds")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.TESTING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message="Vitest timed out after 600 seconds",
                )
                return TestResult()
            except Exception as e:
                LOGGER.error(f"Failed to run Vitest: {e}")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.TESTING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Failed to run Vitest: {e}",
                )
                return TestResult()

            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root)
            else:
                return self._parse_json_output(result.stdout, context.project_root)

    def _parse_json_report(
        self,
        report_file: Path,
        project_root: Path,
    ) -> TestResult:
        """Parse Vitest JSON report file.

        Delegates to base class _parse_json_report_file.
        """
        return self._parse_json_report_file(report_file, project_root)

    def _process_report(
        self,
        report,
        project_root,
    ) -> TestResult:
        """Process Vitest JSON report (Jest-compatible format)."""
        return self._process_jest_report(report, project_root)
