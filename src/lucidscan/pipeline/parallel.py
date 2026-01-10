"""Parallel scanner execution using ThreadPoolExecutor."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from lucidscan.core.logging import get_logger
from lucidscan.core.models import ScanContext, UnifiedIssue
from lucidscan.plugins.scanners import get_scanner_plugin

LOGGER = get_logger(__name__)

# Default number of worker threads
DEFAULT_MAX_WORKERS = 4


@dataclass
class ScannerResult:
    """Result from a single scanner execution."""

    scanner_name: str
    scanner_version: str
    domains: List[str]
    issues: List[UnifiedIssue] = field(default_factory=list)
    error: Optional[str] = None
    success: bool = True


class ParallelScannerExecutor:
    """Executes scanners in parallel using ThreadPoolExecutor.

    Thread-safe aggregation of results using a lock.
    """

    def __init__(
        self,
        max_workers: int = DEFAULT_MAX_WORKERS,
        sequential: bool = False,
    ) -> None:
        """Initialize the executor.

        Args:
            max_workers: Maximum number of concurrent scanner threads.
            sequential: If True, run scanners sequentially (for debugging).
        """
        self._max_workers = max_workers
        self._sequential = sequential
        self._results_lock = threading.Lock()

    def execute(
        self,
        scanner_names: List[str],
        context: ScanContext,
    ) -> Tuple[List[UnifiedIssue], List[ScannerResult]]:
        """Execute scanners and return aggregated results.

        Args:
            scanner_names: List of scanner plugin names to execute.
            context: Scan context for all scanners.

        Returns:
            Tuple of (all_issues, scanner_results) with thread-safe aggregation.
        """
        if not scanner_names:
            return [], []

        if self._sequential:
            return self._execute_sequential(scanner_names, context)
        return self._execute_parallel(scanner_names, context)

    def _execute_parallel(
        self,
        scanner_names: List[str],
        context: ScanContext,
    ) -> Tuple[List[UnifiedIssue], List[ScannerResult]]:
        """Execute scanners in parallel."""
        all_issues: List[UnifiedIssue] = []
        scanner_results: List[ScannerResult] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # Submit all scanner tasks
            future_to_scanner = {
                executor.submit(self._run_scanner, name, context): name
                for name in scanner_names
            }

            # Collect results as they complete
            for future in as_completed(future_to_scanner):
                scanner_name = future_to_scanner[future]
                try:
                    result = future.result()
                    with self._results_lock:
                        all_issues.extend(result.issues)
                        scanner_results.append(result)
                except Exception as e:
                    LOGGER.error(f"Scanner {scanner_name} raised exception: {e}")
                    with self._results_lock:
                        scanner_results.append(
                            ScannerResult(
                                scanner_name=scanner_name,
                                scanner_version="unknown",
                                domains=[],
                                error=str(e),
                                success=False,
                            )
                        )

        return all_issues, scanner_results

    def _execute_sequential(
        self,
        scanner_names: List[str],
        context: ScanContext,
    ) -> Tuple[List[UnifiedIssue], List[ScannerResult]]:
        """Execute scanners sequentially (for debugging)."""
        all_issues: List[UnifiedIssue] = []
        scanner_results: List[ScannerResult] = []

        for name in scanner_names:
            result = self._run_scanner(name, context)
            all_issues.extend(result.issues)
            scanner_results.append(result)

        return all_issues, scanner_results

    def _run_scanner(
        self,
        scanner_name: str,
        context: ScanContext,
    ) -> ScannerResult:
        """Run a single scanner and return its result.

        This method is thread-safe and catches all exceptions.
        """
        scanner = get_scanner_plugin(scanner_name, project_root=context.project_root)
        if not scanner:
            LOGGER.error(f"Scanner plugin '{scanner_name}' not found")
            return ScannerResult(
                scanner_name=scanner_name,
                scanner_version="unknown",
                domains=[],
                error=f"Plugin '{scanner_name}' not found",
                success=False,
            )

        LOGGER.info(f"Running {scanner_name} scanner...")

        try:
            issues = scanner.scan(context)
            LOGGER.info(f"{scanner_name}: found {len(issues)} issues")

            return ScannerResult(
                scanner_name=scanner_name,
                scanner_version=scanner.get_version(),
                domains=[d.value for d in scanner.domains],
                issues=issues,
            )

        except Exception as e:
            LOGGER.error(f"Scanner {scanner_name} failed: {e}")
            # Try to get version even on failure
            try:
                version = scanner.get_version()
            except Exception:
                version = "unknown"

            try:
                domains = [d.value for d in scanner.domains]
            except Exception:
                domains = []

            return ScannerResult(
                scanner_name=scanner_name,
                scanner_version=version,
                domains=domains,
                error=str(e),
                success=False,
            )
