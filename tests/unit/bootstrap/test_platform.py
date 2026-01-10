"""Tests for platform detection functionality."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lucidscan.bootstrap.platform import (
    get_platform_info,
    PlatformInfo,
    detect_os,
    detect_arch,
    normalize_arch,
)


class TestDetectOS:
    """Tests for OS detection."""

    def test_detect_os_darwin(self) -> None:
        with patch("platform.system", return_value="Darwin"):
            assert detect_os() == "darwin"

    def test_detect_os_linux(self) -> None:
        with patch("platform.system", return_value="Linux"):
            assert detect_os() == "linux"

    def test_detect_os_windows(self) -> None:
        with patch("platform.system", return_value="Windows"):
            assert detect_os() == "windows"

    def test_detect_os_unknown_raises(self) -> None:
        with patch("platform.system", return_value="UnknownOS"):
            with pytest.raises(ValueError, match="Unsupported operating system"):
                detect_os()


class TestDetectArch:
    """Tests for architecture detection."""

    def test_detect_arch_x86_64(self) -> None:
        with patch("platform.machine", return_value="x86_64"):
            assert detect_arch() == "amd64"

    def test_detect_arch_amd64(self) -> None:
        with patch("platform.machine", return_value="AMD64"):
            assert detect_arch() == "amd64"

    def test_detect_arch_arm64(self) -> None:
        with patch("platform.machine", return_value="arm64"):
            assert detect_arch() == "arm64"

    def test_detect_arch_aarch64(self) -> None:
        with patch("platform.machine", return_value="aarch64"):
            assert detect_arch() == "arm64"

    def test_detect_arch_unknown_raises(self) -> None:
        with patch("platform.machine", return_value="mips"):
            with pytest.raises(ValueError, match="Unsupported architecture"):
                detect_arch()


class TestNormalizeArch:
    """Tests for architecture normalization."""

    def test_normalize_x86_64(self) -> None:
        assert normalize_arch("x86_64") == "amd64"

    def test_normalize_amd64(self) -> None:
        assert normalize_arch("AMD64") == "amd64"

    def test_normalize_arm64(self) -> None:
        assert normalize_arch("arm64") == "arm64"

    def test_normalize_aarch64(self) -> None:
        assert normalize_arch("aarch64") == "arm64"

    def test_normalize_unknown(self) -> None:
        assert normalize_arch("unknown") is None


class TestPlatformInfo:
    """Tests for PlatformInfo dataclass."""

    def test_platform_info_creation(self) -> None:
        info = PlatformInfo(os="linux", arch="amd64")
        assert info.os == "linux"
        assert info.arch == "amd64"

    def test_platform_info_bundle_name(self) -> None:
        info = PlatformInfo(os="darwin", arch="arm64")
        assert info.bundle_name == "darwin-arm64"

    def test_platform_info_is_supported_valid(self) -> None:
        info = PlatformInfo(os="linux", arch="amd64")
        assert info.is_supported() is True

    def test_platform_info_is_supported_invalid_os(self) -> None:
        info = PlatformInfo(os="freebsd", arch="amd64")
        assert info.is_supported() is False


class TestGetPlatformInfo:
    """Tests for get_platform_info function."""

    def test_get_platform_info_returns_platform_info(self) -> None:
        with patch("platform.system", return_value="Linux"):
            with patch("platform.machine", return_value="x86_64"):
                info = get_platform_info()
                assert isinstance(info, PlatformInfo)
                assert info.os == "linux"
                assert info.arch == "amd64"

    def test_get_platform_info_darwin_arm64(self) -> None:
        with patch("platform.system", return_value="Darwin"):
            with patch("platform.machine", return_value="arm64"):
                info = get_platform_info()
                assert info.os == "darwin"
                assert info.arch == "arm64"
                assert info.bundle_name == "darwin-arm64"

