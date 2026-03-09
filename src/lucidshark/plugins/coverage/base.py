"""Base class for coverage plugins.

All coverage plugins inherit from CoveragePlugin and implement the measure_coverage() method.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    CoverageSummary,
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

__all__ = ["CoveragePlugin", "CoverageResult", "FileCoverage"]


@dataclass
class FileCoverage:
    """Coverage statistics for a single file."""

    file_path: Path
    total_lines: int = 0
    covered_lines: int = 0
    missing_lines: List[int] = field(default_factory=list)
    excluded_lines: int = 0

    @property
    def percentage(self) -> float:
        """Coverage percentage for this file."""
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100


@dataclass
class CoverageResult:
    """Result statistics from coverage analysis."""

    total_lines: int = 0
    covered_lines: int = 0
    missing_lines: int = 0
    excluded_lines: int = 0
    threshold: float = 0.0
    files: Dict[str, FileCoverage] = field(default_factory=dict)
    issues: List[UnifiedIssue] = field(default_factory=list)
    tool: str = ""  # Name of the coverage tool that produced this result

    @property
    def percentage(self) -> float:
        """Overall coverage percentage."""
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    @property
    def passed(self) -> bool:
        """Whether coverage meets the threshold."""
        return self.percentage >= self.threshold

    def to_summary(self) -> CoverageSummary:
        """Convert to CoverageSummary for CLI output.

        Returns:
            CoverageSummary dataclass with all coverage statistics.
        """
        return CoverageSummary(
            coverage_percentage=round(self.percentage, 2),
            threshold=self.threshold,
            total_lines=self.total_lines,
            covered_lines=self.covered_lines,
            missing_lines=self.missing_lines,
            passed=self.passed,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MCP/JSON output.

        Returns:
            Dictionary with coverage statistics.
        """
        return {
            "coverage_percentage": round(self.percentage, 2),
            "threshold": self.threshold,
            "total_lines": self.total_lines,
            "covered_lines": self.covered_lines,
            "missing_lines": self.missing_lines,
            "passed": self.passed,
        }

    def filter_to_changed_files(
        self,
        changed_files: List[Path],
        project_root: Path,
    ) -> "CoverageResult":
        """Create filtered copy with only coverage for changed files.

        This is used for PR-based incremental coverage reporting. The full test
        suite still runs, but only coverage for changed files is reported.

        Args:
            changed_files: List of changed file paths (absolute).
            project_root: Project root for path resolution.

        Returns:
            New CoverageResult with filtered files and recalculated stats.
        """
        # Build a set of relative path strings for matching
        changed_set: set[str] = set()
        for f in changed_files:
            try:
                rel_path = f.relative_to(project_root)
                changed_set.add(str(rel_path))
            except ValueError:
                # File is outside project root, use absolute path
                changed_set.add(str(f))

        # Filter files dict to only include changed files
        filtered_files: Dict[str, FileCoverage] = {}
        for path, cov in self.files.items():
            # Check if this file matches any changed file
            if path in changed_set:
                filtered_files[path] = cov
            else:
                # Also check if paths match by suffix (handles src/foo.py vs foo.py)
                # Use Path objects to ensure proper path comparison (not string suffix)
                path_obj = Path(path)
                for changed in changed_set:
                    changed_path = Path(changed)
                    # Check if one path ends with the other's parts
                    # e.g., "src/utils/foo.py" matches "utils/foo.py" or "foo.py"
                    try:
                        # Try to check if path ends with changed or vice versa
                        if path_obj.parts[-len(changed_path.parts):] == changed_path.parts:
                            filtered_files[path] = cov
                            break
                        elif changed_path.parts[-len(path_obj.parts):] == path_obj.parts:
                            filtered_files[path] = cov
                            break
                    except (IndexError, ValueError):
                        continue

        # Recalculate totals from filtered files
        total_lines = sum(f.total_lines for f in filtered_files.values())
        covered_lines = sum(f.covered_lines for f in filtered_files.values())
        missing_lines = sum(len(f.missing_lines) for f in filtered_files.values())

        return CoverageResult(
            total_lines=total_lines,
            covered_lines=covered_lines,
            missing_lines=missing_lines,
            excluded_lines=self.excluded_lines,
            threshold=self.threshold,
            files=filtered_files,
            issues=[],  # Issues will be regenerated if coverage is below threshold
            tool=self.tool,
        )


class CoveragePlugin(ABC):
    """Abstract base class for coverage plugins.

    Coverage plugins provide code coverage analysis functionality.
    Each plugin wraps a specific coverage tool (coverage.py, Istanbul, etc.).
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the coverage plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g., 'coverage_py', 'istanbul').

        Returns:
            Plugin name string.
        """

    @property
    @abstractmethod
    def languages(self) -> List[str]:
        """Languages this coverage tool supports.

        Returns:
            List of language names (e.g., ['python'], ['javascript', 'typescript']).
        """

    @property
    def domain(self) -> ToolDomain:
        """Tool domain (always COVERAGE for coverage plugins).

        Returns:
            ToolDomain.COVERAGE
        """
        return ToolDomain.COVERAGE

    def get_version(self) -> str:
        """Get the version of the underlying coverage tool.

        Default implementation calls ``ensure_binary()`` and parses the
        CLI output via ``get_cli_version``.  Subclasses that need custom
        parsing (e.g. coverage_py, jacoco) should override this method.

        Returns:
            Version string, or ``"unknown"`` on failure.
        """
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the coverage tool is installed.

        Finds or installs the tool if not present.

        Returns:
            Path to the tool binary.

        Raises:
            FileNotFoundError: If the tool cannot be found or installed.
        """

    @abstractmethod
    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
    ) -> CoverageResult:
        """Parse existing coverage data and return results.

        Coverage plugins only parse existing coverage data files. They never
        run tests independently. If no coverage data is found, the result
        should contain an error issue directing the user to run the testing
        domain first.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).

        Returns:
            CoverageResult with coverage statistics and issues if below threshold.
        """

    # --- Shared helpers for Istanbul-format coverage reports ---

    def _parse_istanbul_summary(
        self,
        report: Dict[str, Any],
        project_root: Path,
        threshold: float,
    ) -> CoverageResult:
        """Parse Istanbul-format summary report (coverage-summary.json).

        Both Istanbul/NYC and Vitest produce this same format.

        Args:
            report: Parsed JSON report.
            project_root: Project root directory.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        total = report.get("total", {})
        lines = total.get("lines", {})
        statements = total.get("statements", {})
        branches = total.get("branches", {})
        functions = total.get("functions", {})

        total_lines = lines.get("total", 0)
        covered_lines = lines.get("covered", 0)
        percent_covered = lines.get("pct", 0.0)

        result = CoverageResult(
            total_lines=total_lines,
            covered_lines=covered_lines,
            missing_lines=total_lines - covered_lines,
            excluded_lines=0,
            threshold=threshold,
            tool=self.name,
        )

        # Parse per-file coverage
        for file_path, file_data in report.items():
            if file_path == "total":
                continue

            file_lines = file_data.get("lines", {})
            file_total = file_lines.get("total", 0)
            file_covered = file_lines.get("covered", 0)

            try:
                rel_path = str(Path(file_path).relative_to(project_root))
            except ValueError:
                rel_path = file_path

            file_coverage = FileCoverage(
                file_path=project_root / rel_path,
                total_lines=file_total,
                covered_lines=file_covered,
                missing_lines=[],
                excluded_lines=0,
            )
            result.files[rel_path] = file_coverage

        if percent_covered < threshold:
            result.issues.append(
                self._create_coverage_issue(
                    percent_covered,
                    threshold,
                    total_lines,
                    covered_lines,
                    statements=statements,
                    branches=branches,
                    functions=functions,
                )
            )

        LOGGER.info(
            f"{self.name} coverage: {percent_covered:.1f}% "
            f"({covered_lines}/{total_lines} lines) - threshold: {threshold}%"
        )

        return result

    def _parse_istanbul_final(
        self,
        report: Dict[str, Any],
        project_root: Path,
        threshold: float,
    ) -> CoverageResult:
        """Parse Istanbul-format coverage-final.json report.

        Extracts statement-level coverage from the ``s`` dict and uses
        ``statementMap`` to identify missing lines.

        Args:
            report: Parsed JSON report.
            project_root: Project root directory.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        total_statements = 0
        covered_statements = 0
        files: Dict[str, FileCoverage] = {}

        for file_path, file_data in report.items():
            s_map = file_data.get("s", {})
            statement_map = file_data.get("statementMap", {})
            file_total = len(s_map)
            file_covered = sum(1 for v in s_map.values() if v > 0)

            # Collect missing lines from statementMap where s[key] == 0
            missing_lines: list[int] = []
            for key, count in s_map.items():
                if count == 0 and key in statement_map:
                    start_line = statement_map[key].get("start", {}).get("line")
                    if start_line is not None:
                        missing_lines.append(start_line)
                elif count == 0:
                    # No statementMap entry — use key as line number
                    missing_lines.append(int(key))
            missing_lines.sort()

            total_statements += file_total
            covered_statements += file_covered

            try:
                rel_path = str(Path(file_path).relative_to(project_root))
            except ValueError:
                rel_path = file_path

            files[rel_path] = FileCoverage(
                file_path=project_root / rel_path,
                total_lines=file_total,
                covered_lines=file_covered,
                missing_lines=missing_lines,
                excluded_lines=0,
            )

        percent_covered = (
            (covered_statements / total_statements * 100)
            if total_statements > 0
            else 100.0
        )

        result = CoverageResult(
            total_lines=total_statements,
            covered_lines=covered_statements,
            missing_lines=total_statements - covered_statements,
            excluded_lines=0,
            threshold=threshold,
            files=files,
            tool=self.name,
        )

        if percent_covered < threshold:
            result.issues.append(
                self._create_coverage_issue(
                    percent_covered, threshold, total_statements, covered_statements
                )
            )

        LOGGER.info(
            f"{self.name} coverage: {percent_covered:.1f}% "
            f"({covered_statements}/{total_statements} statements) "
            f"- threshold: {threshold}%"
        )

        return result

    def _load_json_report(
        self,
        report_file: Path,
        threshold: float,
    ) -> Optional[Dict[str, Any]]:
        """Load and parse a JSON coverage report file.

        Args:
            report_file: Path to JSON report file.
            threshold: Coverage threshold (used for empty result on failure).

        Returns:
            Parsed JSON dict, or None on failure.
        """
        try:
            with open(report_file) as f:
                return json.load(f)
        except Exception as e:
            LOGGER.error(f"Failed to parse {self.name} coverage report: {e}")
            return None

    def _create_coverage_issue(
        self,
        percentage: float,
        threshold: float,
        total_lines: int,
        covered_lines: int,
        statements: Optional[Dict[str, Any]] = None,
        branches: Optional[Dict[str, Any]] = None,
        functions: Optional[Dict[str, Any]] = None,
    ) -> UnifiedIssue:
        """Create a UnifiedIssue for coverage below threshold.

        Args:
            percentage: Actual coverage percentage.
            threshold: Required coverage threshold.
            total_lines: Total number of lines.
            covered_lines: Number of covered lines.
            statements: Optional statement coverage data.
            branches: Optional branch coverage data.
            functions: Optional function coverage data.

        Returns:
            UnifiedIssue for coverage failure.
        """
        if percentage < 50:
            severity = Severity.HIGH
        elif percentage < threshold - 10:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        issue_id = self._generate_coverage_issue_id(percentage, threshold)
        gap = threshold - percentage
        missing_lines = total_lines - covered_lines

        desc_parts = [
            f"Project coverage is {percentage:.1f}%, which is {gap:.1f}% below "
            f"the required threshold of {threshold}%. "
            f"Lines: {covered_lines}/{total_lines} ({percentage:.1f}%)"
        ]

        if statements:
            desc_parts.append(
                f", Statements: {statements.get('covered', 0)}/{statements.get('total', 0)} "
                f"({statements.get('pct', 0):.1f}%)"
            )
        if branches:
            desc_parts.append(
                f", Branches: {branches.get('covered', 0)}/{branches.get('total', 0)} "
                f"({branches.get('pct', 0):.1f}%)"
            )
        if functions:
            desc_parts.append(
                f", Functions: {functions.get('covered', 0)}/{functions.get('total', 0)} "
                f"({functions.get('pct', 0):.1f}%)"
            )

        return UnifiedIssue(
            id=issue_id,
            domain=ToolDomain.COVERAGE,
            source_tool=self.name,
            severity=severity,
            rule_id="coverage_below_threshold",
            title=f"Coverage {percentage:.1f}% is below threshold {threshold}%",
            description="".join(desc_parts),
            recommendation=f"Add tests to cover at least {gap:.1f}% more of the codebase.",
            file_path=None,
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
            },
        )

    def _generate_coverage_issue_id(
        self, percentage: float, threshold: float
    ) -> str:
        """Generate deterministic issue ID for coverage issues.

        Args:
            percentage: Coverage percentage.
            threshold: Coverage threshold.

        Returns:
            Unique issue ID.
        """
        content = f"{self.name}:{round(percentage)}:{threshold}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"{self.name}-cov-{hash_val}"

    def _create_no_data_issue(self) -> UnifiedIssue:
        """Create a UnifiedIssue when no coverage data is found."""
        return UnifiedIssue(
            id=f"no-coverage-data-{self.name}",
            domain=ToolDomain.COVERAGE,
            source_tool=self.name,
            severity=Severity.HIGH,
            rule_id="no_coverage_data",
            title="No coverage data found",
            description=(
                f"No coverage data found for {self.name}. "
                "Ensure the testing domain is active and has run before coverage analysis. "
                "Test runners generate coverage data automatically when they execute."
            ),
            fixable=False,
        )
