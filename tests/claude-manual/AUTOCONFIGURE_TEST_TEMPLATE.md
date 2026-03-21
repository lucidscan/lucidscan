# Autoconfiguration Testing Template

This template should be inserted into Phase 3 of all E2E test files after the `lucidshark init` tests.

---

## Phase 3.3: End-to-End Autoconfiguration Testing

**CRITICAL:** This phase tests the complete autoconfiguration workflow from detection to validation to execution. Do NOT skip steps or use pre-written configs. The goal is to verify that LucidShark can automatically configure itself for real-world projects.

### 3.3.1 Analyze Project Structure

**Objective:** Use the autoconfigure instructions to detect project characteristics.

#### Step 1: Call Autoconfigure MCP Tool
```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Mentions detecting the correct language(s) for this project
- [ ] Mentions detecting package managers (package.json, pyproject.toml, Cargo.toml, go.mod, pom.xml, etc.)
- [ ] Mentions detecting test frameworks
- [ ] Mentions detecting linters/type checkers
- [ ] Includes example configs relevant to the detected language
- [ ] Includes common exclusion patterns

#### Step 2: Detect Package Manager and Language

**For Python projects:**
```bash
ls -la pyproject.toml setup.py requirements.txt 2>/dev/null
cat pyproject.toml | head -20  # Check for [tool.pytest], [tool.ruff], etc.
```

**For JavaScript/TypeScript projects:**
```bash
ls -la package.json tsconfig.json 2>/dev/null
cat package.json | jq '.scripts' | grep -i test
cat package.json | jq '.devDependencies' | grep -i 'jest\|mocha\|vitest\|karma\|playwright'
```

**For Java projects:**
```bash
ls -la pom.xml build.gradle 2>/dev/null
cat pom.xml | grep -A 5 '<plugin>' | grep -i 'jacoco\|checkstyle\|pmd\|spotbugs'
```

**For Go projects:**
```bash
ls -la go.mod 2>/dev/null
cat go.mod | head -10
```

**For Rust projects:**
```bash
ls -la Cargo.toml 2>/dev/null
cat Cargo.toml | grep -A 3 '\[dev-dependencies\]'
```

**Record findings:**
- [ ] Detected language(s): _______________
- [ ] Package manager: _______________
- [ ] Existing tool configs found: _______________

#### Step 3: Detect Test Framework

**For Python:**
```bash
ls -la pytest.ini conftest.py .pytest_cache 2>/dev/null
cat pyproject.toml | grep -A 5 '\[tool.pytest\]'
```

**For JavaScript/TypeScript:**
```bash
ls -la jest.config.* vitest.config.* karma.conf.* playwright.config.* .mocharc.* 2>/dev/null
cat package.json | jq '.scripts.test'
```

**For Java:**
```bash
find src/test -name '*Test.java' -o -name '*IT.java' 2>/dev/null | head -5
cat pom.xml | grep -i 'maven-surefire-plugin\|junit'
```

**For Go:**
```bash
find . -name '*_test.go' 2>/dev/null | head -5
```

**For Rust:**
```bash
find . -name '*.rs' -exec grep -l '#\[test\]' {} \; 2>/dev/null | head -5
```

**Record findings:**
- [ ] Test framework detected: _______________
- [ ] Test file pattern: _______________
- [ ] Coverage tool available: _______________

#### Step 4: Detect Linters and Type Checkers

**For Python:**
```bash
cat pyproject.toml | grep -E '\[tool\.(ruff|flake8|mypy|pyright)\]'
ls -la .flake8 mypy.ini pyrightconfig.json 2>/dev/null
```

**For JavaScript/TypeScript:**
```bash
ls -la .eslintrc* eslint.config.js biome.json tsconfig.json 2>/dev/null
cat package.json | jq '.devDependencies' | grep -i 'eslint\|biome\|typescript'
```

**For Java:**
```bash
ls -la checkstyle.xml pmd.xml spotbugs.xml 2>/dev/null
cat pom.xml | grep -i 'checkstyle\|pmd\|spotbugs'
```

**For Go:**
```bash
which golangci-lint
ls -la .golangci.yml 2>/dev/null
```

**For Rust:**
```bash
which cargo-clippy
cargo --list | grep clippy
```

**Record findings:**
- [ ] Linter detected: _______________
- [ ] Type checker detected: _______________
- [ ] Linter config file: _______________

#### Step 5: Identify Project-Specific Exclusions

Examine the directory structure to find generated code, build artifacts, dependencies, etc. that should be excluded:

```bash
tree -L 2 -d -I 'node_modules|.git' . 2>/dev/null | head -30
# OR
find . -maxdepth 2 -type d ! -path '*/\.*' ! -path '*/node_modules/*' 2>/dev/null | head -30
```

Look for:
- [ ] Build output directories (dist/, build/, target/, out/, bin/, obj/)
- [ ] Dependency directories (node_modules/, vendor/, .venv/, venv/)
- [ ] Generated code directories (generated/, codegen/, *_pb2.py, *.generated.ts)
- [ ] Cache directories (__pycache__/, .pytest_cache/, .ruff_cache/, .gradle/)
- [ ] Documentation build output (docs/_build/, site/, .docusaurus/)
- [ ] IDE directories (.idea/, .vscode/, .vs/)
- [ ] Data/fixture directories (data/, fixtures/, testdata/)

**Record exclusions needed:** _______________

### 3.3.2 Generate lucidshark.yml

**IMPORTANT:** Do NOT copy-paste a template. Generate the config based on the ACTUAL tools detected in 3.3.1.

#### Step 1: Check Current Tool Installation

**For Python:**
```bash
pip list | grep -iE '^(ruff|mypy|pyright|pytest|coverage) '
```

**For JavaScript/TypeScript:**
```bash
npm list eslint typescript jest vitest mocha 2>/dev/null | grep -v 'UNMET'
```

**For Java:**
```bash
cat pom.xml | grep -E '<artifactId>(checkstyle|jacoco|pmd|spotbugs)'
```

**Record which tools need installation:** _______________

#### Step 2: Install Missing Tools (CRITICAL STEP)

This step is often skipped but is ESSENTIAL for end-to-end testing.

**For Python:**
```bash
pip install ruff mypy pytest pytest-cov coverage
# Verify installation
pip list | grep -iE '^(ruff|mypy|pytest|coverage) '
```

**For JavaScript/TypeScript:**
```bash
npm install --save-dev eslint typescript @typescript-eslint/parser @typescript-eslint/eslint-plugin
# For projects with Jest
npm install --save-dev jest @types/jest
# For projects with Mocha
npm install --save-dev mocha @types/mocha
# For projects with Vitest
npm install --save-dev vitest
# Verify installation
npm list eslint typescript jest 2>/dev/null | grep -v 'UNMET'
```

**For Java:**
Verify plugins in pom.xml or build.gradle. If missing, add them.

**For Rust:**
```bash
rustup component add clippy
cargo install cargo-tarpaulin
```

**For Go:**
```bash
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
which golangci-lint
```

**Verify:**
- [ ] All required tools are now installed
- [ ] Tools are available in PATH or project dependencies

#### Step 3: Write lucidshark.yml Based on Detection

Using the findings from 3.3.1, create a lucidshark.yml that:
1. Enables domains ONLY for tools that were detected/installed
2. Uses the correct tool names for this project
3. Includes appropriate excludes for this project type
4. Sets reasonable thresholds (coverage: 80% for new projects, 50% for legacy; duplication: 5%)
5. Sets appropriate fail_on levels

**Example for Python project with pytest, ruff, mypy:**
```yaml
version: 1

project:
  name: <project-name>
  languages: [python]

pipeline:
  linting:
    enabled: true
    tools: [ruff]

  type_checking:
    enabled: true
    tools: [mypy]

  testing:
    enabled: true
    tools: [pytest]

  coverage:
    enabled: true
    tools: [coverage_py]
    threshold: 80

  duplication:
    enabled: true
    tools: [duplo]
    threshold: 5.0
    min_lines: 7

  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]

fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/.venv/**"
  - "**/venv/**"
  - "**/__pycache__/**"
  - "**/*.egg-info/**"
  - "**/.pytest_cache/**"
  - "**/.ruff_cache/**"
  - "**/.mypy_cache/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/htmlcov/**"
```

**Example for TypeScript project with Jest, ESLint:**
```yaml
version: 1

project:
  name: <project-name>
  languages: [typescript, javascript]

pipeline:
  linting:
    enabled: true
    tools: [eslint]

  type_checking:
    enabled: true
    tools: [typescript]

  testing:
    enabled: true
    tools: [jest]

  coverage:
    enabled: true
    tools: [istanbul]
    threshold: 80

  duplication:
    enabled: true
    tools: [duplo]
    threshold: 5.0
    min_lines: 7

  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: opengrep
        domains: [sast]

fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
  - "**/.next/**"
```

**Write the config:**
```bash
cat > lucidshark.yml << 'EOF'
<paste generated config here>
EOF
```

### 3.3.3 Validate the Generated Configuration

#### Via CLI:
```bash
./lucidshark validate
echo "Exit code: $?"
cat lucidshark.yml
```

**Verify:**
- [ ] Exit code 0 (config is valid)
- [ ] No validation errors
- [ ] Warnings (if any) are documented

**If validation fails:**
- [ ] Record the error message
- [ ] Fix the config based on error
- [ ] Re-validate until exit code is 0

#### Via MCP:
```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Returns "valid": true or similar success indicator
- [ ] Shows parsed configuration
- [ ] Lists enabled domains
- [ ] Lists configured tools

**If validation fails:**
- [ ] Record the MCP error response
- [ ] Fix the config
- [ ] Re-validate

### 3.3.4 Test Generated Config with Real Scans

**CRITICAL:** This step verifies that the generated config actually works in practice.

#### Test 1: Linting Scan
```bash
./lucidshark scan --linting --format ai
```

**Verify:**
- [ ] Scan executes without crashes
- [ ] Uses the tool specified in lucidshark.yml (check output for tool name)
- [ ] Returns issues (or passes if code is clean)
- [ ] Output includes domain_status with "linting" status
- [ ] Does NOT scan excluded directories (check that node_modules/.venv not in file paths)

#### Test 2: Type Checking Scan
```bash
./lucidshark scan --type-checking --format ai
```

**Verify:**
- [ ] Scan executes without crashes
- [ ] Uses the tool specified in lucidshark.yml
- [ ] Returns type errors (or passes)
- [ ] Output includes domain_status with "type_checking" status

#### Test 3: Testing Scan
```bash
./lucidshark scan --testing --format ai
```

**Verify:**
- [ ] Scan executes without crashes
- [ ] Runs the test framework specified in lucidshark.yml (Jest/Mocha/Vitest/pytest/etc.)
- [ ] Output shows test results
- [ ] If tests fail, blocking is set correctly based on fail_on.testing

#### Test 4: Coverage Scan (with Testing)
```bash
rm -rf coverage .coverage htmlcov  # Clean previous coverage
./lucidshark scan --testing --coverage --format ai
```

**Verify:**
- [ ] Coverage is generated
- [ ] Coverage percentage is reported
- [ ] If coverage < threshold, scan is blocking (fail_on.coverage: any)
- [ ] Coverage files created on disk (.coverage, coverage.xml, htmlcov/, etc.)

#### Test 5: Test Exclusion Patterns
```bash
./lucidshark scan --duplication --all-files --format ai 2>&1 | grep -i 'node_modules\|\.venv\|__pycache__'
echo "Excluded directories in output: $?"
```

**Verify:**
- [ ] Exit code 1 (no excluded directories found in output)
- [ ] Duplication scan did NOT analyze node_modules, .venv, __pycache__, etc.
- [ ] Only scanned files in src/, lib/, app/, etc. (actual source code)

**Alternative verification:**
```bash
./lucidshark scan --duplication --all-files --debug 2>&1 | tee /tmp/scan-debug.log
grep -c 'node_modules' /tmp/scan-debug.log
grep -c '\.venv' /tmp/scan-debug.log
```

Should show 0 or minimal mentions, not hundreds of files.

#### Test 6: Full Scan with Generated Config
```bash
./lucidshark scan --all --all-files --format ai > /tmp/full-scan-result.json
cat /tmp/full-scan-result.json | jq '.domain_status'
```

**Verify:**
- [ ] All configured domains execute (linting, type_checking, testing, coverage, duplication, security)
- [ ] Each domain status is reported (pass/fail/skipped)
- [ ] Total issue count matches sum of domain issue counts
- [ ] No crashes or errors
- [ ] Scan completes in reasonable time (document time for future comparison)

#### Test 7: Threshold Enforcement

**Test coverage threshold:**

Option A: If current coverage is ABOVE threshold (e.g., 85% > 80%):
```bash
# Temporarily lower threshold to cause failure
cp lucidshark.yml lucidshark.yml.backup
sed -i.bak 's/threshold: 80/threshold: 95/' lucidshark.yml
./lucidshark scan --testing --coverage --format ai
echo "Exit code: $?"
# Should be non-zero (failure) because coverage < 95%
# Restore
mv lucidshark.yml.backup lucidshark.yml
```

Option B: If current coverage is BELOW threshold (e.g., 60% < 80%):
```bash
./lucidshark scan --testing --coverage --format ai
echo "Exit code: $?"
# Should be non-zero (failure) because coverage < threshold
```

**Verify:**
- [ ] Scan fails when coverage < threshold
- [ ] Error message mentions coverage threshold
- [ ] blocking field is true in output

**Test duplication threshold:**
```bash
# Run duplication scan
./lucidshark scan --duplication --all-files --format ai > /tmp/dup-result.json
cat /tmp/dup-result.json | jq '.domain_status.duplication'
```

**Verify:**
- [ ] If duplication > threshold (5%), scan fails
- [ ] If duplication < threshold, scan passes
- [ ] Duplication percentage is reported

### 3.3.5 Test Autoconfigure on Each Real-World Project

**CRITICAL:** Repeat the entire autoconfiguration process (3.3.1 through 3.3.4) for EACH real-world project cloned in Phase 2.

For example, if testing JavaScript:
- Repeat for axios project (Vitest)
- Repeat for zustand project (Vitest)
- Repeat for sinon project (Mocha)
- Repeat for any other projects

**For EACH project, verify:**
- [ ] Autoconfigure detects the CORRECT test framework (Vitest for axios, Mocha for sinon, etc.)
- [ ] Generated lucidshark.yml includes the correct tools
- [ ] Generated config validates successfully
- [ ] Scans work with the generated config
- [ ] Exclusions are appropriate for the project structure

**Common mistakes to catch:**
- ❌ Generated config for axios should use Vitest, NOT Jest
- ❌ Generated config for sinon should use Mocha, NOT Jest
- ❌ Generated config should NOT enable coverage if no coverage tool detected
- ❌ Generated config should NOT include tools that aren't installed

### 3.3.6 Document Autoconfiguration Results

For each project, record:

| Project | Detected Language | Detected Test Framework | Detected Linter | Detected Type Checker | Config Valid? | Scans Pass? | Notes |
|---------|-------------------|-------------------------|-----------------|----------------------|---------------|-------------|-------|
| test-project | | | | | | | |
| axios | | | | | | | |
| zustand | | | | | | | |
| sinon | | | | | | | |

**Final Autoconfiguration Test Verdict:**
- [ ] PASS: Autoconfigure correctly detected tools in all projects
- [ ] PASS: Generated configs validated successfully
- [ ] PASS: Scans executed successfully with generated configs
- [ ] PASS: Exclusions prevented scanning of non-source directories
- [ ] PASS: Thresholds enforced correctly

OR

- [ ] FAIL: <describe what failed>

---

## INSTRUCTIONS FOR TEST EXECUTION

1. **Do NOT skip steps** - Each step builds on the previous one
2. **Do NOT use pre-written configs** - The point is to TEST autoconfiguration, not copy-paste templates
3. **Do install missing tools** - This is part of the autoconfiguration workflow
4. **Do verify actual behavior** - Don't assume it works, verify the output
5. **Do test on multiple projects** - Each project may have different tools/configs
6. **Do document failures** - If something doesn't work, record exactly what failed

## COMMON MISTAKES TO AVOID

1. ❌ Calling `mcp__lucidshark__autoconfigure()` but not following the instructions
2. ❌ Writing a lucidshark.yml without detecting what tools are actually installed
3. ❌ Skipping validation
4. ❌ Not running scans with the generated config
5. ❌ Not testing that excludes work
6. ❌ Not testing that thresholds work
7. ❌ Only testing on one project (the test-project) and not real-world projects
8. ❌ Using the same config for all projects (each should be auto-configured separately)
