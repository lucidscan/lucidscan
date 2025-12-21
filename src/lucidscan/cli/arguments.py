"""Argument parser construction for lucidscan CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

EXAMPLES = """\
Examples:
  Quick SCA scan (dependencies):
    lucidscan --sca

  Full security scan:
    lucidscan --all

  Scan with CI threshold (exit 1 on high+ severity):
    lucidscan --all --fail-on high

  Container image scan:
    lucidscan --container --image nginx:latest --image redis:7

  SAST scan with JSON output:
    lucidscan --sast --format json > results.json

  IaC scan for Terraform files:
    lucidscan --iac

  Use custom config file:
    lucidscan --all --config ./security/lucidscan.yml

  Check scanner status:
    lucidscan --status
"""


def _add_global_options(parser: argparse.ArgumentParser) -> None:
    """Add global options: version, debug, verbose, quiet, format."""
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
        default=None,
        help="Output format (default: json, or as specified in config file).",
    )


def _add_diagnostic_options(parser: argparse.ArgumentParser) -> None:
    """Add diagnostic options: status, list-scanners."""
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show scanner plugin status and installed versions.",
    )
    parser.add_argument(
        "--list-scanners",
        action="store_true",
        help="List all available scanner plugins and exit.",
    )


def _add_domain_options(parser: argparse.ArgumentParser) -> None:
    """Add scanner domain options: sca, container, iac, sast, all."""
    parser.add_argument(
        "--sca",
        action="store_true",
        help="Scan dependencies for known vulnerabilities (uses Trivy).",
    )
    parser.add_argument(
        "--container",
        action="store_true",
        help="Scan container images for vulnerabilities. Use with --image.",
    )
    parser.add_argument(
        "--iac",
        action="store_true",
        help="Scan Infrastructure-as-Code (Terraform, K8s, CloudFormation).",
    )
    parser.add_argument(
        "--sast",
        action="store_true",
        help="Static application security testing (code pattern analysis).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Enable all scanner types (SCA, SAST, IaC, Container).",
    )


def _add_target_options(parser: argparse.ArgumentParser) -> None:
    """Add target options: path, image."""
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to scan (default: current directory).",
    )
    parser.add_argument(
        "--image",
        action="append",
        dest="images",
        metavar="IMAGE",
        help="Container image to scan (can be specified multiple times).",
    )


def _add_config_options(parser: argparse.ArgumentParser) -> None:
    """Add configuration options: config, fail-on."""
    parser.add_argument(
        "--fail-on",
        choices=["critical", "high", "medium", "low"],
        default=None,
        help="Exit with code 1 if issues at or above this severity are found.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        help="Path to config file (default: .lucidscan.yml in project root).",
    )


def _add_execution_options(parser: argparse.ArgumentParser) -> None:
    """Add execution options: sequential."""
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Disable parallel scanner execution (for debugging).",
    )


def _add_enricher_options(parser: argparse.ArgumentParser) -> None:
    """Add enricher options: ai."""
    parser.add_argument(
        "--ai",
        action="store_true",
        help="Enable AI-powered explanations for issues (requires API key).",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for lucidscan CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="lucidscan",
        description="LucidScan - Plugin-based security scanning framework.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    _add_global_options(parser)
    _add_diagnostic_options(parser)
    _add_domain_options(parser)
    _add_target_options(parser)
    _add_config_options(parser)
    _add_execution_options(parser)
    _add_enricher_options(parser)

    return parser
