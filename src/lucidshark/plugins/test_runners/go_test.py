"""Go test runner plugin.

Runs Go tests via `go test -json` and parses the JSON output
for test results and failures.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming, temporary_env
from lucidshark.plugins.go_utils import (
    ensure_go_in_path,
    find_go,
    get_go_version,
    has_go_mod,
)
from lucidshark.plugins.test_runners.base import TestResult, TestRunnerPlugin

LOGGER = get_logger(__name__)


class GoTestRunner(TestRunnerPlugin):
    """Go test runner plugin for Go test execution."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize GoTestRunner.

        Args:
            project_root: Optional project root for tool resolution.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "go_test"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["go"]

    def get_version(self) -> str:
        """Get Go version."""
        return get_go_version()

    def ensure_binary(self) -> Path:
        """Ensure go is available.

        Returns:
            Path to go binary.

        Raises:
            FileNotFoundError: If go is not available.
        """
        return find_go()

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run tests using go test -json.

        When the coverage domain is enabled, adds -coverprofile=coverage.out
        so that coverage data is generated alongside test execution.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            go_bin = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="go_test")

        # Check for go.mod
        if not has_go_mod(context.project_root):
            LOGGER.info("No go.mod found, skipping go test")
            return TestResult(tool="go_test")

        cmd = [str(go_bin), "test", "-json", "-count=1"]

        # Add coverage instrumentation when coverage domain is enabled
        if ToolDomain.COVERAGE in context.enabled_domains:
            cmd.append("-coverprofile=coverage.out")

        cmd.append("./...")

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        # Ensure 'go' command is in PATH
        env_vars = ensure_go_in_path()

        stdout = ""
        stderr = ""
        try:
            with temporary_env(env_vars):
                proc = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="go-test",
                    stream_handler=context.stream_handler,
                    timeout=600,
                )
            stdout = proc.stdout
            stderr = proc.stderr
            # go test returns non-zero on test failures or build failures — that's normal
            # We parse the JSON output to determine what happened
            if proc.returncode != 0:
                LOGGER.debug(f"go test exited with code {proc.returncode}")
        except subprocess.TimeoutExpired:
            LOGGER.warning("go test timed out after 600 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="go test timed out after 600 seconds",
            )
            return TestResult(tool="go_test")
        except subprocess.CalledProcessError as e:
            # go test can raise CalledProcessError on failures
            # Extract stdout if available and parse it
            LOGGER.debug(f"go test raised CalledProcessError: {e}")
            if hasattr(e, "stdout") and e.stdout:
                stdout = (
                    e.stdout
                    if isinstance(e.stdout, str)
                    else e.stdout.decode("utf-8", errors="replace")
                )
            if hasattr(e, "stderr") and e.stderr:
                stderr = (
                    e.stderr
                    if isinstance(e.stderr, str)
                    else e.stderr.decode("utf-8", errors="replace")
                )
            # Continue to parse the output below
        except Exception as e:
            LOGGER.warning(f"go test failed to execute: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"go test failed to execute: {e}",
            )
            return TestResult(tool="go_test")

        # Parse test results from JSON output
        result = self._parse_json_output(stdout, context.project_root)

        # If we got no test results but stderr has content, it might be a build failure
        # Note: We may have already created issues for package-level failures above
        if (
            result.passed == 0
            and result.failed == 0
            and result.skipped == 0
            and result.errors == 0  # Only if we haven't already recorded an error
            and stderr.strip()
        ):
            LOGGER.debug(f"No test results found, stderr: {stderr[:200]}")
            # Create an issue for build failure
            result.errors = 1
            result.issues.append(
                UnifiedIssue(
                    id="go-test-build-failure",
                    domain=ToolDomain.TESTING,
                    source_tool="go_test",
                    severity=Severity.HIGH,
                    rule_id="build_failed",
                    title="Go test build failed",
                    description=f"Failed to build Go tests:\n{stderr[:500]}",
                    fixable=False,
                )
            )

        return result

    def _parse_json_output(self, output: str, project_root: Path) -> TestResult:
        """Parse go test -json output.

        Each line of output is a JSON object with Action, Package, Test,
        Output, and Elapsed fields.

        Args:
            output: stdout from go test -json.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="go_test")

        if not output or not output.strip():
            return result

        # Track test events: (package, test) -> list of output lines
        test_outputs: Dict[Tuple[str, str], List[str]] = {}
        # Track final action per test
        test_actions: Dict[Tuple[str, str], str] = {}
        # Track elapsed per test
        test_elapsed: Dict[Tuple[str, str], float] = {}
        # Track package-level failures (build errors, no tests, etc.)
        package_failures: Dict[str, List[str]] = {}

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            package = event.get("Package")
            test = event.get("Test")
            action = event.get("Action")

            # Handle package-level events (build failures, etc.)
            if package and not test:
                if action == "output":
                    # Collect package-level output for build errors
                    if package not in package_failures:
                        package_failures[package] = []
                    output_line = event.get("Output", "")
                    package_failures[package].append(output_line)
                elif action == "fail":
                    # Package-level fail indicates build failure or no tests
                    # Only create an issue if there's actual error output collected
                    output_lines = package_failures.get(package, [])
                    if output_lines:
                        result.errors += 1
                        # Create an issue for the package failure
                        full_output = "".join(output_lines)
                        result.issues.append(
                            UnifiedIssue(
                                id=f"go-test-pkg-failure-{package}",
                                domain=ToolDomain.TESTING,
                                source_tool="go_test",
                                severity=Severity.HIGH,
                                rule_id="package_build_failed",
                                title=f"Package {package} failed to build or has no tests",
                                description=f"Build or package error in {package}:\n{full_output[:500]}",
                                fixable=False,
                                metadata={"package": package, "outcome": "failed"},
                            )
                        )
                continue

            # Process test-specific events (have both Package and Test fields)
            if not package or not test:
                continue

            key = (package, test)

            if action == "output":
                output_line = event.get("Output", "")
                if key not in test_outputs:
                    test_outputs[key] = []
                test_outputs[key].append(output_line)
            elif action in ("pass", "fail", "skip"):
                test_actions[key] = action
                elapsed = event.get("Elapsed", 0.0)
                test_elapsed[key] = elapsed

        # Count results and create issues for failures
        total_elapsed_ms = 0
        for key, action in test_actions.items():
            package, test_name = key
            elapsed = test_elapsed.get(key, 0.0)
            total_elapsed_ms += int(elapsed * 1000)

            if action == "pass":
                result.passed += 1
            elif action == "skip":
                result.skipped += 1
            elif action == "fail":
                result.failed += 1
                output_lines = test_outputs.get(key, [])
                issue = self._failure_to_issue(
                    package, test_name, output_lines, project_root
                )
                if issue:
                    result.issues.append(issue)

        result.duration_ms = total_elapsed_ms

        LOGGER.info(
            f"go_test: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )

        return result

    def _failure_to_issue(
        self,
        package: str,
        test_name: str,
        output_lines: List[str],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a test failure to UnifiedIssue.

        Args:
            package: Go package name.
            test_name: Test function name.
            output_lines: Collected output lines for this test.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            # Join output lines and extract a short message
            full_output = "".join(output_lines)
            short_message = self._extract_short_message(output_lines)

            # Try to extract file path and line number from output
            file_path, line_number = self._extract_location(output_lines, project_root)

            title = f"{package}::{test_name} FAILED: {short_message}"
            if len(title) > 200:
                title = title[:197] + "..."

            issue_id = self._generate_go_issue_id(package, test_name)

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="go_test",
                severity=Severity.HIGH,
                rule_id="test_failed",
                title=title,
                description=f"Test {package}::{test_name} failed:\n{full_output[:500]}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "package": package,
                    "test_name": test_name,
                    "outcome": "failed",
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse go test failure: {e}")
            return None

    def _extract_short_message(self, output_lines: List[str]) -> str:
        """Extract a short failure message from test output lines.

        Args:
            output_lines: Output lines collected for a test.

        Returns:
            Short message string.
        """
        for line in output_lines:
            stripped = line.strip()
            # Skip decorative lines and empty lines
            if not stripped or stripped.startswith("---") or stripped.startswith("==="):
                continue
            # Look for assertion-like lines (indented lines from t.Errorf etc.)
            if stripped.startswith("    ") or ":" in stripped:
                cleaned = stripped.replace("\n", " ").strip()
                if len(cleaned) > 5:
                    return cleaned[:100]

        # Fallback: use first non-empty line
        for line in output_lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("---")
                and not stripped.startswith("===")
            ):
                return stripped.replace("\n", " ")[:100]

        return "Test failed"

    def _extract_location(
        self,
        output_lines: List[str],
        project_root: Path,
    ) -> Tuple[Optional[Path], Optional[int]]:
        """Extract file path and line number from test output.

        Looks for patterns like 'main_test.go:15:' in the output.

        Args:
            output_lines: Output lines from the test.
            project_root: Project root directory.

        Returns:
            Tuple of (file_path, line_number). Either may be None.
        """
        for line in output_lines:
            # Match patterns like "    main_test.go:15: expected 4, got 3"
            match = re.search(r"(\S+_test\.go):(\d+):", line)
            if match:
                file_name = match.group(1)
                line_number = int(match.group(2))
                file_path = project_root / file_name
                if file_path.exists():
                    return file_path, line_number
                # Try without assuming it's directly in project root
                return None, line_number

            # Also try general .go file patterns
            match = re.search(r"(\S+\.go):(\d+):", line)
            if match:
                file_name = match.group(1)
                line_number = int(match.group(2))
                file_path = project_root / file_name
                if file_path.exists():
                    return file_path, line_number
                return None, line_number

        return None, None

    def _generate_go_issue_id(self, package: str, test_name: str) -> str:
        """Generate deterministic issue ID for a go test failure.

        Args:
            package: Go package name.
            test_name: Test function name.

        Returns:
            Unique issue ID.
        """
        content = f"{package}::{test_name}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"go-test-{hash_val}"
