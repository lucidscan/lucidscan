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
        scanners: Dict[str, Dict[str, Any]] = {}

        if args.all:
            # Enable all domains
            for domain in ["sca", "sast", "iac", "container"]:
                scanners[domain] = {"enabled": True}
        else:
            if args.sca:
                scanners["sca"] = {"enabled": True}
            if args.sast:
                scanners["sast"] = {"enabled": True}
            if args.iac:
                scanners["iac"] = {"enabled": True}
            if args.container:
                scanners["container"] = {"enabled": True}

        # Container images go into container scanner options
        if args.images:
            if "container" not in scanners:
                scanners["container"] = {}
            scanners["container"]["enabled"] = True
            scanners["container"]["images"] = args.images

        if scanners:
            overrides["scanners"] = scanners

        # Fail-on threshold
        if args.fail_on:
            overrides["fail_on"] = args.fail_on

        # AI enrichment toggle
        if hasattr(args, "ai") and args.ai:
            overrides["ai"] = {"enabled": True}

        return overrides

    @staticmethod
    def get_enabled_domains(
        config: LucidScanConfig,
        args: argparse.Namespace,
    ) -> List[ScanDomain]:
        """Determine which scan domains are enabled.

        If CLI flags (--sca, --sast, etc.) are provided, use those.
        Otherwise, use domains enabled in config file.

        Args:
            config: Loaded configuration.
            args: Parsed CLI arguments.

        Returns:
            List of enabled ScanDomain values.
        """
        # Check if any domain flags were explicitly set on CLI
        cli_domains_set = any([
            args.sca,
            args.sast,
            args.iac,
            args.container,
            args.all,
        ])

        if cli_domains_set:
            # CLI flags take precedence - use what was explicitly requested
            domains: List[ScanDomain] = []
            if args.all:
                domains = [
                    ScanDomain.SCA,
                    ScanDomain.SAST,
                    ScanDomain.IAC,
                    ScanDomain.CONTAINER,
                ]
            else:
                if args.sca:
                    domains.append(ScanDomain.SCA)
                if args.sast:
                    domains.append(ScanDomain.SAST)
                if args.iac:
                    domains.append(ScanDomain.IAC)
                if args.container:
                    domains.append(ScanDomain.CONTAINER)
            return domains

        # Use config file settings
        enabled_domains: List[ScanDomain] = []
        for domain_name in config.get_enabled_domains():
            try:
                enabled_domains.append(ScanDomain(domain_name))
            except ValueError:
                LOGGER.warning(f"Unknown domain in config: {domain_name}")

        return enabled_domains
