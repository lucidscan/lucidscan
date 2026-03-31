"""RSpec test runner plugin.

RSpec is a testing tool for Ruby.
https://rspec.info/
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.test_runners.base import TestResult, TestRunnerPlugin

LOGGER = get_logger(__name__)


class RspecRunner(TestRunnerPlugin):
    """RSpec test runner plugin for Ruby test execution."""

    def __init__(self, project_root: Optional[Path] = None):
        super().__init__(project_root=project_root)

    @property
    def name(self) -> str:
        return "rspec"

    @property
    def languages(self) -> List[str]:
        return ["ruby"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            from lucidshark.plugins.utils import get_cli_version

            return get_cli_version(
                binary,
                parser=lambda s: s.strip().split()[-1] if s.strip() else "unknown",
            )
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Find RSpec binary.

        Checks for rspec in:
        1. Project binstubs (bin/rspec)
        2. System PATH

        Returns:
            Path to rspec binary.

        Raises:
            FileNotFoundError: If RSpec is not installed.
        """
        if self._project_root:
            binstub = self._project_root / "bin" / "rspec"
            if binstub.exists():
                return binstub

        system_binary = shutil.which("rspec")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "RSpec is not installed. Install it with:\n"
            "  gem install rspec\n"
            "  OR add to your Gemfile:\n"
            "  gem 'rspec', group: :test"
        )

    def run_tests(self, context: ScanContext) -> TestResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
                suggestion="gem install rspec",
            )
            return TestResult()

        cmd = [str(binary), "--format", "json", "--no-color"]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        proc = self._run_test_subprocess(cmd, context, timeout=600)
        if proc is None:
            return self._execution_failure_result(cmd)

        # RSpec writes JSON to stdout
        output = proc.stdout or ""
        if not output.strip():
            LOGGER.warning("RSpec produced no output")
            return self._execution_failure_result(cmd)

        return self._parse_json_output(output, context.project_root)

    def _execution_failure_result(self, cmd: List[str]) -> TestResult:
        cmd_str = " ".join(cmd)
        return TestResult(
            errors=1,
            issues=[
                UnifiedIssue(
                    id=self._generate_issue_id("execution-failure", cmd_str),
                    domain=ToolDomain.TESTING,
                    source_tool="rspec",
                    severity=Severity.HIGH,
                    rule_id="execution-failure",
                    title="RSpec failed to execute",
                    description=(
                        f"Failed to run test command: {cmd_str}\n\n"
                        "This may be caused by a missing RSpec installation, "
                        "broken Gemfile, or a timeout. "
                        "Check that RSpec is installed and working."
                    ),
                    fixable=False,
                )
            ],
        )

    def _parse_json_output(
        self,
        output: str,
        project_root: Path,
    ) -> TestResult:
        """Parse RSpec JSON output.

        RSpec JSON format:
        {
          "examples": [...],
          "summary": {
            "duration": 0.5,
            "example_count": 10,
            "failure_count": 2,
            "pending_count": 1,
            "errors_outside_of_examples_count": 0
          }
        }
        """
        try:
            report = json.loads(output)
        except json.JSONDecodeError as e:
            LOGGER.warning(f"Failed to parse RSpec JSON output: {e}")
            return TestResult()

        summary = report.get("summary", {})
        examples = report.get("examples", [])

        total = summary.get("example_count", 0)
        failures = summary.get("failure_count", 0)
        pending = summary.get("pending_count", 0)
        errors_outside = summary.get("errors_outside_of_examples_count", 0)
        duration = summary.get("duration", 0)

        result = TestResult(
            passed=total - failures - pending,
            failed=failures,
            skipped=pending,
            errors=errors_outside,
            duration_ms=int(duration * 1000),
            tool=self.name,
        )

        for example in examples:
            status = example.get("status", "")
            if status == "failed":
                issue = self._example_to_issue(example, project_root)
                if issue:
                    result.issues.append(issue)

        LOGGER.info(
            f"rspec: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} pending"
        )
        return result

    def _example_to_issue(
        self,
        example: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        try:
            full_description = example.get("full_description", "")
            description = example.get("description", "")
            file_path_str = example.get("file_path", "")
            line_number = example.get("line_number")
            exception = example.get("exception", {})
            run_time = example.get("run_time", 0)

            error_class = exception.get("class", "")
            error_message = exception.get("message", "")
            backtrace = exception.get("backtrace", [])

            file_path = Path(file_path_str.lstrip("./")) if file_path_str else None
            if file_path and not file_path.is_absolute():
                file_path = project_root / file_path

            assertion = self._extract_assertion(error_message)
            issue_id = self._generate_issue_id(full_description, assertion)

            title = (
                f"{full_description}: {assertion}"
                if assertion
                else f"{full_description} failed"
            )

            desc_parts = []
            if error_class:
                desc_parts.append(f"{error_class}: {error_message}")
            elif error_message:
                desc_parts.append(error_message)
            if backtrace:
                desc_parts.append("\n".join(backtrace[:5]))

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="rspec",
                severity=Severity.HIGH,
                rule_id="failed",
                title=title,
                description="\n".join(desc_parts) or "Test failed",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "full_description": full_description,
                    "description": description,
                    "exception_class": error_class,
                    "exception_message": error_message,
                    "run_time": run_time,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse RSpec example failure: {e}")
            return None

    def _extract_assertion(self, message: str) -> str:
        if not message:
            return ""

        lines = message.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("expected"):
                return self._truncate(line, 100)
            if "to equal" in line or "to eq" in line or "to be" in line:
                return self._truncate(line, 100)

        if lines:
            return self._truncate(lines[0], 100)
        return ""

    def _generate_issue_id(self, full_name: str, assertion: str) -> str:
        content = f"{full_name}:{assertion}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"rspec-{hash_val}"
