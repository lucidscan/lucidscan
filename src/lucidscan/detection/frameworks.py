"""Framework detection module.

Detects web frameworks, testing frameworks, and libraries by analyzing:
- Dependencies in package manifests (pyproject.toml, package.json)
- Import statements (optional, for deeper analysis)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional

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
    deps = set()

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
