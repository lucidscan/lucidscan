# Ruby

**Support tier: Full**

Ruby projects are fully supported with linting, type checking, testing, coverage, formatting, security scanning, and duplication detection.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.rb`, `.rake`, `.gemspec` |
| **Marker files** | `Gemfile`, `Rakefile` |
| **Version detection** | `.ruby-version` file, `ruby` directive in `Gemfile` |

## Tools by Domain

| Domain | Tool | Notes |
|--------|------|-------|
| **Linting** | RuboCop | Static code analyzer with 400+ cops; supports auto-fix |
| **Formatting** | RuboCop Format | Uses RuboCop's Layout cops for formatting; supports auto-fix |
| **Type Checking** | Sorbet | Gradual type checker for Ruby; requires `sorbet/` directory |
| **Testing** | RSpec | BDD testing framework with JSON output |
| **Coverage** | SimpleCov | Parses `coverage/.resultset.json` produced by test runs |
| **Security (SAST)** | OpenGrep | Ruby-specific vulnerability rules |
| **Security (SCA)** | Trivy | Scans `Gemfile.lock` |
| **Duplication** | Duplo | Scans `.rb` files |

## Linting

**Tool: [RuboCop](https://rubocop.org/)**

RuboCop is a Ruby static code analyzer and formatter, based on the community Ruby style guide. It has 400+ cops across multiple departments.

- JSON output via `rubocop --format json`
- Supports auto-fix via `rubocop -a` (safe autocorrect)
- Configurable via `.rubocop.yml`
- Cop departments: Style, Layout, Lint, Metrics, Naming, Security, and more

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: rubocop
```

**Severity mapping:** Severity is determined by both the offense severity and cop department:

- **High** -- `error`/`fatal` severity, or `Security/*` department cops
- **Medium** -- `warning` severity, or `Lint/*` department cops
- **Low** -- `convention`/`refactor` severity, or `Layout/*`/`Style/*`/`Naming/*`/`Metrics/*` department cops

**Installation:** `gem install rubocop` or add `gem 'rubocop', require: false` to your Gemfile

## Formatting

**Tool: [RuboCop Format](https://docs.rubocop.org/rubocop/cops_layout.html)**

Uses RuboCop's Layout cops for format checking and auto-correction. This runs RuboCop with `--only Layout` to focus exclusively on formatting issues.

- Supports auto-fix (runs `rubocop -a --only Layout`)
- Check-only mode lists all Layout cop violations
- Uses the same `.rubocop.yml` configuration as the linter

```yaml
pipeline:
  formatting:
    enabled: true
    tools:
      - name: rubocop_format
```

## Type Checking

**Tool: [Sorbet](https://sorbet.org/)**

Sorbet is a fast, powerful type checker for Ruby developed by Stripe. It supports gradual typing, allowing you to add types incrementally.

- Requires `sorbet/` directory (run `srb init` to set up)
- Text output parsed from `srb tc`
- Supports strict mode via file-level annotations (`# typed: strict`)
- Error codes map to documentation at `https://srb.help/<code>`

**Severity mapping:** Based on Sorbet error code ranges:

- **High** -- resolver errors (2000-2999), type checking errors (6000-6999), type errors (7000-7999)
- **Medium** -- parse errors (1000-1999), namer errors (3000-3999), constant errors (4000-5999)

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: sorbet
```

**Installation:** `gem install sorbet sorbet-runtime` or add to your Gemfile:
```ruby
gem 'sorbet', group: :development
gem 'sorbet-runtime'
```

## Testing

**Tool: [RSpec](https://rspec.info/)**

RSpec is a BDD testing framework for Ruby. It provides expressive syntax for writing tests (specs).

- JSON output via `rspec --format json`
- Supports pending/skipped examples
- Failure details include exception class, message, and backtrace

```yaml
pipeline:
  testing:
    enabled: true
    tools:
      - name: rspec
```

**Installation:** `gem install rspec` or add `gem 'rspec', group: :test` to your Gemfile

## Coverage

**Tool: [SimpleCov](https://github.com/simplecov-ruby/simplecov)**

SimpleCov is a code coverage analysis tool for Ruby. It integrates with test runners (RSpec, Minitest) and generates coverage data automatically.

- Parses existing `coverage/.resultset.json` file
- Supports merging coverage from multiple test suites (RSpec + Minitest)
- No standalone binary needed -- configure SimpleCov in your test helper
- Returns error if no coverage data found (requires testing domain to run first)

> **Note:** SimpleCov must be configured in your test helper (`spec_helper.rb` or `test_helper.rb`). Add this to the top of the file:
> ```ruby
> require 'simplecov'
> SimpleCov.start
> ```

```yaml
pipeline:
  coverage:
    enabled: true
    tools:
      - name: simplecov
    threshold: 80
```

**Installation:** `gem install simplecov` or add `gem 'simplecov', group: :test` to your Gemfile

## Security

### SAST: OpenGrep (language-agnostic)

OpenGrep provides Ruby SAST coverage with auto-detected rule sets for common Ruby vulnerabilities including SQL injection, XSS, command injection, and insecure deserialization.

### SCA: Trivy

Trivy SCA scans Ruby manifests: `Gemfile.lock`.

See the domain-specific sections in the [main documentation](../main.md) for details on OpenGrep, Trivy, and Checkov.

## Duplication

Duplo scans `.rb` files for duplicate code blocks.

```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 5.0
```

## Timeouts

| Tool | Timeout | Rationale |
|------|---------|-----------|
| RuboCop (lint) | 120s | Standard linting timeout |
| RuboCop (format) | 120s | Layout-only cops; fast |
| Sorbet | 300s | Type checking large codebases can be slow |
| RSpec | 600s | Test suites can be inherently slow |

## Prerequisites

- **Ruby** (any recent version)
- **RuboCop**: `gem install rubocop`
- **Sorbet**: `gem install sorbet sorbet-runtime`, then `srb init`
- **RSpec**: `gem install rspec`
- **SimpleCov**: `gem install simplecov`, configure in test helper
- **OpenGrep**, **Trivy**, **Duplo**: Auto-downloaded by LucidShark

## Example Configuration

```yaml
version: 1
project:
  languages: [ruby]
pipeline:
  linting:
    enabled: true
    tools:
      - name: rubocop
  formatting:
    enabled: true
    tools:
      - name: rubocop_format
  type_checking:
    enabled: true
    tools:
      - name: sorbet
  testing:
    enabled: true
    tools:
      - name: rspec
  coverage:
    enabled: true
    tools:
      - name: simplecov
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
