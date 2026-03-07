# JavaScript

**Support tier: Full**

JavaScript has full tool coverage in LucidShark across linting, testing, coverage, security, and duplication.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.js`, `.mjs`, `.cjs`, `.jsx` |
| **Marker files** | `package.json` |

## Tools by Domain

| Domain | Tool | Auto-Fix | Notes |
|--------|------|----------|-------|
| **Linting** | ESLint | Yes | Standard JS/TS linter |
| **Linting** | Biome | Yes | Fast alternative, also lints JSON |
| **Security (SAST)** | OpenGrep | -- | JavaScript-specific vulnerability rules |
| **Security (SCA)** | Trivy | -- | Scans `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |
| **Testing** | Jest | -- | JSON output, assertion extraction |
| **Testing** | Karma | -- | Angular projects |
| **Testing** | Playwright | -- | E2E browser testing |
| **Coverage** | Istanbul (NYC) | -- | Lines, statements, branches, functions |
| **Duplication** | Duplo | -- | Scans `.js` and `.jsx` files |

## Linting

**Tool: [ESLint](https://eslint.org/)**

The standard linter for JavaScript projects.

- Supports auto-fix
- Scans `.js`, `.jsx`, `.mjs`, `.cjs` files
- Requires ESLint installed in `node_modules`
- Configurable via `eslint.config.js`, `.eslintrc.*`, or `package.json`

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: eslint
```

**Tool: [Biome](https://biomejs.dev/)**

A fast alternative linter that supports JavaScript, TypeScript, and JSON.

- Supports auto-fix via `biome check --apply`
- No Node.js dependency -- standalone binary
- Also lints JSON files

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: biome
```

## Testing

**Tool: [Jest](https://jestjs.io/)**

The most popular JavaScript test runner.

- JSON output with per-test assertion results
- Failure message extraction
- Line number tracking

```yaml
pipeline:
  testing:
    enabled: true
    tools:
      - name: jest
```

**Tool: [Karma](https://karma-runner.github.io/)**

Test runner commonly used with Angular projects.

- Config detection: `karma.conf.js`, `karma.conf.ts`
- JSON reporter output
- Per-browser test results

**Tool: [Playwright](https://playwright.dev/)**

End-to-end browser testing framework.

- JSON reporter
- Multi-browser project support
- Extended timeout (900s) for E2E tests
- Flaky test detection

## Coverage

**Tool: [Istanbul (NYC)](https://istanbul.js.org/)**

Code coverage for JavaScript via the NYC CLI.

- Tracks lines, statements, branches, and functions
- Per-file coverage reporting
- Severity scaling based on threshold gap

```yaml
pipeline:
  coverage:
    enabled: true
    tools: [{ name: istanbul }]
    threshold: 80
```

## Security

Security tools (OpenGrep, Trivy, Checkov) are language-agnostic. See the domain-specific sections in the [main documentation](../main.md) for details.

Trivy SCA scans these JavaScript manifests: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`.

## Duplication

Duplo scans `.js` and `.jsx` files for duplicate code blocks.

```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 5.0
```

## Example Configuration

```yaml
version: 1
project:
  languages: [javascript]
pipeline:
  linting:
    enabled: true
    tools: [{ name: eslint }]
  security:
    enabled: true
    tools:
      - { name: trivy, domains: [sca] }
      - { name: opengrep, domains: [sast] }
  testing:
    enabled: true
    tools: [{ name: jest }]
  coverage:
    enabled: true
    tools: [{ name: istanbul }]
    threshold: 80
  duplication:
    enabled: true
    threshold: 5.0
```

## See Also

- [TypeScript](typescript.md) -- closely related language with type checking support
- [Supported Languages Overview](README.md)
