# Ignore Patterns in LucidShark

LucidShark supports multiple ways to exclude files and findings from your quality pipeline.

## File-Level Ignores

### .lucidsharkignore File

Create a `.lucidsharkignore` file in your project root with gitignore-style patterns:

```gitignore
# Dependencies
node_modules/
.venv/
vendor/

# Build output
dist/
build/
*.pyc
__pycache__/

# Test fixtures (but not tests themselves)
**/__fixtures__/
**/testdata/

# Generated files
*.generated.ts
*.min.js

# But keep important config
!vendor/config.yml
```

**Supported syntax:**

| Pattern | Description | Example |
|---------|-------------|---------|
| `*` | Match any characters except `/` | `*.log` matches `debug.log` |
| `**` | Match any directory depth | `**/test_*.py` matches files at any depth |
| `/` (trailing) | Match directories only | `vendor/` matches the vendor directory |
| `!` | Negate a pattern (re-include) | `!important.log` keeps the file |
| `#` | Comment line | `# This is ignored` |

LucidShark uses the [pathspec](https://pypi.org/project/pathspec/) library for full gitignore compliance.

### Config File Ignores

Add patterns to your config file (`.lucidshark.yml`, `.lucidshark.yaml`, `lucidshark.yml`, or `lucidshark.yaml`):

```yaml
ignore:
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/dist/**"
  - "*.md"
```

**Note:** Patterns from both `.lucidsharkignore` and your config file are merged, with `.lucidsharkignore` patterns applied first.

## How Ignore Patterns Work

LucidShark applies ignore patterns in two layers:

1. **Pre-filtering** -- When explicit file paths are provided, LucidShark filters them through the ignore patterns before passing them to any tool.
2. **Tool CLI flags** -- Ignore patterns are also passed to each tool using their native exclude mechanisms.

| Domain | Tool | How Ignores Are Passed |
|--------|------|------------------------|
| Linting | Ruff | `--extend-exclude` (preserves Ruff's built-in defaults like `.git`, `.venv`) |
| Linting | ESLint | `--ignore-pattern` |
| Linting | Biome | Relies on `biome.json` config; LucidShark does not pass patterns to CLI |
| Linting | Checkstyle | Pre-filtered by LucidShark via `ignore_patterns.matches()` per file |
| Type Checking | mypy | `--exclude` (glob patterns are converted to regex) |
| Type Checking | Pyright | Relies on `pyrightconfig.json` / `pyproject.toml`; no CLI exclude flags |
| Type Checking | TypeScript (tsc) | Relies on `tsconfig.json` `exclude` field |
| Type Checking | SpotBugs | Pre-filtered by LucidShark (only scans compiled class directories) |
| Security | Trivy | `--skip-dirs` (directory patterns), `--skip-files` (file patterns) |
| Security | OpenGrep | `--exclude` |
| Security | Checkov | `--skip-path` (glob patterns are converted to regex) |
| Testing | pytest | Full test suite runs by default; test discovery controlled by pytest config |
| Testing | Jest | Test discovery controlled by Jest config |
| Duplication | Duplo | Pre-filtered by LucidShark; always excludes `.git`, `node_modules`, `__pycache__`, `.venv`, `target`, `build`, `dist`, `.lucidshark` |

## Inline Ignores (Per-Finding)

Inline ignores suppress specific findings at the code level. These are handled natively by each tool.

### Linting

#### Ruff (Python)

Suppress a specific rule:

```python
x = 1  # noqa: E501
```

Suppress all rules on a line:

```python
x = 1  # noqa
```

Suppress for entire file (at top):

```python
# ruff: noqa: E501
```

#### ESLint (JavaScript/TypeScript)

Suppress next line:

```javascript
// eslint-disable-next-line no-console
console.log("debug");
```

Suppress specific rule on same line:

```javascript
console.log("debug"); // eslint-disable-line no-console
```

Suppress for block:

```javascript
/* eslint-disable no-console */
console.log("debug");
/* eslint-enable no-console */
```

#### Biome (JavaScript/TypeScript)

Suppress a specific rule on next line:

```javascript
// biome-ignore lint/suspicious/noExplicitAny: needed for legacy API
const data: any = fetchData();
```

Suppress for a block (wrap in `/* biome-ignore */`):

```javascript
/* biome-ignore lint/complexity/noForEach: performance not critical here */
items.forEach(item => process(item));
```

#### Checkstyle (Java)

Suppress a specific check via annotation:

```java
@SuppressWarnings("checkstyle:MagicNumber")
public int calculate() {
    return 42;
}
```

Suppress via inline comment (requires `SuppressionCommentFilter`):

```java
// CHECKSTYLE:OFF
int x = 42;
// CHECKSTYLE:ON
```

### Type Checking

#### mypy (Python)

Suppress on line:

```python
x: int = "hello"  # type: ignore
```

Suppress specific error:

```python
x: int = "hello"  # type: ignore[assignment]
```

#### Pyright (Python)

Suppress on line:

```python
x: int = "hello"  # pyright: ignore[reportAssignmentType]
```

Suppress all errors on a line:

```python
x: int = "hello"  # type: ignore
```

Note: Pyright also honors `# type: ignore` comments for compatibility with mypy.

#### TypeScript (tsc)

Suppress next line:

```typescript
// @ts-ignore
const x: number = "hello";
```

Suppress with reason (TS 3.9+, preferred):

```typescript
// @ts-expect-error: Legacy API returns string
const x: number = legacyApi();
```

#### SpotBugs (Java)

Suppress via annotation:

```java
@edu.umd.cs.findbugs.annotations.SuppressFBWarnings("NP_NULL_ON_SOME_PATH")
public void process() {
    // ...
}
```

Suppress with reason:

```java
@SuppressFBWarnings(value = "NP_NULL_ON_SOME_PATH", justification = "Null check done upstream")
public void process() {
    // ...
}
```

### Security

#### OpenGrep / Semgrep (SAST)

Suppress a specific rule:

```python
password = "hardcoded"  # nosemgrep: hardcoded-password
```

Suppress all rules on a line:

```python
eval(user_input)  # nosemgrep
```

#### Checkov (IaC)

Suppress with reason:

```hcl
resource "aws_s3_bucket" "example" {
  # checkov:skip=CKV_AWS_18:Access logging not required for this bucket
  bucket = "my-bucket"
}
```

Suppress multiple checks:

```yaml
# checkov:skip=CKV_K8S_1,CKV_K8S_2:Known issues to be fixed later
apiVersion: v1
kind: Pod
```

#### Trivy (SCA)

Trivy does not support inline ignores. Use a `.trivyignore` file:

```
# .trivyignore - List CVEs to ignore
CVE-2021-1234
CVE-2021-5678
```

### Testing

#### pytest (Python)

Skip a test:

```python
import pytest

@pytest.mark.skip(reason="Not implemented yet")
def test_feature():
    pass
```

Skip conditionally:

```python
@pytest.mark.skipif(sys.version_info < (3, 10), reason="Requires Python 3.10+")
def test_new_feature():
    pass
```

Expected failure:

```python
@pytest.mark.xfail(reason="Known bug #123")
def test_buggy_feature():
    pass
```

#### Jest (JavaScript/TypeScript)

Skip a test:

```javascript
test.skip('not implemented', () => {
  // ...
});
```

Skip describe block:

```javascript
describe.skip('feature', () => {
  // ...
});
```

#### Playwright (JavaScript/TypeScript)

Skip a test:

```javascript
test.skip('not ready', async ({ page }) => {
  // ...
});
```

Skip conditionally:

```javascript
test.skip(({ browserName }) => browserName === 'webkit', 'Not supported in WebKit');
```

#### Karma / Jasmine (JavaScript/TypeScript)

Skip a test:

```javascript
xit('not ready', () => {
  // ...
});
```

Skip a suite:

```javascript
xdescribe('feature', () => {
  // ...
});
```

#### Maven / JUnit (Java)

Skip a test:

```java
@Disabled("Not implemented yet")
@Test
void testFeature() {
    // ...
}
```

Skip conditionally (JUnit 5):

```java
@EnabledOnOs(OS.LINUX)
@Test
void testLinuxOnly() {
    // ...
}
```

## Domain-Specific Configuration

### Disable Entire Domains

```yaml
pipeline:
  linting:
    enabled: false  # Skip linting entirely
  type_checking:
    enabled: true
  security:
    enabled: true
  testing:
    enabled: true
  coverage:
    enabled: false  # Skip coverage checks
  duplication:
    enabled: false  # Skip duplication detection
```

### Tool-Specific Ignores

Some tools have their own ignore/config files that LucidShark respects:

| Tool | Ignore / Config File |
|------|----------------------|
| Ruff | `.ruff.toml`, `ruff.toml`, `pyproject.toml` (exclude section) |
| ESLint | `.eslintignore`, `eslint.config.js`, `eslint.config.mjs` |
| Biome | `biome.json`, `biome.jsonc` |
| Checkstyle | `checkstyle.xml`, `.checkstyle.xml`, `config/checkstyle/checkstyle.xml` |
| mypy | `mypy.ini`, `setup.cfg`, `pyproject.toml` (mypy section) |
| Pyright | `pyrightconfig.json`, `pyproject.toml` (pyright section) |
| TypeScript | `tsconfig.json` (exclude field) |
| SpotBugs | SpotBugs filter XML files |
| Trivy | `.trivyignore` |
| Checkov | `.checkov.yml` |
| pytest | `pytest.ini`, `pyproject.toml`, `setup.cfg` |
| Jest | `jest.config.js`, `jest.config.ts`, `package.json` (jest section) |

LucidShark does not override these -- they work alongside `.lucidsharkignore`.

## Best Practices

### Do Ignore

- **Dependencies**: `node_modules/`, `.venv/`, `vendor/`
- **Build output**: `dist/`, `build/`, `*.pyc`
- **Generated code**: `*.generated.ts`, `*.pb.go`
- **Test fixtures**: `**/__fixtures__/`, `**/testdata/`
- **IDE/editor files**: `.idea/`, `.vscode/` (usually in `.gitignore` already)

### Don't Ignore

- **Your application code** -- fix issues instead of ignoring
- **Configuration files** -- security issues here are real
- **Test files** -- keep `tests/` scanned for security issues
- **CI/CD files** -- `.github/`, `.gitlab-ci.yml` should be checked

### Inline Ignore Guidelines

1. **Always document the reason** when using inline ignores
2. **Prefer specific rule IDs** over blanket ignores
3. **Review inline ignores periodically** -- they may no longer be needed
4. **Use inline ignores sparingly** -- they are exceptions, not the norm

## Examples

### Python Project

`.lucidsharkignore`:

```gitignore
# Virtual environments
.venv/
venv/
env/

# Build artifacts
dist/
build/
*.egg-info/
*.pyc
__pycache__/

# Test fixtures
tests/fixtures/
**/conftest.py  # if you don't want conftest scanned

# Generated
*.pyi  # if generated
```

### JavaScript/TypeScript Project

`.lucidsharkignore`:

```gitignore
# Dependencies
node_modules/

# Build output
dist/
build/
.next/
out/

# Generated
*.d.ts  # if generated
coverage/

# Test fixtures
**/__mocks__/
**/__fixtures__/
```

### Java Project

`.lucidsharkignore`:

```gitignore
# Build output
target/
build/

# IDE files
.idea/
*.iml

# Generated sources
**/generated-sources/
**/generated-test-sources/
```

### Infrastructure Project

`.lucidsharkignore`:

```gitignore
# Example configurations
examples/
samples/

# Local development overrides
*.local.tf
*.tfvars  # if contains secrets (should be in .gitignore)

# Test fixtures
**/testdata/

# Generated
.terraform/
*.tfstate*
```

### Monorepo

`.lucidsharkignore`:

```gitignore
# Shared dependencies
node_modules/
**/node_modules/

# Build outputs
**/dist/
**/build/

# Per-package ignores can also be in each package's directory
```

## Troubleshooting

### Pattern Not Working

1. Check the pattern syntax -- use `**` for recursive matching
2. Verify the path is relative to project root
3. Run with `--debug` to see which files are being scanned
4. Check if the tool has its own ignore file overriding
5. Some tools convert patterns internally (mypy and Checkov convert globs to regex)

### Too Many Files Ignored

1. Check for overly broad patterns like `*` or `**/*`
2. Use `!` negation to re-include important files
3. Be specific: `tests/fixtures/` instead of `tests/`

### Inline Ignore Not Working

1. Verify the exact comment syntax for the tool
2. Check if the rule ID is correct
3. Some tools require the ignore on the same line, others on the line before
4. Biome uses `biome-ignore`, not `eslint-disable` -- check you are using the right syntax for your configured linter
