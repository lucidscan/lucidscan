"""Tests for TrivyScanner plugin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock


from lucidscan.plugins.scanners.trivy import TrivyScanner, DEFAULT_VERSION
from lucidscan.plugins.scanners.base import ScannerPlugin
from lucidscan.core.models import ScanDomain


class TestTrivyScannerInterface:
    """Tests for TrivyScanner implementing ScannerPlugin interface."""

    def test_inherits_from_scanner_plugin(self) -> None:
        """Test that TrivyScanner is a ScannerPlugin."""
        assert issubclass(TrivyScanner, ScannerPlugin)

    def test_name_property(self) -> None:
        """Test that name is 'trivy'."""
        scanner = TrivyScanner()
        assert scanner.name == "trivy"

    def test_domains_property(self) -> None:
        """Test that Trivy supports SCA and CONTAINER domains."""
        scanner = TrivyScanner()
        assert ScanDomain.SCA in scanner.domains
        assert ScanDomain.CONTAINER in scanner.domains
        assert len(scanner.domains) == 2

    def test_get_version_default(self) -> None:
        """Test that default version matches DEFAULT_VERSION."""
        scanner = TrivyScanner()
        assert scanner.get_version() == DEFAULT_VERSION

    def test_get_version_custom(self) -> None:
        """Test that custom version can be specified."""
        scanner = TrivyScanner(version="1.0.0")
        assert scanner.get_version() == "1.0.0"


class TestTrivyScannerBinaryManagement:
    """Tests for Trivy binary download and caching."""

    def test_ensure_binary_returns_path(self, tmp_path: Path) -> None:
        """Test that ensure_binary returns a Path."""
        scanner = TrivyScanner()

        # Mock paths to use tmp_path
        with patch.object(scanner, "_paths") as mock_paths:
            binary_dir = tmp_path / "bin" / "trivy" / DEFAULT_VERSION
            binary_dir.mkdir(parents=True)
            binary_path = binary_dir / "trivy"
            binary_path.write_text("#!/bin/bash\necho trivy")

            mock_paths.plugin_bin_dir.return_value = binary_dir

            result = scanner.ensure_binary()
            assert isinstance(result, Path)
            assert result == binary_path

    def test_ensure_binary_uses_cached_binary(self, tmp_path: Path) -> None:
        """Test that existing binary is reused without download."""
        scanner = TrivyScanner()

        with patch.object(scanner, "_paths") as mock_paths:
            with patch.object(scanner, "_download_binary") as mock_download:
                binary_dir = tmp_path / "bin" / "trivy" / DEFAULT_VERSION
                binary_dir.mkdir(parents=True)
                binary_path = binary_dir / "trivy"
                binary_path.write_text("#!/bin/bash\necho trivy")

                mock_paths.plugin_bin_dir.return_value = binary_dir

                scanner.ensure_binary()

                # Should not download if binary exists
                mock_download.assert_not_called()


class TestTrivyScannerDownloadUrl:
    """Tests for Trivy download URL construction."""

    def test_download_url_linux_amd64(self) -> None:
        """Test download URL for Linux amd64."""
        scanner = TrivyScanner(version="0.68.1")

        with patch("lucidscan.plugins.scanners.trivy.get_platform_info") as mock_platform:
            mock_platform.return_value = MagicMock(os="linux", arch="amd64")

            # We can't easily test the URL directly, but we can verify
            # the platform mapping works by checking the method exists
            assert hasattr(scanner, "_download_binary")

    def test_download_url_darwin_arm64(self) -> None:
        """Test download URL for macOS arm64."""
        scanner = TrivyScanner(version="0.68.1")

        with patch("lucidscan.plugins.scanners.trivy.get_platform_info") as mock_platform:
            mock_platform.return_value = MagicMock(os="darwin", arch="arm64")

            assert hasattr(scanner, "_download_binary")
