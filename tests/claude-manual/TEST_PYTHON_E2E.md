# LucidShark Python Support — End-to-End Test Instructions

**Purpose:** You are performing a comprehensive end-to-end test of LucidShark's Python support. You will test both the CLI and MCP interfaces across all domains, using real open-source Python projects checked out from GitHub. You will test installation via both the install script and pip, run `lucidshark init`, `autoconfigure`, and exercise every scan domain and MCP tool. At the end, write a detailed test report.

**IMPORTANT:** Execute every step below. Do not skip steps or summarize without actually running the commands. Capture actual output, exit codes, and timings. If a step fails, document the failure in detail and continue with the next step.

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
```

All subsequent work happens inside `$TEST_WORKSPACE`. Do NOT use any pre-existing LucidShark installation.

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

### 1.3 Install via pip

```bash
cd "$TEST_WORKSPACE"
python3 -m venv pip-install-test
source pip-install-test/bin/activate
pip install lucidshark
```

**Verify:**
- [ ] `pip install lucidshark` succeeds without errors
- [ ] `lucidshark --version` outputs a version string
- [ ] `lucidshark --help` shows all subcommands
- [ ] `lucidshark status` works
- [ ] `lucidshark doctor` works
- [ ] Compare: does the pip version match the install.sh latest version? Document any differences.

### 1.4 Install via pip with Specific Version

```bash
pip install lucidshark==0.5.63
lucidshark --version
```

**Verify:**
- [ ] Correct version installed
- [ ] Downgrade/upgrade worked cleanly

### 1.5 Install from Source (Development)

```bash
cd "$TEST_WORKSPACE"
git clone https://github.com/toniantunovi/lucidshark.git lucidshark-source
cd lucidshark-source
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
lucidshark --version
```

**Verify:**
- [ ] Editable install succeeds
- [ ] `lucidshark` command is available
- [ ] Version matches source

**Decide which installation to use for remaining tests.** Prefer the pip install (1.3) for consistency. Keep the venv activated.

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

---

## Phase 3: Init & Configuration Testing

### 3.1 Test `lucidshark init` on Test Project

```bash
cd "$TEST_WORKSPACE/test-project"
```

#### 3.1.1 Init Dry Run
```bash
lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files WOULD be created without creating them
- [ ] Lists: `.mcp.json`, `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/skills/lucidshark/SKILL.md`
- [ ] No files actually created (check with `ls -la .mcp.json .claude/ 2>/dev/null`)

#### 3.1.2 Init (Full)
```bash
lucidshark init
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
lucidshark init
```

**Verify:**
- [ ] Detects existing configuration
- [ ] Suggests `--force` to overwrite
- [ ] Does NOT overwrite existing files

#### 3.1.4 Init Force
```bash
lucidshark init --force
```

**Verify:**
- [ ] Overwrites all files successfully
- [ ] Files are identical or updated versions

#### 3.1.5 Init Remove
```bash
lucidshark init --remove
```

**Verify:**
- [ ] All LucidShark artifacts removed
- [ ] `.mcp.json` is `{}` (empty object) or removed
- [ ] `.claude/CLAUDE.md` has lucidshark section removed
- [ ] `.claude/settings.json` has lucidshark hooks removed
- [ ] `.claude/skills/lucidshark/` removed

Re-run init for remaining tests:
```bash
lucidshark init
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
lucidshark validate
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
lucidshark scan --linting --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Ruff executes successfully
- [ ] Output shows domain_status.linting
- [ ] Finds issues or passes (Flask is well-maintained)

**Test type checking:**
```bash
lucidshark scan --type-checking --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Mypy executes successfully
- [ ] May find type errors (expected)

**Test testing:**
```bash
lucidshark scan --testing --format ai 2>&1 | head -30
```

**Verify:**
- [ ] **CRITICAL: pytest runs**
- [ ] Tests execute

**Test exclusions work:**
```bash
lucidshark scan --duplication --all-files --format ai 2>&1 | grep -c '__pycache__'
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
lucidshark validate
lucidshark scan --testing --format ai 2>&1 | head -30
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
lucidshark validate
lucidshark scan --linting --type-checking --format ai 2>&1 | head -40
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
lucidshark validate
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
lucidshark validate
echo "Exit code: $?"
mv lucidshark.yml.backup lucidshark.yml
```

**Verify:** [ ] Validation fails or warns

---

### 3.6 Test lucidshark init on Real Projects

```bash
cd "$TEST_WORKSPACE/flask"
lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files would be created
- [ ] Does not conflict with existing pyproject.toml

```bash
lucidshark init
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
lucidshark scan --linting --all-files --format json
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
lucidshark scan --linting --all-files --format json
```

**Verify:**
- [ ] Same issues detected as without config
- [ ] Exclude patterns applied (no `.venv/**` files scanned)

#### 4.1.3 CLI — Linting Auto-Fix
```bash
cp -r src src.backup
lucidshark scan --linting --all-files --fix --format json
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
lucidshark scan --linting --files src/myapp/security.py --format json
```

**Verify:**
- [ ] Only scans `security.py`
- [ ] Does NOT report issues from `main.py`

#### 4.1.5 CLI — Linting on Flask (Clean Project)
```bash
cd "$TEST_WORKSPACE/flask"
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Zero or very few linting issues on well-maintained project
- [ ] Ruff auto-detected

#### 4.1.6 CLI — Linting on httpx
```bash
cd "$TEST_WORKSPACE/httpx"
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify and record issue count.**

### 4.2 Type Checking (mypy + Pyright)

#### 4.2.1 CLI — Type Checking Only (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --type-checking --all-files --format json
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
lucidshark scan --type-checking --all-files --format json
```

**Verify:**
- [ ] Only mypy runs (no pyright output)
- [ ] Type errors detected

Restore config to `tools: [mypy, pyright]`.

#### 4.2.3 CLI — Type Checking with Config (pyright only)
Edit config to `tools: [pyright]`, then:
```bash
lucidshark scan --type-checking --all-files --format json
```

**Verify:**
- [ ] Only pyright runs (no mypy output)
- [ ] Type errors detected
- [ ] Line numbers are 1-based (pyright natively uses 0-based)

Restore config.

#### 4.2.4 CLI — Type Checking on httpx (Typed Project)
```bash
cd "$TEST_WORKSPACE/httpx"
lucidshark scan --type-checking --all-files --format json 2>&1 | head -100
cd "$TEST_WORKSPACE/test-project"
```

**Record results.** httpx is well-typed, so expect few/zero errors.

### 4.3 Formatting (Ruff Format)

#### 4.3.1 CLI — `--formatting` Flag (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --formatting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] Does the `--formatting` flag work without config? (Previously reported as BUG-001)
- [ ] If it fails, record the exact error message

#### 4.3.2 CLI — Formatting via `--all` with Config
```bash
lucidshark scan --all --all-files --format json 2>&1 | python3 -c "
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
lucidshark scan --all --all-files --fix --format json 2>&1 | python3 -c "
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
lucidshark scan --testing --all-files --format json
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
lucidshark scan --testing --coverage --all-files --format json
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
lucidshark scan --coverage --all-files --format json
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
lucidshark scan --testing --coverage --all-files --coverage-threshold 10 --format json
echo "Exit code: $?"

# High threshold (should fail)
lucidshark scan --testing --coverage --all-files --coverage-threshold 90 --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] With 10% threshold: no coverage issue
- [ ] With 90% threshold: coverage issue reported with gap percentage

### 4.6 Duplication (Duplo)

#### 4.6.1 CLI — Duplication Domain
```bash
lucidshark scan --duplication --all-files --format json
```

**Verify:**
- [ ] Duplo detects duplicates between `duplicate1.py` and `duplicate2.py`
- [ ] Reports duplication percentage
- [ ] Reports file locations of duplicate blocks
- [ ] Respects `min_lines: 4` config

### 4.7 SAST (OpenGrep)

#### 4.7.1 CLI — SAST Domain
```bash
lucidshark scan --sast --all-files --format json
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

#### 4.8.1 CLI — SCA Domain
```bash
lucidshark scan --sca --all-files --format json
```

**Verify:**
- [ ] Trivy scans `requirements.txt`
- [ ] Finds known CVEs in old package versions (flask 2.0.0, requests 2.25.0, pyyaml 5.3.1, etc.)
- [ ] Each CVE has: CVE ID, severity, affected package, fixed version
- [ ] If Trivy DB download fails, document the error handling behavior

#### 4.8.2 SCA on httpx
```bash
cd "$TEST_WORKSPACE/httpx"
lucidshark scan --sca --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

### 4.9 Full Scan (`--all`)

#### 4.9.1 CLI — `--all` with Config
```bash
lucidshark scan --all --all-files --format json > /tmp/full-scan-with-config.json
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
lucidshark scan --all --all-files --format json > /tmp/full-scan-no-config.json
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
lucidshark scan --linting --all-files --format json > /tmp/out-json.json
lucidshark scan --linting --all-files --format summary > /tmp/out-summary.txt
lucidshark scan --linting --all-files --format table > /tmp/out-table.txt
lucidshark scan --linting --all-files --format ai > /tmp/out-ai.txt
lucidshark scan --linting --all-files --format sarif > /tmp/out-sarif.json
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
lucidshark scan --all --all-files --dry-run
```

**Verify:**
- [ ] Shows planned domains, tools, file targeting
- [ ] Does NOT actually execute scans

#### 4.11.2 `--fail-on`
```bash
lucidshark scan --linting --all-files --fail-on medium
echo "Exit code for medium: $?"

lucidshark scan --linting --all-files --fail-on critical
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

lucidshark scan --linting --all-files --base-branch main --format json
echo "Exit code: $?"

git checkout main
git branch -D test-branch
```

**Verify:**
- [ ] Only reports issues from files changed since `main`

#### 4.11.4 `--debug` and `--verbose`
```bash
lucidshark --debug scan --linting --all-files --format summary 2>&1 | head -50
lucidshark --verbose scan --linting --all-files --format summary 2>&1 | head -50
```

**Verify:**
- [ ] `--debug` shows detailed debug logs (tool commands, paths, etc.)
- [ ] `--verbose` shows info-level logs
- [ ] Note: `--debug` must come BEFORE `scan` subcommand

#### 4.11.5 `--stream`
```bash
lucidshark scan --linting --all-files --stream 2>&1 | head -30
```

**Verify:**
- [ ] Produces streaming output
- [ ] Check if output is raw JSON or parsed (UX-005)

#### 4.11.6 Incremental Scanning (Default)
```bash
# With no uncommitted changes
lucidshark scan --linting --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Scans only uncommitted/changed files (not `--all-files`)
- [ ] If no changes, may report 0 issues

### 4.12 Other CLI Commands

#### 4.12.1 `lucidshark status`
```bash
lucidshark status
```

**Verify:**
- [ ] Shows version, platform
- [ ] Shows available plugins/tools
- [ ] Shows scanner versions (ruff, mypy, pyright, etc.)
- [ ] Check: does it show configured domains from `lucidshark.yml`? (UX-009)

#### 4.12.2 `lucidshark doctor`
```bash
lucidshark doctor
```

**Verify:**
- [ ] Checks config validity
- [ ] Checks tool availability
- [ ] Checks environment
- [ ] Reports any issues/warnings

#### 4.12.3 `lucidshark help`
```bash
lucidshark help | head -100
```

**Verify:**
- [ ] Outputs comprehensive markdown reference
- [ ] Documents all subcommands and flags

#### 4.12.4 `lucidshark overview --update`
```bash
lucidshark overview --update
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

All MCP tests use the test-project with `lucidshark.yml` in place.

```bash
cd "$TEST_WORKSPACE/test-project"
```

### 5.1 `mcp__lucidshark__scan()`

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

```
mcp__lucidshark__check_file(file_path="src/myapp/main.py")
```

**Verify:**
- [ ] Returns issues for `main.py`
- [ ] Check which domains run (UX-002: does it run ALL domains including SCA?)
- [ ] Returns domain_status, issues_by_domain, instructions
- [ ] Response time reasonable for single-file check

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

```
mcp__lucidshark__apply_fix(issue_id="<linting-F401-issue-id>")
```

**Verify:**
- [ ] Fix applied to file on disk
- [ ] Check: does it fix ONLY the targeted issue or ALL auto-fixable issues in the file? (BUG-008)
- [ ] Return message indicates success

**Test with non-linting issue:**
```
mcp__lucidshark__apply_fix(issue_id="<sast-issue-id>")
```

**Verify:**
- [ ] Correctly rejects with "Only linting issues support auto-fix" or similar

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
lucidshark scan --all --all-files --format json > /tmp/flask-scan.json
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
lucidshark scan --linting --files src/myapp/empty.py --format json
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
lucidshark scan --linting --files src/myapp/broken.py --format json
lucidshark scan --type-checking --files src/myapp/broken.py --format json
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
lucidshark scan --linting --files src/myapp/large.py --format json
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
lucidshark scan --linting --files src/myapp/unicode.py --format json
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
lucidshark scan --linting --all-files --format json
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
lucidshark scan --linting --all-files --format json
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

If you completed both install.sh (1.1) and pip (1.3) installations, compare them:

### 8.1 Feature Parity
Run a subset of scans with BOTH installation methods and compare:

```bash
# With install.sh binary:
cd "$TEST_WORKSPACE/install-script-test"
cp -r "$TEST_WORKSPACE/test-project/src" .
cp "$TEST_WORKSPACE/test-project/lucidshark.yml" .
./lucidshark scan --linting --all-files --format json > /tmp/install-sh-results.json

# With pip:
source "$TEST_WORKSPACE/pip-install-test/bin/activate"
cd "$TEST_WORKSPACE/test-project"
lucidshark scan --linting --all-files --format json > /tmp/pip-results.json
```

**Compare:**
- [ ] Same issues detected?
- [ ] Same output format?
- [ ] Same exit codes?
- [ ] Any behavioral differences?

### 8.2 Tool Availability
```bash
# install.sh binary
cd "$TEST_WORKSPACE/install-script-test"
./lucidshark doctor

# pip install
cd "$TEST_WORKSPACE/test-project"
lucidshark doctor
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
**Installation Methods Tested:** install.sh, pip
**Python Version:** (from `python3 --version`)
**Platform:** (from `uname -a`)
**Tool Versions:** Ruff X.Y.Z, mypy X.Y.Z, Pyright X.Y.Z, OpenGrep X.Y.Z, Trivy X.Y.Z, Duplo X.Y.Z

---

## Executive Summary
(2-3 paragraph overview: what works, what's broken, overall assessment)

## Installation Testing Results
### install.sh
### pip
### Source Install
### Comparison

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
```

---

## Important Notes for the Tester

1. **Execute every command.** Do not skip steps even if you think you know the outcome.
2. **Capture actual output.** Include relevant snippets in the report, not just pass/fail.
3. **Record exit codes** for every `lucidshark scan` command.
4. **Measure wall-clock time** for scans on large projects (Flask, FastAPI).
5. **Compare MCP vs CLI** results for the same operation — discrepancies are bugs.
6. **Check for regressions** against all previously reported bugs (BUG-001 through BUG-008).
7. **Test BOTH with and without `lucidshark.yml`** to verify config-less experience.
8. **Clean up** between tests that modify files (`git checkout -- .`).
9. **If disk space is limited**, skip Trivy/SCA tests and note it.
10. **If a tool is not installed** (e.g., opengrep, duplo), document it — don't skip the test.
