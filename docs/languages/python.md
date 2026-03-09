# Python

**Support tier: Full**

Python has the deepest tool coverage in LucidShark, with dedicated tools across all six quality domains.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.py`, `.pyw`, `.pyi` |
| **Marker files** | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile` |
| **Version detection** | `requires-python` from `pyproject.toml`, `.python-version` file |

## Tools by Domain

| Domain | Tool | Auto-Fix | Notes |
|--------|------|----------|-------|
| **Linting** | Ruff | Yes | Fast Rust-based linter with 100+ rule categories |
| **Type Checking** | mypy | -- | Strict mode available |
| **Type Checking** | Pyright | -- | Strict mode available |
| **Security (SAST)** | OpenGrep | -- | Python-specific vulnerability rules |
| **Security (SCA)** | Trivy | -- | Scans `requirements.txt`, `Pipfile.lock`, `pyproject.toml` |
| **Testing** | pytest | -- | JSON report via pytest-json-report, JUnit XML fallback |
| **Coverage** | coverage.py | -- | Integrates with pytest, per-file tracking |
| **Duplication** | Duplo | -- | Configurable min lines and threshold |

## Linting

**Tool: [Ruff](https://docs.astral.sh/ruff/)**

Ruff is an extremely fast Python linter and formatter written in Rust. LucidShark downloads the binary automatically.

- Supports auto-fix via `--fix`
- 100+ rule categories including: pyflakes (F), pycodestyle (E/W), isort (I), pep8-naming (N), flake8-bugbear (B), flake8-security (S), and many more
- Configurable via `ruff.toml`, `pyproject.toml [tool.ruff]`, or `.ruff.toml`

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: ruff
```

## Type Checking

**Tool: [mypy](https://mypy.readthedocs.io/)**

Static type checker for Python. Supports strict mode for stricter type enforcement.

- JSON output format
- Config detection: `mypy.ini`, `setup.cfg`, `pyproject.toml`
- Error codes (e.g., `assignment`, `return-value`, `arg-type`)

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: mypy
        strict: true
```

**Tool: [Pyright](https://github.com/microsoft/pyright)**

Microsoft's Python type checker. Can be used as an alternative or complement to mypy.

- Strict mode available
- Supports `.venv`, `node_modules`, and system PATH installations
- 0-based indexing auto-adjusted to 1-based

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: pyright
        strict: true
```

## Testing

**Tool: [pytest](https://docs.pytest.org/)**

The standard Python test framework.

- JSON report via `pytest-json-report` plugin (falls back to JUnit XML)
- Automatic source directory detection for coverage integration
- Assertion failure extraction with context

```yaml
pipeline:
  testing:
    enabled: true
    tools:
      - name: pytest
```

## Coverage

**Tool: [coverage.py](https://coverage.readthedocs.io/)**

Parses existing `.coverage` data files produced by the pytest test runner.

- JSON report generation via `coverage json`
- Per-file coverage tracking with missing line numbers
- Threshold-based pass/fail
- Returns error if no `.coverage` file found (requires testing domain to be active)

```yaml
pipeline:
  coverage:
    enabled: true
    tools: [{ name: coverage_py }]
    threshold: 80
```

## Security

Security tools (OpenGrep, Trivy, Checkov) are language-agnostic. See the domain-specific sections in the [main documentation](../main.md) for details.

Trivy SCA scans these Python-specific manifests: `requirements.txt`, `Pipfile.lock`, `poetry.lock`, `pyproject.toml`.

## Duplication

Duplo scans `.py` files for duplicate code blocks. Configure the minimum lines and duplication threshold:

```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 5.0
```

## Example Configurations

### Production (all domains, strict checks)

```yaml
version: 1
project:
  languages: [python]
pipeline:
  linting:
    enabled: true
    tools: [{ name: ruff }]
  type_checking:
    enabled: true
    tools: [{ name: mypy, strict: true }]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
  testing:
    enabled: true
    tools: [{ name: pytest }]
  coverage:
    enabled: true
    threshold: 80
  duplication:
    enabled: true
    threshold: 5.0
fail_on:
  linting: error
  type_checking: error
  security: high
  testing: any
  coverage: below_threshold
  duplication: above_threshold
exclude:
  - "**/__pycache__/**"
  - "**/.venv/**"
  - "**/.mypy_cache/**"
```

### Minimal (linting + security only)

```yaml
version: 1
project:
  languages: [python]
pipeline:
  linting:
    enabled: true
    tools: [{ name: ruff }]
  type_checking:
    enabled: true
    tools: [{ name: mypy }]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
exclude:
  - "**/__pycache__/**"
  - "**/.venv/**"
```

### With Pyright instead of mypy

```yaml
version: 1
project:
  languages: [python]
pipeline:
  type_checking:
    enabled: true
    tools: [{ name: pyright, strict: true }]
```

## See Also

- [Supported Languages Overview](README.md)
