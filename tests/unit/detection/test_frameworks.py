"""Tests for framework detection module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lucidscan.detection.frameworks import (
    detect_frameworks,
    _get_python_dependencies,
    _get_js_dependencies,
    _parse_pyproject_deps,
    _parse_requirements_txt,
    _extract_package_names,
    PYTHON_FRAMEWORKS,
    PYTHON_TEST_FRAMEWORKS,
    JS_FRAMEWORKS,
    JS_TEST_FRAMEWORKS,
)


class TestDetectFrameworks:
    """Tests for detect_frameworks function."""

    def test_detect_python_framework_fastapi(self, tmp_path: Path) -> None:
        """Test detecting FastAPI framework."""
        pyproject = '''
[project]
dependencies = ["fastapi>=0.100.0"]
'''
        (tmp_path / "pyproject.toml").write_text(pyproject)

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "fastapi" in frameworks

    def test_detect_python_framework_django(self, tmp_path: Path) -> None:
        """Test detecting Django framework."""
        (tmp_path / "requirements.txt").write_text("django>=4.0\n")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "django" in frameworks

    def test_detect_python_framework_flask(self, tmp_path: Path) -> None:
        """Test detecting Flask framework."""
        (tmp_path / "requirements.txt").write_text("flask==2.3.0\n")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "flask" in frameworks

    def test_detect_python_test_framework_pytest(self, tmp_path: Path) -> None:
        """Test detecting pytest test framework."""
        (tmp_path / "requirements.txt").write_text("pytest>=7.0\n")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "pytest" in test_frameworks

    def test_detect_pytest_by_config_file(self, tmp_path: Path) -> None:
        """Test detecting pytest by pytest.ini."""
        (tmp_path / "pytest.ini").write_text("[pytest]\n")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "pytest" in test_frameworks

    def test_detect_pytest_by_conftest(self, tmp_path: Path) -> None:
        """Test detecting pytest by conftest.py."""
        (tmp_path / "conftest.py").write_text("# conftest")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "pytest" in test_frameworks

    def test_detect_js_framework_react(self, tmp_path: Path) -> None:
        """Test detecting React framework."""
        package_json = {"dependencies": {"react": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "react" in frameworks

    def test_detect_js_framework_vue(self, tmp_path: Path) -> None:
        """Test detecting Vue framework."""
        package_json = {"dependencies": {"vue": "^3.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "vue" in frameworks

    def test_detect_js_framework_angular(self, tmp_path: Path) -> None:
        """Test detecting Angular framework."""
        package_json = {"dependencies": {"@angular/core": "^16.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "angular" in frameworks

    def test_detect_js_framework_next(self, tmp_path: Path) -> None:
        """Test detecting Next.js framework."""
        package_json = {"dependencies": {"next": "^13.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "next" in frameworks

    def test_detect_js_framework_express(self, tmp_path: Path) -> None:
        """Test detecting Express framework."""
        package_json = {"dependencies": {"express": "^4.18.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "express" in frameworks

    def test_detect_js_test_framework_jest(self, tmp_path: Path) -> None:
        """Test detecting Jest test framework."""
        package_json = {"devDependencies": {"jest": "^29.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "jest" in test_frameworks

    def test_detect_jest_by_config_file(self, tmp_path: Path) -> None:
        """Test detecting Jest by jest.config.js."""
        (tmp_path / "jest.config.js").write_text("module.exports = {}")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "jest" in test_frameworks

    def test_detect_jest_by_ts_config(self, tmp_path: Path) -> None:
        """Test detecting Jest by jest.config.ts."""
        (tmp_path / "jest.config.ts").write_text("export default {}")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "jest" in test_frameworks

    def test_detect_jest_by_mjs_config(self, tmp_path: Path) -> None:
        """Test detecting Jest by jest.config.mjs."""
        (tmp_path / "jest.config.mjs").write_text("export default {}")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "jest" in test_frameworks

    def test_detect_js_test_framework_vitest(self, tmp_path: Path) -> None:
        """Test detecting Vitest test framework."""
        package_json = {"devDependencies": {"vitest": "^1.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "vitest" in test_frameworks

    def test_detect_multiple_frameworks(self, tmp_path: Path) -> None:
        """Test detecting multiple frameworks."""
        pyproject = '''
[project]
dependencies = ["fastapi>=0.100.0", "starlette>=0.20.0"]
'''
        (tmp_path / "pyproject.toml").write_text(pyproject)

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert "fastapi" in frameworks
        assert "starlette" in frameworks

    def test_no_frameworks(self, tmp_path: Path) -> None:
        """Test when no frameworks are detected."""
        frameworks, test_frameworks = detect_frameworks(tmp_path)
        assert frameworks == []
        assert test_frameworks == []

    def test_doesnt_duplicate_pytest(self, tmp_path: Path) -> None:
        """Test pytest isn't duplicated when found multiple ways."""
        (tmp_path / "requirements.txt").write_text("pytest>=7.0\n")
        (tmp_path / "pytest.ini").write_text("[pytest]\n")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        # Should only appear once
        assert test_frameworks.count("pytest") == 1

    def test_doesnt_duplicate_jest(self, tmp_path: Path) -> None:
        """Test jest isn't duplicated when found multiple ways."""
        package_json = {"devDependencies": {"jest": "^29.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))
        (tmp_path / "jest.config.js").write_text("module.exports = {}")

        frameworks, test_frameworks = detect_frameworks(tmp_path)
        # Should only appear once
        assert test_frameworks.count("jest") == 1


class TestGetPythonDependencies:
    """Tests for _get_python_dependencies function."""

    def test_from_pyproject(self, tmp_path: Path) -> None:
        """Test getting deps from pyproject.toml."""
        pyproject = '''
[project]
dependencies = ["fastapi>=0.100.0", "pydantic>=2.0"]
'''
        (tmp_path / "pyproject.toml").write_text(pyproject)

        deps = _get_python_dependencies(tmp_path)
        assert "fastapi" in deps
        assert "pydantic" in deps

    def test_from_requirements_txt(self, tmp_path: Path) -> None:
        """Test getting deps from requirements.txt."""
        (tmp_path / "requirements.txt").write_text("flask>=2.0\nrequests==2.28.0\n")

        deps = _get_python_dependencies(tmp_path)
        assert "flask" in deps
        assert "requests" in deps

    def test_from_requirements_dev_txt(self, tmp_path: Path) -> None:
        """Test getting deps from requirements-dev.txt."""
        (tmp_path / "requirements-dev.txt").write_text("pytest>=7.0\n")

        deps = _get_python_dependencies(tmp_path)
        assert "pytest" in deps

    def test_from_requirements_dev_underscore(self, tmp_path: Path) -> None:
        """Test getting deps from requirements_dev.txt."""
        (tmp_path / "requirements_dev.txt").write_text("black>=23.0\n")

        deps = _get_python_dependencies(tmp_path)
        assert "black" in deps

    def test_from_dev_requirements_txt(self, tmp_path: Path) -> None:
        """Test getting deps from dev-requirements.txt."""
        (tmp_path / "dev-requirements.txt").write_text("mypy>=1.0\n")

        deps = _get_python_dependencies(tmp_path)
        assert "mypy" in deps

    def test_combines_multiple_sources(self, tmp_path: Path) -> None:
        """Test combining deps from multiple sources."""
        (tmp_path / "requirements.txt").write_text("flask>=2.0\n")
        (tmp_path / "requirements-dev.txt").write_text("pytest>=7.0\n")

        deps = _get_python_dependencies(tmp_path)
        assert "flask" in deps
        assert "pytest" in deps

    def test_empty_project(self, tmp_path: Path) -> None:
        """Test empty project returns empty set."""
        deps = _get_python_dependencies(tmp_path)
        assert deps == set()

    def test_handles_invalid_file(self, tmp_path: Path) -> None:
        """Test handling invalid file content gracefully."""
        # Binary content that can't be parsed
        (tmp_path / "pyproject.toml").write_bytes(b"\x00\x01\x02")

        # Should not raise, just return empty
        deps = _get_python_dependencies(tmp_path)
        assert isinstance(deps, set)


class TestParsePyprojectDeps:
    """Tests for _parse_pyproject_deps function."""

    def test_parse_dependencies_array(self) -> None:
        """Test parsing dependencies array."""
        content = '''
[project]
dependencies = [
    "fastapi>=0.100.0",
    "pydantic>=2.0",
]
'''
        deps = _parse_pyproject_deps(content)
        assert "fastapi" in deps
        assert "pydantic" in deps

    def test_parse_optional_dependencies(self) -> None:
        """Test parsing optional dependencies."""
        # The regex expects [project.optional-dependencies.groupname] format
        content = '''
[project.optional-dependencies.dev]
"pytest>=7.0"
"black>=23.0"
'''
        deps = _parse_pyproject_deps(content)
        assert "pytest" in deps
        assert "black" in deps

    def test_parse_poetry_dependencies(self) -> None:
        """Test parsing Poetry-style dependencies."""
        content = '''
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.100.0"
pydantic = "^2.0"
'''
        deps = _parse_pyproject_deps(content)
        assert "fastapi" in deps
        assert "pydantic" in deps

    def test_parse_with_extras(self) -> None:
        """Test parsing dependencies with extras."""
        content = '''
[project]
dependencies = [
    "fastapi[all]>=0.100.0",
]
'''
        deps = _parse_pyproject_deps(content)
        assert "fastapi" in deps

    def test_empty_content(self) -> None:
        """Test parsing empty content."""
        deps = _parse_pyproject_deps("")
        assert deps == set()


class TestParseRequirementsTxt:
    """Tests for _parse_requirements_txt function."""

    def test_parse_simple_requirements(self) -> None:
        """Test parsing simple requirements."""
        content = "flask>=2.0\nrequests==2.28.0\n"

        deps = _parse_requirements_txt(content)
        assert "flask" in deps
        assert "requests" in deps

    def test_ignores_comments(self) -> None:
        """Test comments are ignored."""
        content = "# This is a comment\nflask>=2.0\n# Another comment\n"

        deps = _parse_requirements_txt(content)
        assert "flask" in deps
        assert len(deps) == 1

    def test_ignores_empty_lines(self) -> None:
        """Test empty lines are ignored."""
        content = "flask>=2.0\n\n\nrequests>=2.0\n"

        deps = _parse_requirements_txt(content)
        assert len(deps) == 2

    def test_ignores_flags(self) -> None:
        """Test -r and other flags are ignored."""
        content = "-r base.txt\nflask>=2.0\n--index-url https://pypi.org\n"

        deps = _parse_requirements_txt(content)
        assert "flask" in deps
        assert len(deps) == 1

    def test_normalizes_underscores(self) -> None:
        """Test underscores are normalized to hyphens."""
        content = "some_package>=1.0\n"

        deps = _parse_requirements_txt(content)
        assert "some-package" in deps

    def test_empty_content(self) -> None:
        """Test parsing empty content."""
        deps = _parse_requirements_txt("")
        assert deps == set()


class TestExtractPackageNames:
    """Tests for _extract_package_names function."""

    def test_extract_double_quoted(self) -> None:
        """Test extracting double-quoted packages."""
        text = '"fastapi>=0.100.0", "pydantic>=2.0"'

        names = _extract_package_names(text)
        assert "fastapi" in names
        assert "pydantic" in names

    def test_extract_single_quoted(self) -> None:
        """Test extracting single-quoted packages."""
        text = "'flask>=2.0', 'requests>=2.0'"

        names = _extract_package_names(text)
        assert "flask" in names
        assert "requests" in names

    def test_removes_extras(self) -> None:
        """Test extras are removed."""
        text = '"fastapi[all]>=0.100.0"'

        names = _extract_package_names(text)
        assert "fastapi" in names
        assert "fastapi[all]" not in names

    def test_normalizes_case(self) -> None:
        """Test names are lowercased."""
        text = '"FastAPI>=0.100.0"'

        names = _extract_package_names(text)
        assert "fastapi" in names

    def test_normalizes_underscores(self) -> None:
        """Test underscores are normalized to hyphens."""
        text = '"some_package>=1.0"'

        names = _extract_package_names(text)
        assert "some-package" in names


class TestGetJsDependencies:
    """Tests for _get_js_dependencies function."""

    def test_from_dependencies(self, tmp_path: Path) -> None:
        """Test getting from dependencies."""
        package_json = {"dependencies": {"react": "^18.0.0", "axios": "^1.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        deps = _get_js_dependencies(tmp_path)
        assert "react" in deps
        assert "axios" in deps

    def test_from_dev_dependencies(self, tmp_path: Path) -> None:
        """Test getting from devDependencies."""
        package_json = {"devDependencies": {"jest": "^29.0.0", "typescript": "^5.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        deps = _get_js_dependencies(tmp_path)
        assert "jest" in deps
        assert "typescript" in deps

    def test_from_peer_dependencies(self, tmp_path: Path) -> None:
        """Test getting from peerDependencies."""
        package_json = {"peerDependencies": {"react": ">=17.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        deps = _get_js_dependencies(tmp_path)
        assert "react" in deps

    def test_combines_all_dependency_types(self, tmp_path: Path) -> None:
        """Test combining all dependency types."""
        package_json = {
            "dependencies": {"react": "^18.0.0"},
            "devDependencies": {"jest": "^29.0.0"},
            "peerDependencies": {"lodash": "^4.0.0"},
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        deps = _get_js_dependencies(tmp_path)
        assert "react" in deps
        assert "jest" in deps
        assert "lodash" in deps

    def test_no_package_json(self, tmp_path: Path) -> None:
        """Test when no package.json exists."""
        deps = _get_js_dependencies(tmp_path)
        assert deps == set()

    def test_handles_invalid_json(self, tmp_path: Path) -> None:
        """Test handling invalid JSON gracefully."""
        (tmp_path / "package.json").write_text("not valid json {{{")

        deps = _get_js_dependencies(tmp_path)
        assert deps == set()

    def test_handles_empty_package_json(self, tmp_path: Path) -> None:
        """Test handling empty package.json."""
        (tmp_path / "package.json").write_text("{}")

        deps = _get_js_dependencies(tmp_path)
        assert deps == set()


class TestConstants:
    """Tests for module constants."""

    def test_python_frameworks_complete(self) -> None:
        """Test PYTHON_FRAMEWORKS contains common frameworks."""
        assert "fastapi" in PYTHON_FRAMEWORKS
        assert "django" in PYTHON_FRAMEWORKS
        assert "flask" in PYTHON_FRAMEWORKS
        assert "starlette" in PYTHON_FRAMEWORKS

    def test_python_test_frameworks_complete(self) -> None:
        """Test PYTHON_TEST_FRAMEWORKS contains common test frameworks."""
        assert "pytest" in PYTHON_TEST_FRAMEWORKS
        assert "unittest" in PYTHON_TEST_FRAMEWORKS
        assert "hypothesis" in PYTHON_TEST_FRAMEWORKS

    def test_js_frameworks_complete(self) -> None:
        """Test JS_FRAMEWORKS contains common frameworks."""
        assert "react" in JS_FRAMEWORKS
        assert "vue" in JS_FRAMEWORKS
        assert "angular" in JS_FRAMEWORKS
        assert "next" in JS_FRAMEWORKS
        assert "express" in JS_FRAMEWORKS

    def test_js_test_frameworks_complete(self) -> None:
        """Test JS_TEST_FRAMEWORKS contains common test frameworks."""
        assert "jest" in JS_TEST_FRAMEWORKS
        assert "mocha" in JS_TEST_FRAMEWORKS
        assert "vitest" in JS_TEST_FRAMEWORKS
        assert "cypress" in JS_TEST_FRAMEWORKS
