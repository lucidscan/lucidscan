# LucidShark Python Support — End-to-End Test Instructions

## 🚨🚨🚨 CRITICAL INSTALLATION REQUIREMENT 🚨🚨🚨

**YOU MUST TEST THE LOCAL DEVELOPMENT VERSION, NOT THE PUBLISHED VERSION!**

**USE THE UNIVERSAL SETUP SCRIPT:**
```bash
/Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual/setup-test-installation.sh <project-path>
```

This script is the **SOURCE OF TRUTH** for all E2E tests. It automatically:
- ✅ Builds PyInstaller binary from local source
- ✅ Installs lucidshark from local source in editable mode
- ✅ Verifies ALL versions match your local development version
- ✅ Fails if testing wrong version (e.g., 0.6.4 from PyPI instead of 0.6.5 local)

**See `tests/claude-manual/README.md` for details and `TEST_GO_E2E.md` Phase 2.3 for usage examples.**

---

## 🚨 CRITICAL TESTING PHILOSOPHY 🚨

**YOU ARE A QUALITY ASSURANCE ENGINEER, NOT A CHEERLEADER.**

Your job is to **FIND BUGS**, not to confirm that things work. Approach every test with skepticism and rigor:

### Non-Negotiable Testing Rules

1. **EXECUTE EVERY SINGLE STEP** - No exceptions. No shortcuts. No "I think this will work so I'll skip it."
   - If a step says run a command, YOU RUN THAT COMMAND.
   - If a step says verify something, YOU VERIFY IT THOROUGHLY.
   - If you skip a step, you have FAILED this test.

2. **TRY TO BREAK THINGS** - Your goal is to find edge cases, bugs, and failures:
   - What happens with malformed input?
   - What happens when things fail?
   - What happens with empty files, large files, Unicode?
   - What happens when tools are missing?
   - Does the error handling actually work?

3. **BE DEEPLY SKEPTICAL** - Question everything:
   - Does the output actually make sense or is it just non-error output?
   - Are line numbers correct? Are file paths correct?
   - Do counts add up? (e.g., if metadata says 10 issues, are there actually 10?)
   - Does auto-fix actually fix things or does it break them?
   - Are JSON outputs valid? Are they complete?

4. **DOCUMENT EVERYTHING IN EXTREME DETAIL** - Other engineers must reproduce your findings:
   - Exact commands run
   - Complete output (not just "it worked")
   - Exit codes
   - Timing information
   - File changes (before/after)
   - Any discrepancies, no matter how small

5. **IF SOMETHING SEEMS OFF, INVESTIGATE RUTHLESSLY** - Don't make excuses:
   - "It probably works" → NO. Test it.
   - "That's expected" → Prove it. Document why.
   - "Close enough" → NO. Either it's correct or it's a bug.
   - "It timed out" → Why? Debug it. Make it work.

6. **COMPARE ACTUAL VS EXPECTED** - For every verification:
   - State what you EXPECTED to happen
   - State what ACTUALLY happened
   - If they don't match EXACTLY, it's a finding (bug, UX issue, or documentation gap)

7. **NO PARTIAL CREDIT** - Either you completed the test or you didn't:
   - "I ran most of the tests" = INCOMPLETE
   - "I skipped SCA because it seemed slow" = FAILED
   - "I didn't test MCP because context" = FAILED
   - Report must say "ALL TESTS COMPLETE" or list exactly what's missing and why

### What This Means in Practice

**BAD Testing:**
- ❌ "The scan worked" → Too vague. What did it find? Was it correct?
- ❌ "SCA seems to timeout, moving on" → You gave up. Investigate.
- ❌ "MCP tools will be tested later" → No. Test them NOW.
- ❌ "I found 9 linting issues" → Were they the RIGHT issues? Did you verify each one?

**GOOD Testing:**
- ✅ "SCA scan completed in 9.033 seconds, found exactly 28 CVEs (1 critical, 9 high, 14 medium, 4 low). Verified CVE-2025-50181 for urllib3 with CVSS score 6.1. All CVEs have complete metadata including fix versions and references."
- ✅ "apply_fix removed all 6 F401 unused import issues from main.py. Verified file diff shows removed lines: os, sys, json, subprocess, Optional, List. Type error and unused variable issues remain (expected - not fixable by ruff)."
- ✅ "Line numbers appear as 'None' in CLI JSON output but show correctly in MCP output. This is ISSUE-001, severity Moderate, reproducible 100%."

### Your Mission

You are performing a comprehensive end-to-end test of LucidShark's Python support. You will test both the CLI and MCP interfaces across all domains, using real open-source Python projects checked out from GitHub. You will test installation via both the install script and pip, run `lucidshark init`, `autoconfigure`, and exercise every scan domain and MCP tool.

**SUCCESS CRITERIA:**
- ✅ Every step executed and documented
- ✅ Every bug found and reported with reproduction steps
- ✅ Every discrepancy investigated and explained
- ✅ Detailed test report with actual data, not summaries
- ✅ Clear verdict: PASS (ready for production) or FAIL (blocking issues found)

**FAILURE CRITERIA:**
- ❌ Any step skipped without documented reason
- ❌ Any "seems to work" or "probably correct" statements
- ❌ Any bugs found but not thoroughly documented
- ❌ Test report with vague summaries instead of concrete data

At the end, write a detailed test report that another engineer could use to reproduce your findings.

---

## Phase 0: Environment Setup

### 0.1 Record Environment Info

```bash
uname -a
python3 --version
pip3 --version
node --version 2>/dev/null || echo "Node.js not installed"
git --version
echo "Disk space:" && df -h .
echo "Working directory:" && pwd
```

Record all output in the test report under "Environment".

### 0.2 Create Clean Test Workspace

```bash
export TEST_WORKSPACE="/tmp/lucidshark-python-e2e-$(date +%s)"
mkdir -p "$TEST_WORKSPACE"
cd "$TEST_WORKSPACE"
echo "Test workspace created at: $TEST_WORKSPACE"
```

**📁 IMPORTANT: Workspace Isolation**

All subsequent work happens inside `$TEST_WORKSPACE`. Do NOT use any pre-existing LucidShark installation.

**Everything runs in the `/tmp` folder:**
- All real-world projects are cloned to: `$TEST_WORKSPACE/<project-name>/`
- The artificial test project is created at: `$TEST_WORKSPACE/test-project/`
- Installation tests happen in: `$TEST_WORKSPACE/install-*/`
- **Nothing touches your actual workspace or home directory**
- The entire test environment is isolated and can be safely deleted after testing

---

## Phase 1: Installation Testing

### 1.1 Install via install.sh (Binary)

```bash
cd "$TEST_WORKSPACE"
mkdir install-script-test && cd install-script-test
git init  # install.sh expects to be in a project root
curl -fsSL https://raw.githubusercontent.com/toniantunovi/lucidshark/main/install.sh | bash
```

**Verify:**
- [ ] Binary downloaded successfully to `./lucidshark`
- [ ] `./lucidshark --version` outputs a version string
- [ ] `./lucidshark --help` shows help text with all subcommands (scan, init, status, doctor, help, validate, overview, serve)
- [ ] `./lucidshark status` runs without error
- [ ] `./lucidshark doctor` runs and shows tool availability

Record the version number and which tools `doctor` reports as available/missing.

### 1.2 Install via install.sh with Specific Version

```bash
cd "$TEST_WORKSPACE"
mkdir install-version-test && cd install-version-test
git init
curl -fsSL https://raw.githubusercontent.com/toniantunovi/lucidshark/main/install.sh | bash -s -- --version v0.5.63
```

**Verify:**
- [ ] Correct version installed (check `./lucidshark --version`)
- [ ] The binary works (`./lucidshark status`)


---

## Phase 2: Test Project Setup

### 2.1 Clone Test Projects from GitHub

Clone these real-world Python projects. Each serves a different test purpose:

```bash
cd "$TEST_WORKSPACE"

# Project 1: Flask — well-maintained, clean code, good test suite
git clone --depth 1 https://github.com/pallets/flask.git

# Project 2: httpx — modern Python, type-annotated, async code
git clone --depth 1 https://github.com/encode/httpx.git

# Project 3: FastAPI — heavily typed, Pydantic models, complex deps
git clone --depth 1 https://github.com/fastapi/fastapi.git

# Project 4: Sanic — async web framework, different structure
git clone --depth 1 https://github.com/sanic-org/sanic.git
```

**Verify all projects cloned successfully:**
```bash
ls -la "$TEST_WORKSPACE"
echo ""
echo "Expected directories:"
echo "  - flask/"
echo "  - httpx/"
echo "  - fastapi/"
echo "  - sanic/"
```

**Verify:**
- [ ] All four project directories exist in `$TEST_WORKSPACE`
- [ ] Each directory contains a git repository (`.git/` folder)
- [ ] Each directory is inside `/tmp/lucidshark-python-e2e-*/`

### 2.2 Create Custom Vulnerable Test Project

This project has intentional issues across ALL domains for comprehensive testing:

```bash
mkdir -p "$TEST_WORKSPACE/test-project/src/myapp"
mkdir -p "$TEST_WORKSPACE/test-project/tests"
cd "$TEST_WORKSPACE/test-project"
git init
```

**Create `src/myapp/__init__.py`:**
```python
"""MyApp - intentionally flawed for testing."""
__version__ = "0.1.0"
```

**Create `src/myapp/main.py`** (linting + formatting + type errors):
```python
import os
import sys
import json
import subprocess
from typing import Optional, List, Dict

def process_data(  data: str  ) -> str:
    x: str = 123  # type error
    unused_var = "never used"  # unused variable
    result = data.upper(  )
    return 42  # wrong return type

def    badly_formatted(   a,b,c   ):
    if(a):
        return b
    else:
            return c

class UserManager:
    def __init__(self):
        self.users: Dict[str, str] = {}

    def add_user(self, name: str, age: int) -> None:
        self.users[name] = age  # type error: int assigned to str value
```

**Create `src/myapp/security.py`** (SAST issues):
```python
import os
import pickle
import hashlib
import sqlite3
import subprocess

# SQL Injection
def get_user(db_path: str, username: str) -> dict:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE name = '" + username + "'")
    return cursor.fetchone()

# Command Injection
def run_command(user_input: str) -> str:
    result = subprocess.run(user_input, shell=True, capture_output=True)
    return result.stdout.decode()

# Also via os.system
def run_system(cmd: str) -> None:
    os.system(cmd)

# Insecure Deserialization
def load_data(data: bytes) -> object:
    return pickle.loads(data)

# Weak Crypto
def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()

# Hardcoded Secrets
API_KEY = "sk-1234567890abcdef1234567890abcdef"
DATABASE_PASSWORD = "super_secret_password_123"

# Path Traversal
def read_file(base_dir: str, filename: str) -> str:
    filepath = base_dir + "/" + filename
    with open(filepath) as f:
        return f.read()

# Eval
def evaluate(expression: str) -> object:
    return eval(expression)
```

**Create `src/myapp/duplicate1.py`** (duplication detection):
```python
def calculate_statistics(numbers: list) -> dict:
    total = sum(numbers)
    count = len(numbers)
    if count == 0:
        return {"mean": 0, "total": 0, "count": 0, "min": 0, "max": 0}
    mean = total / count
    minimum = min(numbers)
    maximum = max(numbers)
    variance = sum((x - mean) ** 2 for x in numbers) / count
    std_dev = variance ** 0.5
    return {
        "mean": mean,
        "total": total,
        "count": count,
        "min": minimum,
        "max": maximum,
        "variance": variance,
        "std_dev": std_dev,
    }
```

**Create `src/myapp/duplicate2.py`** (near-duplicate of duplicate1.py):
```python
def compute_statistics(values: list) -> dict:
    total = sum(values)
    count = len(values)
    if count == 0:
        return {"mean": 0, "total": 0, "count": 0, "min": 0, "max": 0}
    mean = total / count
    minimum = min(values)
    maximum = max(values)
    variance = sum((x - mean) ** 2 for x in values) / count
    std_dev = variance ** 0.5
    return {
        "mean": mean,
        "total": total,
        "count": count,
        "min": minimum,
        "max": maximum,
        "variance": variance,
        "std_dev": std_dev,
    }
```

**Create `tests/test_main.py`:**
```python
from myapp.main import process_data, badly_formatted, UserManager

def test_process_data():
    # This will fail because process_data returns 42, not a string
    result = process_data("hello")
    assert result == "HELLO"

def test_badly_formatted():
    assert badly_formatted(True, 1, 2) == 1
    assert badly_formatted(False, 1, 2) == 2

def test_user_manager():
    mgr = UserManager()
    mgr.add_user("alice", 30)
    assert "alice" in mgr.users

def test_passing_1():
    assert 1 + 1 == 2

def test_passing_2():
    assert "hello".upper() == "HELLO"
```

**Create `requirements.txt`** (with known vulnerable packages):
```
flask==2.0.0
requests==2.25.0
pyyaml==5.3.1
jinja2==3.0.0
urllib3==1.26.4
cryptography==3.3.2
```

**Create `pyproject.toml`:**
```toml
[project]
name = "test-project"
version = "0.1.0"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

**Create `setup.py`:**
```python
from setuptools import setup, find_packages
setup(
    name="test-project",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
)
```

Commit everything:
```bash
cd "$TEST_WORKSPACE/test-project"
git add -A && git commit -m "Initial commit with intentional issues"
```

### 2.3 Install LucidShark in Test Project Using Setup Script

**🚨 CRITICAL: Use the Universal Setup Script**

All E2E tests (Python, Java, JavaScript, Go, etc.) MUST use the universal setup script located at:
`/Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual/setup-test-installation.sh`

This script is the **SOURCE OF TRUTH** for E2E test installations. It ensures deterministic, reproducible installations across all language tests.

#### 2.3.1 Run the Setup Script

```bash
cd /Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual
./setup-test-installation.sh "$TEST_WORKSPACE/test-project"
```

**What the script does:**
1. Builds PyInstaller binary from local source (cached in /tmp for speed)
2. Copies binary to `$TEST_WORKSPACE/test-project/lucidshark`
3. Creates venv at `$TEST_WORKSPACE/test-project/.venv`
4. Installs lucidshark from local source in editable mode
5. Verifies ALL versions match the local development version

**Expected output:**
```
[INFO] LucidShark E2E Test Installation Setup
[INFO] ========================================
[INFO] Local development version: 0.6.X
[SUCCESS] Binary verified: version 0.6.X
[SUCCESS] Binary copied to .../test-project/lucidshark (version 0.6.X)
[SUCCESS] Pip installation verified: version 0.6.X
[SUCCESS] ✅ All versions match! Installation successful.
```

**Verify:**
- [ ] Script completes without errors
- [ ] All three versions (local, binary, pip) match
- [ ] Binary exists at `$TEST_WORKSPACE/test-project/lucidshark`
- [ ] Venv exists at `$TEST_WORKSPACE/test-project/.venv`

**If the script fails:** DO NOT PROCEED. Debug and fix the installation issue first.

---

## Phase 3: Init & Configuration Testing

### 3.1 Test `lucidshark init` on Test Project

```bash
cd "$TEST_WORKSPACE/test-project"
```

#### 3.1.1 Init Dry Run
```bash
./lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files WOULD be created without creating them
- [ ] Lists: `.mcp.json`, `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/skills/lucidshark/SKILL.md`
- [ ] No files actually created (check with `ls -la .mcp.json .claude/ 2>/dev/null`)

#### 3.1.2 Init (Full)
```bash
./lucidshark init
```

**Verify:**
- [ ] `.mcp.json` created with correct MCP server config
- [ ] `.claude/CLAUDE.md` created with lucidshark instructions (check for `<!-- lucidshark:start -->` markers)
- [ ] `.claude/settings.json` created with PostToolUse hooks
- [ ] `.claude/skills/lucidshark/SKILL.md` created
- [ ] Read each file and verify contents are sensible

```bash
cat .mcp.json
cat .claude/CLAUDE.md
cat .claude/settings.json
cat .claude/skills/lucidshark/SKILL.md
```

#### 3.1.3 Init Re-run (Should Detect Existing)
```bash
./lucidshark init
```

**Verify:**
- [ ] Detects existing configuration
- [ ] Suggests `--force` to overwrite
- [ ] Does NOT overwrite existing files

#### 3.1.4 Init Force
```bash
./lucidshark init --force
```

**Verify:**
- [ ] Overwrites all files successfully
- [ ] Files are identical or updated versions

#### 3.1.5 Init Remove
```bash
./lucidshark init --remove
```

**Verify:**
- [ ] All LucidShark artifacts removed
- [ ] `.mcp.json` is `{}` (empty object) or removed
- [ ] `.claude/CLAUDE.md` has lucidshark section removed
- [ ] `.claude/settings.json` has lucidshark hooks removed
- [ ] `.claude/skills/lucidshark/` removed

Re-run init for remaining tests:
```bash
./lucidshark init
```

### 3.2: End-to-End Autoconfiguration Testing

**CRITICAL:** This phase tests the complete autoconfiguration workflow from detection to validation to execution. Do NOT skip steps or use pre-written configs.

---

### 3.2.1 Autoconfigure Real-World Project: Flask

**Objective:** Test autoconfiguration on a well-established Python web framework.

#### Step 1: Call Autoconfigure MCP Tool
```bash
cd "$TEST_WORKSPACE/flask"
```
```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Mentions detecting Python from pyproject.toml or setup.py
- [ ] Mentions detecting pytest
- [ ] Mentions detecting ruff, mypy, or other linters
- [ ] Includes example configs for Python projects
- [ ] Includes common exclusion patterns (.venv, __pycache__, *.egg-info, etc.)

#### Step 2: Detect Project Tools

```bash
# Check package manager
ls -la pyproject.toml setup.py requirements*.txt 2>/dev/null
cat pyproject.toml | grep -A 5 '\[project\]' | head -10

# Check for test framework
ls -la pytest.ini conftest.py .pytest_cache setup.cfg 2>/dev/null
cat pyproject.toml | grep -A 3 '\[tool.pytest\]' 2>/dev/null

# Check for linters and type checkers
cat pyproject.toml | grep -E '\[tool\.(ruff|flake8|mypy|pyright)\]' 2>/dev/null
ls -la .flake8 mypy.ini pyrightconfig.json ruff.toml .ruff.toml 2>/dev/null

# Check for coverage
cat pyproject.toml | grep -A 3 '\[tool.coverage\]' 2>/dev/null
```

**Record findings:**
- [ ] Test framework detected: _____________ (should be pytest)
- [ ] Linter detected: _____________ (ruff, flake8, or none)
- [ ] Type checker detected: _____________ (mypy, pyright, or none)
- [ ] Coverage tool: _____________ (pytest-cov, coverage.py)

#### Step 3: Check Current Tool Installation

```bash
pip list | grep -iE '^(ruff|mypy|pyright|pytest|coverage|pytest-cov) '
```

**Record which tools are installed:** _____________

**Install missing tools:**
```bash
pip install ruff mypy pytest pytest-cov coverage
pip list | grep -iE '^(ruff|mypy|pytest|coverage) '
```

**Verify:** [ ] All required tools installed

#### Step 4: Generate lucidshark.yml Based on Detection

**IMPORTANT:** Based on ACTUAL detected tools, create config. Do NOT use generic template.

```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: flask
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
    threshold: 70

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
EOF
```

#### Step 5: Validate Configuration

```bash
./lucidshark validate
echo "Validation exit code: $?"
```

**Verify:**
- [ ] Exit code 0 (valid config)
- [ ] No validation errors

**If validation fails:**
- [ ] Record error: _____________
- [ ] Fix config
- [ ] Re-validate

#### Step 6: Test Generated Config with Scans

**Test linting:**
```bash
./lucidshark scan --linting --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Ruff executes successfully
- [ ] Output shows domain_status.linting
- [ ] Finds issues or passes (Flask is well-maintained)

**Test type checking:**
```bash
./lucidshark scan --type-checking --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Mypy executes successfully
- [ ] May find type errors (expected)

**Test testing:**
```bash
./lucidshark scan --testing --format ai 2>&1 | head -30
```

**Verify:**
- [ ] **CRITICAL: pytest runs**
- [ ] Tests execute

**Test exclusions work:**
```bash
./lucidshark scan --duplication --all-files --format ai 2>&1 | grep -c '__pycache__'
echo "__pycache__ files scanned (should be 0): $?"
```

**Verify:**
- [ ] __pycache__, .venv NOT scanned

---

### 3.2.2 Autoconfigure Real-World Project: httpx

**Objective:** Test on modern async HTTP client (uses pytest, ruff, mypy).

```bash
cd "$TEST_WORKSPACE/httpx"

# Detect tools
cat pyproject.toml | grep -E '\[project\]|\[tool\.pytest\]|\[tool\.ruff\]|\[tool\.mypy\]' | head -20
ls -la pytest.ini conftest.py 2>/dev/null
```

**Generate config based on detection:**
```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: httpx
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
EOF
```

**Validate and test:**
```bash
./lucidshark validate
./lucidshark scan --testing --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Config validates
- [ ] pytest runs successfully
- [ ] Modern Python tools detected correctly

---

### 3.2.3 Autoconfigure Real-World Project: fastapi

**Objective:** Test on FastAPI (modern async framework).

```bash
cd "$TEST_WORKSPACE/fastapi"

# Detect tools
cat pyproject.toml | head -50
find . -name pytest.ini -o -name conftest.py 2>/dev/null | head -5
```

**Generate appropriate config and test:**
```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: fastapi
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
    threshold: 90

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
  - "**/.mypy_cache/**"
  - "**/dist/**"
  - "**/build/**"
EOF
```

```bash
./lucidshark validate
./lucidshark scan --linting --type-checking --format ai 2>&1 | head -40
```

**Verify:**
- [ ] Config valid
- [ ] Scans work correctly

---

### 3.2.4 Summary Table: Autoconfiguration Results

| Project | Expected Test Framework | Detected Framework | Expected Linter | Detected Linter | Config Valid? | Scans Work? |
|---------|-------------------------|-------------------|-----------------|-----------------|---------------|-------------|
| Flask | pytest | | ruff | | | |
| httpx | pytest | | ruff | | | |
| fastapi | pytest | | ruff | | | |

**Autoconfiguration Test Verdict:**
- [ ] **PASS:** All projects correctly detected pytest
- [ ] **PASS:** All configs validated successfully
- [ ] **PASS:** Scans executed successfully
- [ ] **PASS:** Exclusions prevented scanning .venv, __pycache__
- [ ] **FAIL:** <describe failure> _____________

---

### 3.3 Test Autoconfigure MCP Tool Directly

```
mcp__lucidshark__autoconfigure()
```

**Verify returns:**
- [ ] Step-by-step analysis instructions
- [ ] Python detection guidance
- [ ] pytest detection guidance
- [ ] Tool installation steps
- [ ] Example lucidshark.yml for Python
- [ ] Common exclusions for Python

---

### 3.4 Validate Configuration via MCP

```bash
cd "$TEST_WORKSPACE/flask"
```

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Reports config as valid
- [ ] Shows parsed domains and tools

**Test invalid config:**
```bash
cp lucidshark.yml lucidshark.yml.backup
echo "invalid yaml syntax:" > lucidshark.yml
```

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Returns validation error
- [ ] Error message is clear

```bash
mv lucidshark.yml.backup lucidshark.yml
```

---

### 3.5 Test Invalid Configurations

```bash
cd "$TEST_WORKSPACE/flask"
```

**Test validation error handling:**

#### 1. Missing version field
```bash
cp lucidshark.yml lucidshark.yml.backup
sed '/^version:/d' lucidshark.yml > lucidshark.yml.tmp && mv lucidshark.yml.tmp lucidshark.yml
./lucidshark validate
echo "Exit code (should be non-zero): $?"
mv lucidshark.yml.backup lucidshark.yml
```

**Verify:** [ ] Validation fails with clear error

#### 2. Coverage without testing
```bash
cp lucidshark.yml lucidshark.yml.backup
cat > lucidshark.yml << 'EOF'
version: 1
pipeline:
  testing:
    enabled: false
  coverage:
    enabled: true
    tools: [coverage_py]
EOF
./lucidshark validate
echo "Exit code: $?"
mv lucidshark.yml.backup lucidshark.yml
```

**Verify:** [ ] Validation fails or warns

---

### 3.6 Test lucidshark init on Real Projects

```bash
cd "$TEST_WORKSPACE/flask"
./lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files would be created
- [ ] Does not conflict with existing pyproject.toml

```bash
./lucidshark init
```

**Verify:**
- [ ] Creates .mcp.json, .claude/CLAUDE.md, etc.
- [ ] Does not break project structure

---

## Phase 4: CLI Scan Testing

Use the test-project for all CLI tests unless otherwise noted.

```bash
cd "$TEST_WORKSPACE/test-project"
```

### 4.1 Linting (Ruff)

#### 4.1.1 CLI — Linting Only (No Config)
Remove or rename `lucidshark.yml` temporarily:
```bash
mv lucidshark.yml lucidshark.yml.bak
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] Ruff auto-detected for Python project
- [ ] Finds unused imports (F401) in `main.py` — `os`, `sys`, `json`, `subprocess`
- [ ] Finds unused variable (F841) in `main.py` — `unused_var`
- [ ] Finds security issues (S-prefixed rules) in `security.py`
- [ ] Each issue has: file_path, line, column, rule_id, message, severity
- [ ] Exit code is non-zero (issues found)

#### 4.1.2 CLI — Linting with Config
```bash
./lucidshark scan --linting --all-files --format json
```

**Verify:**
- [ ] Same issues detected as without config
- [ ] Exclude patterns applied (no `.venv/**` files scanned)

#### 4.1.3 CLI — Linting Auto-Fix
```bash
cp -r src src.backup
./lucidshark scan --linting --all-files --fix --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Unused imports removed from `main.py`
- [ ] Files actually modified on disk (diff `src/myapp/main.py` vs backup)
- [ ] Issues that can't be auto-fixed (F841 unused var) remain
- [ ] Re-scan shows fewer issues

Restore: `rm -rf src && mv src.backup src`

#### 4.1.4 CLI — Linting Specific File
```bash
./lucidshark scan --linting --files src/myapp/security.py --format json
```

**Verify:**
- [ ] Only scans `security.py`
- [ ] Does NOT report issues from `main.py`

#### 4.1.5 CLI — Linting on Flask (Clean Project)
```bash
cd "$TEST_WORKSPACE/flask"
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Zero or very few linting issues on well-maintained project
- [ ] Ruff auto-detected

#### 4.1.6 CLI — Linting on httpx
```bash
cd "$TEST_WORKSPACE/httpx"
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify and record issue count.**

### 4.2 Type Checking (mypy + Pyright)

#### 4.2.1 CLI — Type Checking Only (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
./lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] mypy and/or pyright auto-detected
- [ ] Finds type error: `x: str = 123` in `main.py`
- [ ] Finds type error: `return 42` in `-> str` function
- [ ] Finds type error: int assigned to Dict[str, str] value
- [ ] Each issue has severity mapped (expect HIGH)

#### 4.2.2 CLI — Type Checking with Config (mypy only)
Edit `lucidshark.yml` to set `tools: [mypy]` under type_checking, then:
```bash
./lucidshark scan --type-checking --all-files --format json
```

**Verify:**
- [ ] Only mypy runs (no pyright output)
- [ ] Type errors detected

Restore config to `tools: [mypy, pyright]`.

#### 4.2.3 CLI — Type Checking with Config (pyright only)
Edit config to `tools: [pyright]`, then:
```bash
./lucidshark scan --type-checking --all-files --format json
```

**Verify:**
- [ ] Only pyright runs (no mypy output)
- [ ] Type errors detected
- [ ] Line numbers are 1-based (pyright natively uses 0-based)

Restore config.

#### 4.2.4 CLI — Type Checking on httpx (Typed Project)
```bash
cd "$TEST_WORKSPACE/httpx"
./lucidshark scan --type-checking --all-files --format json 2>&1 | head -100
cd "$TEST_WORKSPACE/test-project"
```

**Record results.** httpx is well-typed, so expect few/zero errors.

### 4.3 Formatting (Ruff Format)

#### 4.3.1 CLI — `--formatting` Flag (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
./lucidshark scan --formatting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] Does the `--formatting` flag work without config? (Previously reported as BUG-001)
- [ ] If it fails, record the exact error message

#### 4.3.2 CLI — Formatting via `--all` with Config
```bash
./lucidshark scan --all --all-files --format json 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
fmt_issues = [i for i in data.get('issues', []) if i.get('domain') == 'formatting']
print(f'Formatting issues: {len(fmt_issues)}')
for i in fmt_issues:
    print(f'  {i.get(\"file_path\")}:{i.get(\"line\")} - {i.get(\"title\")}')"
```

**Verify:**
- [ ] Formatting issues detected in `main.py` (badly formatted function)
- [ ] Check for ghost issue (BUG-003): is there an issue with file_path containing "files would be reformatted"?

#### 4.3.3 CLI — Formatting Auto-Fix
```bash
cp -r src src.backup
./lucidshark scan --all --all-files --fix --format json 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
fmt_issues = [i for i in data.get('issues', []) if i.get('domain') == 'formatting']
print(f'Formatting issues after fix: {len(fmt_issues)}')"
```

**Verify:**
- [ ] `main.py` reformatted on disk
- [ ] Re-scan shows zero formatting issues

Restore: `rm -rf src && mv src.backup src`

### 4.4 Testing (pytest)

#### 4.4.1 CLI — Testing Domain
```bash
./lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] pytest auto-detected and executed
- [ ] Reports test results (pass/fail counts)
- [ ] `test_process_data` should FAIL (returns 42 instead of "HELLO")
- [ ] Other tests should pass
- [ ] Auto-wraps with `coverage run -m pytest` if coverage domain also enabled

#### 4.4.2 CLI — Testing + Coverage Together
```bash
# Clean slate — remove any pre-existing coverage data
rm -f .coverage
rm -rf htmlcov
./lucidshark scan --testing --coverage --all-files --format json
echo "Exit code: $?"
# Prove the testing step produced coverage data
ls -la .coverage
echo ".coverage file exists: $?"
python3 -c "import sqlite3, os; assert os.path.exists('.coverage'), 'No .coverage file'; db=sqlite3.connect('.coverage'); print('Coverage DB tables:', db.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())"
```

**Verify:**
- [ ] `.coverage` file exists on disk after scan (verified with `ls`)
- [ ] Coverage data is valid (SQLite database with coverage tables)
- [ ] Tests run (pass/fail counts reported)
- [ ] Coverage percentage calculated and non-zero
- [ ] Coverage threshold comparison works (below 80% → issue)
- [ ] Gap percentage reported

### 4.5 Coverage (coverage.py)

#### 4.5.1 CLI — Coverage Without Testing (Should Error)
```bash
# Clean slate — ensure no leftover coverage data from previous runs
rm -f .coverage
rm -rf htmlcov
./lucidshark scan --coverage --all-files --format json
echo "Exit code: $?"
ls .coverage 2>/dev/null
echo ".coverage exists after coverage-only scan: $?"
```

**Verify:**
- [ ] No `.coverage` file produced (testing didn't run)
- [ ] Reports error or "no coverage data" (coverage requires testing to run first)
- [ ] Exit code is non-zero
- [ ] Does not crash

#### 4.5.2 CLI — Coverage Threshold
Run with different thresholds:
```bash
# Low threshold (should pass)
./lucidshark scan --testing --coverage --all-files --coverage-threshold 10 --format json
echo "Exit code: $?"

# High threshold (should fail)
./lucidshark scan --testing --coverage --all-files --coverage-threshold 90 --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] With 10% threshold: no coverage issue
- [ ] With 90% threshold: coverage issue reported with gap percentage

### 4.6 Duplication (Duplo)

#### 4.6.1 CLI — Duplication Domain
```bash
./lucidshark scan --duplication --all-files --format json
```

**Verify:**
- [ ] Duplo detects duplicates between `duplicate1.py` and `duplicate2.py`
- [ ] Reports duplication percentage
- [ ] Reports file locations of duplicate blocks
- [ ] Respects `min_lines: 4` config

### 4.7 SAST (OpenGrep)

#### 4.7.1 CLI — SAST Domain
```bash
./lucidshark scan --sast --all-files --format json
```

**Verify and record which of these are detected:**
- [ ] SQL injection in `security.py` (string concatenation in SQL)
- [ ] Command injection via `subprocess.run(shell=True)` in `security.py`
- [ ] Command injection via `os.system()` in `security.py`
- [ ] Insecure deserialization via `pickle.loads()` in `security.py`
- [ ] Weak crypto via `hashlib.md5()` for password in `security.py`
- [ ] Hardcoded secrets (`API_KEY`, `DATABASE_PASSWORD`) in `security.py`
- [ ] Path traversal (string concat in file path) in `security.py`
- [ ] `eval()` usage in `security.py`
- [ ] Each SAST issue has CWE and/or OWASP references

### 4.8 SCA (Trivy)

**🚨 CRITICAL: This test was FAILED in a previous run because the tester gave up after one timeout error instead of debugging it. DO NOT REPEAT THIS MISTAKE.**

**What happened:** The tester ran the command, got a JSON parsing error (because they used an invalid timeout wrapper), and immediately wrote "⏳ Test incomplete due to timeout" in their report without investigating.

**What should have happened:** Remove the wrapper, run the command properly, wait for Trivy to download its database (first run only), and verify the results.

**This test takes 9-12 seconds. That is NOT a timeout. That is normal operation. Wait for it.**

#### 4.8.1 CLI — SCA Domain

**Before running:** Ensure you're not wrapping this in timeout commands or other shell wrappers that break JSON output.

```bash
./lucidshark scan --sca --all-files --format json
```

**Verify:**
- [ ] Trivy scans `requirements.txt` (check output mentions requirements.txt)
- [ ] Finds known CVEs in old package versions (flask 2.0.0, requests 2.25.0, pyyaml 5.3.1, etc.)
- [ ] COUNT the exact number of CVEs found (should be ~28)
- [ ] VERIFY the severity breakdown (how many critical/high/medium/low)
- [ ] CHECK at least 3 sample CVEs have complete metadata:
  - CVE ID (e.g., CVE-2025-50181)
  - Package name and versions (installed → fixed)
  - CVSS score
  - CWE IDs
  - Reference URLs
- [ ] RECORD the scan duration from metadata.duration_ms
- [ ] VERIFY scanners_used includes trivy with version number
- [ ] If Trivy DB download fails, document the EXACT error message and investigate why

**DO NOT write "seems to work" or "probably found CVEs". COUNT THEM. VERIFY THEM.**

#### 4.8.2 SCA on httpx
```bash
cd "$TEST_WORKSPACE/httpx"
./lucidshark scan --sca --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

### 4.9 Full Scan (`--all`)

#### 4.9.1 CLI — `--all` with Config
```bash
./lucidshark scan --all --all-files --format json > /tmp/full-scan-with-config.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/full-scan-with-config.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
print('Duration ms:', data.get('metadata', {}).get('duration_ms', 'N/A'))
for domain, count in data.get('metadata', {}).get('issues_by_domain', {}).items():
    print(f'  {domain}: {count}')
"
```

**Verify:**
- [ ] ALL domains executed: linting, type_checking, formatting, testing, coverage, duplication, sca, sast
- [ ] Issues found in each applicable domain
- [ ] Duration is non-zero (check BUG-004)
- [ ] `enabled_domains` populated (check BUG-005)
- [ ] `scanners_used` populated (check BUG-006)

#### 4.9.2 CLI — `--all` WITHOUT Config
```bash
mv lucidshark.yml lucidshark.yml.bak
./lucidshark scan --all --all-files --format json > /tmp/full-scan-no-config.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/full-scan-no-config.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] How many domains execute? (Previously BUG-002: only linting + type_checking)
- [ ] Compare with `--all` WITH config — are the same domains covered?
- [ ] If not all domains run, this is a regression/bug — document it

### 4.10 Output Formats

Run a scan and test each output format:

```bash
./lucidshark scan --linting --all-files --format json > /tmp/out-json.json
./lucidshark scan --linting --all-files --format summary > /tmp/out-summary.txt
./lucidshark scan --linting --all-files --format table > /tmp/out-table.txt
./lucidshark scan --linting --all-files --format ai > /tmp/out-ai.txt
./lucidshark scan --linting --all-files --format sarif > /tmp/out-sarif.json
```

**Verify each format:**
- [ ] **json**: Valid JSON, has `issues` array and `metadata` object
- [ ] **summary**: Human-readable text with severity counts and domain breakdown
- [ ] **table**: Tabular output with columns (check for truncation UX-006)
- [ ] **ai**: Rich structured output with priorities, fix steps, instructions
- [ ] **sarif**: Valid SARIF 2.1.0 schema with `runs`, `results`, `rules`

### 4.11 CLI Flags & Features

#### 4.11.1 `--dry-run`
```bash
./lucidshark scan --all --all-files --dry-run
```

**Verify:**
- [ ] Shows planned domains, tools, file targeting
- [ ] Does NOT actually execute scans

#### 4.11.2 `--fail-on`
```bash
./lucidshark scan --linting --all-files --fail-on medium
echo "Exit code for medium: $?"

./lucidshark scan --linting --all-files --fail-on critical
echo "Exit code for critical: $?"
```

**Verify:**
- [ ] `--fail-on medium`: exit code 1 (there are medium+ issues)
- [ ] `--fail-on critical`: exit code 0 (if no critical issues) or 1 (if there are)

#### 4.11.3 `--base-branch`
```bash
# Create a branch with changes
git checkout -b test-branch
echo "# new issue" >> src/myapp/main.py
git add -A && git commit -m "add change"

./lucidshark scan --linting --all-files --base-branch main --format json
echo "Exit code: $?"

git checkout main
git branch -D test-branch
```

**Verify:**
- [ ] Only reports issues from files changed since `main`

#### 4.11.4 `--debug` and `--verbose`
```bash
./lucidshark --debug scan --linting --all-files --format summary 2>&1 | head -50
./lucidshark --verbose scan --linting --all-files --format summary 2>&1 | head -50
```

**Verify:**
- [ ] `--debug` shows detailed debug logs (tool commands, paths, etc.)
- [ ] `--verbose` shows info-level logs
- [ ] Note: `--debug` must come BEFORE `scan` subcommand

#### 4.11.5 `--stream`
```bash
./lucidshark scan --linting --all-files --stream 2>&1 | head -30
```

**Verify:**
- [ ] Produces streaming output
- [ ] Check if output is raw JSON or parsed (UX-005)

#### 4.11.6 Incremental Scanning (Default)
```bash
# With no uncommitted changes
./lucidshark scan --linting --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Scans only uncommitted/changed files (not `--all-files`)
- [ ] If no changes, may report 0 issues

### 4.12 Other CLI Commands

#### 4.12.1 `lucidshark status`
```bash
./lucidshark status
```

**Verify:**
- [ ] Shows version, platform
- [ ] Shows available plugins/tools
- [ ] Shows scanner versions (ruff, mypy, pyright, etc.)
- [ ] Check: does it show configured domains from `lucidshark.yml`? (UX-009)

#### 4.12.2 `lucidshark doctor`
```bash
./lucidshark doctor
```

**Verify:**
- [ ] Checks config validity
- [ ] Checks tool availability
- [ ] Checks environment
- [ ] Reports any issues/warnings

#### 4.12.3 `lucidshark help`
```bash
./lucidshark help | head -100
```

**Verify:**
- [ ] Outputs comprehensive markdown reference
- [ ] Documents all subcommands and flags

#### 4.12.4 `lucidshark overview --update`
```bash
./lucidshark overview --update
cat QUALITY.md | head -50
```

**Verify:**
- [ ] Generates `QUALITY.md` file
- [ ] Contains health score, issue counts
- [ ] Contains domain breakdown

#### 4.12.5 `lucidshark serve --mcp`
```bash
timeout 5 lucidshark serve --mcp 2>&1 || true
```

**Verify:**
- [ ] MCP server starts without crash
- [ ] Outputs MCP protocol initialization

---

## Phase 5: MCP Tool Testing

**🚨 CRITICAL: This ENTIRE PHASE was SKIPPED in a previous test run with the excuse "context/time constraints". This is UNACCEPTABLE.**

**Why this matters:**
- MCP integration is THE PRIMARY WAY users interact with LucidShark through Claude Code
- If MCP tools don't work, the entire product is broken for AI-assisted development
- This is NOT optional. This is NOT "nice to have". This is CORE FUNCTIONALITY.

**What happened in the failed test:**
- Tester wrote "⏳ Not tested in this session due to context/time constraints"
- Tester marked MCP testing as "pending" instead of "completed"
- Tester wrote a test report claiming "8.5/10" despite not testing the PRIMARY FEATURE

**What should have happened:**
- Test ALL 7+ MCP tools listed below
- Compare MCP results with CLI results for parity
- Verify every MCP tool returns correct data structures
- Test apply_fix actually fixes files
- Test autoconfigure returns comprehensive guidance

**You have the MCP tools available RIGHT NOW. Use them. If you skip this phase, you have FAILED the entire test.**

---

All MCP tests use the test-project with `lucidshark.yml` in place.

```bash
cd "$TEST_WORKSPACE/test-project"
```

### 5.1 `mcp__lucidshark__scan()`

**IMPORTANT:** Run EVERY domain scan listed below. Verify results for EACH ONE.

#### 5.1.1 Scan — Individual Domains

Test each domain individually via MCP:

```
mcp__lucidshark__scan(domains=["linting"], all_files=true)
mcp__lucidshark__scan(domains=["type_checking"], all_files=true)
mcp__lucidshark__scan(domains=["formatting"], all_files=true)
mcp__lucidshark__scan(domains=["testing"], all_files=true)
mcp__lucidshark__scan(domains=["testing", "coverage"], all_files=true)
mcp__lucidshark__scan(domains=["duplication"], all_files=true)
mcp__lucidshark__scan(domains=["sca"], all_files=true)
mcp__lucidshark__scan(domains=["sast"], all_files=true)
```

For EACH call, verify:
- [ ] Correct domain executed
- [ ] Issues returned with proper structure (file_path, line, severity, message)
- [ ] No errors or crashes
- [ ] Results consistent with CLI results for same domain

**Additional verification for testing + coverage MCP call:**
```bash
# Verify coverage data was produced by the MCP scan
rm -f .coverage && rm -rf htmlcov
```
```
mcp__lucidshark__scan(domains=["testing", "coverage"], all_files=true)
```
```bash
ls -la .coverage
echo ".coverage file exists after MCP scan: $?"
```

**Verify:**
- [ ] `.coverage` file exists on disk after MCP scan
- [ ] Coverage percentage in MCP result matches CLI result
- [ ] Coverage data was produced by the scan itself, not leftover from a previous run

#### 5.1.2 Scan — All Domains
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] All 8 domains execute
- [ ] Compare total issue counts with CLI `--all` results

#### 5.1.3 Scan — Specific Files
```
mcp__lucidshark__scan(files=["src/myapp/security.py"], domains=["linting", "sast"])
```

**Verify:**
- [ ] Only `security.py` scanned
- [ ] Linting and SAST issues for that file only

#### 5.1.4 Scan — Auto-Fix
```
mcp__lucidshark__scan(domains=["linting"], all_files=true, fix=true)
```

**Verify:**
- [ ] Issues auto-fixed
- [ ] Fewer/zero linting issues in result
- [ ] Files modified on disk

Restore files after: `git checkout -- .`

#### 5.1.5 Scan — Formatting Fix via MCP
```
mcp__lucidshark__scan(domains=["formatting"], all_files=true, fix=true)
```

**Verify:**
- [ ] Formatting issues fixed
- [ ] `main.py` reformatted

Restore: `git checkout -- .`

### 5.2 `mcp__lucidshark__check_file()`

**This is one of the MOST USED MCP tools. Test it thoroughly.**

```
mcp__lucidshark__check_file(file_path="src/myapp/main.py")
```

**Verify EVERYTHING in the response:**
- [ ] Returns issues for `main.py` - COUNT them, don't just say "returns issues"
- [ ] Check which domains run (does it run ALL domains including SCA? Or just linting/type checking?)
- [ ] Returns domain_status - verify each domain shows pass/fail/skipped correctly
- [ ] Returns issues_by_domain - verify issue counts match actual issues returned
- [ ] Returns instructions - verify they're actionable (not generic)
- [ ] Returns severity_counts - verify they add up to total_issues
- [ ] Returns recommended_action - verify it's appropriate for the findings
- [ ] Response time reasonable for single-file check (should be < 10 seconds)

```
mcp__lucidshark__check_file(file_path="src/myapp/security.py")
```

**Verify:**
- [ ] Returns security-related issues
- [ ] SAST issues included

### 5.3 `mcp__lucidshark__get_fix_instructions()`

First, run a scan to get issue IDs:
```
mcp__lucidshark__scan(domains=["linting", "sast", "sca"], all_files=true)
```

Then for each type of issue, get fix instructions:

```
mcp__lucidshark__get_fix_instructions(issue_id="<linting-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sast-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sca-issue-id>")
```

**Verify for each:**
- [ ] Returns priority, fix_steps, suggested_fix
- [ ] Returns documentation_url where applicable
- [ ] Guidance is specific and actionable

**Test with nonexistent ID:**
```
mcp__lucidshark__get_fix_instructions(issue_id="nonexistent-id-12345")
```

**Verify:**
- [ ] Returns "Issue not found" error

### 5.4 `mcp__lucidshark__apply_fix()`

**CRITICAL TEST for BUG-008: Previous reports claim apply_fix "fixes ALL issues instead of one". Verify the actual behavior.**

**Before testing:** Get the current state of the file:
```bash
cat src/myapp/main.py > /tmp/before-fix.txt
```

```
mcp__lucidshark__apply_fix(issue_id="<linting-F401-issue-id>")
```

**After apply_fix, verify EXACTLY what changed:**
```bash
cat src/myapp/main.py > /tmp/after-fix.txt
diff -u /tmp/before-fix.txt /tmp/after-fix.txt
```

**Verify:**
- [ ] Fix applied to file on disk - SHOW THE DIFF
- [ ] COUNT: How many issues were fixed? Just the one with that ID? All F401s? All linting issues?
- [ ] DOCUMENT the actual behavior: "Fixed X issues of type Y"
- [ ] Return message indicates success - QUOTE IT EXACTLY
- [ ] If it fixed more than one issue, is that correct behavior? (e.g., fixing all F401s in a file makes sense)
- [ ] VERDICT on BUG-008: Is this a bug or is the previous report wrong?

**Test with non-linting issue:**
```
mcp__lucidshark__apply_fix(issue_id="<sast-issue-id>")
```

**Verify:**
- [ ] Correctly rejects with error message - QUOTE THE EXACT ERROR
- [ ] Error message is clear and actionable
- [ ] Does not crash or modify files

Restore: `git checkout -- .`

### 5.5 `mcp__lucidshark__get_status()`

```
mcp__lucidshark__get_status()
```

**Verify:**
- [ ] Returns tool inventory
- [ ] Returns scanner versions
- [ ] Check: does `enabled_domains` show all configured domains? (UX-007)

### 5.6 `mcp__lucidshark__get_help()`

```
mcp__lucidshark__get_help()
```

**Verify:**
- [ ] Returns comprehensive documentation
- [ ] Covers all domains, CLI flags, MCP tools
- [ ] Response size is reasonable (not truncated)

### 5.7 `mcp__lucidshark__autoconfigure()`

```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Detects Python language
- [ ] Detects pytest for testing
- [ ] Provides example configs
- [ ] Mentions tool installation

### 5.8 `mcp__lucidshark__validate_config()`

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Reports valid config as valid
- [ ] Check with intentionally broken configs (same as Phase 3.4)

### 5.9 MCP vs CLI Parity

For each domain, compare MCP and CLI results:

| Domain | CLI Issues | MCP Issues | Match? |
|--------|-----------|------------|--------|
| linting | | | |
| type_checking | | | |
| formatting | | | |
| testing | | | |
| coverage | | | |
| duplication | | | |
| sca | | | |
| sast | | | |

Document any discrepancies.

---

## Phase 6: Real-World Project Testing

### 6.1 Flask

```bash
cd "$TEST_WORKSPACE/flask"
```

#### 6.1.1 Create lucidshark.yml for Flask
Use autoconfigure or manually create a config appropriate for Flask.

#### 6.1.2 Full Scan
```bash
./lucidshark scan --all --all-files --format json > /tmp/flask-scan.json
```
Also via MCP:
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] Scan completes without errors
- [ ] Record issue counts per domain
- [ ] No false positives on well-maintained code (especially linting, type checking)
- [ ] SCA finds known CVEs if any in Flask's deps
- [ ] Record scan duration

### 6.2 httpx

```bash
cd "$TEST_WORKSPACE/httpx"
```

#### 6.2.1 Full Scan (CLI + MCP)
Same process as Flask.

**Verify:**
- [ ] Scan completes
- [ ] Type checking works well (httpx is well-typed)
- [ ] Record results

### 6.3 FastAPI

```bash
cd "$TEST_WORKSPACE/fastapi"
```

#### 6.3.1 Full Scan
Same process.

**Additional checks:**
- [ ] Handles Pydantic models correctly in type checking
- [ ] Handles async code correctly
- [ ] Large codebase doesn't cause timeout/OOM

### 6.4 Sanic

```bash
cd "$TEST_WORKSPACE/sanic"
```

#### 6.4.1 Full Scan
Same process.

**Additional checks:**
- [ ] Handles different project structure
- [ ] No crashes on edge cases

---

## Phase 7: Edge Case Testing

### 7.1 Empty Python File
```bash
touch "$TEST_WORKSPACE/test-project/src/myapp/empty.py"
./lucidshark scan --linting --files src/myapp/empty.py --format json
```

**Verify:**
- [ ] No crash on empty file
- [ ] Zero issues reported

### 7.2 Syntax Error File
```bash
cat > "$TEST_WORKSPACE/test-project/src/myapp/broken.py" << 'EOF'
def broken(
    # missing closing paren and colon
    pass
EOF
./lucidshark scan --linting --files src/myapp/broken.py --format json
./lucidshark scan --type-checking --files src/myapp/broken.py --format json
```

**Verify:**
- [ ] Handles syntax errors gracefully
- [ ] Reports syntax error as an issue
- [ ] Does not crash

### 7.3 Very Large File
```bash
python3 -c "
for i in range(10000):
    print(f'def func_{i}(x): return x + {i}')
" > "$TEST_WORKSPACE/test-project/src/myapp/large.py"
./lucidshark scan --linting --files src/myapp/large.py --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Handles large file without OOM or timeout
- [ ] Results returned in reasonable time

### 7.4 Non-ASCII / Unicode File
```bash
cat > "$TEST_WORKSPACE/test-project/src/myapp/unicode.py" << 'EOF'
# -*- coding: utf-8 -*-
"""Módulo con caracteres españoles y emojis 🎉"""

def grüße(name: str) -> str:
    """Grüße an den Benutzer."""
    return f"Hallo, {name}! 👋"

変数 = "日本語テスト"
EOF
./lucidshark scan --linting --files src/myapp/unicode.py --format json
```

**Verify:**
- [ ] Handles Unicode filenames and content
- [ ] No encoding errors

### 7.5 No Python Project (Wrong Language Detection)
```bash
mkdir -p "$TEST_WORKSPACE/not-python"
cd "$TEST_WORKSPACE/not-python"
git init
echo "console.log('hello')" > index.js
echo '{"name": "test"}' > package.json
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Does NOT try to run Python tools on JavaScript project
- [ ] Auto-detects JavaScript/TypeScript instead, or reports no applicable tools

### 7.6 Mixed Language Project
```bash
mkdir -p "$TEST_WORKSPACE/mixed-lang"
cd "$TEST_WORKSPACE/mixed-lang"
git init
mkdir src
echo "import os" > src/app.py
echo "console.log('hello')" > src/app.js
echo "package main" > src/main.go
./lucidshark scan --linting --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Handles multiple languages
- [ ] Runs appropriate linter for each

Clean up edge case files:
```bash
cd "$TEST_WORKSPACE/test-project"
rm -f src/myapp/empty.py src/myapp/broken.py src/myapp/large.py src/myapp/unicode.py
```

---

## Phase 8: Installation Method Comparison

Compare the binary (from install.sh in Phase 1.1) and pip installation (from setup script in Phase 2.3):

### 8.1 Feature Parity
Run a subset of scans with BOTH installation methods and compare:

```bash
cd "$TEST_WORKSPACE/test-project"

# Test with binary (CLI tests use this)
./lucidshark scan --linting --all-files --format json > /tmp/binary-results.json
echo "Binary exit code: $?"

# Test with pip (from venv created by setup script)
source .venv/bin/activate
lucidshark scan --linting --all-files --format json > /tmp/pip-results.json
echo "Pip exit code: $?"
deactivate
```

**Compare:**
- [ ] Same issues detected?
- [ ] Same output format?
- [ ] Same exit codes?
- [ ] Any behavioral differences?

**Note:** Both installations (binary and pip) are from the same local source (installed by setup script in Phase 2.3), so they MUST match.

### 8.2 Tool Availability
```bash
cd "$TEST_WORKSPACE/test-project"

# Binary
./lucidshark doctor

# Pip (from venv)
source .venv/bin/activate
lucidshark doctor
deactivate
```

**Compare which tools are bundled vs. required externally for each method.**

---

## Phase 9: Regression Checks for Known Bugs

Check whether these previously reported bugs are still present:

| Bug | Test | Status |
|-----|------|--------|
| BUG-001: `--formatting` CLI flag broken | Run `lucidshark scan --formatting --all-files` without config | |
| BUG-002: `--all` without config only runs 2 domains | Run `lucidshark scan --all --all-files` without config, check executed_domains | |
| BUG-003: ruff_format ghost issue | Run formatting scan, check for issue with "files would be reformatted" in file_path | |
| BUG-004: Duration always 0ms | Check `duration_ms` in any scan metadata | |
| BUG-005: `enabled_domains` empty without config | Check metadata when scanning without config | |
| BUG-006: `scanners_used` empty for non-security | Check metadata when running linting only | |
| BUG-007: MCP coverage "no data" after testing | Run `mcp__lucidshark__scan(domains=["testing", "coverage"])` | |
| BUG-008: `apply_fix` fixes ALL issues | Fix one F401, check if other F401s also fixed | |

---

## Test Report Template

Write the report with this structure:

```markdown
# LucidShark Python Support — E2E Test Report

**Date:** YYYY-MM-DD
**Tester:** Claude (model version)
**LucidShark Version:** (from `lucidshark --version`)
**Installation Method:** Universal setup script (installed both binary and pip from local source)
**Python Version:** (from `python3 --version`)
**Platform:** (from `uname -a`)
**Tool Versions:** Ruff X.Y.Z, mypy X.Y.Z, Pyright X.Y.Z, OpenGrep X.Y.Z, Trivy X.Y.Z, Duplo X.Y.Z

---

## Executive Summary
(2-3 paragraph overview: what works, what's broken, overall assessment)

## Installation Testing Results
### install.sh (Binary)
### Setup Script Installation (Binary + Pip Editable)
### Binary vs Pip Comparison

## Init & Configuration Results
### lucidshark init
### Autoconfigure
### Config Validation

## CLI Scan Results by Domain
### Linting (Ruff)
### Type Checking (mypy / Pyright)
### Formatting (Ruff Format)
### Testing (pytest)
### Coverage (coverage.py)
### Duplication (Duplo)
### SAST (OpenGrep)
### SCA (Trivy)

## MCP Tool Results
### scan()
### check_file()
### get_fix_instructions()
### apply_fix()
### get_status()
### get_help()
### autoconfigure()
### validate_config()

## MCP vs CLI Parity
(Table comparing issue counts and behavior differences)

## Real-World Project Results
### Flask
### httpx
### FastAPI
### Sanic

## Edge Case Results

## Output Format Results
(json, summary, table, ai, sarif)

## Regression Check Results
(Status of each previously reported bug)

## New Bugs Found
### BUG-XXX: Title
**Severity:** Critical/Moderate/Minor
**Reproducibility:** X%
**Description:** ...
**Expected:** ...
**Actual:** ...

## New UX Issues Found

## Recommendations (Priority Order)
### P0 — Must Fix
### P1 — Should Fix
### P2 — Nice to Have

## Conclusion
(Overall assessment with score out of 10)

## Cleanup

After completing the test, remove all test artifacts:

```bash
# If you still have the TEST_WORKSPACE variable:
rm -rf "$TEST_WORKSPACE"

# Or if the variable is lost:
rm -rf /tmp/lucidshark-python-e2e-*

# Verify cleanup:
ls /tmp/lucidshark-python-e2e-* 2>/dev/null || echo "✓ All test artifacts removed"
```

**What gets deleted:**
- All cloned projects (flask, httpx, fastapi, sanic)
- The artificial test-project
- All installation test directories
- Any generated coverage reports, test artifacts, and cache directories

**Safe to delete:** Everything was isolated in `/tmp` — no files in your actual workspace were touched.
```

---

## 🚨 CRITICAL: Read This Before You Start Testing 🚨

### Absolute Requirements - Zero Tolerance

1. ✅ **EXECUTE EVERY COMMAND** - "I think this will work" is not testing. RUN IT.
   - If you skip even one step, you have failed this test.
   - If you don't run a command because "it probably works", you are not doing your job.

2. ✅ **CAPTURE ACTUAL OUTPUT** - "It worked" is meaningless.
   - Include actual command output (at least first 50 lines for long output)
   - Record exact exit codes (not "non-zero" - the ACTUAL number)
   - Copy/paste actual error messages verbatim
   - Show before/after diffs for file modifications

3. ✅ **VERIFY EVERYTHING DEEPLY** - Don't trust surface-level results:
   - If output says "28 CVEs found", LIST some of them with details
   - If output says "9 issues", verify each issue is real and correct
   - If auto-fix claims success, DIFF the file to prove it
   - If metadata says duration=9033ms, did it actually take 9 seconds?

4. ✅ **COMPARE MCP vs CLI** - Same operation MUST produce same results:
   - Run same scan via CLI and MCP, compare issue counts
   - If CLI finds 9 issues and MCP finds 10, that's a BUG - investigate
   - Document any differences, even if they seem minor

5. ✅ **CHECK FOR REGRESSIONS** - Test ALL previously reported bugs:
   - BUG-001 through BUG-008 are listed in this document
   - For each bug, run the exact scenario that triggered it
   - Report: FIXED, STILL PRESENT, or PARTIALLY FIXED

6. ✅ **TEST WITH AND WITHOUT CONFIG** - lucidshark.yml changes behavior:
   - Some tests explicitly say "without config" - that means DELETE or rename lucidshark.yml
   - Some say "with config" - that means ensure lucidshark.yml exists
   - Document which tools run with/without config

7. ✅ **MEASURE ACTUAL PERFORMANCE** - "Fast" is not a measurement:
   - Record wall-clock time for scans (use `time` command or capture duration_ms from JSON)
   - Large project scans (Flask, FastAPI): how long did they take?
   - First-time vs subsequent scans: document the difference

8. ✅ **NO EXCUSES FOR SKIPPING TESTS**:
   - ❌ "Disk space limited" → Free up space or use a different machine
   - ❌ "Tool not installed" → Install it. That's what package managers are for.
   - ❌ "It seems slow" → Wait for it. Use proper timeouts.
   - ❌ "Context running low" → You should have planned better. Finish the tests.
   - ❌ "I'll test MCP later" → No. Test it NOW.

9. ✅ **CLEAN UP PROPERLY** - Tests must be reproducible:
   - Between tests that modify files: `git checkout -- .`
   - Between tests that need fresh state: `rm -f .coverage`
   - Document cleanup steps you performed

10. ✅ **INVESTIGATE FAILURES RUTHLESSLY** - Never accept "it didn't work":
    - Command failed? Read the error. Debug it. Find root cause.
    - Timeout? Increase timeout. See what happens.
    - Unexpected output? Compare with expected. Document difference.
    - JSON parsing failed? Look at raw output. Why isn't it JSON?

### If You Are Tempted to Skip Something...

**Ask yourself:**
- Would I accept this quality of testing from a junior engineer? (Answer: No)
- Would I ship code to production based on testing this shallow? (Answer: No)
- Am I doing this because it's hard or because it's the right thing to do? (Answer: It's hard)

**Then do it anyway.** You are a professional. Act like one.

### Red Flags That You're Failing

- 🚩 Using phrases like "seems to work", "probably correct", "looks good"
- 🚩 Skipping steps because "it's taking too long" or "context is low"
- 🚩 Writing "⏳ Not tested" in your report for critical functionality
- 🚩 Not actually running commands, just assuming they work
- 🚩 Accepting failures without investigation
- 🚩 Reporting bugs without reproduction steps
- 🚩 Comparing numbers without verifying they're correct (e.g., "found 28 CVEs" - did you verify ANY of them?)

### What Good Testing Looks Like

**Scenario: Testing SCA scan**

❌ BAD:
```
Ran SCA scan. It found some CVEs. Seems to work.
```

✅ GOOD:
```
Command: lucidshark scan --sca --all-files --format json
Exit code: 1 (non-zero due to high-severity findings)
Duration: 9.033 seconds (from metadata.duration_ms: 9033)
CVEs found: 28 total (1 critical, 9 high, 14 medium, 4 low)

Sample CVEs verified:
- CVE-2025-50181: urllib3 1.26.4 → 2.5.0 (Medium, CVSS 6.1)
  - File: requirements.txt
  - CWE: CWE-601 (Open Redirect)
  - References: 9 URLs including NVD and GitHub advisory

Metadata verification:
- scanners_used[0].name: "trivy"
- scanners_used[0].version: "0.69.3"
- scanners_used[0].success: true
- executed_domains: ["sca"] ✓
- all_files: true ✓

Verdict: ✅ SCA works correctly. Trivy detects all known CVEs with complete metadata.
```

**This is the standard you must meet for EVERY test.**

---

## 📋 Final Completion Checklist

**Before you submit your test report, verify you can answer YES to EVERY question below:**

### Test Execution
- [ ] Did you execute EVERY command in this document? (Not "most" - EVERY)
- [ ] Did you run all installation methods (install.sh, pip, source)?
- [ ] Did you test ALL CLI scan domains (linting, type checking, formatting, testing, coverage, duplication, SAST, SCA)?
- [ ] Did you test ALL MCP tools (scan, check_file, get_fix_instructions, apply_fix, get_status, autoconfigure, validate_config)?
- [ ] Did you test with AND without lucidshark.yml config?
- [ ] Did you verify all regression bugs (BUG-001 through BUG-008)?

### Data Quality
- [ ] Did you COUNT actual issues found (not just say "found issues")?
- [ ] Did you VERIFY sample issues with complete details?
- [ ] Did you RECORD actual durations, exit codes, and version numbers?
- [ ] Did you DIFF files before/after auto-fix to prove changes?
- [ ] Did you COMPARE MCP vs CLI results for parity?

### Thoroughness
- [ ] Did you investigate EVERY failure instead of moving on?
- [ ] Did you document EVERY discrepancy, no matter how small?
- [ ] Did you verify metadata fields (duration_ms, scanners_used, enabled_domains)?
- [ ] Did you test error cases (invalid inputs, missing tools)?
- [ ] Did you read actual error messages instead of assuming what went wrong?

### Report Quality
- [ ] Does your report contain ACTUAL DATA (numbers, counts, durations)?
- [ ] Does your report contain ACTUAL OUTPUT (quotes, diffs, error messages)?
- [ ] Does your report have CLEAR VERDICTS (PASS/FAIL, FIXED/BROKEN)?
- [ ] Does your report document NEW BUGS with reproduction steps?
- [ ] Does your report have a CLEAR RECOMMENDATION (production-ready or not)?

### Honesty Check
- [ ] Did you skip ANY steps? (If yes, document which ones and why)
- [ ] Did you encounter ANY failures you didn't investigate? (If yes, list them)
- [ ] Did you write "seems to work" or "probably correct" anywhere? (If yes, go back and verify)
- [ ] Did you make ANY assumptions instead of testing? (If yes, test them now)
- [ ] Would you trust your own report if you were deploying to production? (If no, redo the test)

---

## ✅ Test Completion Certificate

**Copy this to the END of your test report if and only if you can honestly answer YES to every question above:**

```
═══════════════════════════════════════════════════════════════════
                    TEST COMPLETION CERTIFICATE
═══════════════════════════════════════════════════════════════════

I certify that I have:
✅ Executed every command in the test plan without exception
✅ Verified every result with actual data, not assumptions
✅ Investigated every failure and discrepancy thoroughly
✅ Documented all findings with reproduction steps
✅ Compared MCP vs CLI results for parity
✅ Tested all regression bugs from previous reports
✅ Provided a clear production-readiness recommendation

Total tests executed: _____ / _____ (must be 100%)
Total bugs found: _____
Total bugs verified fixed: _____
Overall verdict: PASS / FAIL (production-ready or blocking issues)

Tester: [Your name/model]
Date: [YYYY-MM-DD]
Test duration: [Hours]

═══════════════════════════════════════════════════════════════════
```

**If you cannot honestly sign this certificate, your test is INCOMPLETE.**
