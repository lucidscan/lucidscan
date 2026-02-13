"""Secure download utilities with SSL certificate handling.

This module provides SSL-aware download functions that work correctly
on macOS standalone binaries where the system certificate store is not
accessible by default.
"""

from __future__ import annotations

import ssl
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

import certifi


def get_ssl_context() -> ssl.SSLContext:
    """Get an SSL context that uses certifi's CA bundle.

    This is necessary for standalone binaries on macOS where Python
    cannot access the system's certificate store.

    Returns:
        An SSL context configured with certifi's CA certificates.
    """
    return ssl.create_default_context(cafile=certifi.where())


def secure_urlopen(url: str, timeout: Optional[float] = 30.0):
    """Open a URL with proper SSL certificate verification.

    Args:
        url: The URL to open.
        timeout: Connection timeout in seconds.

    Returns:
        A file-like object for reading the response.

    Raises:
        URLError: If the URL cannot be opened.
        ValueError: If the URL is not HTTPS.
    """
    if not url.startswith("https://"):
        raise ValueError(f"Only HTTPS URLs are supported: {url}")

    ssl_context = get_ssl_context()
    return urlopen(url, timeout=timeout, context=ssl_context)  # nosec B310


def download_file(url: str, dest_path: Path, timeout: Optional[float] = 60.0) -> None:
    """Download a file from a URL with proper SSL certificate verification.

    Args:
        url: The URL to download from.
        dest_path: Path to save the downloaded file.
        timeout: Connection timeout in seconds.

    Raises:
        URLError: If the URL cannot be opened.
        ValueError: If the URL is not HTTPS.
        IOError: If the file cannot be written.
    """
    with secure_urlopen(url, timeout=timeout) as response:
        dest_path.write_bytes(response.read())
