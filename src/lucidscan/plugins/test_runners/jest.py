"""Jest test runner plugin.

Jest is a delightful JavaScript Testing Framework.
https://jestjs.io/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidscan.core.logging import get_logger
from lucidscan.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidscan.plugins.test_runners.base import TestRunnerPlugin, TestResult

LOGGER = get_logger(__name__)


class JestRunner(TestRunnerPlugin):
    """Jest test runner plugin for JavaScript/TypeScript test execution."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize JestRunner.

        Args:
            project_root: Optional project root for finding Jest installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "jest"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    def get_version(self) -> str:
        """Get Jest version.

        Returns:
            Version string or 'unknown' if unable to determine.
        """
        try:
            binary = self.ensure_binary()
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            # Output is just the version number like "29.7.0"
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure Jest is available.

        Checks for Jest in:
        1. Project's node_modules/.bin/jest
        2. System PATH (globally installed)

        Returns:
            Path to Jest binary.

        Raises:
            FileNotFoundError: If Jest is not installed.
        """
        # Check project node_modules first
        if self._project_root:
            node_jest = self._project_root / "node_modules" / ".bin" / "jest"
            if node_jest.exists():
                return node_jest

        # Check system PATH
        jest_path = shutil.which("jest")
        if jest_path:
            return Path(jest_path)

        raise FileNotFoundError(
            "Jest is not installed. Install it with:\n"
            "  npm install jest --save-dev\n"
            "  OR\n"
            "  npm install -g jest"
        )

    def run_tests(
        self, context: ScanContext, with_coverage: bool = False
    ) -> TestResult:
        """Run Jest on the specified paths.

        Args:
            context: Scan context with paths and configuration.
            with_coverage: If True, run tests with coverage instrumentation.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "jest-results.json"

            cmd = [
                str(binary),
                "--json",
                f"--outputFile={report_file}",
                "--passWithNoTests",  # Don't fail if no tests found
            ]

            # Add coverage flag if requested
            if with_coverage:
                cmd.append("--coverage")

            # Add paths to test if specified
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
                    timeout=600,  # 10 minute timeout for test runs
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("Jest timed out after 600 seconds")
                return TestResult()
            except Exception as e:
                LOGGER.error(f"Failed to run Jest: {e}")
                return TestResult()

            # Parse JSON report
            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root)
            else:
                # Jest might output JSON to stdout if no outputFile
                return self._parse_json_output(result.stdout, context.project_root)

    def _parse_json_report(
        self,
        report_file: Path,
        project_root: Path,
    ) -> TestResult:
        """Parse Jest JSON report file.

        Args:
            report_file: Path to JSON report file.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        try:
            with open(report_file) as f:
                report = json.load(f)
        except Exception as e:
            LOGGER.error(f"Failed to parse Jest JSON report: {e}")
            return TestResult()

        return self._process_report(report, project_root)

    def _parse_json_output(
        self,
        output: str,
        project_root: Path,
    ) -> TestResult:
        """Parse Jest JSON output from stdout.

        Args:
            output: JSON output from Jest.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        if not output.strip():
            return TestResult()

        try:
            report = json.loads(output)
        except json.JSONDecodeError as e:
            LOGGER.warning(f"Failed to parse Jest JSON output: {e}")
            return TestResult()

        return self._process_report(report, project_root)

    def _process_report(
        self,
        report: Dict[str, Any],
        project_root: Path,
    ) -> TestResult:
        """Process Jest JSON report.

        Args:
            report: Parsed JSON report.
            project_root: Project root directory.

        Returns:
            TestResult with processed data.
        """
        # Extract summary statistics
        num_passed = report.get("numPassedTests", 0)
        num_failed = report.get("numFailedTests", 0)
        num_pending = report.get("numPendingTests", 0)
        num_todo = report.get("numTodoTests", 0)

        # Calculate duration from individual test results
        test_results = report.get("testResults", [])
        duration_ms = 0
        for test_result in test_results:
            duration_ms += test_result.get("endTime", 0) - test_result.get("startTime", 0)

        result = TestResult(
            passed=num_passed,
            failed=num_failed,
            skipped=num_pending + num_todo,
            errors=0,  # Jest doesn't distinguish errors from failures
            duration_ms=duration_ms,
        )

        # Convert failures to issues
        for test_file in test_results:
            status = test_file.get("status", "")
            if status == "failed":
                for assertion in test_file.get("assertionResults", []):
                    if assertion.get("status") == "failed":
                        issue = self._assertion_to_issue(
                            assertion, test_file, project_root
                        )
                        if issue:
                            result.issues.append(issue)

        LOGGER.info(
            f"Jest: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )
        return result

    def _assertion_to_issue(
        self,
        assertion: Dict[str, Any],
        test_file: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert Jest assertion failure to UnifiedIssue.

        Args:
            assertion: Assertion result dict.
            test_file: Test file result dict.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            # Get test information
            full_name = assertion.get("fullName", "")
            title_parts = assertion.get("ancestorTitles", [])
            test_name = assertion.get("title", "")
            failure_messages = assertion.get("failureMessages", [])
            location = assertion.get("location", {})

            # Build file path
            file_name = test_file.get("name", "")
            file_path = Path(file_name)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            # Get line number if available
            line_number = location.get("line") if location else None

            # Build test name with ancestors
            if title_parts:
                display_name = " > ".join(title_parts + [test_name])
            else:
                display_name = test_name

            # Get failure message
            message = failure_messages[0] if failure_messages else "Test failed"
            # Extract assertion from message
            assertion_text = self._extract_assertion(message)

            # Generate deterministic ID
            issue_id = self._generate_issue_id(full_name, assertion_text)

            # Build title
            title = f"{display_name}: {assertion_text}" if assertion_text else f"{display_name} failed"

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="jest",
                severity=Severity.HIGH,
                rule_id="failed",
                title=title,
                description=message,
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "full_name": full_name,
                    "test_name": test_name,
                    "ancestor_titles": title_parts,
                    "failure_messages": failure_messages,
                    "assertion": assertion_text,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Jest assertion failure: {e}")
            return None

    def _extract_assertion(self, message: str) -> str:
        """Extract assertion from Jest failure message.

        Args:
            message: Failure message from Jest.

        Returns:
            Extracted assertion or truncated message.
        """
        if not message:
            return ""

        lines = message.strip().split("\n")

        # Look for expect/received patterns
        for line in lines:
            line = line.strip()
            if line.startswith("expect("):
                return line[:100]
            if line.startswith("Expected:"):
                # Find the corresponding Received line
                idx = lines.index(line) if line in lines else -1
                if idx >= 0 and idx + 1 < len(lines):
                    received = lines[idx + 1].strip()
                    return f"{line} {received}"[:100]
                return line[:100]

        # Return first meaningful line
        for line in lines:
            line = line.strip()
            if line and not line.startswith("at ") and len(line) > 5:
                return line[:100]

        return message[:100]

    def _generate_issue_id(self, full_name: str, assertion: str) -> str:
        """Generate deterministic issue ID.

        Args:
            full_name: Full test name with ancestors.
            assertion: Assertion message.

        Returns:
            Unique issue ID.
        """
        content = f"{full_name}:{assertion}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"jest-{hash_val}"
