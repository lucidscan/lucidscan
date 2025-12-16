from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from importlib.metadata import version, PackageNotFoundError

from lucidscan.core.logging import configure_logging, get_logger
from lucidscan.core.models import (
    ScanContext,
    ScanDomain,
    ScanMetadata,
    ScanResult,
    UnifiedIssue,
)
from lucidscan.bootstrap.paths import get_lucidscan_home, LucidscanPaths
from lucidscan.bootstrap.platform import get_platform_info
from lucidscan.bootstrap.validation import validate_binary, ToolStatus
from lucidscan.scanners import discover_scanner_plugins, get_scanner_plugin
from lucidscan.reporters import get_reporter_plugin


LOGGER = get_logger(__name__)

# Exit codes per Section 14 of the spec
EXIT_SUCCESS = 0
EXIT_ISSUES_FOUND = 1
EXIT_SCANNER_ERROR = 2
EXIT_INVALID_USAGE = 3
EXIT_BOOTSTRAP_FAILURE = 4


def _get_version() -> str:
    try:
        return version("lucidscan")
    except PackageNotFoundError:
        # Fallback for editable installs that have not yet built metadata.
        from lucidscan import __version__

        return __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lucidscan",
        description="lucidscan — Plugin-based security scanning framework.",
    )

    # Global options
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show lucidscan version and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (info-level) logging.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce logging output to errors only.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table", "sarif", "summary"],
        default="json",
        help="Output format (default: json).",
    )

    # Status flag
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show scanner plugin status and installed versions.",
    )

    # Scanner domain flags
    parser.add_argument(
        "--sca",
        action="store_true",
        help="Enable Software Composition Analysis (Trivy plugin).",
    )
    parser.add_argument(
        "--container",
        action="store_true",
        help="Enable container image scanning (Trivy plugin).",
    )
    parser.add_argument(
        "--iac",
        action="store_true",
        help="Enable Infrastructure-as-Code scanning (Checkov plugin).",
    )
    parser.add_argument(
        "--sast",
        action="store_true",
        help="Enable static application security testing (OpenGrep plugin).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Enable all scanner plugins.",
    )

    # Target path
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to scan (default: current directory).",
    )

    # Container image targets
    parser.add_argument(
        "--image",
        action="append",
        dest="images",
        metavar="IMAGE",
        help="Container image to scan (can be specified multiple times).",
    )

    # Severity threshold for exit code
    parser.add_argument(
        "--fail-on",
        choices=["critical", "high", "medium", "low"],
        default=None,
        help="Exit with code 1 if issues at or above this severity are found.",
    )

    return parser


def _handle_status() -> int:
    """Handle --status command.

    Shows scanner plugin status and environment information.

    Returns:
        Exit code (0 for success).
    """
    home = get_lucidscan_home()
    paths = LucidscanPaths(home)
    platform_info = get_platform_info()

    print(f"lucidscan version: {_get_version()}")
    print(f"Platform: {platform_info.os}-{platform_info.arch}")
    print(f"Binary cache: {home}/bin/")
    print()

    # Discover plugins via entry points
    print("Scanner plugins:")
    plugins = discover_scanner_plugins()

    if plugins:
        for name, plugin_class in sorted(plugins.items()):
            try:
                plugin = plugin_class()
                domains = ", ".join(d.value.upper() for d in plugin.domains)
                binary_dir = paths.plugin_bin_dir(name, plugin.get_version())
                binary_path = binary_dir / name

                status = validate_binary(binary_path)
                if status == ToolStatus.PRESENT:
                    status_str = f"v{plugin.get_version()} installed"
                else:
                    status_str = f"v{plugin.get_version()} (not downloaded)"

                print(f"  {name}: {status_str} [{domains}]")
            except Exception as e:
                print(f"  {name}: error loading plugin ({e})")
    else:
        print("  No plugins discovered.")

    print()
    print("Scanner binaries are downloaded automatically on first use.")

    return EXIT_SUCCESS


def _get_enabled_domains(args: argparse.Namespace) -> List[ScanDomain]:
    """Determine which scan domains are enabled based on CLI arguments."""
    domains: List[ScanDomain] = []

    if args.all:
        # Enable all domains we have plugins for
        domains = [ScanDomain.SCA, ScanDomain.CONTAINER, ScanDomain.SAST, ScanDomain.IAC]
    else:
        if args.sca:
            domains.append(ScanDomain.SCA)
        if args.container:
            domains.append(ScanDomain.CONTAINER)
        if args.iac:
            domains.append(ScanDomain.IAC)
        if args.sast:
            domains.append(ScanDomain.SAST)

    return domains


def _run_scan(args: argparse.Namespace) -> ScanResult:
    """Execute the scan based on CLI arguments.

    Args:
        args: Parsed CLI arguments.

    Returns:
        ScanResult containing all issues found.
    """
    start_time = datetime.now(timezone.utc)
    project_root = Path(args.path).resolve()

    if not project_root.exists():
        raise FileNotFoundError(f"Path does not exist: {project_root}")

    enabled_domains = _get_enabled_domains(args)
    if not enabled_domains:
        LOGGER.warning("No scan domains enabled")
        return ScanResult()

    # Build scan context
    config: Dict[str, Any] = {}
    if args.images:
        config["container_images"] = args.images

    context = ScanContext(
        project_root=project_root,
        paths=[project_root],
        enabled_domains=enabled_domains,
        config=config,
    )

    all_issues: List[UnifiedIssue] = []
    scanners_used: List[Dict[str, Any]] = []

    # Map domains to scanner plugins
    domain_to_scanner = {
        ScanDomain.SCA: "trivy",
        ScanDomain.CONTAINER: "trivy",
        ScanDomain.SAST: "opengrep",
        ScanDomain.IAC: "checkov",
    }

    # Collect unique scanners needed
    needed_scanners: set[str] = set()
    for domain in enabled_domains:
        scanner_name = domain_to_scanner.get(domain)
        if scanner_name:
            needed_scanners.add(scanner_name)
        else:
            LOGGER.warning(f"No scanner available for domain: {domain.value}")

    # Run each scanner
    for scanner_name in needed_scanners:
        scanner = get_scanner_plugin(scanner_name)
        if not scanner:
            LOGGER.error(f"Scanner plugin '{scanner_name}' not found")
            continue

        LOGGER.info(f"Running {scanner_name} scanner...")

        try:
            issues = scanner.scan(context)
            all_issues.extend(issues)

            scanners_used.append({
                "name": scanner_name,
                "version": scanner.get_version(),
                "domains": [d.value for d in scanner.domains],
            })

            LOGGER.info(f"{scanner_name}: found {len(issues)} issues")

        except Exception as e:
            LOGGER.error(f"Scanner {scanner_name} failed: {e}")

    end_time = datetime.now(timezone.utc)
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    # Build result
    result = ScanResult(issues=all_issues)
    result.metadata = ScanMetadata(
        lucidscan_version=_get_version(),
        scan_started_at=start_time.isoformat(),
        scan_finished_at=end_time.isoformat(),
        duration_ms=duration_ms,
        project_root=str(project_root),
        scanners_used=scanners_used,
    )
    result.summary = result.compute_summary()

    return result


def _check_severity_threshold(
    result: ScanResult, threshold: Optional[str]
) -> bool:
    """Check if any issues meet or exceed the severity threshold.

    Args:
        result: Scan result to check.
        threshold: Severity threshold ('critical', 'high', 'medium', 'low').

    Returns:
        True if issues at or above threshold exist, False otherwise.
    """
    if not threshold or not result.issues:
        return False

    threshold_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    threshold_level = threshold_order.get(threshold.lower(), 99)

    for issue in result.issues:
        issue_level = threshold_order.get(issue.severity.value, 99)
        if issue_level <= threshold_level:
            return True

    return False


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI entrypoint.

    Returns an exit code suitable for use as a console script.
    """

    parser = build_parser()

    # Handle --help specially to return 0
    if argv is not None:
        argv_list = list(argv)
        if "--help" in argv_list or "-h" in argv_list:
            parser.print_help()
            return EXIT_SUCCESS
    else:
        argv_list = None

    args = parser.parse_args(argv_list)

    # Configure logging as early as possible.
    configure_logging(debug=args.debug, verbose=args.verbose, quiet=args.quiet)

    if args.version:
        print(_get_version())
        return EXIT_SUCCESS

    if args.status:
        return _handle_status()

    # Scanner execution
    if any([args.sca, args.container, args.iac, args.sast, args.all]):
        try:
            result = _run_scan(args)

            # Get reporter plugin
            reporter = get_reporter_plugin(args.format)
            if not reporter:
                LOGGER.error(f"Reporter plugin '{args.format}' not found")
                return EXIT_SCANNER_ERROR

            # Write output to stdout
            reporter.report(result, sys.stdout)

            # Check severity threshold for exit code
            if _check_severity_threshold(result, args.fail_on):
                return EXIT_ISSUES_FOUND

            return EXIT_SUCCESS

        except FileNotFoundError as e:
            LOGGER.error(str(e))
            return EXIT_INVALID_USAGE
        except Exception as e:
            LOGGER.error(f"Scan failed: {e}")
            return EXIT_SCANNER_ERROR

    # If no scanners are selected, show help to guide users.
    parser.print_help()
    return EXIT_SUCCESS


if __name__ == "__main__":  # pragma: no cover - exercised via console script
    raise SystemExit(main())
