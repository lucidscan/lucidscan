# Binary Integration Tests

These tests verify that the PyInstaller binary correctly bundles all necessary resources and functions properly as a standalone executable.

## Purpose

The binary tests catch issues that only appear in the compiled binary, such as:

- **Missing bundled resources**: Files like `help.md` that need to be included in the binary
- **Symlink issues**: PyInstaller doesn't follow symlinks properly, so files referenced via symlinks won't work in the binary
- **Import issues**: Missing hidden imports or incorrect module paths
- **Platform-specific issues**: Differences between the binary and pip-installed version

## Running the Tests

### Test Execution Behavior

**Without Binary (Normal Development):**
```bash
$ pytest tests/integration/binary/ -v
# Result: 8 skipped in 0.02s ⚡
# Tests auto-skip when binary doesn't exist - no impact on regular test runs!
```

**With Binary (After Building):**
```bash
$ pyinstaller lucidshark.spec
$ pytest tests/integration/binary/ -v
# Result: 7 passed, 1 skipped in ~40s
```

### Running the Tests

#### Option 1: Run by Directory (Recommended)
```bash
# Run all binary tests
pytest tests/integration/binary/ -v

# Run specific test class
pytest tests/integration/binary/test_binary_help.py::TestBinaryHelpCommand -v

# Run specific test
pytest tests/integration/binary/test_binary_help.py::TestBinaryHelpCommand::test_binary_help_contains_documentation -v
```

#### Option 2: Run by Marker
```bash
# Run all tests marked with @pytest.mark.binary
pytest -m binary -v

# Skip binary tests explicitly
pytest -m "not binary" -v
```

#### Option 3: Build and Test in One Command
```bash
# For quick verification during development
pyinstaller lucidshark.spec --noconfirm && pytest tests/integration/binary/ -v
```

### Test Skipping

If the binary doesn't exist, tests are automatically skipped:

```
SKIPPED [8] tests/integration/binary/test_binary_help.py:47:
  Binary not found at /path/to/dist/lucidshark.
  Run 'pyinstaller lucidshark.spec' first.
```

**This means:**
- ✅ Normal test runs (`pytest`) are not affected (tests skip instantly)
- ✅ No need to build binary for regular development
- ✅ When you do build binary, tests verify it works correctly

## Test Coverage

### `test_binary_help.py`

Tests for help documentation accessibility in the binary:

- **TestBinaryHelpCommand**: Verifies the `lucidshark help` command works correctly
  - `test_binary_help_command_exists`: Binary can execute help command
  - `test_binary_help_contains_documentation`: Help output contains full documentation (not fallback message)
  - `test_binary_help_documents_cli_commands`: All CLI commands are documented
  - `test_binary_help_documents_mcp_tools`: All MCP tools are documented

- **TestBinaryMCPGetHelp**: Verifies the MCP `get_help` tool works correctly
  - Currently skipped due to complexity of MCP protocol testing
  - Help command test verifies the same code path

- **TestBinaryHelpValidation**: Quality checks for help documentation
  - `test_binary_help_has_minimum_length`: Output is substantial (>50KB)
  - `test_binary_help_has_all_major_sections`: All required sections present
  - `test_binary_help_contains_tool_availability_table`: Tool reference is complete

## What These Tests Caught

### Issue: Symlink Not Bundled in Binary

**Problem**: The PyInstaller spec file referenced `src/lucidshark/data/help.md`, which is a symlink to `docs/help.md`. PyInstaller doesn't follow symlinks correctly, so the binary ended up without the help documentation.

**Symptom**: When users ran `lucidshark help` or called the MCP `get_help` tool, they got the fallback message: "Help documentation not found. Visit https://github.com/toniantunovi/lucidshark"

**Fix**: Changed `lucidshark.spec` line 21 from:
```python
('src/lucidshark/data/help.md', 'lucidshark/data'),  # ❌ Symlink - doesn't work
```
to:
```python
('docs/help.md', 'lucidshark/data'),  # ✅ Actual file - works
```

**Test that caught it**: `test_binary_help_contains_documentation` checks that the output doesn't contain "Help documentation not found" and verifies key sections are present.

## CI/CD Integration

### Recommended: Run on Release Builds

Add binary tests to your release workflow to verify binaries before publishing:

**GitHub Actions Example:**
```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-test-binary:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pyinstaller pytest

      - name: Build binary
        run: pyinstaller lucidshark.spec

      - name: Test binary
        run: pytest tests/integration/binary/ -v --tb=short

      - name: Upload binary artifact
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: lucidshark-${{ matrix.os }}
          path: dist/lucidshark*
```

### Alternative: Separate Test Job

For faster feedback, run unit tests first, then build and test binary:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: pytest -m "not binary" -v

  test-binary:
    needs: test  # Only run if unit tests pass
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and test binary
        run: |
          pyinstaller lucidshark.spec
          pytest -m binary -v
```

### Skip Binary Tests in Regular CI

If you want to skip binary tests in regular CI runs:

```yaml
# Regular CI - skip binary tests
- name: Run tests
  run: pytest -m "not binary" -v

# Or exclude the directory entirely
- name: Run tests
  run: pytest --ignore=tests/integration/binary -v
```

This ensures every release has a working binary with all resources correctly bundled.

## Adding New Binary Tests

When adding new bundled resources or functionality to the binary:

1. Add the resource to `lucidshark.spec` in the `datas` list
2. Add a test in `tests/integration/binary/` to verify it's accessible
3. Run `pyinstaller lucidshark.spec` and verify the test passes
4. Commit both the spec change and the test

This ensures future releases don't break the bundled resources.
