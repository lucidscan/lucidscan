# lucidscan

[![CI](https://github.com/voldeq/lucidscan/actions/workflows/ci.yml/badge.svg)](https://github.com/voldeq/lucidscan/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/voldeq/lucidscan/graph/badge.svg)](https://codecov.io/gh/voldeq/lucidscan)
[![PyPI version](https://img.shields.io/pypi/v/lucidscan)](https://pypi.org/project/lucidscan/)
[![Python](https://img.shields.io/pypi/pyversions/lucidscan)](https://pypi.org/project/lucidscan/)
[![License](https://img.shields.io/github/license/voldeq/lucidscan)](https://github.com/voldeq/lucidscan/blob/main/LICENSE)

A unified CLI for running multiple security scanners (Trivy, OpenGrep, Checkov) with consistent output.

## Installation

```bash
pip install lucidscan
```

## Usage

```bash
# Scan dependencies for vulnerabilities
lucidscan --sca

# Scan code for security issues
lucidscan --sast

# Scan Terraform/Kubernetes configs
lucidscan --iac

# Scan container images
lucidscan --container --image nginx:latest

# Run all scanners
lucidscan --all

# Output formats
lucidscan --all --format json
lucidscan --all --format table
lucidscan --all --format sarif

# Fail CI if high severity issues found
lucidscan --all --fail-on high
```

Scanner binaries are downloaded automatically on first use.

## What it does

lucidscan wraps these tools behind a single CLI:

| Domain | Scanner | Detects |
|--------|---------|---------|
| SCA | [Trivy](https://github.com/aquasecurity/trivy) | Vulnerable dependencies |
| Container | [Trivy](https://github.com/aquasecurity/trivy) | Image vulnerabilities |
| SAST | [OpenGrep](https://github.com/opengrep/opengrep) | Code security issues |
| IaC | [Checkov](https://github.com/bridgecrewio/checkov) | Infrastructure misconfigs |

All results are normalized to a common JSON schema:

```json
{
  "id": "trivy-a1b2c3d4",
  "scanner": "sca",
  "source_tool": "trivy",
  "severity": "high",
  "title": "CVE-2024-1234: RCE in lodash",
  "file_path": "package.json",
  "recommendation": "Upgrade to 4.17.21"
}
```

## CI Integration

### GitHub Actions

```yaml
- name: Security scan
  run: |
    pip install lucidscan
    lucidscan --all --fail-on high
```

### With SARIF upload

```yaml
- name: Security scan
  run: |
    pip install lucidscan
    lucidscan --all --format sarif > results.sarif

- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results.sarif
```

## Configuration

Optional `.lucidscan.yml`:

```yaml
scanners:
  sca:
    enabled: true
  sast:
    enabled: true
  iac:
    enabled: true

ignore:
  - path: "vendor/**"
  - path: "node_modules/**"

severity_threshold: medium
```

## Plugin Architecture

Scanners are implemented as plugins. Built-in:

- `TrivyScanner` - SCA + container scanning
- `OpenGrepScanner` - static code analysis
- `CheckovScanner` - IaC scanning

Third-party plugins can be installed from PyPI:

```bash
pip install lucidscan-snyk  # hypothetical
```

## Development

```bash
git clone https://github.com/voldeq/lucidscan.git
cd lucidscan
pip install -e ".[dev]"
pytest tests/
```

## Documentation

See [docs/main.md](docs/main.md) for the full specification.

## License

Apache-2.0 - Copyright 2025 Voldeq GmbH, Zollikofen, Switzerland
