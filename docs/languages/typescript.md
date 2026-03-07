# TypeScript

**Support tier: Full**

TypeScript has full tool coverage in LucidShark across all six quality domains.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.ts`, `.tsx`, `.mts`, `.cts` |
| **Marker files** | `tsconfig.json` |
| **Version detection** | `typescript` version from `package.json` dependencies |

## Tools by Domain

| Domain | Tool | Auto-Fix | Notes |
|--------|------|----------|-------|
| **Linting** | ESLint | Yes | Standard JS/TS linter |
| **Linting** | Biome | Yes | Fast alternative to ESLint |
| **Type Checking** | tsc | -- | TypeScript compiler, strict mode via tsconfig |
| **Security (SAST)** | OpenGrep | -- | TypeScript-specific vulnerability rules |
| **Security (SCA)** | Trivy | -- | Scans `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |
| **Testing** | Jest | -- | JSON output, assertion extraction |
| **Testing** | Karma | -- | Angular projects |
| **Testing** | Playwright | -- | E2E browser testing |
| **Coverage** | Istanbul (NYC) | -- | Lines, statements, branches, functions |
| **Duplication** | Duplo | -- | Scans `.ts` and `.tsx` files |

## Linting

**Tool: [ESLint](https://eslint.org/)**

The standard linter for TypeScript projects.

- Supports auto-fix
- Scans `.ts`, `.tsx`, `.mts`, `.cts` files
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

A fast alternative linter that supports TypeScript, JavaScript, and JSON.

- Supports auto-fix via `biome check --apply`
- No Node.js dependency -- standalone binary
- Version-aware (supports 1.x and 2.x)

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: biome
```

## Type Checking

**Tool: [TypeScript Compiler (tsc)](https://www.typescriptlang.org/)**

Uses the TypeScript compiler in `--noEmit` mode for type checking.

- Strict mode configured via `tsconfig.json`
- Error codes in `TSXXXX` format
- Requires `tsconfig.json` in the project

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: typescript
        strict: true
```

## Testing

**Tool: [Jest](https://jestjs.io/)**

The most popular JavaScript/TypeScript test runner.

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

Code coverage for JavaScript/TypeScript via the NYC CLI.

- Tracks lines, statements, branches, and functions
- Per-file coverage reporting
- Severity scaling based on threshold gap
- Automatically fails if tests have failures or errors (prevents stale coverage data)

```yaml
pipeline:
  coverage:
    enabled: true
    tools: [{ name: istanbul }]
    threshold: 80
```

## Security

Security tools (OpenGrep, Trivy, Checkov) are language-agnostic. See the domain-specific sections in the [main documentation](../main.md) for details.

Trivy SCA scans these TypeScript/JavaScript manifests: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`.

## Duplication

Duplo scans `.ts` and `.tsx` files for duplicate code blocks.

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
  languages: [typescript]
pipeline:
  linting:
    enabled: true
    tools: [{ name: eslint }]
  type_checking:
    enabled: true
    tools: [{ name: typescript, strict: true }]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
  testing:
    enabled: true
    tools: [{ name: jest }]
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
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
```

### Minimal (linting + security only)

```yaml
version: 1
project:
  languages: [typescript]
pipeline:
  linting:
    enabled: true
    tools: [{ name: eslint }]
  type_checking:
    enabled: true
    tools: [{ name: typescript }]
  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]
exclude:
  - "**/node_modules/**"
  - "**/dist/**"
```

### With Biome instead of ESLint

```yaml
version: 1
project:
  languages: [typescript]
pipeline:
  linting:
    enabled: true
    tools: [{ name: biome }]
```

### With Playwright E2E tests

```yaml
version: 1
project:
  languages: [typescript]
pipeline:
  testing:
    enabled: true
    tools:
      - name: jest
      - name: playwright
```

## See Also

- [JavaScript](javascript.md) -- closely related language support
- [Supported Languages Overview](README.md)
