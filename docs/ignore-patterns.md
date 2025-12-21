# Ignore Patterns in LucidScan

LucidScan supports multiple ways to exclude files and findings from scan results.

## File-Level Ignores

### .lucidscanignore File

Create a `.lucidscanignore` file in your project root with gitignore-style patterns:

```gitignore
# Ignore all log files
*.log

# Ignore test directories
tests/
**/test_*.py

# Ignore vendor/third-party code
vendor/
node_modules/

# But keep important vendor config
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

### Config File Ignores

Add patterns to `.lucidscan.yml`:

```yaml
ignore:
  - "tests/**"
  - "*.md"
  - "vendor/"
  - ".venv/**"
```

**Note:** Patterns from both `.lucidscanignore` and `config.ignore` are merged.

## How Ignore Patterns Work

When you specify ignore patterns, LucidScan passes them to each scanner using their native exclude mechanisms:

| Scanner | CLI Flag Used |
|---------|---------------|
| Trivy (SCA) | `--skip-dirs`, `--skip-files` |
| OpenGrep (SAST) | `--exclude` |
| Checkov (IaC) | `--skip-path` |

This approach ensures that scanners efficiently skip ignored paths during their internal file discovery.

## Inline Ignores (Per-Finding)

Inline ignores suppress specific findings at the code level. These are handled natively by each scanner.

### OpenGrep / Semgrep (SAST)

Suppress a specific rule:

```python
password = "hardcoded"  # nosemgrep: hardcoded-password
```

Suppress all rules on a line:

```python
eval(user_input)  # nosemgrep
```

### Checkov (IaC)

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

### Trivy (SCA)

Trivy does not support inline ignores. Use a `.trivyignore` file instead:

```
# .trivyignore - List CVEs to ignore
CVE-2021-1234
CVE-2021-5678
```

Or configure in `.lucidscan.yml`:

```yaml
scanners:
  sca:
    # Scanner-specific options
    ignore_unfixed: true
    severity:
      - CRITICAL
      - HIGH
```

## Best Practices

1. **Start with `.lucidscanignore`** for project-level exclusions (vendor, tests, generated code)
2. **Use inline ignores sparingly** and always document the reason
3. **Review ignore patterns periodically** to ensure they're still relevant
4. **Don't ignore security-critical code** - fix issues instead of suppressing them

## Examples

### Typical `.lucidscanignore` for a Node.js Project

```gitignore
# Dependencies
node_modules/

# Build output
dist/
build/

# Test fixtures
**/__fixtures__/
**/__mocks__/

# Generated files
*.min.js
*.bundle.js
```

### Typical `.lucidscanignore` for a Python Project

```gitignore
# Virtual environments
.venv/
venv/
env/

# Test directories
tests/
**/test_*.py

# Generated files
*.pyc
__pycache__/

# Documentation
docs/
```

### Typical `.lucidscanignore` for Infrastructure Code

```gitignore
# Example/sample configurations
examples/
samples/

# Test fixtures
**/testdata/

# Local development overrides
*.local.tf
```
