"""Istanbul/NYC coverage plugin.

Istanbul (via NYC) is a JavaScript code coverage tool.
https://istanbul.js.org/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lucidshark.core.logging import get_logger
from lucidshark.core.paths import resolve_node_bin
from lucidshark.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
    TestStatistics,
)
from lucidshark.plugins.utils import (
    ensure_node_binary,
    get_cli_version,
    create_test_failure_issue,
)

LOGGER = get_logger(__name__)


class IstanbulPlugin(CoveragePlugin):
    """Istanbul/NYC coverage plugin for JavaScript/TypeScript coverage analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize IstanbulPlugin.

        Args:
            project_root: Optional project root for finding NYC installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "istanbul"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    def get_version(self) -> str:
        """Get NYC version."""
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure NYC is available."""
        return ensure_node_binary(
            self._project_root,
            "nyc",
            "NYC (Istanbul) is not installed. Install it with:\n"
            "  npm install nyc --save-dev\n"
            "  OR\n"
            "  npm install -g nyc",
        )

    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
        run_tests: bool = True,
    ) -> CoverageResult:
        """Run coverage analysis on the specified paths.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).
            run_tests: Whether to run tests if no existing coverage data exists.

        Returns:
            CoverageResult with coverage statistics and issues if below threshold.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return CoverageResult(threshold=threshold)

        test_stats: Optional[TestStatistics] = None

        # Always run tests fresh when run_tests=True to ensure accurate coverage
        if run_tests:
            LOGGER.info("Running tests with coverage...")
            success, test_stats = self._run_tests_with_coverage(binary, context)
            if not success:
                LOGGER.warning("Failed to run tests with coverage")
                return CoverageResult(threshold=threshold, tool="istanbul")

            # If tests had failures (non-zero exit), fail coverage immediately
            if test_stats and not test_stats.success:
                LOGGER.warning(
                    f"Tests failed ({test_stats.failed} failed, {test_stats.errors} errors) "
                    f"- coverage is invalid"
                )
                result = CoverageResult(threshold=threshold, tool="istanbul")
                result.test_stats = test_stats
                result.issues.append(create_test_failure_issue(
                    source_tool="istanbul",
                    failed=test_stats.failed,
                    errors=test_stats.errors,
                    total=test_stats.total,
                ))
                return result

        # Generate JSON report from coverage data
        result = self._generate_and_parse_report(binary, context, threshold)
        result.test_stats = test_stats

        return result

    def _run_tests_with_coverage(
        self,
        binary: Path,
        context: ScanContext,
    ) -> Tuple[bool, Optional[TestStatistics]]:
        """Run tests with NYC coverage.

        Args:
            binary: Path to NYC binary.
            context: Scan context.

        Returns:
            Tuple of (success, test_stats). Success is True if tests ran.
            Test stats indicate pass/fail via the return code.
        """
        # Check for jest or npm test
        jest_path = None
        if self._project_root:
            node_jest = resolve_node_bin(self._project_root, "jest")
            if node_jest:
                jest_path = node_jest

        if not jest_path:
            jest_which = shutil.which("jest")
            if jest_which:
                jest_path = Path(jest_which)

        if jest_path:
            # Run nyc jest
            cmd = [str(binary), str(jest_path), "--passWithNoTests"]
        else:
            # Fall back to npm test
            cmd = [str(binary), "npm", "test"]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(context.project_root),
            )
            # Non-zero exit code means tests failed
            if proc.returncode != 0:
                test_stats = TestStatistics(total=1, failed=1)
                return True, test_stats
            return True, TestStatistics()
        except Exception as e:
            LOGGER.error(f"Failed to run tests with coverage: {e}")
            return False, None

    def _generate_and_parse_report(
        self,
        binary: Path,
        context: ScanContext,
        threshold: float,
    ) -> CoverageResult:
        """Generate JSON report and parse it.

        Args:
            binary: Path to NYC binary.
            context: Scan context.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)

            cmd = [
                str(binary),
                "report",
                "--reporter=json-summary",
                f"--report-dir={report_dir}",
            ]

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(context.project_root),
                )

                if result.returncode != 0:
                    LOGGER.warning(f"NYC report failed: {result.stderr}")
                    return CoverageResult(threshold=threshold)

            except Exception as e:
                LOGGER.error(f"Failed to generate coverage report: {e}")
                return CoverageResult(threshold=threshold)

            # Parse JSON report
            report_file = report_dir / "coverage-summary.json"
            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root, threshold)
            else:
                LOGGER.warning("Coverage JSON report not generated")
                return CoverageResult(threshold=threshold)

    def _parse_json_report(
        self,
        report_file: Path,
        project_root: Path,
        threshold: float,
    ) -> CoverageResult:
        """Parse Istanbul JSON summary report.

        Args:
            report_file: Path to JSON report file.
            project_root: Project root directory.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        try:
            with open(report_file) as f:
                report = json.load(f)
        except Exception as e:
            LOGGER.error(f"Failed to parse Istanbul JSON report: {e}")
            return CoverageResult(threshold=threshold)

        # Get total statistics
        total = report.get("total", {})
        lines = total.get("lines", {})
        statements = total.get("statements", {})
        branches = total.get("branches", {})
        functions = total.get("functions", {})

        # Calculate overall coverage (use lines as primary metric)
        total_lines = lines.get("total", 0)
        covered_lines = lines.get("covered", 0)
        percent_covered = lines.get("pct", 0.0)

        result = CoverageResult(
            total_lines=total_lines,
            covered_lines=covered_lines,
            missing_lines=total_lines - covered_lines,
            excluded_lines=0,
            threshold=threshold,
        )

        # Parse per-file coverage (all keys except "total")
        for file_path, file_data in report.items():
            if file_path == "total":
                continue

            file_lines = file_data.get("lines", {})
            file_total = file_lines.get("total", 0)
            file_covered = file_lines.get("covered", 0)

            file_coverage = FileCoverage(
                file_path=project_root / file_path,
                total_lines=file_total,
                covered_lines=file_covered,
                missing_lines=[],  # Istanbul doesn't provide specific line numbers in summary
                excluded_lines=0,
            )
            result.files[file_path] = file_coverage

        # Generate issue if below threshold
        if percent_covered < threshold:
            issue = self._create_coverage_issue(
                percent_covered,
                threshold,
                total_lines,
                covered_lines,
                total_lines - covered_lines,
                statements,
                branches,
                functions,
            )
            result.issues.append(issue)

        LOGGER.info(
            f"Coverage: {percent_covered:.1f}% ({covered_lines}/{total_lines} lines) "
            f"- threshold: {threshold}%"
        )

        return result

    def _create_coverage_issue(
        self,
        percentage: float,
        threshold: float,
        total_lines: int,
        covered_lines: int,
        missing_lines: int,
        statements: Dict[str, Any],
        branches: Dict[str, Any],
        functions: Dict[str, Any],
    ) -> UnifiedIssue:
        """Create a UnifiedIssue for coverage below threshold.

        Args:
            percentage: Actual coverage percentage.
            threshold: Required coverage threshold.
            total_lines: Total number of lines.
            covered_lines: Number of covered lines.
            missing_lines: Number of missing lines.
            statements: Statement coverage data.
            branches: Branch coverage data.
            functions: Function coverage data.

        Returns:
            UnifiedIssue for coverage failure.
        """
        # Determine severity based on how far below threshold
        if percentage < 50:
            severity = Severity.HIGH
        elif percentage < threshold - 10:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        # Generate deterministic ID
        issue_id = self._generate_issue_id(percentage, threshold)

        gap = threshold - percentage

        return UnifiedIssue(
            id=issue_id,
            domain=ToolDomain.COVERAGE,
            source_tool="istanbul",
            severity=severity,
            rule_id="coverage_below_threshold",
            title=f"Coverage {percentage:.1f}% is below threshold {threshold}%",
            description=(
                f"Project coverage is {percentage:.1f}%, which is {gap:.1f}% below "
                f"the required threshold of {threshold}%. "
                f"Lines: {covered_lines}/{total_lines} ({percentage:.1f}%), "
                f"Statements: {statements.get('covered', 0)}/{statements.get('total', 0)} ({statements.get('pct', 0):.1f}%), "
                f"Branches: {branches.get('covered', 0)}/{branches.get('total', 0)} ({branches.get('pct', 0):.1f}%), "
                f"Functions: {functions.get('covered', 0)}/{functions.get('total', 0)} ({functions.get('pct', 0):.1f}%)"
            ),
            recommendation=f"Add tests to cover at least {gap:.1f}% more of the codebase.",
            file_path=None,  # Project-level issue
            line_start=None,
            line_end=None,
            fixable=False,
            metadata={
                "coverage_percentage": round(percentage, 2),
                "threshold": threshold,
                "total_lines": total_lines,
                "covered_lines": covered_lines,
                "missing_lines": missing_lines,
                "gap_percentage": round(gap, 2),
                "statements": statements,
                "branches": branches,
                "functions": functions,
            },
        )

    def _generate_issue_id(self, percentage: float, threshold: float) -> str:
        """Generate deterministic issue ID.

        Args:
            percentage: Coverage percentage.
            threshold: Coverage threshold.

        Returns:
            Unique issue ID.
        """
        # ID based on rounded percentage and threshold for stability
        content = f"istanbul:{round(percentage)}:{threshold}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"istanbul-{hash_val}"
