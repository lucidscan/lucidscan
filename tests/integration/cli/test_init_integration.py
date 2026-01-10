"""Integration tests for the init CLI command.

These tests verify the init command works correctly for project detection
and configuration generation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan import cli
from lucidscan.cli.exit_codes import EXIT_SUCCESS, EXIT_INVALID_USAGE


class TestInitCommandBasic:
    """Basic integration tests for init command."""

    def test_init_creates_config_file(self) -> None:
        """Test that init creates lucidscan.yml config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a simple Python file to make it a Python project
            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Config file should be created
            config_path = tmpdir_path / "lucidscan.yml"
            assert config_path.exists()

    def test_init_detects_python_project(self) -> None:
        """Test that init detects Python projects correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create pyproject.toml to make it a Python project
            pyproject = tmpdir_path / "pyproject.toml"
            pyproject.write_text(
                '[project]\n'
                'name = "test-project"\n'
                'version = "0.1.0"\n'
            )

            # Create a Python file
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            test_file = src_dir / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Config should include Python tools
            config_path = tmpdir_path / "lucidscan.yml"
            assert config_path.exists()
            config_content = config_path.read_text()
            # Should contain ruff or mypy (Python tools)
            assert "ruff" in config_content or "mypy" in config_content

    def test_init_detects_javascript_project(self) -> None:
        """Test that init detects JavaScript projects correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create package.json to make it a JavaScript project
            package_json = tmpdir_path / "package.json"
            package_json.write_text(
                '{\n'
                '  "name": "test-project",\n'
                '  "version": "1.0.0"\n'
                '}\n'
            )

            # Create a JavaScript file
            test_file = tmpdir_path / "index.js"
            test_file.write_text("console.log('hello');\n")

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Config should include JavaScript tools
            config_path = tmpdir_path / "lucidscan.yml"
            assert config_path.exists()
            config_content = config_path.read_text()
            # Should contain eslint or typescript (JS tools)
            assert "eslint" in config_content or "typescript" in config_content


class TestInitCommandNonInteractive:
    """Tests for init command non-interactive mode."""

    def test_init_non_interactive_uses_defaults(self) -> None:
        """Test that --non-interactive uses opinionated defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file
            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS
            config_path = tmpdir_path / "lucidscan.yml"
            assert config_path.exists()

    def test_init_non_interactive_short_flag(self) -> None:
        """Test that -y flag works as non-interactive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "-y",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS
            config_path = tmpdir_path / "lucidscan.yml"
            assert config_path.exists()


class TestInitCommandCIGeneration:
    """Tests for init command CI configuration generation."""

    def test_init_with_ci_flag_github(self) -> None:
        """Test that --ci github generates GitHub Actions config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                "--ci", "github",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # GitHub Actions config should be created
            ci_path = tmpdir_path / ".github" / "workflows" / "lucidscan.yml"
            assert ci_path.exists()

    def test_init_with_ci_flag_gitlab(self) -> None:
        """Test that --ci gitlab generates GitLab CI config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                "--ci", "gitlab",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # GitLab CI config should be created
            ci_path = tmpdir_path / ".gitlab-ci.yml"
            assert ci_path.exists()

    def test_init_with_ci_flag_bitbucket(self) -> None:
        """Test that --ci bitbucket generates Bitbucket Pipelines config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                "--ci", "bitbucket",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Bitbucket Pipelines config should be created
            ci_path = tmpdir_path / "bitbucket-pipelines.yml"
            assert ci_path.exists()


class TestInitCommandForce:
    """Tests for init command force/overwrite behavior."""

    def test_init_force_overwrites_existing(self) -> None:
        """Test that --force overwrites existing lucidscan.yml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create existing config
            config_path = tmpdir_path / "lucidscan.yml"
            config_path.write_text("# Old config\n")

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                "--force",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Config should be overwritten
            new_content = config_path.read_text()
            assert "# Old config" not in new_content

    def test_init_force_short_flag(self) -> None:
        """Test that -f flag works as force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            config_path = tmpdir_path / "lucidscan.yml"
            config_path.write_text("# Old config\n")

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "-y",
                "-f",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

    def test_init_non_interactive_fails_without_force(self) -> None:
        """Test that non-interactive mode fails if config exists without --force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create existing config
            config_path = tmpdir_path / "lucidscan.yml"
            config_path.write_text("# Old config\n")

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            # Should fail due to existing config
            assert exit_code == EXIT_INVALID_USAGE


class TestInitCommandErrors:
    """Tests for init command error handling."""

    def test_init_invalid_path(self) -> None:
        """Test that init fails with invalid directory path."""
        exit_code = cli.main([
            "init",
            "--non-interactive",
            "/nonexistent/path/that/does/not/exist",
        ])

        assert exit_code == EXIT_INVALID_USAGE

    def test_init_file_instead_of_directory(self) -> None:
        """Test that init fails when given a file instead of directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a file
            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(test_file),  # File, not directory
            ])

            assert exit_code == EXIT_INVALID_USAGE


class TestInitCommandDetectsExistingTools:
    """Tests for init command detecting existing tools."""

    def test_init_detects_existing_ruff_config(self) -> None:
        """Test that init detects existing ruff configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create pyproject.toml with ruff config
            pyproject = tmpdir_path / "pyproject.toml"
            pyproject.write_text(
                '[project]\n'
                'name = "test-project"\n'
                '\n'
                '[tool.ruff]\n'
                'line-length = 100\n'
            )

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Should use ruff (detected)
            config_path = tmpdir_path / "lucidscan.yml"
            config_content = config_path.read_text()
            assert "ruff" in config_content

    def test_init_detects_existing_mypy_config(self) -> None:
        """Test that init detects existing mypy configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create mypy.ini
            mypy_ini = tmpdir_path / "mypy.ini"
            mypy_ini.write_text(
                '[mypy]\n'
                'strict = true\n'
            )

            test_file = tmpdir_path / "main.py"
            test_file.write_text('"""Main module."""\n')

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Should use mypy (detected)
            config_path = tmpdir_path / "lucidscan.yml"
            config_content = config_path.read_text()
            assert "mypy" in config_content

    def test_init_detects_existing_eslint_config(self) -> None:
        """Test that init detects existing eslint configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create package.json
            package_json = tmpdir_path / "package.json"
            package_json.write_text('{"name": "test"}\n')

            # Create eslint config
            eslint_config = tmpdir_path / "eslint.config.js"
            eslint_config.write_text('export default [];\n')

            test_file = tmpdir_path / "index.js"
            test_file.write_text("console.log('hello');\n")

            exit_code = cli.main([
                "init",
                "--non-interactive",
                str(tmpdir_path),
            ])

            assert exit_code == EXIT_SUCCESS

            # Should use eslint (detected)
            config_path = tmpdir_path / "lucidscan.yml"
            config_content = config_path.read_text()
            assert "eslint" in config_content
