"""Background auto-update for LucidShark.

Implements a two-phase update system:

Phase A (background): During normal CLI execution, a daemon thread checks
GitHub for a newer release (at most once per 24h). If found, it silently
downloads the new binary to .lucidshark/cache/pending-update/.

Phase B (apply): On the next CLI invocation, if a pending update exists,
the binary is validated, atomically swapped in, and the process re-execs.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)

# GitHub release API endpoint
GITHUB_REPO = "toniantunovi/lucidshark"
GITHUB_API_LATEST = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
)

# Cache settings
CHECK_INTERVAL_SECONDS = 86400  # 24 hours
UPDATE_CHECK_FILE = "update_check.json"
PENDING_UPDATE_DIR = "pending-update"
PENDING_VERSION_FILE = "version.json"

# Minimum binary size to consider valid (1 MB)
MIN_BINARY_SIZE = 1_000_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_version(v: str) -> tuple:
    """Parse a version string like '0.7.0' into a comparable tuple."""
    v = v.lstrip("v")
    parts = []
    for part in v.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer(candidate: str, current: str) -> bool:
    """Return True if *candidate* is strictly newer than *current*."""
    return _parse_version(candidate) > _parse_version(current)


def get_self_binary_path() -> Optional[Path]:
    """Return the path to the currently running lucidshark binary.

    Returns None when running from source (not a PyInstaller bundle),
    which disables auto-update during development.
    """
    if not getattr(sys, "frozen", False):
        return None

    binary = Path(sys.executable).resolve()
    if binary.exists():
        return binary
    return None


# ---------------------------------------------------------------------------
# Phase B: Apply pending update
# ---------------------------------------------------------------------------


def apply_pending_update(cache_dir: Path, current_version: str) -> Optional[str]:
    """Check for and apply a pending update.

    Args:
        cache_dir: The .lucidshark/cache directory.
        current_version: Current LucidShark version string.

    Returns:
        The new version string if an update was applied, None otherwise.
    """
    pending_dir = cache_dir / PENDING_UPDATE_DIR
    pending_binary = pending_dir / "lucidshark"
    version_file = pending_dir / PENDING_VERSION_FILE

    if not pending_binary.exists() or not version_file.exists():
        return None

    try:
        with open(version_file, "r") as f:
            meta = json.load(f)
        new_version = meta.get("version", "")
    except Exception:
        _cleanup_pending(pending_dir)
        return None

    if not new_version or not _is_newer(new_version, current_version):
        _cleanup_pending(pending_dir)
        return None

    # Validate: file is large enough to be a real binary
    if pending_binary.stat().st_size < MIN_BINARY_SIZE:
        LOGGER.debug("Pending update binary too small, discarding")
        _cleanup_pending(pending_dir)
        return None

    # Validate: file is executable
    if not os.access(pending_binary, os.X_OK):
        LOGGER.debug("Pending update binary not executable, discarding")
        _cleanup_pending(pending_dir)
        return None

    # Apply: atomic swap
    self_path = get_self_binary_path()
    if self_path is None:
        return None

    try:
        # Write pending binary next to the running binary, then atomic rename.
        # os.rename is atomic on the same filesystem on Unix.
        staging = self_path.parent / "lucidshark.update"
        shutil.copy2(pending_binary, staging)
        os.chmod(staging, staging.stat().st_mode | stat.S_IEXEC)
        os.rename(staging, self_path)
    except OSError as e:
        LOGGER.debug(f"Failed to apply update: {e}")
        # Clean up staging file if it exists
        staging = self_path.parent / "lucidshark.update"
        if staging.exists():
            staging.unlink(missing_ok=True)
        return None

    _cleanup_pending(pending_dir)
    return new_version


def re_exec() -> None:
    """Replace the current process with the (now updated) binary.

    Uses os.execv to restart with the same arguments. This is a no-return
    call -- the current process image is replaced entirely.
    """
    os.execv(sys.executable, [sys.executable] + sys.argv[1:])


def _cleanup_pending(pending_dir: Path) -> None:
    """Remove the pending-update directory."""
    try:
        shutil.rmtree(pending_dir, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase A: Background check + download
# ---------------------------------------------------------------------------


def should_check_for_update(cache_dir: Path) -> bool:
    """Return True if enough time has passed since the last check."""
    check_file = cache_dir / UPDATE_CHECK_FILE
    if not check_file.exists():
        return True

    try:
        with open(check_file, "r") as f:
            data = json.load(f)
        last_check = data.get("last_check_utc", "")
        last_dt = datetime.fromisoformat(last_check)
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
        return elapsed >= CHECK_INTERVAL_SECONDS
    except Exception:
        return True


def check_for_update(
    cache_dir: Path,
    current_version: str,
) -> Optional[Dict[str, Any]]:
    """Query GitHub API for the latest release.

    Returns release info dict if a newer version is available, None otherwise.
    Also writes the check timestamp to the cache file regardless of result.
    """
    from lucidshark.bootstrap.download import secure_urlopen
    from lucidshark.bootstrap.platform import get_platform_info

    now_utc = datetime.now(timezone.utc).isoformat()

    try:
        platform_info = get_platform_info()
    except ValueError:
        return None

    try:
        with secure_urlopen(GITHUB_API_LATEST, timeout=10) as resp:
            release = json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Network error — silently skip, don't block the CLI
        return None

    tag = release.get("tag_name", "")
    latest_version = tag.lstrip("v")

    # Build download URL for this platform
    asset_name = f"lucidshark-{platform_info.bundle_name}"
    download_url = (
        f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{asset_name}"
    )

    # Write cache regardless of whether there's an update
    _write_check_cache(cache_dir, now_utc, latest_version, current_version)

    if _is_newer(latest_version, current_version):
        return {
            "version": latest_version,
            "download_url": download_url,
            "tag": tag,
        }

    return None


def download_pending_update(
    cache_dir: Path,
    download_url: str,
    version: str,
) -> bool:
    """Download the new binary to the pending-update staging area.

    Returns True on success, False on any error.
    """
    from lucidshark.bootstrap.download import download_file

    pending_dir = cache_dir / PENDING_UPDATE_DIR
    pending_binary = pending_dir / "lucidshark"
    version_file = pending_dir / PENDING_VERSION_FILE

    try:
        pending_dir.mkdir(parents=True, exist_ok=True)

        # Download to a temp file first, then rename into place
        tmp = pending_dir / "lucidshark.tmp"
        download_file(download_url, tmp, timeout=120)

        # Validate size
        if tmp.stat().st_size < MIN_BINARY_SIZE:
            tmp.unlink(missing_ok=True)
            return False

        # Make executable and move into place
        os.chmod(tmp, 0o755)
        os.rename(tmp, pending_binary)

        # Write version metadata
        meta = {
            "version": version,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "url": download_url,
        }
        with open(version_file, "w") as f:
            json.dump(meta, f)

        LOGGER.debug(f"Downloaded pending update v{version}")
        return True

    except Exception as e:
        LOGGER.debug(f"Failed to download update: {e}")
        # Clean up partial downloads
        _cleanup_pending(pending_dir)
        return False


def _write_check_cache(
    cache_dir: Path,
    timestamp: str,
    latest_version: str,
    current_version: str,
) -> None:
    """Write the update check cache file."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    check_file = cache_dir / UPDATE_CHECK_FILE
    data = {
        "last_check_utc": timestamp,
        "latest_version": latest_version,
        "current_version_at_check": current_version,
    }
    try:
        with open(check_file, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def background_update_check(cache_dir: Path, current_version: str) -> None:
    """Orchestrate the background update check and download.

    This runs in a daemon thread. It must never raise — all exceptions
    are caught and logged at debug level.
    """
    try:
        if not should_check_for_update(cache_dir):
            return

        result = check_for_update(cache_dir, current_version)
        if result is None:
            return

        # Don't re-download if we already have this version staged
        pending_version_file = cache_dir / PENDING_UPDATE_DIR / PENDING_VERSION_FILE
        if pending_version_file.exists():
            try:
                with open(pending_version_file, "r") as f:
                    existing = json.load(f)
                if existing.get("version") == result["version"]:
                    return
            except Exception:
                pass

        download_pending_update(
            cache_dir,
            result["download_url"],
            result["version"],
        )
    except Exception as e:
        LOGGER.debug(f"Background update check failed: {e}")


def start_background_update_check(cache_dir: Path, current_version: str) -> None:
    """Spawn a daemon thread to check for and download updates.

    The thread is a daemon so it won't prevent process exit if the main
    CLI command finishes before the check completes.
    """
    thread = threading.Thread(
        target=background_update_check,
        args=(cache_dir, current_version),
        daemon=True,
        name="lucidshark-update-check",
    )
    thread.start()
