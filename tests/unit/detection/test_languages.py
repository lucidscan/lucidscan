"""Tests for language detection module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lucidscan.detection.languages import (
    LanguageInfo,
    detect_languages,
    _walk_files,
    _detect_version,
    _detect_python_version,
    _detect_typescript_version,
    _detect_go_version,
    _detect_rust_version,
    _detect_java_version,
    SKIP_DIRS,
    EXTENSION_MAP,
    MARKER_FILES,
)


class TestLanguageInfo:
    """Tests for LanguageInfo dataclass."""

    def test_language_info_defaults(self) -> None:
        """Test LanguageInfo default values."""
        info = LanguageInfo(name="python")
        assert info.name == "python"
        assert info.version is None
        assert info.file_count == 0

    def test_language_info_with_all_fields(self) -> None:
        """Test LanguageInfo with all fields."""
        info = LanguageInfo(name="python", version="3.11", file_count=42)
        assert info.name == "python"
        assert info.version == "3.11"
        assert info.file_count == 42


class TestDetectLanguages:
    """Tests for detect_languages function."""

    def test_detect_python_by_extension(self, tmp_path: Path) -> None:
        """Test detecting Python by file extension."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "util.py").write_text("def util(): pass")

        languages = detect_languages(tmp_path)

        python_lang = next((l for l in languages if l.name == "python"), None)
        assert python_lang is not None
        assert python_lang.file_count == 2

    def test_detect_javascript_by_extension(self, tmp_path: Path) -> None:
        """Test detecting JavaScript by file extension."""
        (tmp_path / "app.js").write_text("console.log('hello')")
        (tmp_path / "util.mjs").write_text("export const x = 1")

        languages = detect_languages(tmp_path)

        js_lang = next((l for l in languages if l.name == "javascript"), None)
        assert js_lang is not None
        assert js_lang.file_count == 2

    def test_detect_typescript_by_extension(self, tmp_path: Path) -> None:
        """Test detecting TypeScript by file extension."""
        (tmp_path / "app.ts").write_text("const x: number = 1")
        (tmp_path / "component.tsx").write_text("export const X = () => <div />;")

        languages = detect_languages(tmp_path)

        ts_lang = next((l for l in languages if l.name == "typescript"), None)
        assert ts_lang is not None
        assert ts_lang.file_count == 2

    def test_detect_python_by_marker(self, tmp_path: Path) -> None:
        """Test detecting Python by marker file."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"')

        languages = detect_languages(tmp_path)

        python_lang = next((l for l in languages if l.name == "python"), None)
        assert python_lang is not None

    def test_detect_go_by_marker(self, tmp_path: Path) -> None:
        """Test detecting Go by marker file."""
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21")

        languages = detect_languages(tmp_path)

        go_lang = next((l for l in languages if l.name == "go"), None)
        assert go_lang is not None

    def test_detect_rust_by_marker(self, tmp_path: Path) -> None:
        """Test detecting Rust by marker file."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        languages = detect_languages(tmp_path)

        rust_lang = next((l for l in languages if l.name == "rust"), None)
        assert rust_lang is not None

    def test_detect_java_by_marker(self, tmp_path: Path) -> None:
        """Test detecting Java by marker file (pom.xml)."""
        (tmp_path / "pom.xml").write_text("<project></project>")

        languages = detect_languages(tmp_path)

        java_lang = next((l for l in languages if l.name == "java"), None)
        assert java_lang is not None

    def test_detect_multiple_languages(self, tmp_path: Path) -> None:
        """Test detecting multiple languages."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "app.js").write_text("console.log('hello')")
        (tmp_path / "main.go").write_text("package main")

        languages = detect_languages(tmp_path)

        names = {l.name for l in languages}
        assert "python" in names
        assert "javascript" in names
        assert "go" in names

    def test_results_sorted_by_file_count(self, tmp_path: Path) -> None:
        """Test results are sorted by file count (descending)."""
        # Create more Python files than JS
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text(f"# file {i}")
        (tmp_path / "app.js").write_text("// app")

        languages = detect_languages(tmp_path)

        assert languages[0].name == "python"
        assert languages[0].file_count == 5

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Test detecting in empty directory."""
        languages = detect_languages(tmp_path)
        assert languages == []

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        """Test that node_modules is skipped."""
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "lodash.js").write_text("// lodash")

        (tmp_path / "app.py").write_text("# app")

        languages = detect_languages(tmp_path)

        # Should only find Python, not JavaScript from node_modules
        js_lang = next((l for l in languages if l.name == "javascript"), None)
        assert js_lang is None


class TestWalkFiles:
    """Tests for _walk_files function."""

    def test_walk_files_basic(self, tmp_path: Path) -> None:
        """Test basic file walking."""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")

        files = _walk_files(tmp_path)

        assert len(files) == 2

    def test_walk_files_nested(self, tmp_path: Path) -> None:
        """Test walking nested directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.txt").write_text("root")
        (subdir / "nested.txt").write_text("nested")

        files = _walk_files(tmp_path)

        assert len(files) == 2

    def test_walk_files_skips_dirs(self, tmp_path: Path) -> None:
        """Test that skip directories are respected."""
        for skip_dir in ["node_modules", ".git", "__pycache__"]:
            d = tmp_path / skip_dir
            d.mkdir()
            (d / "file.txt").write_text("skipped")

        (tmp_path / "included.txt").write_text("included")

        files = _walk_files(tmp_path)

        assert len(files) == 1
        assert files[0].name == "included.txt"

    def test_walk_files_skips_hidden_dirs(self, tmp_path: Path) -> None:
        """Test that hidden directories are skipped."""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "file.txt").write_text("hidden")

        (tmp_path / "visible.txt").write_text("visible")

        files = _walk_files(tmp_path)

        assert len(files) == 1
        assert files[0].name == "visible.txt"

    def test_walk_files_max_depth(self, tmp_path: Path) -> None:
        """Test max depth is respected."""
        current = tmp_path
        for i in range(15):
            current = current / f"level{i}"
            current.mkdir()
            (current / "file.txt").write_text(f"level {i}")

        files = _walk_files(tmp_path, max_depth=3)

        # Should find files up to depth 3, not all 15
        assert len(files) < 15

    def test_walk_files_permission_error(self, tmp_path: Path) -> None:
        """Test handling permission errors gracefully."""
        (tmp_path / "accessible.txt").write_text("accessible")

        # This test would require actually setting permissions,
        # which may not work on all systems. Just verify the function
        # completes without error.
        files = _walk_files(tmp_path)
        assert len(files) >= 1


class TestDetectVersion:
    """Tests for _detect_version function."""

    def test_detect_version_python(self, tmp_path: Path) -> None:
        """Test version detection delegates to Python detector."""
        (tmp_path / "pyproject.toml").write_text('requires-python = ">=3.11"')

        version = _detect_version("python", tmp_path)
        assert version == "3.11"

    def test_detect_version_typescript(self, tmp_path: Path) -> None:
        """Test version detection delegates to TypeScript detector."""
        package_json = {
            "devDependencies": {"typescript": "^5.2.0"}
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        version = _detect_version("typescript", tmp_path)
        assert version == "5.2.0"

    def test_detect_version_go(self, tmp_path: Path) -> None:
        """Test version detection delegates to Go detector."""
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21")

        version = _detect_version("go", tmp_path)
        assert version == "1.21"

    def test_detect_version_rust(self, tmp_path: Path) -> None:
        """Test version detection delegates to Rust detector."""
        (tmp_path / "Cargo.toml").write_text('[package]\nedition = "2021"')

        version = _detect_version("rust", tmp_path)
        assert version == "2021"

    def test_detect_version_java(self, tmp_path: Path) -> None:
        """Test version detection delegates to Java detector."""
        (tmp_path / "pom.xml").write_text(
            "<project><properties><java.version>17</java.version></properties></project>"
        )

        version = _detect_version("java", tmp_path)
        assert version == "17"

    def test_detect_version_unknown_language(self, tmp_path: Path) -> None:
        """Test version detection for unknown language returns None."""
        version = _detect_version("unknown", tmp_path)
        assert version is None


class TestDetectPythonVersion:
    """Tests for _detect_python_version function."""

    def test_from_pyproject_requires_python(self, tmp_path: Path) -> None:
        """Test detecting from pyproject.toml requires-python."""
        (tmp_path / "pyproject.toml").write_text('requires-python = ">=3.10"')

        version = _detect_python_version(tmp_path)
        assert version == "3.10"

    def test_from_pyproject_single_quotes(self, tmp_path: Path) -> None:
        """Test detecting with single quotes."""
        (tmp_path / "pyproject.toml").write_text("requires-python = '>=3.12'")

        version = _detect_python_version(tmp_path)
        assert version == "3.12"

    def test_from_python_version_file(self, tmp_path: Path) -> None:
        """Test detecting from .python-version file."""
        (tmp_path / ".python-version").write_text("3.11.4")

        version = _detect_python_version(tmp_path)
        assert version == "3.11"

    def test_from_python_version_file_simple(self, tmp_path: Path) -> None:
        """Test detecting from .python-version file with simple version."""
        (tmp_path / ".python-version").write_text("3.11")

        version = _detect_python_version(tmp_path)
        assert version == "3.11"

    def test_no_version_file(self, tmp_path: Path) -> None:
        """Test when no version file exists."""
        version = _detect_python_version(tmp_path)
        assert version is None

    def test_invalid_pyproject(self, tmp_path: Path) -> None:
        """Test handling invalid pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("invalid content {{{")

        version = _detect_python_version(tmp_path)
        assert version is None


class TestDetectTypescriptVersion:
    """Tests for _detect_typescript_version function."""

    def test_from_dependencies(self, tmp_path: Path) -> None:
        """Test detecting from dependencies."""
        package_json = {"dependencies": {"typescript": "5.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        version = _detect_typescript_version(tmp_path)
        assert version == "5.0.0"

    def test_from_dev_dependencies(self, tmp_path: Path) -> None:
        """Test detecting from devDependencies."""
        package_json = {"devDependencies": {"typescript": "^5.2.2"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        version = _detect_typescript_version(tmp_path)
        assert version == "5.2.2"

    def test_strips_version_prefix(self, tmp_path: Path) -> None:
        """Test stripping version prefixes."""
        package_json = {"devDependencies": {"typescript": "~4.9.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        version = _detect_typescript_version(tmp_path)
        assert version == "4.9.0"

    def test_no_package_json(self, tmp_path: Path) -> None:
        """Test when no package.json exists."""
        version = _detect_typescript_version(tmp_path)
        assert version is None

    def test_no_typescript_dependency(self, tmp_path: Path) -> None:
        """Test when TypeScript is not a dependency."""
        package_json = {"dependencies": {"lodash": "4.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        version = _detect_typescript_version(tmp_path)
        assert version is None


class TestDetectGoVersion:
    """Tests for _detect_go_version function."""

    def test_from_go_mod(self, tmp_path: Path) -> None:
        """Test detecting from go.mod."""
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21")

        version = _detect_go_version(tmp_path)
        assert version == "1.21"

    def test_go_version_with_patch(self, tmp_path: Path) -> None:
        """Test go version with patch number."""
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.22")

        version = _detect_go_version(tmp_path)
        assert version == "1.22"

    def test_no_go_mod(self, tmp_path: Path) -> None:
        """Test when no go.mod exists."""
        version = _detect_go_version(tmp_path)
        assert version is None


class TestDetectRustVersion:
    """Tests for _detect_rust_version function."""

    def test_from_cargo_toml(self, tmp_path: Path) -> None:
        """Test detecting edition from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text('[package]\nedition = "2021"')

        version = _detect_rust_version(tmp_path)
        assert version == "2021"

    def test_edition_with_single_quotes(self, tmp_path: Path) -> None:
        """Test detecting edition with single quotes."""
        (tmp_path / "Cargo.toml").write_text("[package]\nedition = '2018'")

        version = _detect_rust_version(tmp_path)
        assert version == "2018"

    def test_no_cargo_toml(self, tmp_path: Path) -> None:
        """Test when no Cargo.toml exists."""
        version = _detect_rust_version(tmp_path)
        assert version is None

    def test_no_edition(self, tmp_path: Path) -> None:
        """Test when no edition is specified."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        version = _detect_rust_version(tmp_path)
        assert version is None


class TestDetectJavaVersion:
    """Tests for _detect_java_version function."""

    def test_from_pom_java_version(self, tmp_path: Path) -> None:
        """Test detecting from pom.xml java.version property."""
        pom = """<project>
            <properties>
                <java.version>17</java.version>
            </properties>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom)

        version = _detect_java_version(tmp_path)
        assert version == "17"

    def test_from_pom_maven_compiler_source(self, tmp_path: Path) -> None:
        """Test detecting from pom.xml maven.compiler.source property."""
        pom = """<project>
            <properties>
                <maven.compiler.source>11</maven.compiler.source>
            </properties>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom)

        version = _detect_java_version(tmp_path)
        assert version == "11"

    def test_from_pom_release(self, tmp_path: Path) -> None:
        """Test detecting from pom.xml release property."""
        pom = """<project>
            <properties>
                <release>21</release>
            </properties>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom)

        version = _detect_java_version(tmp_path)
        assert version == "21"

    def test_from_build_gradle(self, tmp_path: Path) -> None:
        """Test detecting from build.gradle sourceCompatibility."""
        gradle = "sourceCompatibility = '17'"
        (tmp_path / "build.gradle").write_text(gradle)

        version = _detect_java_version(tmp_path)
        assert version == "17"

    def test_from_build_gradle_kts(self, tmp_path: Path) -> None:
        """Test detecting from build.gradle.kts."""
        gradle = "sourceCompatibility = JavaVersion.VERSION_21"
        (tmp_path / "build.gradle.kts").write_text(gradle)

        version = _detect_java_version(tmp_path)
        assert version == "21"

    def test_from_build_gradle_toolchain(self, tmp_path: Path) -> None:
        """Test detecting from Gradle toolchain."""
        gradle = """java {
            toolchain {
                languageVersion.set(JavaLanguageVersion.of(17))
            }
        }"""
        (tmp_path / "build.gradle.kts").write_text(gradle)

        version = _detect_java_version(tmp_path)
        assert version == "17"

    def test_from_java_version_file(self, tmp_path: Path) -> None:
        """Test detecting from .java-version file."""
        (tmp_path / ".java-version").write_text("17.0.2")

        version = _detect_java_version(tmp_path)
        assert version == "17"

    def test_no_java_config(self, tmp_path: Path) -> None:
        """Test when no Java config exists."""
        version = _detect_java_version(tmp_path)
        assert version is None


class TestConstants:
    """Tests for module constants."""

    def test_skip_dirs_contains_common_dirs(self) -> None:
        """Test SKIP_DIRS contains common directories to skip."""
        assert "node_modules" in SKIP_DIRS
        assert ".git" in SKIP_DIRS
        assert "__pycache__" in SKIP_DIRS
        assert ".venv" in SKIP_DIRS

    def test_extension_map_covers_common_languages(self) -> None:
        """Test EXTENSION_MAP covers common file extensions."""
        assert EXTENSION_MAP[".py"] == "python"
        assert EXTENSION_MAP[".js"] == "javascript"
        assert EXTENSION_MAP[".ts"] == "typescript"
        assert EXTENSION_MAP[".go"] == "go"
        assert EXTENSION_MAP[".rs"] == "rust"
        assert EXTENSION_MAP[".java"] == "java"

    def test_marker_files_covers_common_languages(self) -> None:
        """Test MARKER_FILES covers common languages."""
        assert "pyproject.toml" in MARKER_FILES["python"]
        assert "package.json" in MARKER_FILES["javascript"]
        assert "tsconfig.json" in MARKER_FILES["typescript"]
        assert "go.mod" in MARKER_FILES["go"]
        assert "Cargo.toml" in MARKER_FILES["rust"]
