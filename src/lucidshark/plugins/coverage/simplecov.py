"""SimpleCov coverage plugin.

SimpleCov is a code coverage analysis tool for Ruby.
https://github.com/simplecov-ruby/simplecov
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
)

LOGGER = get_logger(__name__)

# Common SimpleCov result file locations
RESULTSET_PATHS = [
    "coverage/.resultset.json",
]


class SimpleCovPlugin(CoveragePlugin):
    """SimpleCov plugin for Ruby code coverage analysis.

    SimpleCov generates coverage data as part of the test run.
    This plugin parses the existing .resultset.json file.
    """

    def __init__(self, project_root: Optional[Path] = None):
        super().__init__(project_root=project_root)

    @property
    def name(self) -> str:
        return "simplecov"

    @property
    def languages(self) -> List[str]:
        return ["ruby"]

    def get_version(self) -> str:
        # SimpleCov is a Ruby library, not a standalone binary.
        # We report "installed" if ruby is available.
        ruby_path = shutil.which("ruby")
        if ruby_path:
            return "installed"
        return "unknown"

    def ensure_binary(self) -> Path:
        """SimpleCov doesn't have a standalone binary.

        Returns the ruby binary as a proxy to confirm Ruby is available.

        Returns:
            Path to ruby binary.

        Raises:
            FileNotFoundError: If Ruby is not installed.
        """
        ruby_path = shutil.which("ruby")
        if ruby_path:
            return Path(ruby_path)
        raise FileNotFoundError(
            "Ruby is not installed. SimpleCov requires Ruby and is configured "
            "in your test helper (spec_helper.rb or test_helper.rb)."
        )

    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
    ) -> CoverageResult:
        """Parse existing SimpleCov coverage data.

        Looks for coverage/.resultset.json and parses it.
        If no data file exists, returns an error issue directing the user
        to configure SimpleCov in their test helper.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).

        Returns:
            CoverageResult with coverage statistics.
        """
        # Find the resultset file
        resultset_file = self._find_resultset(context.project_root)
        if resultset_file is None:
            LOGGER.warning("No SimpleCov .resultset.json found")
            result = CoverageResult(threshold=threshold, tool="simplecov")
            result.issues.append(self._create_no_data_issue())
            return result

        # Parse the resultset
        result = self._parse_resultset(resultset_file, context.project_root, threshold)

        if result.total_lines == 0 and not result.issues:
            result.issues.append(self._create_no_data_issue())

        return result

    def _find_resultset(self, project_root: Path) -> Optional[Path]:
        """Find SimpleCov resultset file."""
        for rel_path in RESULTSET_PATHS:
            full_path = project_root / rel_path
            if full_path.exists():
                return full_path
        return None

    def _parse_resultset(
        self,
        resultset_file: Path,
        project_root: Path,
        threshold: float,
    ) -> CoverageResult:
        """Parse SimpleCov .resultset.json.

        SimpleCov resultset format:
        {
          "RSpec": {
            "coverage": {
              "/absolute/path/to/file.rb": {
                "lines": [null, 1, 1, 0, null, ...]
              }
            },
            "timestamp": 1234567890
          }
        }

        Or legacy format where coverage values are arrays directly:
        {
          "RSpec": {
            "coverage": {
              "/absolute/path/to/file.rb": [null, 1, 1, 0, null, ...]
            }
          }
        }
        """
        try:
            with open(resultset_file) as f:
                data = json.load(f)
        except Exception as e:
            LOGGER.error(f"Failed to parse SimpleCov resultset: {e}")
            return CoverageResult(threshold=threshold, tool="simplecov")

        # Merge coverage from all test suites (RSpec, Minitest, etc.)
        merged_coverage: Dict[str, List[Optional[int]]] = {}

        for suite_name, suite_data in data.items():
            if not isinstance(suite_data, dict):
                continue
            coverage = suite_data.get("coverage", {})
            for file_path, file_coverage in coverage.items():
                # Handle both formats
                if isinstance(file_coverage, dict):
                    lines = file_coverage.get("lines", [])
                elif isinstance(file_coverage, list):
                    lines = file_coverage
                else:
                    continue

                if file_path not in merged_coverage:
                    merged_coverage[file_path] = lines
                else:
                    # Merge: take max of each line (across test suites)
                    existing = merged_coverage[file_path]
                    merged: List[Optional[int]] = []
                    for i in range(max(len(existing), len(lines))):
                        a = existing[i] if i < len(existing) else None
                        b = lines[i] if i < len(lines) else None
                        if a is None and b is None:
                            merged.append(None)
                        elif a is None:
                            merged.append(b)
                        elif b is None:
                            merged.append(a)
                        else:
                            merged.append(max(a, b))
                    merged_coverage[file_path] = merged

        # Calculate coverage statistics
        total_lines = 0
        covered_lines = 0
        files: Dict[str, FileCoverage] = {}

        for file_path, lines in merged_coverage.items():
            relevant_lines = [count for count in lines if count is not None]
            file_total = len(relevant_lines)
            file_covered = sum(1 for count in relevant_lines if count > 0)
            missing = [
                i + 1
                for i, count in enumerate(lines)
                if count is not None and count == 0
            ]

            total_lines += file_total
            covered_lines += file_covered

            try:
                rel_path = str(Path(file_path).relative_to(project_root))
            except ValueError:
                rel_path = file_path

            files[rel_path] = FileCoverage(
                file_path=Path(file_path),
                total_lines=file_total,
                covered_lines=file_covered,
                missing_lines=missing,
                excluded_lines=len(lines) - file_total,
            )

        percent_covered = (
            (covered_lines / total_lines * 100) if total_lines > 0 else 0.0
        )

        result = CoverageResult(
            total_lines=total_lines,
            covered_lines=covered_lines,
            missing_lines=total_lines - covered_lines,
            excluded_lines=0,
            threshold=threshold,
            files=files,
            tool="simplecov",
        )

        if percent_covered < threshold:
            result.issues.append(
                self._create_coverage_issue(
                    percent_covered, threshold, total_lines, covered_lines
                )
            )

        LOGGER.info(
            f"SimpleCov coverage: {percent_covered:.1f}% "
            f"({covered_lines}/{total_lines} lines) - threshold: {threshold}%"
        )

        return result
