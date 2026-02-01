#!/usr/bin/env bash
#
# LucidShark Installer for Linux and macOS
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.sh | bash
#
# Or with options:
#   curl -fsSL https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.sh | bash -s -- --global
#   curl -fsSL https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.sh | bash -s -- --local
#   curl -fsSL https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.sh | bash -s -- --version v0.5.17

set -euo pipefail

# Configuration
REPO="lucidshark-code/lucidshark"
BINARY_NAME="lucidshark"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
info() { echo -e "${BLUE}$1${NC}"; }
success() { echo -e "${GREEN}$1${NC}"; }
warn() { echo -e "${YELLOW}$1${NC}"; }
error() { echo -e "${RED}Error: $1${NC}" >&2; exit 1; }

# Detect operating system
detect_os() {
    local os
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    case "$os" in
        darwin) echo "darwin" ;;
        linux) echo "linux" ;;
        *) error "Unsupported operating system: $os. Use Windows PowerShell installer for Windows." ;;
    esac
}

# Detect architecture
detect_arch() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64) echo "amd64" ;;
        arm64|aarch64) echo "arm64" ;;
        *) error "Unsupported architecture: $arch" ;;
    esac
}

# Get latest release version from GitHub
get_latest_version() {
    local url="https://api.github.com/repos/${REPO}/releases/latest"
    if command -v curl &> /dev/null; then
        curl -fsSL "$url" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/'
    elif command -v wget &> /dev/null; then
        wget -qO- "$url" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/'
    else
        error "Neither curl nor wget found. Please install one of them."
    fi
}

# Download file
download() {
    local url="$1"
    local output="$2"

    if command -v curl &> /dev/null; then
        curl -fsSL "$url" -o "$output"
    elif command -v wget &> /dev/null; then
        wget -q "$url" -O "$output"
    else
        error "Neither curl nor wget found. Please install one of them."
    fi
}

# Main installation function
main() {
    local install_mode=""
    local version=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --global|-g)
                install_mode="global"
                shift
                ;;
            --local|-l)
                install_mode="local"
                shift
                ;;
            --version|-v)
                version="$2"
                shift 2
                ;;
            --help|-h)
                echo "LucidShark Installer"
                echo ""
                echo "Usage: install.sh [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --global, -g     Install globally to ~/.local/bin"
                echo "  --local, -l      Install locally to .lucidshark/bin"
                echo "  --version, -v    Install specific version (e.g., v0.5.17)"
                echo "  --help, -h       Show this help message"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done

    echo ""
    echo "=========================================="
    info "       LucidShark Installer"
    echo "=========================================="
    echo ""

    # Detect platform
    local os arch platform
    os="$(detect_os)"
    arch="$(detect_arch)"
    platform="${os}-${arch}"

    info "Detected platform: ${platform}"
    echo ""

    # Get version
    if [[ -z "$version" ]]; then
        info "Fetching latest version..."
        version="$(get_latest_version)"
        if [[ -z "$version" ]]; then
            error "Could not determine latest version. Please specify with --version"
        fi
    fi
    info "Version: ${version}"
    echo ""

    # Determine install location
    local install_dir
    if [[ -z "$install_mode" ]]; then
        echo "Where would you like to install LucidShark?"
        echo ""
        echo "  [1] Global (~/.local/bin)"
        echo "      - Available system-wide"
        echo "      - May require adding to PATH"
        echo ""
        echo "  [2] This project (.lucidshark/bin)"
        echo "      - Project-specific installation"
        echo "      - Auto-detected by LucidShark"
        echo ""

        local choice
        read -rp "Choice [1/2]: " choice
        echo ""

        case "$choice" in
            1) install_mode="global" ;;
            2) install_mode="local" ;;
            *) error "Invalid choice: $choice" ;;
        esac
    fi

    if [[ "$install_mode" == "global" ]]; then
        install_dir="${HOME}/.local/bin"
    else
        install_dir=".lucidshark/bin"
    fi

    # Create install directory
    mkdir -p "$install_dir"

    # Construct download URL
    local binary_name="${BINARY_NAME}-${platform}"
    local download_url="https://github.com/${REPO}/releases/download/${version}/${binary_name}"
    local install_path="${install_dir}/${BINARY_NAME}"

    info "Downloading ${binary_name}..."

    # Create temp file for download
    local tmp_file
    tmp_file="$(mktemp)"
    trap 'rm -f "$tmp_file"' EXIT

    if ! download "$download_url" "$tmp_file"; then
        error "Failed to download binary from: $download_url"
    fi

    # Install binary
    info "Installing to ${install_path}..."
    mv "$tmp_file" "$install_path"
    chmod +x "$install_path"

    echo ""
    success "Installation complete!"
    echo ""

    # Verify installation
    if "$install_path" --version &> /dev/null; then
        local installed_version
        installed_version="$("$install_path" --version 2>/dev/null || echo "unknown")"
        success "Verified: ${installed_version}"
    else
        warn "Binary installed but could not verify version"
    fi

    echo ""

    # Post-install instructions
    if [[ "$install_mode" == "global" ]]; then
        if [[ ":$PATH:" != *":${install_dir}:"* ]]; then
            echo "To use lucidshark globally, add to your PATH:"
            echo ""
            echo "  # Add to ~/.bashrc or ~/.zshrc:"
            echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            echo ""
            echo "Then run:"
            echo "  source ~/.bashrc  # or ~/.zshrc"
            echo ""
        fi
        echo "Run: lucidshark --help"
    else
        echo "Run: .lucidshark/bin/lucidshark --help"
        echo ""
        echo "Or set LUCIDSHARK_HOME for global access:"
        echo "  export LUCIDSHARK_HOME=\"$(pwd)/.lucidshark\""
    fi
    echo ""
}

main "$@"
