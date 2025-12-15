## lucidscan

[![CI](https://github.com/voldeq/lucidshark/actions/workflows/ci.yml/badge.svg)](https://github.com/voldeq/lucidshark/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/voldeq/lucidshark/graph/badge.svg)](https://codecov.io/gh/voldeq/lucidshark)
[![PyPI version](https://img.shields.io/pypi/v/lucidscan)](https://pypi.org/project/lucidscan/)
[![Python](https://img.shields.io/pypi/pyversions/lucidscan)](https://pypi.org/project/lucidscan/)
[![License](https://img.shields.io/github/license/voldeq/lucidshark)](https://github.com/voldeq/lucidshark/blob/main/LICENSE)

`lucidscan` is the CLI component of LucidScan, a unified security scanner that
orchestrates multiple open-source tools (Trivy, Semgrep, Checkov) and exposes a
consistent command-line interface and unified issue schema.

At this stage of development, the CLI is a **skeleton only**. It provides:

- A `lucidscan` executable installed via `pip install -e .`.
- `lucidscan --help` with core global flags.
- Stub scanner flags (`--sca`, `--container`, `--iac`, `--sast`, `--all`) that
  are not yet wired to real scanners.

Refer to the docs in `docs/` for the full product specification and development
plan.


