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
TMP_FILE=""

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
                echo "  --local, -l      Install locally to current directory"
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
        echo "  [2] This project (current directory)"
        echo "      - Project-specific installation"
        echo "      - Binary placed in project root"
        echo ""

        local choice
        read -rp "Choice [1/2]: " choice < /dev/tty
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
        install_dir="."
    fi

    # Create install directory
    mkdir -p "$install_dir"

    # Construct download URL
    local binary_name="${BINARY_NAME}-${platform}"
    local download_url="https://github.com/${REPO}/releases/download/${version}/${binary_name}"
    local install_path="${install_dir}/${BINARY_NAME}"

    info "Downloading ${binary_name}..."

    # Create temp file for download
    TMP_FILE="$(mktemp)"
    trap 'rm -f "$TMP_FILE"' EXIT

    if ! download "$download_url" "$TMP_FILE"; then
        error "Failed to download binary from: $download_url"
    fi

    # Install binary
    info "Installing to ${install_path}..."
    mv "$TMP_FILE" "$install_path"
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

    # Detect shell and rc file
    local shell_name rc_file
    shell_name="$(basename "${SHELL:-/bin/bash}")"

    case "$shell_name" in
        zsh)  rc_file="${HOME}/.zshrc" ;;
        fish) rc_file="${HOME}/.config/fish/config.fish" ;;
        *)    rc_file="${HOME}/.bashrc" ;;
    esac

    # Check if lucidshark function/alias already configured
    if [[ -f "$rc_file" ]] && grep -qF "# LucidShark" "$rc_file" 2>/dev/null; then
        info "Shell already configured in ${rc_file}"
    else
        # Add shell function that prefers local binary over global
        echo "" >> "$rc_file"
        echo "# LucidShark - prefers local binary over global (like venv)" >> "$rc_file"
        if [[ "$shell_name" == "fish" ]]; then
            echo 'function lucidshark' >> "$rc_file"
            echo '    if test -x "./lucidshark"' >> "$rc_file"
            echo '        ./lucidshark $argv' >> "$rc_file"
            echo '    else if test -x "$HOME/.local/bin/lucidshark"' >> "$rc_file"
            echo '        $HOME/.local/bin/lucidshark $argv' >> "$rc_file"
            echo '    else' >> "$rc_file"
            echo '        echo "lucidshark not found. Install with: curl -fsSL https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.sh | bash"' >> "$rc_file"
            echo '        return 1' >> "$rc_file"
            echo '    end' >> "$rc_file"
            echo 'end' >> "$rc_file"
        else
            echo 'lucidshark() {' >> "$rc_file"
            echo '    if [[ -x "./lucidshark" ]]; then' >> "$rc_file"
            echo '        ./lucidshark "$@"' >> "$rc_file"
            echo '    elif [[ -x "$HOME/.local/bin/lucidshark" ]]; then' >> "$rc_file"
            echo '        "$HOME/.local/bin/lucidshark" "$@"' >> "$rc_file"
            echo '    else' >> "$rc_file"
            echo '        echo "lucidshark not found. Install with: curl -fsSL https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.sh | bash"' >> "$rc_file"
            echo '        return 1' >> "$rc_file"
            echo '    fi' >> "$rc_file"
            echo '}' >> "$rc_file"
        fi
        success "Added lucidshark to ${rc_file}"
    fi

    echo ""
    echo "=========================================="
    warn "⚠️  ACTION REQUIRED"
    echo "=========================================="
    echo ""
    echo "To use 'lucidshark' command, you must either:"
    echo ""
    echo "  1. Restart your terminal"
    echo ""
    echo "  OR"
    echo ""
    echo "  2. Run this command now:"
    success "     source ${rc_file}"
    echo ""
    echo "=========================================="
    echo ""
    if [[ "$install_mode" == "local" ]]; then
        info "Local install: 'lucidshark' will use ./lucidshark in this directory"
        info "Different projects can have different versions (like Python venv)"
    fi
    echo ""
    echo "Then run: lucidshark --help"
    echo ""
}

main "$@"
