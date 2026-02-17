"""Unit tests for lucidshark.generation.package_installer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lucidshark.detection.languages import LanguageInfo
from lucidshark.detection import ProjectContext
from lucidshark.generation.package_installer import (
    JAVASCRIPT_PACKAGES,
    PYTHON_PACKAGES,
    PackageInstaller,
    _parse_package_spec,
)


class TestParsePackageSpec:
    """Tests for _parse_package_spec function."""

    def test_regular_package_with_version(self) -> None:
        name, version = _parse_package_spec("eslint@^9.0.0")
        assert name == "eslint"
        assert version == "^9.0.0"

    def test_scoped_package_with_version(self) -> None:
        name, version = _parse_package_spec("@biomejs/biome@^1.0.0")
        assert name == "@biomejs/biome"
        assert version == "^1.0.0"

    def test_scoped_package_without_version(self) -> None:
        name, version = _parse_package_spec("@biomejs/biome")
        assert name == "@biomejs/biome"
        assert version == "latest"

    def test_package_without_version(self) -> None:
        name, version = _parse_package_spec("typescript")
        assert name == "typescript"
        assert version == "latest"


def _make_python_context(root: Path) -> ProjectContext:
    """Create a ProjectContext with Python detected."""
    return ProjectContext(
        root=root,
        languages=[LanguageInfo(name="python", file_count=10)],
    )


def _make_js_context(root: Path) -> ProjectContext:
    """Create a ProjectContext with JavaScript detected."""
    return ProjectContext(
        root=root,
        languages=[LanguageInfo(name="javascript", file_count=10)],
    )


class TestPackageInstallerPython:
    """Tests for PackageInstaller with Python projects."""

    @pytest.fixture
    def installer(self) -> PackageInstaller:
        return PackageInstaller()

    def test_add_to_existing_pyproject_with_project_section(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "myapp"\nversion = "1.0"\n'
            'dependencies = [\n  "requests"\n]\n'
        )
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff"])
        assert "ruff" in result
        assert result["ruff"] == pyproject
        content = pyproject.read_text()
        assert "ruff" in content
        assert "[project.optional-dependencies]" in content

    def test_add_to_existing_pyproject_with_optional_deps(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "myapp"\n\n'
            "[project.optional-dependencies]\n"
            'test = [\n  "pytest"\n]\n'
        )
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff"])
        assert "ruff" in result
        content = pyproject.read_text()
        assert "ruff" in content

    def test_add_to_existing_pyproject_with_dev_deps(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "myapp"\n\n'
            "[project.optional-dependencies]\n"
            'dev = [\n  "black"\n]\n'
        )
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff"])
        assert "ruff" in result
        content = pyproject.read_text()
        assert "ruff" in content
        assert "black" in content

    def test_add_to_existing_pyproject_no_project_section(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[build-system]\n"
            'requires = ["setuptools"]\n'
        )
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff"])
        assert "ruff" in result
        content = pyproject.read_text()
        assert "ruff" in content

    def test_add_to_requirements_dev(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements-dev.txt"
        req_file.write_text("black>=22.0\n")
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff", "mypy"])
        assert "ruff" in result
        assert "mypy" in result
        assert result["ruff"] == req_file
        content = req_file.read_text()
        assert "ruff" in content
        assert "mypy" in content

    def test_skip_already_present_in_requirements(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements-dev.txt"
        req_file.write_text("ruff>=0.5.0\n")
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff"])
        # ruff already present, should not be in result
        assert "ruff" not in result

    def test_create_pyproject_when_no_package_file(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff", "pytest"])
        assert "ruff" in result
        assert "pytest" in result
        pyproject = tmp_path / "pyproject.toml"
        assert pyproject.exists()
        content = pyproject.read_text()
        assert "ruff" in content
        assert "pytest" in content
        assert "[project]" in content

    def test_skip_already_present_in_pyproject(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "myapp"\n'
            "dependencies = [\n"
            '  "ruff>=0.8.0"\n'
            "]\n"
        )
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff"])
        assert "ruff" not in result

    def test_no_install_when_not_python(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        ctx = _make_js_context(tmp_path)
        result = installer.install_tools(ctx, ["ruff"])
        assert result == {}


class TestPackageInstallerJavaScript:
    """Tests for PackageInstaller with JavaScript projects."""

    @pytest.fixture
    def installer(self) -> PackageInstaller:
        return PackageInstaller()

    def test_add_to_existing_package_json(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "myapp", "version": "1.0.0"}))
        ctx = _make_js_context(tmp_path)
        result = installer.install_tools(ctx, ["eslint"])
        assert "eslint" in result
        assert result["eslint"] == pkg
        data = json.loads(pkg.read_text())
        assert "eslint" in data["devDependencies"]

    def test_add_to_existing_package_json_with_dev_deps(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps({
                "name": "myapp",
                "devDependencies": {"prettier": "^3.0.0"},
            })
        )
        ctx = _make_js_context(tmp_path)
        result = installer.install_tools(ctx, ["eslint", "typescript"])
        assert "eslint" in result
        assert "typescript" in result
        data = json.loads(pkg.read_text())
        assert "eslint" in data["devDependencies"]
        assert "typescript" in data["devDependencies"]
        assert "prettier" in data["devDependencies"]

    def test_skip_already_present_in_package_json(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps({
                "name": "myapp",
                "devDependencies": {"eslint": "^8.0.0"},
            })
        )
        ctx = _make_js_context(tmp_path)
        result = installer.install_tools(ctx, ["eslint"])
        assert "eslint" not in result

    def test_create_package_json_when_none_exists(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        ctx = _make_js_context(tmp_path)
        result = installer.install_tools(ctx, ["eslint", "jest"])
        assert "eslint" in result
        assert "jest" in result
        pkg = tmp_path / "package.json"
        assert pkg.exists()
        data = json.loads(pkg.read_text())
        assert "eslint" in data["devDependencies"]
        assert "jest" in data["devDependencies"]
        assert data["name"] == tmp_path.name

    def test_scoped_package_installed_correctly(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "myapp"}))
        ctx = _make_js_context(tmp_path)
        result = installer.install_tools(ctx, ["biome"])
        assert "biome" in result
        data = json.loads(pkg.read_text())
        assert "@biomejs/biome" in data["devDependencies"]

    def test_no_install_when_not_javascript(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["eslint"])
        assert result == {}


class TestPackageInstallerMixed:
    """Tests for PackageInstaller with mixed-language projects."""

    @pytest.fixture
    def installer(self) -> PackageInstaller:
        return PackageInstaller()

    def test_install_tools_for_both_languages(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        ctx = ProjectContext(
            root=tmp_path,
            languages=[
                LanguageInfo(name="python", file_count=10),
                LanguageInfo(name="javascript", file_count=5),
            ],
        )
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "myapp"}))

        result = installer.install_tools(ctx, ["ruff", "eslint"])
        assert "ruff" in result
        assert "eslint" in result

    def test_empty_tools_list(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, [])
        assert result == {}

    def test_unknown_tools_ignored(
        self, installer: PackageInstaller, tmp_path: Path
    ) -> None:
        ctx = _make_python_context(tmp_path)
        result = installer.install_tools(ctx, ["unknown_tool"])
        assert result == {}


class TestPackageConstants:
    """Tests for package mapping constants."""

    def test_python_packages_have_versions(self) -> None:
        for tool, spec in PYTHON_PACKAGES.items():
            assert ">=" in spec, f"Python package {tool} missing version constraint"

    def test_javascript_packages_have_versions(self) -> None:
        for tool, spec in JAVASCRIPT_PACKAGES.items():
            assert "@" in spec or spec == spec, f"JS package {tool} should have version"
