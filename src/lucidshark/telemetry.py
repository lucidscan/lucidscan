"""Anonymous, opt-out telemetry for LucidShark.

Collects anonymous usage data to help improve the product. All data is
anonymous - no PII, no source code, no file paths, no IP addresses are stored.

Opt out by setting the environment variable:
    export LUCIDSHARK_TELEMETRY=0

Or by creating a file at ~/.lucidshark/telemetry-optout
"""

from __future__ import annotations

import atexit
import logging
import os
import platform
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

# PostHog project API key (public, safe to embed - this is a write-only key)
_POSTHOG_API_KEY = "phc_LucidShark_anonymous_telemetry_key"
_POSTHOG_HOST = "https://us.i.posthog.com"

_telemetry_client: Optional[Any] = None
_anonymous_id: Optional[str] = None
_enabled: Optional[bool] = None


def _get_lucidshark_dir() -> Path:
    """Get the ~/.lucidshark directory path."""
    return Path.home() / ".lucidshark"


def is_enabled() -> bool:
    """Check if telemetry is enabled.

    Telemetry is enabled by default. It can be disabled by:
    1. Setting LUCIDSHARK_TELEMETRY=0 (or "false", "no", "off")
    2. Setting DO_NOT_TRACK=1 (standard env var)
    3. Creating ~/.lucidshark/telemetry-optout file
    4. Running in CI (CI=true env var) - CI environments are excluded

    Returns:
        True if telemetry should be collected.
    """
    global _enabled
    if _enabled is not None:
        return _enabled

    # Check LUCIDSHARK_TELEMETRY env var
    telemetry_env = os.environ.get("LUCIDSHARK_TELEMETRY", "").lower().strip()
    if telemetry_env in ("0", "false", "no", "off"):
        _enabled = False
        return False

    # Check DO_NOT_TRACK standard env var
    if os.environ.get("DO_NOT_TRACK", "").strip() == "1":
        _enabled = False
        return False

    # Check CI env var - don't collect from CI runs
    ci_env = os.environ.get("CI", "").lower().strip()
    if ci_env in ("true", "1"):
        _enabled = False
        return False

    # Check opt-out file
    optout_file = _get_lucidshark_dir() / "telemetry-optout"
    if optout_file.exists():
        _enabled = False
        return False

    _enabled = True
    return True


def _get_anonymous_id() -> str:
    """Get or create a stable anonymous identifier.

    Stores a random UUID in ~/.lucidshark/anonymous-id. This ID has no
    connection to the user's identity - it's purely for counting unique
    installations.

    Returns:
        Anonymous UUID string.
    """
    global _anonymous_id
    if _anonymous_id is not None:
        return _anonymous_id

    id_file = _get_lucidshark_dir() / "anonymous-id"

    try:
        if id_file.exists():
            stored_id = id_file.read_text().strip()
            if stored_id:
                _anonymous_id = stored_id
                return stored_id
    except OSError:
        pass

    # Generate new ID
    new_id = str(uuid.uuid4())

    try:
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(new_id)
    except OSError:
        pass

    _anonymous_id = new_id
    return new_id


def _get_client() -> Optional[Any]:
    """Get or initialize the PostHog client.

    Returns:
        PostHog client instance, or None if unavailable.
    """
    global _telemetry_client

    if _telemetry_client is not None:
        return _telemetry_client

    try:
        from posthog import Posthog

        client = Posthog(
            api_key=_POSTHOG_API_KEY,
            host=_POSTHOG_HOST,
            sync_mode=False,
        )
        # Disable PostHog's own logging to avoid noise
        client.log = logging.getLogger("posthog")
        client.log.setLevel(logging.CRITICAL)

        # Register shutdown handler to flush events
        atexit.register(_shutdown)

        _telemetry_client = client
        return client
    except Exception:
        LOGGER.debug("PostHog client not available, telemetry disabled")
        return None


def _shutdown() -> None:
    """Flush and shut down the telemetry client."""
    global _telemetry_client
    if _telemetry_client is not None:
        try:
            _telemetry_client.flush()
            _telemetry_client.shutdown()
        except Exception:
            pass
        _telemetry_client = None


def _get_base_properties() -> Dict[str, Any]:
    """Get base properties included with every event.

    Returns:
        Dictionary of anonymous system properties.
    """
    from lucidshark import __version__

    return {
        "lucidshark_version": __version__,
        "os": platform.system().lower(),
        "os_version": platform.release(),
        "arch": platform.machine(),
        "python_version": platform.python_version(),
    }


def track_event(event_name: str, properties: Optional[Dict[str, Any]] = None) -> None:
    """Track an anonymous telemetry event.

    This is fire-and-forget - it never raises exceptions or blocks the CLI.

    Args:
        event_name: Name of the event (e.g., "scan_completed").
        properties: Optional event properties.
    """
    if not is_enabled():
        return

    try:
        client = _get_client()
        if client is None:
            return

        all_properties = _get_base_properties()
        if properties:
            all_properties.update(properties)

        client.capture(
            distinct_id=_get_anonymous_id(),
            event=event_name,
            properties=all_properties,
        )
    except Exception:
        # Never let telemetry crash the CLI
        LOGGER.debug("Failed to send telemetry event", exc_info=True)


def track_command(command_name: str) -> None:
    """Track a CLI command execution.

    Args:
        command_name: The command that was run (scan, init, doctor, etc.).
    """
    track_event("command_executed", {"command": command_name})


def track_scan_completed(
    domains: List[str],
    languages: List[str],
    tools_used: List[str],
    total_issues: int,
    issues_by_severity: Dict[str, int],
    issues_by_domain: Dict[str, int],
    duration_ms: int,
    scan_mode: str,
    output_format: str,
    fix_enabled: bool,
    coverage_percent: Optional[float] = None,
    duplication_percent: Optional[float] = None,
) -> None:
    """Track a completed scan with anonymous metadata.

    All data is aggregate/categorical - no file paths, code, or PII.

    Args:
        domains: List of domains scanned (e.g., ["linting", "sast"]).
        languages: List of project languages (e.g., ["python", "typescript"]).
        tools_used: List of tool names used (e.g., ["ruff", "trivy"]).
        total_issues: Total number of active issues found.
        issues_by_severity: Issue counts by severity level.
        issues_by_domain: Issue counts by domain.
        duration_ms: Scan duration in milliseconds.
        scan_mode: "incremental" or "full".
        output_format: Output format used (json, table, etc.).
        fix_enabled: Whether --fix was used.
        coverage_percent: Coverage percentage if coverage was run.
        duplication_percent: Duplication percentage if duplication was run.
    """
    properties: Dict[str, Any] = {
        "domains": sorted(domains),
        "domain_count": len(domains),
        "languages": sorted(languages),
        "language_count": len(languages),
        "tools_used": sorted(tools_used),
        "tool_count": len(tools_used),
        "total_issues": total_issues,
        "issues_by_severity": issues_by_severity,
        "issues_by_domain": issues_by_domain,
        "duration_ms": duration_ms,
        "scan_mode": scan_mode,
        "output_format": output_format,
        "fix_enabled": fix_enabled,
    }

    if coverage_percent is not None:
        properties["coverage_percent"] = round(coverage_percent, 1)
    if duplication_percent is not None:
        properties["duplication_percent"] = round(duplication_percent, 1)

    track_event("scan_completed", properties)


def reset() -> None:
    """Reset telemetry state. Used for testing."""
    global _telemetry_client, _anonymous_id, _enabled
    _shutdown()
    _telemetry_client = None
    _anonymous_id = None
    _enabled = None
