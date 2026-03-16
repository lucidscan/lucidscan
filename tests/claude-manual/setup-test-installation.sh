#!/usr/bin/env bash
#
# LucidShark E2E Test Installation Setup
#
# This script sets up LucidShark installations for E2E testing in a deterministic way.
# It installs BOTH the pip (venv) and binary versions from the current local source code.
#
# Usage:
#   ./setup-test-installation.sh <target-project-path>
#
# Example:
#   ./setup-test-installation.sh /tmp/lucidshark-e2e-test/my-project
#
# What it does:
#   1. Builds the PyInstaller binary (once, cached in /tmp)
#   2. Creates .venv in target project and installs lucidshark from local source
#   3. Copies the binary to target project root
#   4. Verifies all versions match the local development version
#
# This script is the SOURCE OF TRUTH for E2E test installations.
# All language-specific E2E tests (Python, Go, Java, JavaScript, etc.) should use this script.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# Check arguments
if [ $# -lt 1 ]; then
    error "Usage: $0 <target-project-path>"
fi

TARGET_PROJECT="$1"

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LUCIDSHARK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYPROJECT_TOML="$LUCIDSHARK_ROOT/pyproject.toml"
PYINSTALLER_SPEC="$LUCIDSHARK_ROOT/lucidshark.spec"
BINARY_CACHE_DIR="/tmp/lucidshark-e2e-binaries"

info "LucidShark E2E Test Installation Setup"
info "========================================"
info "LucidShark source: $LUCIDSHARK_ROOT"
info "Target project: $TARGET_PROJECT"
info ""

# Verify target project exists or create it
if [ ! -d "$TARGET_PROJECT" ]; then
    warn "Target project directory does not exist. Creating: $TARGET_PROJECT"
    mkdir -p "$TARGET_PROJECT"
fi

# Verify we're in a LucidShark source directory
if [ ! -f "$PYPROJECT_TOML" ]; then
    error "Cannot find pyproject.toml at $PYPROJECT_TOML. Are you in the LucidShark source directory?"
fi

if [ ! -f "$PYINSTALLER_SPEC" ]; then
    error "Cannot find lucidshark.spec at $PYINSTALLER_SPEC. Binary build will fail."
fi

# Extract local development version from pyproject.toml
LOCAL_VERSION=$(grep '^version = ' "$PYPROJECT_TOML" | cut -d'"' -f2)
if [ -z "$LOCAL_VERSION" ]; then
    error "Could not extract version from pyproject.toml"
fi

info "Local development version: $LOCAL_VERSION"
info ""

# ============================================================================
# STEP 1: Build PyInstaller Binary (with caching)
# ============================================================================

BINARY_CACHE_FILE="$BINARY_CACHE_DIR/lucidshark-$LOCAL_VERSION"
BINARY_VERSION_FILE="$BINARY_CACHE_DIR/VERSION"

info "Step 1: Building PyInstaller binary..."

# Check if we have a cached binary for this version
if [ -f "$BINARY_CACHE_FILE" ] && [ -f "$BINARY_VERSION_FILE" ]; then
    CACHED_VERSION=$(cat "$BINARY_VERSION_FILE")
    if [ "$CACHED_VERSION" = "$LOCAL_VERSION" ]; then
        success "Using cached binary for version $LOCAL_VERSION"
        BINARY_PATH="$BINARY_CACHE_FILE"
    else
        warn "Cached binary is for version $CACHED_VERSION, but local is $LOCAL_VERSION. Rebuilding..."
        BINARY_PATH=""
    fi
else
    info "No cached binary found. Building from source..."
    BINARY_PATH=""
fi

# Build binary if not cached
if [ -z "$BINARY_PATH" ]; then
    info "Installing PyInstaller (if not already installed)..."
    cd "$LUCIDSHARK_ROOT"
    pip install pyinstaller >/dev/null 2>&1 || true

    info "Building binary with: pyinstaller lucidshark.spec --clean"
    info "This may take 1-2 minutes..."

    # Build the binary
    if ! pyinstaller lucidshark.spec --clean >/dev/null 2>&1; then
        error "PyInstaller build failed. Check that all dependencies are installed."
    fi

    BUILT_BINARY="$LUCIDSHARK_ROOT/dist/lucidshark"
    if [ ! -f "$BUILT_BINARY" ]; then
        error "Binary not found at $BUILT_BINARY after build"
    fi

    # Cache the binary
    mkdir -p "$BINARY_CACHE_DIR"
    cp "$BUILT_BINARY" "$BINARY_CACHE_FILE"
    echo "$LOCAL_VERSION" > "$BINARY_VERSION_FILE"
    chmod +x "$BINARY_CACHE_FILE"

    success "Binary built and cached at $BINARY_CACHE_FILE"
    BINARY_PATH="$BINARY_CACHE_FILE"
fi

# Verify binary version
BINARY_VERSION=$("$BINARY_PATH" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ "$BINARY_VERSION" != "$LOCAL_VERSION" ]; then
    error "Binary version mismatch! Expected: $LOCAL_VERSION, Got: $BINARY_VERSION"
fi

success "Binary verified: version $BINARY_VERSION"
info ""

# ============================================================================
# STEP 2: Copy Binary to Target Project
# ============================================================================

info "Step 2: Copying binary to target project..."

TARGET_BINARY="$TARGET_PROJECT/lucidshark"
cp "$BINARY_PATH" "$TARGET_BINARY"
chmod +x "$TARGET_BINARY"

# Verify copied binary
COPIED_VERSION=$("$TARGET_BINARY" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ "$COPIED_VERSION" != "$LOCAL_VERSION" ]; then
    error "Copied binary version mismatch! Expected: $LOCAL_VERSION, Got: $COPIED_VERSION"
fi

success "Binary copied to $TARGET_BINARY (version $COPIED_VERSION)"
info ""

# ============================================================================
# STEP 3: Create venv and Install via Pip
# ============================================================================

info "Step 3: Creating Python venv and installing lucidshark..."

TARGET_VENV="$TARGET_PROJECT/.venv"

# Create venv
if [ -d "$TARGET_VENV" ]; then
    warn "Removing existing venv at $TARGET_VENV"
    rm -rf "$TARGET_VENV"
fi

info "Creating venv at $TARGET_VENV"
python3 -m venv "$TARGET_VENV"

# Activate venv and install
source "$TARGET_VENV/bin/activate"

info "Installing lucidshark from local source (editable mode)..."
pip install --quiet --upgrade pip
pip install --quiet -e "$LUCIDSHARK_ROOT"

# Verify pip installation
if ! command -v lucidshark >/dev/null 2>&1; then
    error "lucidshark command not found after pip install"
fi

PIP_VERSION=$(lucidshark --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ "$PIP_VERSION" != "$LOCAL_VERSION" ]; then
    error "Pip version mismatch! Expected: $LOCAL_VERSION, Got: $PIP_VERSION"
fi

# Verify editable install location
PIP_LOCATION=$(pip show lucidshark | grep "Location:" | cut -d' ' -f2)
if [[ "$PIP_LOCATION" != *"$LUCIDSHARK_ROOT"* ]]; then
    error "Pip installation is not pointing to local source! Location: $PIP_LOCATION"
fi

success "Pip installation verified: version $PIP_VERSION (editable install from $LUCIDSHARK_ROOT)"

# Deactivate venv
deactivate

info ""

# ============================================================================
# STEP 4: Final Verification
# ============================================================================

info "Step 4: Final verification..."
info ""
info "Verification Summary:"
info "  Local source version:     $LOCAL_VERSION"
info "  Binary version:           $BINARY_VERSION"
info "  Pip version:              $PIP_VERSION"
info ""

if [ "$LOCAL_VERSION" = "$BINARY_VERSION" ] && [ "$LOCAL_VERSION" = "$PIP_VERSION" ]; then
    success "✅ All versions match! Installation successful."
else
    error "❌ Version mismatch detected! Installation failed."
fi

info ""
info "Installation complete. Project setup:"
info "  Binary:  $TARGET_BINARY"
info "  Venv:    $TARGET_VENV"
info ""
info "To use the pip installation:"
info "  cd $TARGET_PROJECT"
info "  source .venv/bin/activate"
info "  lucidshark --version"
info ""
info "To use the binary installation:"
info "  cd $TARGET_PROJECT"
info "  ./lucidshark --version"
info ""
success "Ready for E2E testing! 🚀"
