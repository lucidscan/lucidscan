# Go

**Support tier: Full**

Go projects are fully supported with linting, type checking, testing, coverage, formatting, security scanning, and duplication detection.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.go` |
| **Marker files** | `go.mod` |
| **Version detection** | `go` directive from `go.mod` |

## Tools by Domain

| Domain | Tool | Notes |
|--------|------|-------|
| **Linting** | golangci-lint | Meta-linter with 100+ linters (staticcheck, gosimple, govet, errcheck, etc.) |
| **Formatting** | gofmt | Canonical Go formatter; ships with Go |
| **Type Checking** | go vet | Compiler diagnostics + vet analyzers; ships with Go |
| **Testing** | go test | Built-in Go test runner with `-json` output |
| **Coverage** | go cover | Parses coverprofile format; ships with Go |
| **Security (SAST)** | OpenGrep | Go-specific vulnerability rules |
| **Security (SCA)** | Trivy | Scans `go.sum`, `go.mod` |
| **Duplication** | Duplo | Scans `.go` files |

## Linting

**Tool: [golangci-lint](https://golangci-lint.run/)**

golangci-lint is a meta-linter that runs 100+ linters in parallel, including staticcheck, gosimple, govet, errcheck, ineffassign, and many more.

- Supports auto-fix via `golangci-lint run --fix`
- Configurable via `.golangci.yml`, `.golangci.yaml`, `.golangci.toml`, or `.golangci.json`
- Default linters: govet, errcheck, staticcheck, gosimple, ineffassign, typecheck, unused

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: golangci_lint
```

**Severity mapping:** Severity is determined by the linter that reported the issue:

- **High** -- correctness/security linters: govet, staticcheck, gosec, errcheck
- **Medium** -- bug detection linters: ineffassign, unused, gocritic, revive
- **Low** -- style/convention linters: gosimple, goconst, gofmt, misspell

**Installation:** `go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest`

## Formatting

**Tool: [gofmt](https://pkg.go.dev/cmd/gofmt)**

The canonical Go code formatter. Ships with Go -- no separate installation required.

- Supports auto-fix (runs `gofmt -w` directly on files)
- Check-only mode via `gofmt -l` (lists files that differ)
- No configuration needed -- gofmt enforces a single canonical style

```yaml
pipeline:
  formatting:
    enabled: true
    tools:
      - name: gofmt
```

## Type Checking

**Tool: [go vet](https://pkg.go.dev/cmd/vet)**

`go vet` runs the Go compiler's type checking plus additional analyzers that find bugs not caught by the compiler. Ships with Go -- no separate installation required.

- JSON output via `go vet -json` (requires Go 1.16+)
- Detects: printf format mismatches, unreachable code, suspicious constructs, struct tag errors, atomic operation misuse
- Operates on packages (project-wide)
- Outputs JSON to stderr (not stdout); a text fallback parser is included for compatibility with older Go versions

**Severity mapping:** Severity is determined by the analyzer that reported the issue:

- **High** -- correctness analyzers: printf, copylocks, lostcancel, atomic
- **Medium** -- style/convention analyzers: composites, structtag, unreachable

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: go_vet
```

## Testing

**Tool: [go test](https://pkg.go.dev/cmd/go#hdr-Test_packages)**

`go test` runs all unit tests (`*_test.go` files), including table-driven tests, subtests, and benchmarks.

- JSON output via `go test -json`
- Supports partial scanning (specific packages)

```yaml
pipeline:
  testing:
    enabled: true
    tools:
      - name: go_test
```

## Coverage

**Tool: [go cover](https://pkg.go.dev/cmd/cover)**

`go cover` parses coverprofile format files produced by `go test -coverprofile`.

- Parses existing coverprofile data produced by the test runner
- Returns error if no coverprofile found (requires testing domain to be active)

> **Note:** When both the `testing` and `coverage` domains are active, the go test runner automatically adds `-coverprofile=coverage.out` to generate coverage data in the same pass. No manual coverage generation is needed.

```yaml
pipeline:
  coverage:
    enabled: true
    tools:
      - name: go_cover
    threshold: 80
```

## Security

Security tools (OpenGrep, Trivy, Checkov) are language-agnostic. See the domain-specific sections in the [main documentation](../main.md) for details.

Trivy SCA scans these Go manifests: `go.sum`, `go.mod`.

## Duplication

Duplo scans `.go` files for duplicate code blocks.

```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 5.0
```

## Timeouts

| Tool | Timeout | Rationale |
|------|---------|-----------|
| golangci-lint | 300s | Runs many linters in parallel; large projects need headroom |
| go vet | 300s | Operates on packages; large module graphs can be slow |
| go test | 600s | Test suites can be inherently slow (integration tests, etc.) |
| gofmt | 120s | Pure formatting; fastest of the four |

## Prerequisites

- **Go 1.16+** required (for `go vet -json` output)
- **golangci-lint**: `go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest`
- **gofmt**, **go vet**, **go test**, **go cover** ship with Go (no separate installation)

## Example Configuration

```yaml
version: 1
project:
  languages: [go]
pipeline:
  linting:
    enabled: true
    tools:
      - name: golangci_lint
  formatting:
    enabled: true
    tools:
      - name: gofmt
  type_checking:
    enabled: true
    tools:
      - name: go_vet
  testing:
    enabled: true
    tools:
      - name: go_test
  coverage:
    enabled: true
    tools:
      - name: go_cover
    threshold: 80
  security:
    enabled: true
    tools:
      - { name: trivy, domains: [sca] }
      - { name: opengrep, domains: [sast] }
  duplication:
    enabled: true
    threshold: 5.0
```

## See Also

- [Supported Languages Overview](README.md)
