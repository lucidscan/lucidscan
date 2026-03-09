"""Unit tests for cargo test runner plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.test_runners.cargo import CargoTestRunner


class TestCargoTestRunner:
    """Basic property tests for CargoTestRunner."""

    def test_name(self) -> None:
        """Test plugin name."""
        runner = CargoTestRunner()
        assert runner.name == "cargo"

    def test_languages(self) -> None:
        """Test supported languages."""
        runner = CargoTestRunner()
        assert runner.languages == ["rust"]


class TestHasTarpaulin:
    """Tests for _has_tarpaulin method."""

    @patch("subprocess.run")
    def test_returns_true_when_available(self, mock_run: MagicMock) -> None:
        """Test _has_tarpaulin returns True when tarpaulin is installed."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["cargo", "tarpaulin", "--version"],
            returncode=0,
            stdout="cargo-tarpaulin 0.27.0",
        )
        runner = CargoTestRunner()
        assert runner._has_tarpaulin() is True
        mock_run.assert_called_once_with(
            ["cargo", "tarpaulin", "--version"],
            capture_output=True,
            timeout=10,
        )

    @patch("subprocess.run")
    def test_returns_false_when_not_installed(
        self, mock_run: MagicMock
    ) -> None:
        """Test _has_tarpaulin returns False when tarpaulin is not found."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["cargo", "tarpaulin", "--version"],
            returncode=101,
        )
        runner = CargoTestRunner()
        assert runner._has_tarpaulin() is False

    @patch("subprocess.run")
    def test_returns_false_on_file_not_found(
        self, mock_run: MagicMock
    ) -> None:
        """Test _has_tarpaulin returns False when cargo is missing."""
        mock_run.side_effect = FileNotFoundError("cargo not found")
        runner = CargoTestRunner()
        assert runner._has_tarpaulin() is False

    @patch("subprocess.run")
    def test_returns_false_on_timeout(self, mock_run: MagicMock) -> None:
        """Test _has_tarpaulin returns False on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="cargo tarpaulin --version", timeout=10
        )
        runner = CargoTestRunner()
        assert runner._has_tarpaulin() is False


def _make_context(
    project_root: Path,
    enabled_domains: list | None = None,
) -> ScanContext:
    """Create a minimal ScanContext for testing."""
    return ScanContext(
        project_root=project_root,
        paths=[project_root],
        enabled_domains=enabled_domains or [],
    )


class TestRunTestsTarpaulinIntegration:
    """Tests for tarpaulin usage in run_tests."""

    def _setup_cargo_project(self, tmpdir: Path) -> None:
        """Write a minimal Cargo.toml so the project is detected."""
        (tmpdir / "Cargo.toml").write_text(
            '[package]\nname = "test"\nversion = "0.1.0"\n'
        )

    @patch.object(CargoTestRunner, "_has_tarpaulin", return_value=True)
    @patch(
        "lucidshark.plugins.test_runners.cargo.run_with_streaming"
    )
    @patch.object(CargoTestRunner, "ensure_binary")
    def test_uses_tarpaulin_when_coverage_enabled_and_available(
        self,
        mock_binary: MagicMock,
        mock_run: MagicMock,
        mock_tarpaulin: MagicMock,
    ) -> None:
        """Test that tarpaulin is used when coverage domain is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            self._setup_cargo_project(tmpdir_path)
            mock_binary.return_value = Path("/usr/bin/cargo")

            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out",
                stderr="",
            )

            runner = CargoTestRunner()
            context = _make_context(
                tmpdir_path,
                enabled_domains=[ToolDomain.TESTING, ToolDomain.COVERAGE],
            )
            result = runner.run_tests(context)

            # Should have called run_with_streaming with tarpaulin args
            call_args = mock_run.call_args
            cmd = call_args.kwargs.get("cmd") or call_args[1].get("cmd") or call_args[0][0]
            assert "tarpaulin" in cmd[1], f"Expected tarpaulin in command, got: {cmd}"
            assert "--out" in cmd
            assert "Json" in cmd
            assert "--output-dir" in cmd
            assert "target/tarpaulin" in cmd

            assert result.passed == 3
            assert result.failed == 0

    @patch.object(CargoTestRunner, "_has_tarpaulin", return_value=False)
    @patch(
        "lucidshark.plugins.test_runners.cargo.run_with_streaming"
    )
    @patch.object(CargoTestRunner, "ensure_binary")
    def test_uses_cargo_test_when_tarpaulin_not_available(
        self,
        mock_binary: MagicMock,
        mock_run: MagicMock,
        mock_tarpaulin: MagicMock,
    ) -> None:
        """Test that cargo test is used when tarpaulin is not installed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            self._setup_cargo_project(tmpdir_path)
            mock_binary.return_value = Path("/usr/bin/cargo")

            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out",
                stderr="",
            )

            runner = CargoTestRunner()
            context = _make_context(
                tmpdir_path,
                enabled_domains=[ToolDomain.TESTING, ToolDomain.COVERAGE],
            )
            result = runner.run_tests(context)

            call_args = mock_run.call_args
            cmd = call_args.kwargs.get("cmd") or call_args[1].get("cmd") or call_args[0][0]
            assert cmd == ["/usr/bin/cargo", "test"], f"Expected cargo test, got: {cmd}"
            assert result.passed == 2

    @patch.object(CargoTestRunner, "_has_tarpaulin", return_value=True)
    @patch(
        "lucidshark.plugins.test_runners.cargo.run_with_streaming"
    )
    @patch.object(CargoTestRunner, "ensure_binary")
    def test_uses_cargo_test_when_coverage_not_in_domains(
        self,
        mock_binary: MagicMock,
        mock_run: MagicMock,
        mock_tarpaulin: MagicMock,
    ) -> None:
        """Test that cargo test is used when coverage domain is not enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            self._setup_cargo_project(tmpdir_path)
            mock_binary.return_value = Path("/usr/bin/cargo")

            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out",
                stderr="",
            )

            runner = CargoTestRunner()
            # Only TESTING enabled, no COVERAGE
            context = _make_context(
                tmpdir_path,
                enabled_domains=[ToolDomain.TESTING],
            )
            result = runner.run_tests(context)

            call_args = mock_run.call_args
            cmd = call_args.kwargs.get("cmd") or call_args[1].get("cmd") or call_args[0][0]
            assert cmd == ["/usr/bin/cargo", "test"], f"Expected cargo test, got: {cmd}"
            assert result.passed == 4

    @patch.object(CargoTestRunner, "_has_tarpaulin", return_value=True)
    @patch(
        "lucidshark.plugins.test_runners.cargo.run_with_streaming"
    )
    @patch.object(CargoTestRunner, "ensure_binary")
    def test_falls_back_to_cargo_test_when_tarpaulin_crashes(
        self,
        mock_binary: MagicMock,
        mock_run: MagicMock,
        mock_tarpaulin: MagicMock,
    ) -> None:
        """Test fallback to cargo test when tarpaulin fails to execute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            self._setup_cargo_project(tmpdir_path)
            mock_binary.return_value = Path("/usr/bin/cargo")

            # First call (tarpaulin) raises an unexpected error;
            # second call (cargo test) succeeds.
            mock_run.side_effect = [
                RuntimeError("tarpaulin segfaulted"),
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out",
                    stderr="",
                ),
            ]

            runner = CargoTestRunner()
            context = _make_context(
                tmpdir_path,
                enabled_domains=[ToolDomain.TESTING, ToolDomain.COVERAGE],
            )
            result = runner.run_tests(context)

            # Should have fallen back and still got a result
            assert result.passed == 1
            assert result.failed == 0
            # Two calls: first tarpaulin (failed), then cargo test
            assert mock_run.call_count == 2


class TestParseTestOutput:
    """Tests for _parse_test_output."""

    def test_parse_passing_output(self) -> None:
        """Test parsing output where all tests pass."""
        runner = CargoTestRunner()
        output = (
            "running 3 tests\n"
            "test tests::test_one ... ok\n"
            "test tests::test_two ... ok\n"
            "test tests::test_three ... ok\n"
            "\n"
            "test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n"
        )
        result = runner._parse_test_output(output, Path("/tmp"))
        assert result.passed == 3
        assert result.failed == 0
        assert result.skipped == 0

    def test_parse_failed_output(self) -> None:
        """Test parsing output with test failures."""
        runner = CargoTestRunner()
        output = (
            "running 2 tests\n"
            "test tests::test_ok ... ok\n"
            "test tests::test_bad ... FAILED\n"
            "\n"
            "failures:\n"
            "\n"
            "---- tests::test_bad stdout ----\n"
            "thread 'tests::test_bad' panicked at 'assertion failed'\n"
            "\n"
            "failures:\n"
            "    tests::test_bad\n"
            "\n"
            "test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out\n"
        )
        result = runner._parse_test_output(output, Path("/tmp"))
        assert result.passed == 1
        assert result.failed == 1
        assert len(result.issues) == 1
        assert result.issues[0].domain == ToolDomain.TESTING
