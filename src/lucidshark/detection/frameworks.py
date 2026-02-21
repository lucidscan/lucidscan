"""Framework detection module.

Detects web frameworks, testing frameworks, and libraries by analyzing:
- Dependencies in package manifests (pyproject.toml, package.json, pom.xml, build.gradle)
- Import statements (optional, for deeper analysis)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional, Set

# Python frameworks and their package names
PYTHON_FRAMEWORKS: Dict[str, str] = {
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "starlette": "starlette",
    "tornado": "tornado",
    "aiohttp": "aiohttp",
    "sanic": "sanic",
    "quart": "quart",
    "falcon": "falcon",
    "bottle": "bottle",
    "pyramid": "pyramid",
    "cherrypy": "cherrypy",
}

# Python test frameworks
PYTHON_TEST_FRAMEWORKS: Dict[str, Optional[str]] = {
    "pytest": "pytest",
    "unittest": None,  # Built-in, detected by imports
    "nose": "nose",
    "nose2": "nose2",
    "hypothesis": "hypothesis",
}

# JavaScript/TypeScript frameworks
JS_FRAMEWORKS = {
    "react": "react",
    "vue": "vue",
    "angular": "@angular/core",
    "svelte": "svelte",
    "next": "next",
    "nuxt": "nuxt",
    "express": "express",
    "fastify": "fastify",
    "nest": "@nestjs/core",
    "koa": "koa",
    "hapi": "@hapi/hapi",
}

# JavaScript test frameworks
JS_TEST_FRAMEWORKS = {
    "jest": "jest",
    "mocha": "mocha",
    "vitest": "vitest",
    "jasmine": "jasmine",
    "cypress": "cypress",
    "playwright": "@playwright/test",
}

# Java frameworks and their Maven/Gradle identifiers
JAVA_FRAMEWORKS: Dict[str, list[str]] = {
    "spring-boot": [
        "org.springframework.boot:spring-boot",
        "spring-boot-starter",
        "spring-boot-starter-parent",
        "spring-boot-starter-web",
    ],
    "spring": ["org.springframework:spring-core", "spring-context"],
    "quarkus": ["io.quarkus:quarkus-core", "quarkus-bom"],
    "micronaut": ["io.micronaut:micronaut-core", "micronaut-bom"],
    "jakarta-ee": ["jakarta.platform:jakarta.jakartaee-api", "javax:javaee-api"],
    "dropwizard": ["io.dropwizard:dropwizard-core"],
    "vertx": ["io.vertx:vertx-core"],
    "play": ["com.typesafe.play:play"],
    "spark": ["com.sparkjava:spark-core"],
    "jersey": ["org.glassfish.jersey.core:jersey-server"],
}

# Java test frameworks
JAVA_TEST_FRAMEWORKS: Dict[str, list[str]] = {
    "junit5": ["org.junit.jupiter:junit-jupiter", "junit-jupiter"],
    "junit4": ["junit:junit"],
    "testng": ["org.testng:testng"],
    "mockito": ["org.mockito:mockito-core"],
    "assertj": ["org.assertj:assertj-core"],
    "spock": ["org.spockframework:spock-core"],
    "arquillian": ["org.jboss.arquillian:arquillian-bom"],
}


# Rust frameworks and their crate names (from Cargo.toml dependencies)
RUST_FRAMEWORKS: Dict[str, str] = {
    "actix-web": "actix-web",
    "rocket": "rocket",
    "axum": "axum",
    "warp": "warp",
    "hyper": "hyper",
    "tonic": "tonic",
    "tokio": "tokio",
    "tide": "tide",
}

# Rust test frameworks
RUST_TEST_FRAMEWORKS: Dict[str, Optional[str]] = {
    "built-in": None,  # Rust has built-in test support
    "criterion": "criterion",
    "proptest": "proptest",
}


def detect_frameworks(project_root: Path) -> tuple[list[str], list[str]]:
    """Detect frameworks and test frameworks in a project.

    Args:
        project_root: Path to the project root directory.

    Returns:
        Tuple of (frameworks, test_frameworks).
    """
    frameworks = []
    test_frameworks = []

    # Check Python dependencies
    python_deps = _get_python_dependencies(project_root)
    for framework, package in PYTHON_FRAMEWORKS.items():
        if package in python_deps:
            frameworks.append(framework)

    for framework, pkg in PYTHON_TEST_FRAMEWORKS.items():
        if pkg and pkg in python_deps:
            test_frameworks.append(framework)

    # Check JavaScript/TypeScript dependencies
    js_deps = _get_js_dependencies(project_root)
    for framework, package in JS_FRAMEWORKS.items():
        if package in js_deps:
            frameworks.append(framework)

    for framework, package in JS_TEST_FRAMEWORKS.items():
        if package in js_deps:
            test_frameworks.append(framework)

    # Check Java dependencies
    java_deps = _get_java_dependencies(project_root)
    for framework, identifiers in JAVA_FRAMEWORKS.items():
        if any(identifier in java_deps for identifier in identifiers):
            frameworks.append(framework)

    for framework, identifiers in JAVA_TEST_FRAMEWORKS.items():
        if any(identifier in java_deps for identifier in identifiers):
            test_frameworks.append(framework)

    # Check Rust dependencies
    rust_deps = _get_rust_dependencies(project_root)
    for framework, crate_name in RUST_FRAMEWORKS.items():
        if crate_name in rust_deps:
            frameworks.append(framework)

    for framework, test_crate in RUST_TEST_FRAMEWORKS.items():
        if test_crate and test_crate in rust_deps:
            test_frameworks.append(framework)

    # Rust always has built-in test support
    if (project_root / "Cargo.toml").exists():
        if "built-in" not in test_frameworks:
            test_frameworks.append("built-in")

    # Check for pytest.ini or conftest.py as indicators
    if (project_root / "pytest.ini").exists() or (project_root / "conftest.py").exists():
        if "pytest" not in test_frameworks:
            test_frameworks.append("pytest")

    # Check for jest.config.js
    jest_configs = ["jest.config.js", "jest.config.ts", "jest.config.mjs"]
    if any((project_root / cfg).exists() for cfg in jest_configs):
        if "jest" not in test_frameworks:
            test_frameworks.append("jest")

    return frameworks, test_frameworks


def _get_python_dependencies(project_root: Path) -> set[str]:
    """Extract Python dependencies from pyproject.toml or requirements.txt.

    Args:
        project_root: Project root directory.

    Returns:
        Set of package names (lowercase).
    """
    deps = set()

    # Check pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            deps.update(_parse_pyproject_deps(content))
        except Exception:
            pass

    # Check requirements.txt
    requirements = project_root / "requirements.txt"
    if requirements.exists():
        try:
            deps.update(_parse_requirements_txt(requirements.read_text()))
        except Exception:
            pass

    # Check requirements-dev.txt or requirements_dev.txt
    for dev_req in ["requirements-dev.txt", "requirements_dev.txt", "dev-requirements.txt"]:
        dev_requirements = project_root / dev_req
        if dev_requirements.exists():
            try:
                deps.update(_parse_requirements_txt(dev_requirements.read_text()))
            except Exception:
                pass

    return deps


def _parse_pyproject_deps(content: str) -> set[str]:
    """Parse dependencies from pyproject.toml content.

    Args:
        content: pyproject.toml file content.

    Returns:
        Set of package names.
    """
    deps = set()

    # Simple regex-based parsing for dependencies
    # Matches: "package-name>=1.0" or "package-name[extra]>=1.0" etc.
    # In dependencies array or optional-dependencies

    # Find dependencies section
    dep_section = re.search(
        r'dependencies\s*=\s*\[(.*?)\]',
        content,
        re.DOTALL
    )
    if dep_section:
        deps.update(_extract_package_names(dep_section.group(1)))

    # Find optional-dependencies (all groups)
    opt_deps = re.findall(
        r'\[project\.optional-dependencies\.[^\]]+\]\s*\n([^\[]+)',
        content
    )
    for section in opt_deps:
        deps.update(_extract_package_names(section))

    # Also check [tool.poetry.dependencies] for Poetry projects
    poetry_deps = re.search(
        r'\[tool\.poetry\.dependencies\](.*?)(?=\[|$)',
        content,
        re.DOTALL
    )
    if poetry_deps:
        # Poetry uses package = "version" format
        package_matches = re.findall(r'^(\w[\w-]*)\s*=', poetry_deps.group(1), re.MULTILINE)
        deps.update(p.lower().replace("-", "_").replace("_", "-") for p in package_matches)

    return deps


def _extract_package_names(text: str) -> set[str]:
    """Extract package names from a dependencies list.

    Args:
        text: Text containing package specifications.

    Returns:
        Set of normalized package names.
    """
    deps = set()

    # Match quoted strings like "fastapi>=0.100" or 'django[async]'
    matches = re.findall(r'["\']([a-zA-Z][\w.-]*)', text)
    for match in matches:
        # Normalize: remove extras, convert to lowercase
        package = re.sub(r'\[.*?\]', '', match).lower()
        # Normalize underscores and hyphens
        package = package.replace("_", "-")
        deps.add(package)

    return deps


def _parse_requirements_txt(content: str) -> set[str]:
    """Parse package names from requirements.txt content.

    Args:
        content: requirements.txt file content.

    Returns:
        Set of package names.
    """
    deps = set()

    for line in content.splitlines():
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        # Extract package name (before any version specifier)
        match = re.match(r'^([a-zA-Z][\w.-]*)', line)
        if match:
            package = match.group(1).lower().replace("_", "-")
            deps.add(package)

    return deps


def _get_js_dependencies(project_root: Path) -> set[str]:
    """Extract JavaScript/TypeScript dependencies from package.json.

    Args:
        project_root: Project root directory.

    Returns:
        Set of package names.
    """
    deps: Set[str] = set()

    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text())

            # Collect from all dependency types
            for dep_type in ["dependencies", "devDependencies", "peerDependencies"]:
                if dep_type in data:
                    deps.update(data[dep_type].keys())
        except Exception:
            pass

    return deps


def _get_java_dependencies(project_root: Path) -> Set[str]:
    """Extract Java dependencies from pom.xml or build.gradle.

    Args:
        project_root: Project root directory.

    Returns:
        Set of dependency identifiers (groupId:artifactId format or artifact names).
    """
    deps: Set[str] = set()

    # Check Maven pom.xml
    pom_xml = project_root / "pom.xml"
    if pom_xml.exists():
        try:
            deps.update(_parse_maven_pom(pom_xml.read_text()))
        except Exception:
            pass

    # Check Gradle build files
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle_path = project_root / gradle_file
        if gradle_path.exists():
            try:
                deps.update(_parse_gradle_build(gradle_path.read_text()))
            except Exception:
                pass

    return deps


def _parse_maven_pom(content: str) -> Set[str]:
    """Parse dependencies from Maven pom.xml content.

    Args:
        content: pom.xml file content.

    Returns:
        Set of dependency identifiers.
    """
    deps: Set[str] = set()

    # Simple regex-based parsing for Maven dependencies
    # Matches <groupId>...</groupId> and <artifactId>...</artifactId> within <dependency>
    # This is a simplified parser - for full accuracy, use XML parsing

    # Find all dependencies
    dep_pattern = r"<dependency>(.*?)</dependency>"
    group_pattern = r"<groupId>([^<]+)</groupId>"
    artifact_pattern = r"<artifactId>([^<]+)</artifactId>"

    for dep_match in re.finditer(dep_pattern, content, re.DOTALL):
        dep_content = dep_match.group(1)

        group_match = re.search(group_pattern, dep_content)
        artifact_match = re.search(artifact_pattern, dep_content)

        if group_match and artifact_match:
            group_id = group_match.group(1).strip()
            artifact_id = artifact_match.group(1).strip()
            deps.add(f"{group_id}:{artifact_id}")
            deps.add(artifact_id)  # Also add just artifact for simpler matching

    # Check parent for Spring Boot etc.
    parent_pattern = r"<parent>(.*?)</parent>"
    parent_match = re.search(parent_pattern, content, re.DOTALL)
    if parent_match:
        parent_content = parent_match.group(1)
        group_match = re.search(group_pattern, parent_content)
        artifact_match = re.search(artifact_pattern, parent_content)
        if group_match and artifact_match:
            group_id = group_match.group(1).strip()
            artifact_id = artifact_match.group(1).strip()
            deps.add(f"{group_id}:{artifact_id}")
            deps.add(artifact_id)

    return deps


def _parse_gradle_build(content: str) -> Set[str]:
    """Parse dependencies from Gradle build file content.

    Args:
        content: build.gradle or build.gradle.kts file content.

    Returns:
        Set of dependency identifiers.
    """
    deps: Set[str] = set()

    # Match Gradle dependency declarations like:
    # implementation 'org.springframework.boot:spring-boot-starter-web'
    # implementation("org.springframework.boot:spring-boot-starter-web")
    # testImplementation 'junit:junit:4.13.2'

    # Pattern for quoted dependencies
    dep_patterns = [
        r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testCompileOnly|testRuntimeOnly)\s*['\"]([^'\"]+)['\"]",
        r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testCompileOnly|testRuntimeOnly)\s*\(['\"]([^'\"]+)['\"]\)",
    ]

    for pattern in dep_patterns:
        for match in re.finditer(pattern, content):
            dep = match.group(1)
            # Format: group:artifact:version or group:artifact
            parts = dep.split(":")
            if len(parts) >= 2:
                deps.add(f"{parts[0]}:{parts[1]}")
                deps.add(parts[1])  # Also add just artifact

    # Check for Spring Boot plugin
    if "org.springframework.boot" in content or "spring-boot-gradle-plugin" in content:
        deps.add("spring-boot-starter")

    # Check for Quarkus plugin
    if "io.quarkus" in content:
        deps.add("quarkus-bom")

    return deps


def _get_rust_dependencies(project_root: Path) -> set[str]:
    """Extract Rust dependencies from Cargo.toml.

    Args:
        project_root: Project root directory.

    Returns:
        Set of crate names (lowercase).
    """
    deps: Set[str] = set()

    cargo_toml = project_root / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text()
            deps.update(_parse_cargo_toml_deps(content))
        except Exception:
            pass

    return deps


def _parse_cargo_toml_deps(content: str) -> set[str]:
    """Parse dependencies from Cargo.toml content.

    Args:
        content: Cargo.toml file content.

    Returns:
        Set of crate names.
    """
    deps: Set[str] = set()

    # Match [dependencies] and [dev-dependencies] section entries
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()

        # Check for section headers
        if stripped.startswith("["):
            in_deps = "dependencies" in stripped.lower()
            continue

        if in_deps and "=" in stripped:
            # Extract crate name (before the =)
            crate_name = stripped.split("=")[0].strip().lower()
            if crate_name and not crate_name.startswith("#"):
                deps.add(crate_name)

    return deps
