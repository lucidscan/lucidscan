# LucidShark E2E Manual Testing

This directory contains comprehensive end-to-end (E2E) test instructions for LucidShark, designed to be executed by Claude Code as a QA agent.

## Test Documents

- **TEST_GO_E2E.md** - Go language support testing
- **TEST_PYTHON_E2E.md** - Python language support testing
- **TEST_JAVA_E2E.md** - Java language support testing
- **TEST_JAVASCRIPT_E2E.md** - JavaScript/TypeScript language support testing

## Universal Setup Script

### `setup-test-installation.sh`

**This script is the SOURCE OF TRUTH for E2E test installations.**

All language-specific E2E tests MUST use this script to install LucidShark. It ensures deterministic, reproducible installations across all tests.

### Usage

```bash
./setup-test-installation.sh <target-project-path>
```

### What It Does

1. **Builds PyInstaller Binary** (once, cached in `/tmp/lucidshark-e2e-binaries/`)
   - Uses `pyinstaller lucidshark.spec --clean` (same as release process)
   - Caches binary by version for faster subsequent runs
   - Verifies binary version matches local development version

2. **Copies Binary to Project**
   - Places binary at `<project>/lucidshark`
   - Makes it executable
   - Verifies copied binary version

3. **Creates Python Venv in Project**
   - Creates `<project>/.venv`
   - Installs lucidshark from local source in editable mode: `pip install -e .`
   - Verifies pip installation version and location

4. **Version Verification**
   - Compares local source version vs binary version vs pip version
   - **FAILS IMMEDIATELY** if any version mismatch detected
   - Ensures you're testing the LOCAL development version, not published versions

### Example

```bash
# Create test project
export TEST_WORKSPACE="/tmp/lucidshark-go-e2e-$(date +%s)"
mkdir -p "$TEST_WORKSPACE/test-project"
cd "$TEST_WORKSPACE/test-project"
git init

# Run setup script
/Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual/setup-test-installation.sh \
  "$TEST_WORKSPACE/test-project"

# Result:
# - Binary at: test-project/lucidshark
# - Venv at: test-project/.venv
# - Both use local development version

# Use pip installation for testing
source .venv/bin/activate
lucidshark --version

# Or use binary installation
./lucidshark --version
```

### Why This Script Exists

**Problem:** Previous E2E tests were installing LucidShark from PyPI (e.g., version 0.6.4) instead of the local development version (e.g., 0.6.5), causing testers to "go in circles" testing old bugs that had already been fixed.

**Solution:** This script enforces LOCAL VERSION ONLY testing with automatic verification.

### Key Features

- ✅ **Deterministic:** Same installation every time
- ✅ **Fast:** Caches binary builds
- ✅ **Safe:** Version verification prevents wrong-version testing
- ✅ **Universal:** Used by ALL language E2E tests
- ✅ **Production-aligned:** Uses same build process as releases

### Troubleshooting

**"Binary version mismatch" error:**
- The cached binary is for a different version
- Script will automatically rebuild
- If persists, check `pyproject.toml` version

**"Pip installation not pointing to local source" error:**
- The pip install location is wrong
- Check that the lucidshark source path is correct
- Try manually: `pip install -e /path/to/lucidshark/source`

**Script fails with "pyinstaller: command not found":**
- Run: `pip install pyinstaller`
- Script will attempt to install automatically

## Testing Workflow

1. **Read the test document** (e.g., `TEST_GO_E2E.md`)
2. **Follow Phase 0:** Set up test workspace
3. **Follow Phase 1:** Install language-specific tools
4. **Follow Phase 2:** Create test project
5. **Run setup script** (Phase 2.3): `./setup-test-installation.sh <project-path>`
6. **Execute tests:** Follow remaining phases using the venv
7. **Write report:** Document findings in detail

## Important Notes

- **ALWAYS use the setup script** - do not manually install lucidshark
- **Verify versions** - if you see version 0.6.4 but local is 0.6.5, something is wrong
- **Keep venv activated** - use pip installation for most tests (editable install reflects code changes immediately)
- **Test binary separately** - compare binary vs pip results in Phase 8
- **Report discrepancies** - any differences between binary and pip are bugs

## Contributing

When adding new language E2E tests:

1. Create `TEST_<LANGUAGE>_E2E.md`
2. **MUST reference `setup-test-installation.sh` in Phase 2.3**
3. Follow the same structure as existing tests
4. Include explicit version verification steps
5. Document binary vs pip comparison in Phase 8

## Questions?

If you encounter issues with the setup script or test documents, check:

1. Is `pyproject.toml` version correct?
2. Is the lucidshark source path correct?
3. Did you run the script from the correct directory?
4. Are all Python dependencies installed?

For bugs in the setup script itself, report with:
- Exact command run
- Error message
- Python version
- OS and architecture
