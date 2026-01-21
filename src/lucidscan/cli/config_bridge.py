"""Bridge between CLI arguments and configuration models."""

from __future__ import annotations

import argparse
from typing import Any, Dict, List

from lucidscan.config.models import LucidScanConfig
from lucidscan.core.logging import get_logger
from lucidscan.core.models import ScanDomain

LOGGER = get_logger(__name__)


class ConfigBridge:
    """Translates CLI arguments to configuration objects."""

    @staticmethod
    def args_to_overrides(args: argparse.Namespace) -> Dict[str, Any]:
        """Convert CLI arguments to config override dict.

        CLI arguments take precedence over config file values.

        Args:
            args: Parsed CLI arguments.

        Returns:
            Dictionary of config overrides.
        """
        overrides: Dict[str, Any] = {}

        # Domain toggles - only set if explicitly provided on CLI
        # Use getattr with defaults for subcommand compatibility
        scanners: Dict[str, Dict[str, Any]] = {}
        linters: Dict[str, Dict[str, Any]] = {}

        sca = getattr(args, "sca", False)
        sast = getattr(args, "sast", False)
        iac = getattr(args, "iac", False)
        container = getattr(args, "container", False)
        linting = getattr(args, "linting", False)
        fix = getattr(args, "fix", False)
        images = getattr(args, "images", None)

        # --all means "all configured domains", not "all possible domains"
        # Don't override config - let the config determine what's enabled
        # Only set overrides for explicitly specified domain flags
        if sca:
            scanners["sca"] = {"enabled": True}
        if sast:
            scanners["sast"] = {"enabled": True}
        if iac:
            scanners["iac"] = {"enabled": True}
        if container:
            scanners["container"] = {"enabled": True}
        if linting:
            linters["ruff"] = {"enabled": True}

        # Container images go into container scanner options
        if images:
            if "container" not in scanners:
                scanners["container"] = {}
            scanners["container"]["enabled"] = True
            scanners["container"]["images"] = images

        if scanners:
            overrides["scanners"] = scanners

        if linters:
            overrides["linters"] = linters

        # Fix mode for linting
        if fix:
            overrides["fix"] = True

        # Fail-on threshold
        fail_on = getattr(args, "fail_on", None)
        if fail_on:
            overrides["fail_on"] = fail_on

        return overrides

    @staticmethod
    def get_enabled_domains(
        config: LucidScanConfig,
        args: argparse.Namespace,
    ) -> List[ScanDomain]:
        """Determine which scan domains are enabled.

        If specific CLI flags (--sca, --sast, etc.) are provided, use those.
        If --all is provided, use domains from config file.
        If other domain flags (--test, --coverage, --lint, --type-check) are set,
        return empty list (user wants only those specific domains, not security).
        Otherwise, use domains enabled in config file.

        Args:
            config: Loaded configuration.
            args: Parsed CLI arguments.

        Returns:
            List of enabled ScanDomain values.
        """
        # Use getattr for subcommand compatibility
        sca = getattr(args, "sca", False)
        sast = getattr(args, "sast", False)
        iac = getattr(args, "iac", False)
        container = getattr(args, "container", False)
        all_domains = getattr(args, "all", False)

        # Check if specific security domain flags were set
        security_domains_set = any([sca, sast, iac, container])

        if security_domains_set:
            # Specific CLI flags take precedence
            domains: List[ScanDomain] = []
            if sca:
                domains.append(ScanDomain.SCA)
            if sast:
                domains.append(ScanDomain.SAST)
            if iac:
                domains.append(ScanDomain.IAC)
            if container:
                domains.append(ScanDomain.CONTAINER)
            return domains

        # Check if user specified non-security domain flags (testing, coverage, etc.)
        # If so, they don't want security scanning unless explicitly requested
        linting = getattr(args, "linting", False)
        type_checking = getattr(args, "type_checking", False)
        testing = getattr(args, "testing", False)
        coverage = getattr(args, "coverage", False)
        non_security_domains_set = any([linting, type_checking, testing, coverage])

        if non_security_domains_set and not all_domains:
            # User explicitly requested non-security domains only
            # Don't run security scanners unless explicitly requested
            return []

        # --all or no flags: use config file settings
        # This respects what's actually configured in lucidscan.yml
        enabled_domains: List[ScanDomain] = []
        for domain_name in config.get_enabled_domains():
            try:
                enabled_domains.append(ScanDomain(domain_name))
            except ValueError:
                LOGGER.warning(f"Unknown domain in config: {domain_name}")

        return enabled_domains
