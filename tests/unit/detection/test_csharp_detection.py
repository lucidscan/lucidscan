"""Unit tests for C# language and framework detection."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lucidshark.detection.languages import (
    EXTENSION_MAP,
    MARKER_GLOBS,
    _detect_csharp_version,
    detect_languages,
)
from lucidshark.detection.frameworks import (
    _parse_csproj_deps,
    detect_frameworks,
)


class TestCSharpLanguageDetection:
    """Tests for C# language detection."""

    def test_cs_extension_mapped(self) -> None:
        assert EXTENSION_MAP[".cs"] == "csharp"

    def test_marker_globs_defined(self) -> None:
        assert "csharp" in MARKER_GLOBS
        assert "*.sln" in MARKER_GLOBS["csharp"]
        assert "*.csproj" in MARKER_GLOBS["csharp"]

    def test_detects_csharp_by_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Program.cs").write_text("class Program {}")
            languages = detect_languages(project_root)
            names = [lang.name for lang in languages]
            assert "csharp" in names

    def test_detects_csharp_by_sln_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.sln").touch()
            languages = detect_languages(project_root)
            names = [lang.name for lang in languages]
            assert "csharp" in names

    def test_detects_csharp_by_csproj_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()
            languages = detect_languages(project_root)
            names = [lang.name for lang in languages]
            assert "csharp" in names


class TestCSharpVersionDetection:
    """Tests for C# version detection."""

    def test_from_global_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "global.json").write_text(
                '{"sdk": {"version": "8.0.100"}}'
            )
            version = _detect_csharp_version(project_root)
            assert version == "8.0"

    def test_from_csproj_target_framework(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").write_text(
                "<Project>\n"
                "  <PropertyGroup>\n"
                "    <TargetFramework>net8.0</TargetFramework>\n"
                "  </PropertyGroup>\n"
                "</Project>"
            )
            version = _detect_csharp_version(project_root)
            assert version == "8.0"

    def test_from_csproj_netcoreapp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").write_text(
                "<Project>\n"
                "  <PropertyGroup>\n"
                "    <TargetFramework>netcoreapp3.1</TargetFramework>\n"
                "  </PropertyGroup>\n"
                "</Project>"
            )
            version = _detect_csharp_version(project_root)
            assert version == "3.1"

    def test_no_version_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            version = _detect_csharp_version(project_root)
            assert version is None

    def test_prefers_global_json_over_csproj(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "global.json").write_text(
                '{"sdk": {"version": "9.0.100"}}'
            )
            (project_root / "MyApp.csproj").write_text(
                "<Project>\n"
                "  <PropertyGroup>\n"
                "    <TargetFramework>net8.0</TargetFramework>\n"
                "  </PropertyGroup>\n"
                "</Project>"
            )
            version = _detect_csharp_version(project_root)
            assert version == "9.0"


class TestCSharpDependencyParsing:
    """Tests for C# dependency parsing."""

    def test_parse_package_references(self) -> None:
        content = """
<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="xunit" Version="2.5.0" />
    <PackageReference Include="FluentAssertions" Version="6.12.0" />
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
  </ItemGroup>
</Project>
"""
        deps = _parse_csproj_deps(content)
        assert "xunit" in deps
        assert "FluentAssertions" in deps
        assert "Microsoft.EntityFrameworkCore" in deps

    def test_parse_web_sdk(self) -> None:
        content = '<Project Sdk="Microsoft.NET.Sdk.Web">'
        deps = _parse_csproj_deps(content)
        assert "Microsoft.AspNetCore.App" in deps

    def test_parse_framework_references(self) -> None:
        content = """
<Project>
  <ItemGroup>
    <FrameworkReference Include="Microsoft.AspNetCore.App" />
  </ItemGroup>
</Project>
"""
        deps = _parse_csproj_deps(content)
        assert "Microsoft.AspNetCore.App" in deps


class TestCSharpFrameworkDetection:
    """Tests for C# framework detection."""

    def test_detects_xunit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Tests.csproj").write_text(
                '<Project Sdk="Microsoft.NET.Sdk">\n'
                "  <ItemGroup>\n"
                '    <PackageReference Include="xunit" Version="2.5.0" />\n'
                "  </ItemGroup>\n"
                "</Project>"
            )
            _, test_frameworks = detect_frameworks(project_root)
            assert "xunit" in test_frameworks

    def test_detects_aspnet_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "WebApp.csproj").write_text(
                '<Project Sdk="Microsoft.NET.Sdk.Web">\n'
                "  <PropertyGroup>\n"
                "    <TargetFramework>net8.0</TargetFramework>\n"
                "  </PropertyGroup>\n"
                "</Project>"
            )
            frameworks, _ = detect_frameworks(project_root)
            assert "aspnet-core" in frameworks

    def test_detects_entity_framework(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").write_text(
                '<Project Sdk="Microsoft.NET.Sdk">\n'
                "  <ItemGroup>\n"
                '    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />\n'
                "  </ItemGroup>\n"
                "</Project>"
            )
            frameworks, _ = detect_frameworks(project_root)
            assert "entity-framework" in frameworks

    def test_detects_nunit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Tests.csproj").write_text(
                '<Project Sdk="Microsoft.NET.Sdk">\n'
                "  <ItemGroup>\n"
                '    <PackageReference Include="NUnit" Version="3.14.0" />\n'
                '    <PackageReference Include="NUnit3TestAdapter" Version="4.5.0" />\n'
                "  </ItemGroup>\n"
                "</Project>"
            )
            _, test_frameworks = detect_frameworks(project_root)
            assert "nunit" in test_frameworks

    def test_detects_mstest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Tests.csproj").write_text(
                '<Project Sdk="Microsoft.NET.Sdk">\n'
                "  <ItemGroup>\n"
                '    <PackageReference Include="MSTest.TestFramework" Version="3.0.0" />\n'
                "  </ItemGroup>\n"
                "</Project>"
            )
            _, test_frameworks = detect_frameworks(project_root)
            assert "mstest" in test_frameworks
